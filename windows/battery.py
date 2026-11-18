"""Battery parsing and alert hysteresis, independent of Bluetooth and UI."""
from protocol import fields

BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
LOW = 20
CRITICAL = 10


def standard_level(data):
    data = bytes(data)
    return data[0] if len(data) == 1 and data[0] <= 100 else None


def zwift_level(data):
    if not data or data[0] not in (0x19, 0x1A):
        return None
    value = fields(data[1:]).get(2)
    # A charging-state-only message must never look like a zero-percent battery.
    return value if value is not None and 0 <= value <= 100 else None


class BatteryAlerts:
    def __init__(self):
        self.warned = {}

    def update(self, address, level):
        if not isinstance(level, int) or not 0 <= level <= 100:
            return None
        warned = self.warned.setdefault(address, set())
        if level >= LOW + 5:
            warned.discard("low")
        if level >= CRITICAL + 5:
            warned.discard("critical")
        stage = "critical" if level <= CRITICAL else "low" if level <= LOW else None
        if stage and stage not in warned:
            warned.add(stage)
            if stage == "critical":
                warned.add("low")
            return stage
        return None
