"""Independent implementation of the public OpenBikeControl mDNS/TCP protocol.

No BikeControl application/private-module source is included. Incoming app-info
and haptic messages are parsed incrementally: TCP read boundaries are arbitrary.
"""
import asyncio
import re
import socket
import uuid
import sys

SERVICE_TYPE = "_openbikecontrol._tcp.local."
SERVICE_UUID = "d273f680-d548-419d-b9d1-fa0472345229"
ACTIONS = {"OFF": None, "shift_up": 1, "shift_down": 2, "up": 0x10, "down": 0x11,
           "look_left": 0x12, "look_right": 0x13, "confirm": 0x14, "back": 0x15,
           "menu": 0x16, "steer_left": 0x18, "steer_right": 0x19, "emote": 0x20,
           "screenshot": 0x24, "pause": 0x33, "hud_toggle": 0x44}
DEFAULT_MAPPING = dict(plus="shift_up", minus="shift_down", b="shift_down", left="steer_left",
                       right="steer_right", up="up", down="down", a="confirm", y="hud_toggle", z="emote")
HELD_ACTIONS = {0x18, 0x19}


def default_address():
    """Ask the OS for its default IPv4 route; UDP connect sends no packet."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]


def pop_message(buffer):
    """Consume one complete app-to-controller message, or await more bytes."""
    if not buffer:
        return None
    if buffer[0] == 3:  # haptics; unsupported hardware, but consume safely
        size = 4
    elif buffer[0] == 4:
        if len(buffer) < 3:
            return None
        if buffer[1] != 1 or buffer[2] > 32:
            raise ValueError("Invalid OpenBikeControl app-information header")
        version_offset = 3 + buffer[2]
        if len(buffer) <= version_offset:
            return None
        if buffer[version_offset] > 32:
            raise ValueError("App version is too long")
        count_offset = version_offset + 1 + buffer[version_offset]
        if len(buffer) <= count_offset:
            return None
        size = count_offset + 1 + buffer[count_offset]
    else:
        raise ValueError("Unsupported app message type")
    if len(buffer) < size:
        return None
    result = bytes(buffer[:size])
    del buffer[:size]
    return result


class OpenBikeControlServer:
    def __init__(self, emit, log):
        self.emit, self.log = emit, log
        self.server = self.writer = self.zeroconf = self.service = None
        self.peer_task = None
        self.bonjour = None
        self.held = {}
        self.active = set()
        self.supported = None
        self.app_id = None
        self.address = None
        self.port = None

    @property
    def connected(self):
        return self.writer is not None and not self.writer.is_closing()

    def status(self, label, **extra):
        self.emit("network", dict(status=label, connected=self.connected, app=self.app_id,
                                  address=self.address, port=self.port, **extra))

    async def start(self, identity=None, host=None, advertise=True):
        if self.server:
            return
        identity = identity or uuid.uuid4().hex
        self.address = host or default_address()
        try:
            native_bonjour = advertise and sys.platform == "win32" and host is None
            self.server = await asyncio.start_server(self._accept, "0.0.0.0" if native_bonjour else self.address, 0, limit=1024)
            self.port = self.server.sockets[0].getsockname()[1]
            properties = {"version": "1", "id": identity, "name": "ClickToWhoosh by olli.works",
                          "service-uuids": SERVICE_UUID, "manufacturer": "olli.works", "model": "ClickToWhoosh"}
            if native_bonjour:
                from bonjour import BonjourRegistration
                self.bonjour = BonjourRegistration(f"ClickToWhoosh {identity[:6]}", self.port, properties)
                await asyncio.to_thread(self.bonjour.wait_ready)
                self.log("OpenBikeControl discovery registered with Windows Bonjour; hostname owned by Bonjour.")
            elif advertise:
                from zeroconf import ServiceInfo
                from zeroconf.asyncio import AsyncZeroconf
                self.zeroconf = AsyncZeroconf(interfaces=[self.address])
                self.service = ServiceInfo(SERVICE_TYPE, f"ClickToWhoosh {identity[:6]}.{SERVICE_TYPE}",
                    addresses=[socket.inet_aton(self.address)], port=self.port,
                    properties=properties,
                    server=f"clicktowhoosh-{identity[:12]}.local.")
                async with asyncio.timeout(8):
                    await self.zeroconf.async_register_service(self.service, allow_name_change=True)
            self.log(f"OpenBikeControl listening on {self.address}:{self.port}; pair in MyWhoosh.")
            self.status("Waiting for MyWhoosh pairing")
        except BaseException:
            await self.stop()
            raise

    async def stop(self):
        self.clear_buttons()
        writer, self.writer = self.writer, None
        if writer:
            writer.close()
            try:
                async with asyncio.timeout(1):
                    await writer.wait_closed()
            except (OSError, TimeoutError):
                pass

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        if self.peer_task and self.peer_task is not asyncio.current_task():
            self.peer_task.cancel()
            await asyncio.gather(self.peer_task, return_exceptions=True)
        self.peer_task = None
        if self.bonjour:
            await asyncio.to_thread(self.bonjour.close)
            self.bonjour = None
        if self.zeroconf:
            try:
                if self.service:
                    async with asyncio.timeout(3):
                        await self.zeroconf.async_unregister_service(self.service)
            except Exception as exc:
                self.log(f"OpenBikeControl advertisement cleanup: {exc}")
            finally:
                try:
                    async with asyncio.timeout(3):
                        await self.zeroconf.async_close()
                finally:
                    self.zeroconf = self.service = None
        self.app_id = self.supported = None
        self.address = self.port = None
        self.status("Off")

    def _write(self, message):
        if not self.connected:
            return False
        if self.writer.transport.get_write_buffer_size() > 65536:
            self.writer.close()
            self.log("OpenBikeControl peer is too slow; dropped connection instead of queuing controls.")
            return False
        try:
            self.writer.write(message)
            return True
        except (OSError, RuntimeError):
            self.writer.close()
            return False

    def _button(self, action, pressed):
        return self._write(bytes((1, action, int(pressed))))

    def clear_buttons(self):
        for action in sorted(self.active):
            self._button(action, False)
        self.active.clear()
        self.held.clear()

    def release_device(self, address):
        self.held.pop(address, None)
        self._update_held()

    def _update_held(self):
        desired = set().union(*self.held.values()) if self.held else set()
        for action in sorted(self.active - desired):
            self._button(action, False)
        for action in sorted(desired - self.active):
            self._button(action, True)
        self.active = desired

    def buttons(self, address, held, rising, mapping):
        if not self.connected:
            return  # No queues and no replay when a trainer app reconnects.
        allowed = lambda action: action is not None and (self.supported is None or action in self.supported)
        self.held[address] = {ACTIONS.get(mapping.get(button)) for button in held
                              if ACTIONS.get(mapping.get(button)) in HELD_ACTIONS and allowed(ACTIONS.get(mapping.get(button)))}
        self._update_held()
        for button in sorted(rising):
            action = ACTIONS.get(mapping.get(button))
            if allowed(action) and action not in HELD_ACTIONS:
                # Each physical tap has its own transitions, including two
                # different physical buttons mapped to the same shift action.
                if self._button(action, True):
                    self._button(action, False)
                    self.log(f"OpenBikeControl: {button} → {mapping[button]}")

    async def _heartbeat(self, writer):
        try:
            while self.writer is writer and self.connected:
                self._write(b"\x02\xff\x01")
                async with asyncio.timeout(2):
                    await writer.drain()
                await asyncio.sleep(5)
        except (OSError, TimeoutError):
            writer.close()

    async def _accept(self, reader, writer):
        # The bridge is for one paired trainer app, never a broadcast of input.
        if self.writer is not None:
            writer.close()
            await writer.wait_closed()
            return
        self.writer = writer
        self.peer_task = asyncio.current_task()
        self.log("OpenBikeControl TCP peer connected; waiting for optional app identity.")
        self.clear_buttons()
        self.app_id = self.supported = None
        self.status("App connected; identity not reported")
        heartbeat = asyncio.create_task(self._heartbeat(writer))
        try:
            buffer = bytearray()
            while self.writer is writer:
                data = await reader.read(512)
                if not data:
                    break
                buffer.extend(data)
                if len(buffer) > 1024:
                    raise ValueError("App message buffer exceeded limit")
                while (message := pop_message(buffer)) is not None:
                    if message[0] == 4:
                        version_offset = 3 + message[2]
                        app_id = message[3:version_offset].decode("utf-8")
                        if app_id and not re.fullmatch(r"[a-z0-9_-]{1,32}", app_id):
                            raise ValueError("Invalid app identity")
                        count_offset = version_offset + 1 + message[version_offset]
                        self.clear_buttons()
                        self.app_id = app_id or None
                        self.supported = set(message[count_offset + 1:]) if message[count_offset] else None
                        self.status(f"Connected to {app_id or 'trainer app'}")
                        self.log(f"OpenBikeControl app identified: {app_id or 'unknown'}")
        except (OSError, ValueError, TimeoutError) as exc:
            self.log(f"OpenBikeControl connection ended: {exc}")
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            self.log("OpenBikeControl TCP peer disconnected.")
            if self.writer is writer:
                self.clear_buttons()
                self.writer = None
                self.app_id = self.supported = None
                self.status("Waiting for MyWhoosh pairing")
            writer.close()
            try:
                async with asyncio.timeout(1):
                    await writer.wait_closed()
            except (OSError, TimeoutError):
                pass


async def smoke_test():
    """Exercise frozen imports and TCP delivery on loopback, without discovery."""
    from zeroconf import ServiceInfo
    from zeroconf.asyncio import AsyncZeroconf
    assert ServiceInfo and AsyncZeroconf
    server = OpenBikeControlServer(lambda *event: None, lambda message: None)
    writer = None
    try:
        await server.start(host="127.0.0.1", advertise=False)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        async with asyncio.timeout(3):
            assert await reader.readexactly(3) == b"\x02\xff\x01"
            server.buttons("test", {"plus"}, {"plus"}, DEFAULT_MAPPING)
            assert await reader.readexactly(6) == b"\x01\x01\x01\x01\x01\x00"
        return {"ok": True, "transport": "OpenBikeControl TCP", "discovery": "not started", "hardware": "not opened"}
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()
        await server.stop()
