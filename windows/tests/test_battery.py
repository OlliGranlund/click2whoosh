import unittest
from battery import BatteryAlerts, standard_level, zwift_level


class BatteryTests(unittest.TestCase):
    def test_standard_percent_and_zero_are_valid_but_unknown_is_not_zero(self):
        self.assertEqual(standard_level(b"\x00"), 0)
        self.assertEqual(standard_level(b"\x64"), 100)
        for raw in (b"", b"\xff", b"\x65", b"\x20\x00"):
            self.assertIsNone(standard_level(raw))

    def test_zwift_percent_status_and_charging_only(self):
        self.assertEqual(zwift_level(bytes.fromhex("19 10 12")), 18)
        self.assertEqual(zwift_level(bytes.fromhex("1a 08 00 10 00")), 0)
        self.assertIsNone(zwift_level(bytes.fromhex("19 08 01")))
        self.assertIsNone(zwift_level(bytes.fromhex("19 10 7f")))
        self.assertIsNone(zwift_level(b"\x23\x08\x00"))
        with self.assertRaises(ValueError):
            zwift_level(bytes.fromhex("19 10 80"))

    def test_alerts_do_not_repeat_at_each_poll_or_reconnect(self):
        alerts = BatteryAlerts()
        self.assertEqual(alerts.update("right", 20), "low")
        for level in (20, 19, 18, 21, 20):
            self.assertIsNone(alerts.update("right", level))
        self.assertEqual(alerts.update("right", 10), "critical")
        self.assertIsNone(alerts.update("right", 9))
        self.assertIsNone(alerts.update("right", 12))
        self.assertEqual(alerts.update("left", 8), "critical")

    def test_recovery_rearms_alerts_with_hysteresis(self):
        alerts = BatteryAlerts()
        self.assertEqual(alerts.update("right", 8), "critical")
        self.assertIsNone(alerts.update("right", 14))
        self.assertIsNone(alerts.update("right", 9))
        self.assertIsNone(alerts.update("right", 15))
        self.assertEqual(alerts.update("right", 10), "critical")
        self.assertIsNone(alerts.update("right", 25))
        self.assertEqual(alerts.update("right", 20), "low")
