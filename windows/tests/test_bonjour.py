import unittest
from bonjour import encode_txt


class TxtTests(unittest.TestCase):
    def test_wire_lengths_use_utf8_bytes(self):
        self.assertEqual(encode_txt({"version": "1", "name": "é"}),
                         b"\x09version=1\x07name=\xc3\xa9")

    def test_oversized_txt_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_txt({"name": "x" * 251})
