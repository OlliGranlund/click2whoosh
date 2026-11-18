import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zwift_unlock import UnlockClient, ChallengeQueue, AuthError, TOKEN_URL, UNLOCK_URL, protect
import sys


class UnlockTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_refresh_clears_session_but_transient_failure_keeps_it(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/"session.bin"
            client = UnlockClient(path, codec=lambda data,**kw:data)
            client.tokens = dict(access_token="a",refresh_token="r",expires_at=0)
            client._save()
            def unavailable(*args):
                raise RuntimeError("Could not reach Zwift")
            client.transport = unavailable
            with self.assertRaises(RuntimeError):
                await client.solve(b"challenge")
            self.assertTrue(client.ready)
            self.assertTrue(path.exists())
            def rejected(*args):
                raise AuthError("Rejected")
            client.transport = rejected
            with self.assertRaises(AuthError):
                await client.solve(b"challenge")
            self.assertFalse(client.ready)
            self.assertFalse(path.exists())

    async def test_challenge_queue_skips_obsolete_replies_and_cancels(self):
        started, proceed = asyncio.Event(), asyncio.Event()
        calls, writes = [], []
        async def solve(challenge):
            calls.append(challenge)
            if challenge == b"first":
                started.set()
                await proceed.wait()
            return challenge + b"-reply"
        async def write(reply):
            writes.append(reply)
        queue = ChallengeQueue(solve,write,self.fail)
        queue.submit(b"first")
        await started.wait()
        for payload in (b"second",b"third",b"latest"):
            queue.submit(payload)
        proceed.set()
        await queue.task
        self.assertEqual(calls,[b"first",b"latest"])
        self.assertEqual(writes,[b"latest-reply"])
        started.clear(); proceed.clear()
        queue.submit(b"first")
        await started.wait()
        await queue.close()
        self.assertEqual(writes,[b"latest-reply"])

    async def test_login_refresh_challenge_and_forget_without_password_storage(self):
        calls = []
        def transport(url, body, headers):
            calls.append((url, body, headers))
            if url == TOKEN_URL:
                return json.dumps(dict(access_token="access", refresh_token="refresh", expires_in=120)).encode()
            return b"signed-reply"
        codec = lambda data, **kw: data[::-1]
        with TemporaryDirectory() as temp:
            path = Path(temp) / "session.bin"
            client = UnlockClient(path, transport, codec, lambda: 100)
            await client.login("email", "password")
            self.assertNotIn(b"password", path.read_bytes())
            self.assertEqual(await client.solve(b"challenge"), b"\xff\x04\x00signed-reply")
            self.assertEqual(calls[-1], (UNLOCK_URL, b"challenge", {"Authorization":"Bearer access",
                "Content-Type":"application/x-protobuf-lite", "Accept":"application/x-protobuf-lite"}))
            restored = UnlockClient(path, transport, codec, lambda: 1000)
            await restored.solve(b"new")
            self.assertIn(b"grant_type=refresh_token", calls[-2][1])
            restored.forget()
            self.assertFalse(path.exists())
            self.assertFalse(restored.ready)

    async def test_signout_discards_inflight_login(self):
        import threading
        started, proceed = threading.Event(), threading.Event()
        def transport(*args):
            started.set()
            proceed.wait(2)
            return b'{"access_token":"a","refresh_token":"r","expires_in":100}'
        with TemporaryDirectory() as temp:
            path = Path(temp) / "session.bin"
            client = UnlockClient(path, transport, lambda data, **kw:data)
            task = asyncio.create_task(client.login("e", "p"))
            await asyncio.to_thread(started.wait, 1)
            client.forget()
            proceed.set()
            await task
            self.assertFalse(path.exists())
            self.assertFalse(client.ready)

    async def test_empty_reply_and_malformed_tokens_are_rejected(self):
        with TemporaryDirectory() as temp:
            client = UnlockClient(Path(temp)/"session", lambda *args:b'{}', lambda data,**kw:data)
            with self.assertRaisesRegex(RuntimeError, "invalid session"):
                await client.login("e", "p")
            client.tokens = dict(access_token="a",refresh_token="r",expires_at=10**15)
            client.transport = lambda *args:b''
            with self.assertRaisesRegex(RuntimeError, "empty unlock"):
                await client.solve(b"challenge")

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI")
    async def test_native_token_encryption_roundtrip(self):
        secret = b'access-and-refresh-token'
        encrypted = protect(secret)
        self.assertNotIn(secret, encrypted)
        self.assertEqual(protect(encrypted, decrypt=True), secret)
