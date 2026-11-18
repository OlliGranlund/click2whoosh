"""Development-only live BLE probe. Never sends keyboard input."""
import asyncio
import logging
import sys
from app import Engine
from bleak import BleakScanner
from protocol import CONTROL


async def main():
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler("live-test.log", encoding="utf-8")])
    engine = Engine(lambda kind, value: print(kind, value, flush=True))
    try:
        if '--right' in sys.argv:
            print('Waiting up to 30 seconds for right Click to advertise...', flush=True)
            def is_right(device, adv):
                return adv.manufacturer_data.get(0x094A, b'')[:1] == b'\x0a'
            device = await BleakScanner.find_device_by_filter(is_right, timeout=30)
            if device is None:
                print('No right Click advertisement received.', flush=True)
                return
            engine.devices[device.address] = (device, 10)
        else:
            await asyncio.wrap_future(engine.submit(engine.scan()))
        selected = [a for a, (_, kind) in engine.devices.items() if '--right' not in sys.argv or kind == 10]
        await asyncio.wrap_future(engine.submit(engine.connect(selected)))
        if '--probe-start' in sys.argv:
            for _ in range(30):
                if engine.sessions:
                    break
                await asyncio.sleep(1)
            await asyncio.sleep(8)
            async def start_controls():
                for address, client in list(engine.sessions.items()):
                    characteristic = client.services.get_characteristic(CONTROL)
                    print('Testing BikeControl vendor start command ff 04 00 on', address, flush=True)
                    await client.write_gatt_char(characteristic, bytes.fromhex('ff 04 00'),
                                                response='write-without-response' not in characteristic.properties)
            await asyncio.wrap_future(engine.submit(start_controls()))
        await asyncio.sleep(90)
    finally:
        await asyncio.wrap_future(engine.submit(engine.shutdown()))
        engine.loop.call_soon_threadsafe(engine.loop.stop)
        engine.thread.join(timeout=3)
        engine.loop.close()


if __name__ == "__main__":
    asyncio.run(main())
