"""Optional Zwift challenge exchange, informed by MIT-licensed ZwiftBoard.

Passwords are used for one HTTPS request only. On Windows, saved session tokens
are encrypted for the current user with DPAPI. No account request is made until
the user signs in, or a connected pod needs a previously authorized session.
"""
import asyncio
import ctypes
from ctypes import wintypes
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://secure.zwift.com/auth/realms/zwift/protocol/openid-connect/token"
UNLOCK_URL = "https://us-or-rly101.zwift.com/api/d-lock-service/device/authenticate"


class AuthError(RuntimeError):
    pass


def protect(data, decrypt=False):
    if sys.platform != "win32":
        raise RuntimeError("Saved Zwift sign-in is currently Windows-only")
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Windows could not protect the Zwift session")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
            result = response.read(65537)
            if len(result) > 65536:
                raise RuntimeError("Zwift response exceeded size limit")
            return result
    except urllib.error.HTTPError as exc:
        if url == TOKEN_URL:
            try:
                error = json.loads(exc.read(65536)).get("error")
            except (ValueError, AttributeError):
                error = None
            if error in ("invalid_grant", "invalid_client", "unauthorized_client"):
                raise AuthError("Zwift rejected the sign-in or saved session; sign in again") from None
        # Neither response bodies nor request headers/forms go into errors.
        raise RuntimeError(f"Zwift request failed (HTTP {exc.code})") from None
    except (OSError, urllib.error.URLError):
        raise RuntimeError("Could not reach Zwift; check your connection") from None


class UnlockClient:
    def __init__(self, path, transport=request, codec=protect, clock=time.time):
        self.path, self.transport, self.codec, self.clock = path, transport, codec, clock
        self.tokens = {}
        self.lock = asyncio.Lock()
        self.generation = 0
        try:
            self.tokens = json.loads(codec(path.read_bytes(), decrypt=True))
            if not isinstance(self.tokens, dict):
                self.tokens = {}
        except (OSError, ValueError, RuntimeError):
            pass

    @property
    def ready(self):
        return bool(self.tokens.get("refresh_token"))

    async def _grant(self, form):
        form = dict(form, client_id="Zwift Game Client")
        raw = await asyncio.to_thread(self.transport, TOKEN_URL, urllib.parse.urlencode(form).encode(),
                                     {"Content-Type": "application/x-www-form-urlencoded"})
        try:
            result = json.loads(raw)
            access = result["access_token"]
            refresh = result.get("refresh_token") or self.tokens.get("refresh_token")
            expiry = min(max(float(result.get("expires_in", 0)), 0), 86400)
            if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise RuntimeError("Zwift returned an invalid session") from None
        return dict(access_token=access, refresh_token=refresh, expires_at=self.clock() + expiry)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_bytes(self.codec(json.dumps(self.tokens).encode()))
        temp.replace(self.path)

    async def login(self, email, password):
        generation = self.generation
        async with self.lock:
            tokens = await self._grant(dict(grant_type="password", username=email, password=password))
            if generation != self.generation:
                return
            self.tokens = tokens
            try:
                self._save()
            except (OSError, RuntimeError):
                raise RuntimeError("Signed in for this session, but Windows could not save the encrypted token") from None

    def forget(self):
        self.generation += 1
        self.tokens = {}
        self.path.unlink(missing_ok=True)

    async def solve(self, challenge):
        generation = self.generation
        async with self.lock:
            if not self.ready:
                raise RuntimeError("Sign in to Zwift to unlock the left Click")
            for attempt in range(2):
                if attempt or self.clock() + 60 >= self.tokens.get("expires_at", 0):
                    try:
                        tokens = await self._grant(dict(grant_type="refresh_token", refresh_token=self.tokens["refresh_token"]))
                    except AuthError:
                        self.tokens = {}
                        self.generation += 1
                        try:
                            self.path.unlink(missing_ok=True)
                        except OSError:
                            pass
                        raise
                    if generation != self.generation:
                        raise RuntimeError("Zwift session was removed")
                    self.tokens = tokens
                    self._save()
                try:
                    reply = await asyncio.to_thread(self.transport, UNLOCK_URL, challenge,
                        {"Authorization": "Bearer " + self.tokens["access_token"],
                         "Content-Type": "application/x-protobuf-lite", "Accept": "application/x-protobuf-lite"})
                    if generation != self.generation:
                        raise RuntimeError("Zwift session was removed")
                    if not reply:
                        raise RuntimeError("Zwift returned an empty unlock reply")
                    return b"\xff\x04\x00" + reply
                except RuntimeError as exc:
                    if attempt or str(exc) != "Zwift request failed (HTTP 401)":
                        raise


class ChallengeQueue:
    """One in-flight solve plus the newest pending challenge, never a backlog."""
    def __init__(self, solve, write, error):
        self.solve, self.write, self.error = solve, write, error
        self.pending = None
        self.task = None

    def submit(self, challenge):
        self.pending = challenge
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run())

    async def _run(self):
        while self.pending is not None:
            challenge, self.pending = self.pending, None
            try:
                reply = await self.solve(challenge)
                if self.pending is None or self.pending == challenge:
                    self.pending = None
                    await self.write(reply)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.error(str(exc))

    async def close(self):
        self.pending = None
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
