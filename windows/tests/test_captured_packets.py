import json
from pathlib import Path
import unittest
from battery import zwift_level
from protocol import decode


class CapturedPacketTests(unittest.TestCase):
    def test_physical_click_v2_buttons_release_and_battery(self):
        capture = json.loads((Path(__file__).parent / "fixtures" / "click-v2.json").read_text())
        for sample in capture["buttons"]:
            with self.subTest(frame=sample["hex"]):
                self.assertEqual(decode(bytes.fromhex(sample["hex"])), set(sample["pressed"]))
        self.assertEqual(zwift_level(bytes.fromhex(capture["battery"]["hex"])), capture["battery"]["percent"])
