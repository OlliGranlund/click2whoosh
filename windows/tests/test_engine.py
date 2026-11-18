import asyncio
import unittest
from unittest.mock import patch, AsyncMock, Mock
from types import SimpleNamespace
from app import Engine
from battery import BATTERY_LEVEL
from protocol import MEASUREMENT, RESPONSE, CONTROL, EXPERIMENTAL_RESET


class FakeKeyboard:
    def __init__(self):
        self.sent = []
        self.active = True

    def target_active(self):
        return self.active

    def tap(self, key):
        self.sent.append(key)


class FakeClient:
    def __init__(self, device, disconnected_callback, timeout, **kwargs):
        self.services = self
        self.callbacks = {}
        self.writes = []
        self.properties = ["write-without-response"]
        self.uuid = RESPONSE

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get_characteristic(self, uuid):
        if uuid == BATTERY_LEVEL:
            return None
        return self

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback

    async def read_gatt_char(self, uuid):
        return b"1.2.0"

    async def write_gatt_char(self, char, command, response):
        assert set(self.callbacks) == {MEASUREMENT, RESPONSE}
        assert command == b"RideOn"
        self.writes.append(command)
        self.callbacks[RESPONSE](self, b"RideOn\x02\x03")
        if len(self.writes) > 1:
            return
        self.uuid = MEASUREMENT
        # Plus press, duplicate, release, press, B press (on a right v2 pod).
        for frame in ("23 08 ff df ff ff 0f", "23 08 ff df ff ff 0f",
                      "23 08 ff ff ff ff 0f", "23 08 ff df ff ff 0f",
                      "23 08 df ff ff ff 0f"):
            self.callbacks[MEASUREMENT](self, bytes.fromhex(frame))


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_press_focuses_on_physical_down_before_delayed_action(self):
        engine = self.make_engine()
        engine.enabled = engine.auto_focus = True
        engine.keyboard.active = False
        engine.keyboard.focus_target = Mock(side_effect=lambda:setattr(engine.keyboard,"active",True))
        engine.gesture_options = {"plus":{"long":"H","threshold_ms":300}}
        engine.devices["right"] = ("right",10)
        class HeldClient(FakeClient):
            async def write_gatt_char(self,char,command,response):
                if not self.writes:
                    self.callbacks[MEASUREMENT](self,bytes.fromhex("23 08 ff df ff ff 0f"))
                    self.callbacks[RESPONSE](self,b"RideOn")
                self.writes.append(command)
        with patch("app.BleakClient",HeldClient):
            task = asyncio.create_task(engine.session("right"))
            await asyncio.sleep(.05)
            self.assertTrue(engine.keyboard.focus_target.called)
            self.assertEqual(engine.keyboard.sent,[])
            await asyncio.sleep(.3)
            self.assertEqual(engine.keyboard.sent,["H"])
            task.cancel(); await task

    async def test_optional_signed_unlock_and_session_cancellation(self):
        engine = self.make_engine()
        engine.devices["left"] = ("left",11)
        solved, replied, activated = asyncio.Event(), asyncio.Event(), asyncio.Event()
        solve = AsyncMock(return_value=b"\xff\x04\x00signed")
        engine.unlock = SimpleNamespace(ready=True,solve=solve)
        writes = []
        class UnlockBleClient(FakeClient):
            is_connected = True
            async def write_gatt_char(self,char,command,response):
                writes.append(command)
                if command == b"RideOn\x02\x03":
                    self.callbacks[MEASUREMENT](self,b"\xff\x03\x00challenge")
                if command == b"\xff\x04\x00signed":
                    replied.set()
                if command == b"\x00\x08\x10":
                    activated.set()
        with patch("app.BleakClient",UnlockBleClient):
            task = asyncio.create_task(engine.session("left"))
            await asyncio.wait_for(replied.wait(),1)
            await asyncio.wait_for(activated.wait(),1)
            task.cancel(); await task
        solve.assert_awaited_once_with(b"challenge")
        self.assertEqual(writes[:2],[b"RideOn\x02\x03",b"\xff\x04\x00signed"])
        self.assertIn(b"\x00\x08\x00",writes)
        self.assertIn(b"\x00\x08\x10",writes)
        async def slow(challenge):
            solved.set()
            await asyncio.Event().wait()
        engine.unlock.solve = slow
        writes.clear()
        with patch("app.BleakClient",UnlockBleClient):
            task = asyncio.create_task(engine.session("left"))
            await asyncio.wait_for(solved.wait(),1)
            task.cancel(); await task
        self.assertNotIn(b"\xff\x04\x00signed",writes)

    def make_engine(self):
        engine = Engine(lambda *event: self.messages.append(event), FakeKeyboard())
        self.messages = []
        self.addCleanup(self.stop_engine, engine)
        return engine

    @staticmethod
    def stop_engine(engine):
        engine.loop.call_soon_threadsafe(engine.loop.stop)
        engine.thread.join(timeout=2)
        engine.loop.close()

    async def run_session(self, enabled=True, active=True, keepalive=False, kind=10, left_restart=False, battery=None, method="keyboard"):
        messages = []
        engine = Engine(lambda *event: messages.append(event), FakeKeyboard())
        engine.enabled = enabled
        engine.left_restart = left_restart
        engine.connection_method = method
        if method == "network":
            engine.network = Mock()
        engine.keyboard.active = active
        engine.devices["test"] = (object(), kind)
        if battery is not None:
            engine.batteries["test"] = battery
        with patch("app.BleakClient", FakeClient), patch("app.KEEPALIVE_SECONDS", 0.01 if keepalive else 3):
            task = asyncio.create_task(engine.session("test"))
            await asyncio.sleep(0.05)
            writes = list(engine.sessions["test"].writes)
            task.cancel()
            await task
        engine.loop.call_soon_threadsafe(engine.loop.stop)
        engine.thread.join(timeout=2)
        engine.loop.close()
        return engine, messages, writes

    async def test_subscription_handshake_duplicate_filter_and_keys(self):
        engine, messages, _ = await self.run_session()
        self.assertEqual(engine.keyboard.sent, ["K", "K", "I"])
        self.assertFalse(engine.sessions)
        self.assertIn(("state", ("test", "Receiving controls")), messages)

    async def test_monitor_mode_sends_nothing(self):
        engine, _, _ = await self.run_session(enabled=False)
        self.assertEqual(engine.keyboard.sent, [])

    async def test_network_method_routes_frames_without_sending_keyboard_input(self):
        engine, _, _ = await self.run_session(method="network")
        self.assertEqual(engine.keyboard.sent, [])
        rises = [call.args[2] for call in engine.network.buttons.call_args_list]
        self.assertEqual(rises, [{"plus"}, set(), set(), {"plus"}, {"b"}])

    async def test_button_packets_reach_real_loopback_transport_with_correct_shift_ids(self):
        engine = self.make_engine()
        engine.connection_method = "network"
        engine.enabled = True
        engine.devices["right"] = (object(), 10)
        await engine.network.start(host="127.0.0.1", advertise=False)
        task = None
        writer = None
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", engine.network.port)
            self.assertEqual(await asyncio.wait_for(reader.readexactly(3), 1), b"\x02\xff\x01")
            with patch("app.BleakClient", FakeClient):
                task = asyncio.create_task(engine.session("right"))
                expected = b"\x01\x01\x01\x01\x01\x00" * 2 + b"\x01\x02\x01\x01\x02\x00"
                self.assertEqual(await asyncio.wait_for(reader.readexactly(18), 1), expected)
                task.cancel()
                await task
            self.assertEqual(engine.keyboard.sent, [])
        finally:
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if writer:
                writer.close()
                await writer.wait_closed()
            await engine.network.stop()

    async def test_connection_switch_disarms_output_and_stops_old_transport(self):
        engine = self.make_engine()
        engine.enabled = True
        engine.network = Mock(stop=AsyncMock(), start=AsyncMock())
        await engine.set_connection_method("network", "identity")
        self.assertFalse(engine.enabled)
        self.assertEqual(engine.connection_method, "network")
        engine.network.stop.assert_awaited_once()
        engine.network.start.assert_awaited_once_with(identity="identity")
        await engine.set_connection_method("keyboard")
        self.assertEqual(engine.connection_method, "keyboard")
        self.assertEqual(engine.network.stop.await_count, 2)

    async def test_network_start_failure_leaves_controls_off_and_reports_error(self):
        engine = self.make_engine()
        engine.enabled = True
        engine.network = Mock(stop=AsyncMock(), start=AsyncMock(side_effect=OSError("no interface")))
        await engine.set_connection_method("network")
        self.assertFalse(engine.enabled)
        self.assertTrue(any(k == "network" and v.get("error") for k, v in self.messages))

    async def test_background_app_sends_nothing(self):
        engine, _, _ = await self.run_session(active=False)
        self.assertEqual(engine.keyboard.sent, [])

    async def test_keepalive_sends_plain_rideon_without_replaying_buttons(self):
        engine, messages, writes = await self.run_session(keepalive=True)
        self.assertGreaterEqual(len(writes), 2)
        self.assertEqual(set(writes), {b"RideOn"})
        self.assertEqual(engine.keyboard.sent, ["K", "K", "I"])
        self.assertEqual(messages.count(("state", ("test", "Handshake OK; press buttons"))), 1)

    async def test_left_recovery_is_disabled_by_default(self):
        with patch("app.LEFT_RESTART_SECONDS", 0):
            engine, _, writes = await self.run_session(kind=11, keepalive=True)
        self.assertFalse(engine.left_restart)
        self.assertEqual(writes, [b"RideOn"])

    async def test_low_left_battery_stops_reset_and_does_not_rearm_on_recovery(self):
        with patch("app.LEFT_RESTART_SECONDS", 0):
            engine, messages, writes = await self.run_session(kind=11, keepalive=True, left_restart=True, battery=18)
        self.assertFalse(engine.left_restart)
        self.assertEqual(writes, [b"RideOn"])
        self.assertEqual(sum(k == "left_restart_stopped" for k, _ in messages), 1)
        engine.update_battery("test", 100, "test")
        self.assertFalse(engine.left_restart)

    async def test_cutoff_uses_left_readings_only_and_includes_twenty_percent(self):
        engine = self.make_engine()
        engine.devices = {"left": (object(), 11), "right": (object(), 10)}
        engine.left_restart = True
        engine.update_battery("right", 10, "test")
        engine.update_battery("left", 21, "test")
        self.assertTrue(engine.left_restart)
        engine.update_battery("left", 20, "test")
        self.assertFalse(engine.left_restart)

    async def test_left_reset_reconnects_without_resetting_right_or_replaying_held_key(self):
        engine = self.make_engine()
        engine.enabled = engine.left_restart = True
        clients = {"left": [], "right": []}
        reconnected = asyncio.Event()

        class RecoveryClient(FakeClient):
            def __init__(self, device, disconnected_callback, timeout, **kwargs):
                super().__init__(device, disconnected_callback, timeout, **kwargs)
                self.side = device
                self.disconnected_callback = disconnected_callback
                clients[device].append(self)

            async def write_gatt_char(self, char, command, response):
                self.writes.append(command)
                if command == EXPERIMENTAL_RESET:
                    self.disconnected_callback(self)
                    return
                if len(self.writes) > 1:
                    return
                self.callbacks[RESPONSE](self, b"RideOn")
                frame = "23 08 ff fd ff ff 0f" if self.side == "left" else "23 08 ff df ff ff 0f"
                if self.side == "left" and len(clients["left"]) == 2:
                    engine.left_restart = False
                    # Minus held before reset, Up begun during the reboot gap.
                    self.callbacks[MEASUREMENT](self, bytes.fromhex("23 08 fd fd ff ff 0f"))
                    # The held pre-reset paddle must not repeat; a release and
                    # fresh press should still shift down normally.
                    self.callbacks[MEASUREMENT](self, bytes.fromhex("23 08 ff ff ff ff 0f"))
                    self.callbacks[MEASUREMENT](self, bytes.fromhex(frame))
                    reconnected.set()
                else:
                    self.callbacks[MEASUREMENT](self, bytes.fromhex(frame))

        engine.devices = {"left": ("left", 11), "right": ("right", 10)}
        with patch("app.BleakClient", RecoveryClient), patch("app.BleakScanner.find_device_by_filter", AsyncMock(return_value="left")), patch("app.LEFT_RESTART_SECONDS", 0), patch("app.KEEPALIVE_SECONDS", .005):
            engine.start_connection("left")
            engine.start_connection("right")
            try:
                await asyncio.wait_for(reconnected.wait(), 3)
            finally:
                await engine.disconnect()
        self.assertEqual(len(clients["left"]), 2)
        self.assertEqual(len(clients["right"]), 1)
        self.assertEqual(clients["left"][0].writes, [b"RideOn", EXPERIMENTAL_RESET])
        self.assertEqual(set(clients["right"][0].writes), {b"RideOn"})
        self.assertEqual(engine.keyboard.sent.count("I"), 2)
        self.assertEqual(engine.keyboard.sent.count("K"), 1)
        self.assertNotIn("UP", engine.keyboard.sent)
        self.assertFalse(engine.sessions)
        self.assertFalse(engine.tasks)

    async def test_disconnect_cancels_pending_reset_without_retrying(self):
        engine = self.make_engine()
        engine.left_restart = True
        reset_started = asyncio.Event()
        clients = []

        class PendingResetClient(FakeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                clients.append(self)

            async def write_gatt_char(self, char, command, response):
                self.writes.append(command)
                if command == EXPERIMENTAL_RESET:
                    reset_started.set()
                    await asyncio.Event().wait()
                else:
                    self.callbacks[RESPONSE](self, b"RideOn")

        engine.devices["left"] = (object(), 11)
        with patch("app.BleakClient", PendingResetClient), patch("app.LEFT_RESTART_SECONDS", 0), patch("app.KEEPALIVE_SECONDS", .005):
            engine.start_connection("left")
            try:
                await asyncio.wait_for(reset_started.wait(), 1)
            finally:
                await asyncio.wait_for(engine.disconnect(), 1)
        self.assertEqual(len(clients), 1)
        self.assertFalse(engine.sessions)
        self.assertFalse(engine.tasks)

    async def test_reset_failure_and_missing_disconnect_are_reported_as_unverified(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                engine = self.make_engine()
                engine.left_restart = True
                finished = asyncio.Event()

                class UnverifiedClient(FakeClient):
                    async def __aexit__(self, *args):
                        finished.set()

                    async def write_gatt_char(self, char, command, response):
                        if command == EXPERIMENTAL_RESET:
                            if failure:
                                raise OSError("unsupported write")
                        else:
                            self.callbacks[RESPONSE](self, b"RideOn")

                engine.devices["left"] = (object(), 11)
                with patch("app.BleakClient", UnverifiedClient), patch("app.LEFT_RESTART_SECONDS", 0), patch("app.KEEPALIVE_SECONDS", .005), patch("app.RESET_SETTLE_SECONDS", .001):
                    engine.start_connection("left")
                    try:
                        await asyncio.wait_for(finished.wait(), 1)
                    finally:
                        await engine.disconnect()
                logs = "\n".join(v for k, v in self.messages if k == "log")
                self.assertIn("RESET failed" if failure else "no reboot disconnect observed", logs)
                self.assertFalse(engine.tasks)

    async def test_battery_read_notify_and_alert_without_breaking_input(self):
        engine = self.make_engine()
        engine.devices["test"] = (object(), 10)
        characteristic = SimpleNamespace(properties=["read", "notify"])
        client = SimpleNamespace(services=SimpleNamespace(get_characteristic=lambda uuid: characteristic),
                                 start_notify=AsyncMock(), read_gatt_char=AsyncMock(return_value=b"\x12"))
        self.assertIs(await engine.setup_battery(client, "test"), characteristic)
        callback = client.start_notify.call_args.args[1]
        callback(characteristic, b"\x11")
        callback(characteristic, b"\x08")
        callback(characteristic, b"\xff")
        alerts = [value for kind, value in self.messages if kind == "battery_alert"]
        self.assertEqual(alerts, [("test", 18, "low"), ("test", 8, "critical")])
        self.assertEqual(engine.batteries["test"], 8)

    async def test_battery_read_failure_is_optional(self):
        engine = self.make_engine()
        engine.devices["test"] = (object(), 10)
        client = SimpleNamespace(read_gatt_char=AsyncMock(side_effect=RuntimeError("not readable")))
        await engine.read_battery(client, "test", object())
        self.assertNotIn("test", engine.batteries)
        self.assertFalse(any(kind == "battery_alert" for kind, _ in self.messages))

    async def test_scan_autoconnects_identified_devices_once_and_leaves_name_only_manual(self):
        engine = self.make_engine()
        connected = []
        async def fake_session(address):
            connected.append(address)
            await asyncio.Event().wait()
        engine.session = fake_session
        known = SimpleNamespace(address="known", name="Zwift Click")
        unknown = SimpleNamespace(address="unknown", name="Click headphones")
        class Scanner:
            def __init__(self, detection_callback):
                self.callback = detection_callback
            async def __aenter__(self):
                for device, data in ((known, b"\x0a"), (known, b"\x0a"), (unknown, b"")):
                    self.callback(device, SimpleNamespace(manufacturer_data={0x094A: data} if data else {}, local_name=device.name, service_uuids=[], rssi=-50))
                return self
            async def __aexit__(self, *args):
                pass
        with patch("app.BleakScanner", Scanner):
            task = asyncio.create_task(engine.scan())
            await asyncio.sleep(.02)
            self.assertEqual(connected, ["known"])
            self.assertIn("unknown", engine.devices)
            await engine.disconnect()
            await task
        self.assertFalse(engine.scanning)
        self.assertFalse(engine.tasks)

    async def test_disconnect_cancels_pending_right_search(self):
        engine = self.make_engine()
        async def wait_forever(*args, **kwargs):
            await asyncio.Event().wait()
        with patch("app.BleakScanner.find_device_by_filter", side_effect=wait_forever):
            task = asyncio.create_task(engine.connect_right())
            await asyncio.sleep(.01)
            await engine.disconnect()
            await task
        self.assertFalse(engine.scanning)
        self.assertFalse(engine.tasks)


if __name__ == "__main__":
    unittest.main()
