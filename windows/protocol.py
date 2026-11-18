"""Small, strict decoder for the public Zwift controller wire formats.

Protocol reference: OpenBikeControl/bikecontrol prop_public/protocol/zwift.
No upstream application code is included.
"""
RIDE_ON = b"RideOn"
# Public zp.proto enum: RESET = 24. A payload-free command is an experimental
# hypothesis; BikeControl's private reset sequence is not available here.
EXPERIMENTAL_RESET = b"\x18"
SERVICE = "00000001-19ca-4651-86e5-fa29dcdd09d1"
SERVICE_V2 = "0000fc82-0000-1000-8000-00805f9b34fb"
MEASUREMENT = "00000002-19ca-4651-86e5-fa29dcdd09d1"
CONTROL = "00000003-19ca-4651-86e5-fa29dcdd09d1"
RESPONSE = "00000004-19ca-4651-86e5-fa29dcdd09d1"
TYPES = {2: "Play right", 3: "Play left", 7: "Ride right", 8: "Ride left",
         9: "Click", 10: "Click v2 right", 11: "Click v2 left", 14: "Play fw2"}


def fields(data):
    result = {}
    pos = 0

    def varint():
        nonlocal pos
        value = 0
        for shift in range(0, 70, 7):
            if pos >= len(data):
                raise ValueError("Truncated protobuf varint")
            byte = data[pos]
            pos += 1
            if shift == 63 and byte > 1:
                raise ValueError("Protobuf varint overflow")
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
        raise ValueError("Protobuf varint overflow")

    while pos < len(data):
        tag = varint()
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError("Invalid protobuf field")
        if wire == 0:
            result[number] = varint()
        elif wire in (1, 2, 5):
            size = varint() if wire == 2 else (8 if wire == 1 else 4)
            pos += size
            if pos > len(data):
                raise ValueError("Truncated protobuf field")
        else:
            raise ValueError("Unsupported protobuf wire type")
    return result


def decode(data):
    """Return held button names, or None for non-button messages.

    Each transport has its own state; duplicates are handled by the caller.
    Proto3 default zero means pressed for Click and Play enums.
    """
    if not data or data[0] not in (0x37, 0x07, 0x23):
        return None
    f = fields(data[1:])
    if data[0] == 0x37:
        return {name for field, name in ((1, "plus"), (2, "minus")) if f.get(field, 0) == 0}
    if data[0] == 0x23:
        mask = f.get(1, 0)
        buttons = {1: "left", 2: "up", 4: "right", 8: "down", 16: "a", 32: "b",
                   64: "y", 128: "z", 256: "minus", 512: "minus2", 4096: "plus", 8192: "plus2",
                   1024: "power_left", 16384: "power_right", 2048: "on_left", 32768: "on_right"}
        return {name for bit, name in buttons.items() if not mask & bit}
    side = "right" if f.get(1, 0) == 0 else "left"
    names = ("y", "z", "a", "b") if side == "right" else ("up", "left", "right", "down")
    result = {name for field, name in enumerate(names, 2) if f.get(field, 0) == 0}
    if f.get(7, 0) == 0:
        result.add("on_" + side)
    if f.get(6, 0) == 0:
        result.add("plus" if side == "right" else "minus")
    return result
