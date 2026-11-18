import unittest
from protocol import decode, fields


def varint(value):
    data = bytearray()
    while value > 127:
        data.append((value & 127) | 128)
        value >>= 7
    data.append(value)
    return bytes(data)


class ProtocolTests(unittest.TestCase):
    def test_original_click_plus_minus_and_release(self):
        self.assertEqual(decode(bytes.fromhex("37 08 00 10 01")), {"plus"})
        self.assertEqual(decode(bytes.fromhex("37 08 01 10 00")), {"minus"})
        self.assertEqual(decode(bytes.fromhex("37 08 01 10 01")), set())

    def test_v2_each_bit_and_neutral(self):
        neutral = 0xFFFFFFFF
        for bit, name in ((1, "left"), (2, "up"), (4, "right"), (8, "down"),
                          (16, "a"), (32, "b"), (64, "y"), (128, "z"), (256, "minus"), (4096, "plus")):
            with self.subTest(name=name):
                self.assertEqual(decode(b"\x23\x08" + varint(neutral ^ bit)), {name})
        self.assertEqual(decode(b"\x23\x08" + varint(neutral)), set())

    def test_play_shift_field_is_six(self):
        self.assertEqual(decode(bytes.fromhex("07 08 00 10 01 18 01 20 01 28 01 30 00 38 01")), {"plus"})
        self.assertEqual(decode(bytes.fromhex("07 08 01 10 01 18 01 20 01 28 01 30 00 38 01")), {"minus"})

    def test_unknown_and_idle_are_not_button_frames(self):
        for data in (b"", b"\x15", b"RideOn\x02\x03", b"\xff\x05"):
            self.assertIsNone(decode(data))

    def test_truncation_and_invalid_fields_fail(self):
        for data in (b"\x08\x80", b"\x12\x05\x00", b"\x00", b"\x0f", b"\x08" + b"\xff" * 11):
            with self.subTest(data=data), self.assertRaises(ValueError):
                fields(data)

    def test_unknown_length_field_skipped(self):
        self.assertEqual(fields(bytes.fromhex("12 02 ff ff 08 01")), {1: 1})


if __name__ == "__main__":
    unittest.main()
