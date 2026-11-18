import asyncio
import unittest
from unittest.mock import patch
from openbikecontrol import OpenBikeControlServer, DEFAULT_MAPPING, pop_message, SERVICE_TYPE


def app_info(name=b"mywhoosh", supported=b""):
    return bytes((4, 1, len(name))) + name + b"\x01" + b"1" + bytes((len(supported),)) + supported


class ParserTests(unittest.TestCase):
    def test_fragmented_and_coalesced_app_messages(self):
        first, second = app_info(supported=b"\x01\x02"), b"\x03\x01\x00\xff"
        buffer = bytearray()
        for byte in first[:-1]:
            buffer.append(byte)
            self.assertIsNone(pop_message(buffer))
        buffer.extend(first[-1:] + second + app_info())
        self.assertEqual(pop_message(buffer), first)
        self.assertEqual(pop_message(buffer), second)
        self.assertEqual(pop_message(buffer), app_info())
        self.assertIsNone(pop_message(buffer))

    def test_invalid_version_length_and_type_are_rejected(self):
        for data in (b"\x04\x02\x00", b"\x04\x01\x21", b"\x04\x01\x00\x21", b"\x99"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                pop_message(bytearray(data))


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events, self.logs = [], []
        self.server = OpenBikeControlServer(lambda *event: self.events.append(event), self.logs.append)
        await self.server.start(host="127.0.0.1", advertise=False)
        self.addAsyncCleanup(self.server.stop)

    async def peer(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.port)
        self.addCleanup(writer.close)
        self.assertEqual(await asyncio.wait_for(reader.readexactly(3), 1), b"\x02\xff\x01")
        return reader, writer

    async def wait_for(self, predicate):
        async with asyncio.timeout(1):
            while not predicate():
                await asyncio.sleep(.001)

    async def test_every_rapid_shift_is_sent_and_keyboard_is_not_involved(self):
        reader, _ = await self.peer()
        for _ in range(4):
            self.server.buttons("right", {"plus"}, {"plus"}, DEFAULT_MAPPING)
            self.server.buttons("right", set(), set(), DEFAULT_MAPPING)
        expected = b"\x01\x01\x01\x01\x01\x00" * 4
        self.assertEqual(await asyncio.wait_for(reader.readexactly(len(expected)), 1), expected)

    async def test_two_physical_shift_down_buttons_each_produce_a_tap(self):
        reader, _ = await self.peer()
        self.server.buttons("left", {"minus"}, {"minus"}, DEFAULT_MAPPING)
        self.server.buttons("right", {"b"}, {"b"}, DEFAULT_MAPPING)
        expected = b"\x01\x02\x01\x01\x02\x00" * 2
        self.assertEqual(await asyncio.wait_for(reader.readexactly(12), 1), expected)

    async def test_held_action_releases_only_after_its_last_physical_source(self):
        reader, _ = await self.peer()
        mapping = {**DEFAULT_MAPPING, "b": "steer_left"}
        self.server.buttons("left", {"left"}, {"left"}, mapping)
        self.server.buttons("right", {"b"}, {"b"}, mapping)
        self.server.release_device("left")
        self.assertEqual(self.server.active, {0x18})
        self.server.release_device("right")
        self.assertEqual(await asyncio.wait_for(reader.readexactly(6), 1), b"\x01\x18\x01\x01\x18\x00")

    async def test_disable_releases_steering_and_stop_closes_the_listener(self):
        reader, _ = await self.peer()
        self.server.buttons("left", {"left"}, {"left"}, DEFAULT_MAPPING)
        self.server.clear_buttons()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(6), 1), b"\x01\x18\x01\x01\x18\x00")
        await self.server.stop()
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertIsNone(self.server.server)
        self.assertFalse(self.server.connected)
        self.assertEqual(self.events[-1][1]["status"], "Off")

    async def test_lost_connection_drops_input_without_replay_on_new_connection(self):
        _, writer = await self.peer()
        writer.close()
        await writer.wait_closed()
        await self.wait_for(lambda: not self.server.connected)
        self.server.buttons("right", {"plus"}, {"plus"}, DEFAULT_MAPPING)
        reader, _ = await self.peer()
        self.server.buttons("right", set(), set(), DEFAULT_MAPPING)
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(.02):
                await reader.read(3)
        self.server.buttons("right", {"plus"}, {"plus"}, DEFAULT_MAPPING)
        self.assertEqual(await asyncio.wait_for(reader.readexactly(6), 1), b"\x01\x01\x01\x01\x01\x00")

    async def test_capability_message_is_incremental_and_unsupported_actions_are_not_sent(self):
        reader, writer = await self.peer()
        info = app_info(supported=b"\x02")
        for byte in info:
            writer.write(bytes((byte,)))
            await writer.drain()
        await self.wait_for(lambda: self.server.app_id == "mywhoosh")
        self.server.buttons("right", {"plus", "b"}, {"plus", "b"}, DEFAULT_MAPPING)
        self.assertEqual(await asyncio.wait_for(reader.readexactly(6), 1), b"\x01\x02\x01\x01\x02\x00")
        self.assertEqual(self.server.supported, {2})

    async def test_second_peer_cannot_receive_controls_or_replace_first(self):
        reader, _ = await self.peer()
        other_reader, other_writer = await asyncio.open_connection("127.0.0.1", self.server.port)
        self.addCleanup(other_writer.close)
        self.assertEqual(await asyncio.wait_for(other_reader.read(), 1), b"")
        self.server.buttons("right", {"plus"}, {"plus"}, DEFAULT_MAPPING)
        self.assertEqual(await asyncio.wait_for(reader.readexactly(6), 1), b"\x01\x01\x01\x01\x01\x00")

    async def test_invalid_peer_data_closes_connection(self):
        reader, writer = await self.peer()
        writer.write(b"\xff")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        await self.wait_for(lambda: not self.server.connected)

    async def test_service_metadata_and_cleanup_without_multicast(self):
        await self.server.stop()
        calls = []

        class Advertiser:
            def __init__(self, **options):
                calls.append(options)
            async def async_register_service(self, service, **options):
                calls.append(service)
            async def async_unregister_service(self, service):
                calls.append("unregistered")
            async def async_close(self):
                calls.append("closed")

        with patch("zeroconf.asyncio.AsyncZeroconf", Advertiser):
            await self.server.start(identity="a" * 32, host="127.0.0.1")
            service = calls[1]
            self.assertEqual(service.type, SERVICE_TYPE)
            self.assertEqual(service.properties[b"manufacturer"], b"olli.works")
            self.assertEqual(service.port, self.server.port)
            await self.server.stop()
        self.assertEqual(calls[-2:], ["unregistered", "closed"])
