import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import sys
import threading
import time

from bleak import BleakClient, BleakScanner
from protocol import CONTROL, MEASUREMENT, RESPONSE, RIDE_ON, EXPERIMENTAL_RESET, SERVICE, SERVICE_V2, TYPES, decode
from keyboard import create_keyboard
from desktop import data_directory
from battery import BATTERY_LEVEL, BatteryAlerts, standard_level, zwift_level
from openbikecontrol import OpenBikeControlServer, DEFAULT_MAPPING as NETWORK_DEFAULTS
from gestures import Gestures
from zwift_unlock import UnlockClient, ChallengeQueue

DATA = data_directory()
DEFAULTS = {"plus": "K", "minus": "I", "b": "I", "left": "A", "right": "D",
            "up": "UP", "down": "DOWN", "a": "ENTER", "y": "H", "z": "SPACE"}
KEYS = ["OFF"] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") + ["SPACE", "ENTER", "ESC", "UP", "DOWN", "LEFT", "RIGHT"]
KEEPALIVE_SECONDS = 3
BATTERY_POLL_SECONDS = 60
LEFT_RESTART_SECONDS = 45
RESET_WRITE_TIMEOUT = 3
RESET_SETTLE_SECONDS = 2


class Engine:
    def __init__(self, emit, keyboard=None):
        self.emit = emit
        self.keyboard = keyboard or create_keyboard()
        self.mapping = dict(DEFAULTS)
        self.gesture_options = {}
        self.gestures = Gestures(self._gesture_output)
        self._gesture_timer = None
        self.enabled = False
        self.connection_method = "keyboard"
        self.network_mapping = dict(NETWORK_DEFAULTS)
        self.network = OpenBikeControlServer(emit, self.log)
        self._output_lock = asyncio.Lock()
        self._radio_lock = asyncio.Lock()
        self.left_restart = False
        self.auto_focus = False
        self.background_scan = False
        self.program = ""
        self.auto_launch = False
        self._launched = False
        self._scan_retry = None
        self.unlock = UnlockClient(DATA / "zwift-session.bin")
        self.loop = asyncio.new_event_loop()
        self.sessions = {}
        self.stopping = False
        self.tasks = {}
        self.last_input = {}
        self.devices = {}
        self.scanning = False
        self.discovery_task = None
        self.discovery_generation = 0
        self.batteries = {}
        self.battery_alerts = BatteryAlerts()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        def done(f):
            try:
                f.result()
            except Exception as exc:
                self.log(f"Error: {exc}")
        future.add_done_callback(done)
        return future

    def log(self, message):
        logging.info(message)
        self.emit("log", message)

    def _gesture_output(self, event, key, device=None):
        if event == "up":
            if hasattr(self.keyboard, "hold"):
                self.keyboard.hold(key, False)
            else:
                self.keyboard.send(key, up=True)
        elif self.enabled and self.connection_method == "keyboard":
            if self.auto_focus and hasattr(self.keyboard, "focus_target"):
                self.keyboard.focus_target()
            if not self.keyboard.target_active():
                return False
            if event == "down":
                self.keyboard.hold(key, True) if hasattr(self.keyboard, "hold") else self.keyboard.send(key)
            else:
                if hasattr(self.keyboard, "queue_tap"):
                    self.keyboard.queue_tap(key, lambda: self.enabled and self.connection_method == "keyboard", device)
                else:
                    self.keyboard.tap(key)
            self.log(f"Sent {key} to MyWhoosh ({event})")
            return True
        return False

    async def launch_program(self):
        if sys.platform != "win32" or not self.program:
            return
        if self.keyboard.target_active() or (hasattr(self.keyboard, "target_windows") and self.keyboard.target_windows()):
            return
        path = Path(self.program)
        if path.is_file() and path.suffix.lower() == ".exe" and path.name.lower().startswith("mywhoosh"):
            os.startfile(str(path))
            self.log("Started the configured MyWhoosh application.")
        else:
            self.log("MyWhoosh executable not found. Choose it again in Setup.")

    def _poll_gestures(self):
        self._gesture_timer = None
        if not self.enabled or self.connection_method != "keyboard" or not self.keyboard.target_active():
            self.gestures.clear()
        else:
            self.gestures.tick()
        if self.gestures.pressed:
            self._gesture_timer = asyncio.get_running_loop().call_later(.025, self._poll_gestures)

    async def clear_output(self):
        if self._gesture_timer:
            self._gesture_timer.cancel()
            self._gesture_timer = None
        self.gestures.clear()
        if hasattr(self.keyboard, "clear"):
            await self.keyboard.clear()
        self.network.clear_buttons()

    async def zwift_login(self, email, password):
        self.emit("unlock_status", dict(busy=True, ready=self.unlock.ready, message="Signing in to Zwift…"))
        try:
            await self.unlock.login(email, password)
            if not self.unlock.ready:
                self.emit("unlock_status", dict(busy=False, ready=False, message="Sign-in cancelled; no session saved."))
                return
            if self.unlock.ready and self.left_restart:
                self.left_restart = False
                self.emit("left_restart_stopped", "Experimental restart recovery turned off while testing signed Zwift unlock. Verify left − after reconnecting.")
            self.emit("unlock_status", dict(busy=False, ready=self.unlock.ready,
                message="Signed in. Reconnect the left Click to answer its unlock challenge."))
        except Exception as exc:
            self.emit("unlock_status", dict(busy=False, ready=self.unlock.ready, message=str(exc)))

    async def zwift_forget(self):
        try:
            self.unlock.forget()
            self.emit("unlock_status", dict(busy=False, ready=False, message="Saved Zwift session removed from this PC."))
        except OSError:
            self.emit("unlock_status", dict(busy=False, ready=False, message="Could not delete the saved session file. Open the app folder to remove zwift-session.bin."))

    async def set_connection_method(self, method, identity=None):
        if method not in ("keyboard", "network"):
            raise ValueError("Unsupported connection method")
        async with self._output_lock:
            self.enabled = False
            await self.clear_output()
            self.emit("output_enabled", False)
            self.connection_method = method
            try:
                await self.network.stop()
                if method == "network":
                    await self.network.start(identity=identity)
            except Exception as exc:
                self.log(f"OpenBikeControl setup failed: {exc}")
                self.emit("network", dict(status=f"Network unavailable: {exc}", connected=False, error=True))
            finally:
                self.emit("connection_method", method)

    async def clear_network_buttons(self):
        self.network.clear_buttons()

    def start_connection(self, address):
        if not self.stopping and (address not in self.tasks or self.tasks[address].done()):
            self.tasks[address] = asyncio.create_task(self.session(address))

    async def scan(self):
        if self.scanning or self.stopping:
            return
        self.scanning = True
        self.discovery_task = asyncio.current_task()
        generation = self.discovery_generation
        self.log("Finding and connecting controllers for 8 seconds. Press a Click button to wake it.")
        found = set()
        def discovered(device, adv):
            if self.stopping or generation != self.discovery_generation:
                return
            mfg = adv.manufacturer_data.get(0x094A, b"")
            kind = mfg[0] if mfg else None
            name = adv.local_name or device.name or "Unnamed"
            if kind not in TYPES and not {SERVICE, SERVICE_V2}.intersection(adv.service_uuids) and not any(s in name.lower() for s in ("zwift", "click")):
                return
            # Keep a known identity if a scan-response packet omits manufacturer data.
            kind = kind if kind in TYPES else self.devices.get(device.address, (None, None))[1]
            self.devices[device.address] = (device, kind)
            if device.address not in found:
                found.add(device.address)
                self.emit("device", (device.address, name, TYPES.get(kind, "Unknown Zwift"), adv.rssi))
            # Only positively identified controllers auto-connect; name-only matches remain selectable.
            if kind in TYPES:
                self.start_connection(device.address)
        try:
            async with self._radio_lock:
                async with BleakScanner(detection_callback=discovered):
                    await asyncio.sleep(8)
            self.log(f"Scan finished: {len(found)} controller(s). Known controllers connect automatically.")
        except asyncio.CancelledError:
            self.log("Controller search cancelled.")
        finally:
            self.scanning = False
            self.discovery_task = None
            if self.background_scan and not self.stopping and generation == self.discovery_generation:
                self._scan_retry = self.loop.call_later(3, lambda: self.submit(self.scan()))

    async def connect(self, addresses):
        for address in addresses:
            self.start_connection(address)

    async def connect_right(self):
        if self.scanning or self.stopping:
            self.log("A scan is already running; wait for it to finish.")
            return
        if any(self.devices[a][1] == 10 and not task.done() for a, task in self.tasks.items()):
            self.log("The right Click already has a connection task. Disconnect all before starting another.")
            return
        self.scanning = True
        self.discovery_task = asyncio.current_task()
        generation = self.discovery_generation
        try:
            self.log("Waiting up to 30 seconds for the right Click. Press + to wake it; connection starts immediately.")
            observed = {}
            def is_right(device, adv):
                if adv.manufacturer_data.get(0x094A, b"")[:1] == b"\x0a":
                    observed[device.address] = adv
                    return True
                return False
            async with self._radio_lock:
                device = await BleakScanner.find_device_by_filter(is_right, timeout=30)
            if generation != self.discovery_generation or self.stopping:
                return
            if device is None:
                self.log("No right Click advertisement received. Wake it and close other apps connected to it.")
                return
            adv = observed[device.address]
            self.devices[device.address] = (device, 10)
            self.emit("device", (device.address, adv.local_name or device.name or "Zwift Click", TYPES[10], adv.rssi))
            await self.connect([device.address])
        except asyncio.CancelledError:
            self.log("Right Click search cancelled.")
        finally:
            self.scanning = False
            self.discovery_task = None

    def update_battery(self, address, level, source):
        if level is None:
            return
        changed = self.batteries.get(address) != level
        self.batteries[address] = level
        self.emit("battery", (address, level, time.time()))
        self.stop_left_restart_if_low(address)
        if changed:
            self.log(f"{address}: battery {level}% ({source})")
        stage = self.battery_alerts.update(address, level)
        if stage:
            self.emit("battery_alert", (address, level, stage))
            self.log(f"Battery {stage}: {TYPES.get(self.devices[address][1], address)} at {level}%")

    def stop_left_restart_if_low(self, address):
        level = self.batteries.get(address)
        kind = self.devices.get(address, (None, None))[1]
        if self.left_restart and kind == 11 and level is not None and level <= 20:
            self.left_restart = False
            reason = (f"Experimental left recovery stopped: controller reports {level}% battery. "
                      "Let it rest and check the reading before re-enabling; + / B remains available.")
            self.log(reason)
            self.emit("left_restart_stopped", reason)
            return True
        return False

    async def read_battery(self, client, address, characteristic):
        try:
            async with asyncio.timeout(5):
                raw = await client.read_gatt_char(characteristic)
            self.update_battery(address, standard_level(raw), "Bluetooth battery service")
        except Exception as exc:
            logging.debug("%s battery read unavailable: %s", address, exc)

    async def setup_battery(self, client, address):
        characteristic = client.services.get_characteristic(BATTERY_LEVEL)
        if characteristic is None:
            self.log(f"{address}: no standard battery service; waiting for controller battery messages.")
            return None
        if "notify" in characteristic.properties or "indicate" in characteristic.properties:
            try:
                await client.start_notify(characteristic, lambda _, raw: self.update_battery(address, standard_level(raw), "Bluetooth battery notification"))
            except Exception as exc:
                logging.debug("%s battery subscription unavailable: %s", address, exc)
        if "read" in characteristic.properties:
            await self.read_battery(client, address, characteristic)
            return characteristic
        return None

    async def session(self, address):
        device, kind = self.devices[address]
        delay = 1
        suppress_until_release = set()
        awaiting_recovery_baseline = False
        while not self.stopping:
            radio_acquired = False
            try:
                await self._radio_lock.acquire()
                radio_acquired = True
                if delay > 1:
                    self.emit("state", (address, "Waiting for advertisement; press a button"))
                    fresh = await BleakScanner.find_device_by_filter(lambda dev, adv: dev.address == address, timeout=8)
                    if fresh is None:
                        raise RuntimeError("Controller not advertising; waiting before reconnect")
                    device = fresh
                self.emit("state", (address, "Connecting"))
                self.emit("battery", (address, None, None))
                disconnected = asyncio.Event()
                async with BleakClient(device, disconnected_callback=lambda _: disconnected.set(), timeout=20,
                                       **({"winrt": {"use_cached_services": False}} if sys.platform == "win32" else {})) as client:
                    self._radio_lock.release()
                    radio_acquired = False
                    self.sessions[address] = client
                    if self.auto_launch and not self._launched:
                        self._launched = True
                        await self.launch_program()
                    previous = set()
                    recovering = False
                    handshake = asyncio.Event()
                    first_frame = asyncio.Event()
                    async def write_unlock(reply):
                        if self.sessions.get(address) is not client or not getattr(client, "is_connected", False):
                            return
                        control_char = client.services.get_characteristic(CONTROL)
                        async with asyncio.timeout(3):
                            await client.write_gatt_char(CONTROL, reply, response="write-without-response" not in control_char.properties)
                        self.emit("unlock_status", dict(busy=False, ready=self.unlock.ready,
                            message="Signed unlock reply sent. Press left − to verify input."))
                    unlock_queue = ChallengeQueue(self.unlock.solve, write_unlock,
                        lambda error: self.emit("unlock_status", dict(busy=False, ready=self.unlock.ready, message=f"Left unlock: {error}")))
                    def notify(characteristic, raw):
                        nonlocal previous, awaiting_recovery_baseline
                        data = bytes(raw)
                        logging.debug("%s %s RX %s", address, characteristic.uuid, data.hex(" "))
                        try:
                            if kind == 11 and data.startswith(b"\xff\x03\x00") and len(data) > 3:
                                if self.unlock.ready:
                                    unlock_queue.submit(data[3:])
                                else:
                                    self.emit("unlock_status", dict(busy=False, ready=False,
                                        message="Left Click requested unlock. Optional Zwift sign-in is available in Setup."))
                                return
                            if data.startswith(RIDE_ON):
                                if data == RIDE_ON or (len(data) >= 8 and data[6:8] in (b"\x02\x03", b"\x01\x03", b"\x01\x04")):
                                    if not handshake.is_set():
                                        handshake.set()
                                        self.emit("state", (address, "Handshake OK; press buttons"))
                                else:
                                    self.log(f"{address}: unexpected RideOn response {data.hex(' ')}")
                                return
                            if data and data[0] in (0x19, 0x1A):
                                self.update_battery(address, zwift_level(data), "Zwift controller notification")
                                return
                            buttons = decode(data)
                            if buttons is None:
                                if data and data[0] in (0xFE, 0xFF):
                                    self.log(f"{address}: device status {data.hex(' ')}; v2 may require unlock in Zwift.")
                                return
                            # A v2 pod may report the shared full mask: restrict to its own physical buttons.
                            if kind == 10:
                                buttons &= {"a", "b", "y", "z", "plus"}
                            elif kind == 11:
                                buttons &= {"up", "down", "left", "right", "minus"}
                            if recovering:
                                return
                            if awaiting_recovery_baseline:
                                # Also discard a press begun during the reboot
                                # gap, rather than delivering it late on return.
                                suppress_until_release.update(buttons)
                                awaiting_recovery_baseline = False
                            if not first_frame.is_set():
                                self.log(f"{address}: valid button frames received (0x{data[0]:02x}).")
                            first_frame.set()
                            self.last_input[address] = time.monotonic()
                            self.emit("state", (address, "Receiving controls"))
                            self.emit("buttons", (address, kind, buttons))
                            newly_pressed = buttons - previous
                            previous = buttons
                            newly_pressed -= suppress_until_release
                            suppress_until_release.intersection_update(buttons)
                            if self.enabled and self.connection_method == "network":
                                self.network.buttons(address, buttons - suppress_until_release, newly_pressed, self.network_mapping)
                            if self.enabled and self.connection_method == "keyboard":
                                # Focus on the physical down edge, including gestures
                                # whose actual output is intentionally delayed.
                                if newly_pressed and self.auto_focus and hasattr(self.keyboard, "focus_target"):
                                    self.keyboard.focus_target()
                                eligible = {b for a, b in self.gestures.pressed if a == address} | newly_pressed
                                self.gestures.buttons(address, buttons & eligible, self.mapping, self.gesture_options)
                                if self.gestures.pressed and self._gesture_timer is None:
                                    self._gesture_timer = asyncio.get_running_loop().call_later(.025, self._poll_gestures)
                            for button in sorted(newly_pressed):
                                key = (self.network_mapping if self.connection_method == "network" else self.mapping).get(button, "OFF")
                                self.log(f"{TYPES.get(kind, address)}: {button} → {key}")
                        except Exception as exc:
                            self.log(f"{address}: notification error: {exc}; raw={data.hex(' ')}")
                    for uuid in (MEASUREMENT, RESPONSE, CONTROL):
                        if client.services.get_characteristic(uuid) is None:
                            raise RuntimeError(f"Missing {uuid}. Firmware may hide the controller service until unlocked in Zwift.")
                    await client.start_notify(MEASUREMENT, notify)
                    await client.start_notify(RESPONSE, notify)
                    control = client.services.get_characteristic(CONTROL)
                    response = "write-without-response" not in control.properties
                    # Request is plain RideOn. 02 03 is the v2 response header.
                    command = RIDE_ON + b"\x02\x03" if kind == 11 and self.unlock.ready else RIDE_ON
                    self.log(f"{address}: notifications subscribed; sending {command.hex(' ')}")
                    await client.write_gatt_char(control, command, response=response)
                    if kind == 11 and self.unlock.ready:
                        for activation in (b"\x00\x08\x00", b"\x00\x08\x10"):
                            await asyncio.sleep(.1)
                            await client.write_gatt_char(control, activation, response=response)
                    connected_at = time.monotonic()
                    battery_characteristic = await self.setup_battery(client, address)
                    next_battery_read = time.monotonic() + BATTERY_POLL_SECONDS
                    try:
                        firmware = await client.read_gatt_char("00002a26-0000-1000-8000-00805f9b34fb")
                        self.log(f"{address}: firmware {firmware.decode(errors='replace')}")
                    except Exception:
                        pass
                    try:
                        async with asyncio.timeout(6):
                            await handshake.wait()
                    except asyncio.TimeoutError:
                        self.log(f"{address}: no recognised handshake response. Press a button; transport connection alone does not prove controls work.")
                    if not first_frame.is_set():
                        self.emit("state", (address, "Waiting for button frames / possible lock"))
                    delay = 1
                    while not disconnected.is_set():
                        try:
                            async with asyncio.timeout(KEEPALIVE_SECONDS):
                                await disconnected.wait()
                        except asyncio.TimeoutError:
                            self.stop_left_restart_if_low(address)
                            if kind == 11 and self.left_restart and time.monotonic() - connected_at >= LEFT_RESTART_SECONDS:
                                recovering = True
                                self.gestures.clear(address)
                                if hasattr(self.keyboard, "clear_device"):
                                    await self.keyboard.clear_device(address)
                                self.network.release_device(address)
                                suppress_until_release = set(previous)
                                awaiting_recovery_baseline = True
                                self.emit("buttons", (address, kind, set()))
                                self.emit("battery", (address, None, None))
                                self.emit("state", (address, "Experimental restart; reconnecting"))
                                self.log(f"{address}: experimental left RESET TX {EXPERIMENTAL_RESET.hex(' ')}; recovery is not hardware-verified.")
                                try:
                                    async with asyncio.timeout(RESET_WRITE_TIMEOUT):
                                        await client.write_gatt_char(control, EXPERIMENTAL_RESET, response=response)
                                except Exception as exc:
                                    if not disconnected.is_set():
                                        raise RuntimeError(f"Experimental left RESET failed: {exc}") from exc
                                try:
                                    async with asyncio.timeout(RESET_SETTLE_SECONDS):
                                        await disconnected.wait()
                                    self.log(f"{address}: disconnected after experimental RESET; reconnecting left only.")
                                except asyncio.TimeoutError:
                                    self.log(f"{address}: no reboot disconnect observed; cycling left connection. RESET effectiveness is unknown.")
                                break
                            if kind == 10:
                                await client.write_gatt_char(control, RIDE_ON, response=response)
                                logging.debug("%s TX RideOn keep-alive", address)
                            if battery_characteristic is not None and time.monotonic() >= next_battery_read:
                                await self.read_battery(client, address, battery_characteristic)
                                next_battery_read = time.monotonic() + BATTERY_POLL_SECONDS
                            last = self.last_input.get(address)
                            if last and time.monotonic() - last > 30:
                                self.emit("state", (address, "No recent frames; press button to check"))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.log(f"{address}: {type(exc).__name__}: {exc or 'Bluetooth operation did not complete; wake device and close other connected apps.'}")
            finally:
                if radio_acquired:
                    self._radio_lock.release()
                if 'unlock_queue' in locals():
                    await unlock_queue.close()
                self.gestures.clear(address)
                if hasattr(self.keyboard, "clear_device"):
                    await self.keyboard.clear_device(address)
                self.network.release_device(address)
                self.sessions.pop(address, None)
                self.last_input.pop(address, None)
                self.emit("state", (address, "Disconnected"))
            if not self.stopping:
                self.log(f"{address}: reconnecting in {delay}s; wake the controller if asleep.")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15)

    async def disconnect(self):
        await self.clear_output()
        if self._scan_retry:
            self._scan_retry.cancel()
            self._scan_retry = None
        self._launched = False
        self.discovery_generation += 1
        discovery = self.discovery_task
        if discovery and discovery is not asyncio.current_task():
            discovery.cancel()
            await asyncio.gather(discovery, return_exceptions=True)
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()

    async def shutdown(self):
        self.stopping = True
        self.enabled = False
        await self.network.stop()
        await self.disconnect()



def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--transport-smoke":
        from openbikecontrol import smoke_test
        try:
            result = asyncio.run(smoke_test())
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2))
        if not result["ok"]:
            sys.exit(1)
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--ui-smoke":
        from web_ui import run
        run(sys.modules[__name__], smoke_output=sys.argv[2])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--diagnose":
        async def diagnose():
            found = await BleakScanner.discover(timeout=8, return_adv=True)
            controllers = [{"name": a.local_name or d.name, "address": d.address,
                            "type": TYPES.get(a.manufacturer_data.get(0x094A, b"\x00")[0], "unknown")}
                           for d, a in found.values() if 0x094A in a.manufacturer_data]
            return {"scan_ok": True, "advertisements": len(found), "controllers": controllers,
                    "input_struct_size": __import__("ctypes").sizeof(__import__("keyboard").INPUT)}
        try:
            result = asyncio.run(diagnose())
        except Exception as exc:
            result = {"scan_ok": False, "error": str(exc)}
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2))
        return
    DATA.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(DATA / "diagnostics.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.DEBUG, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    logging.info("ClickToWhoosh started; Python %s", sys.version)
    from web_ui import run
    run(sys.modules[__name__])


if __name__ == "__main__":
    main()
