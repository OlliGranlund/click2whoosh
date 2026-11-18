from pathlib import Path
import unittest
from unittest.mock import patch, Mock
import desktop
from keyboard import create_keyboard, UnavailableKeyboard


class DesktopTests(unittest.TestCase):
    def test_data_locations_follow_platform_conventions(self):
        home = Path("/home/rider")
        with patch("pathlib.Path.home", return_value=home), patch.dict("os.environ", {"LOCALAPPDATA": "/windows/state", "XDG_STATE_HOME": "/linux/state"}):
            for platform, expected in (("win32", "/windows/state/ClickToWhoosh"),
                                       ("darwin", "/home/rider/Library/Application Support/ClickToWhoosh"),
                                       ("linux", "/linux/state/clicktowhoosh")):
                with self.subTest(platform=platform), patch("sys.platform", platform):
                    self.assertEqual(desktop.data_directory(), Path(expected))

    def test_non_windows_network_runtime_does_not_initialize_win32_keyboard_or_alerts(self):
        for platform in ("darwin", "linux"):
            with self.subTest(platform=platform), patch("sys.platform", platform):
                self.assertFalse(desktop.keyboard_available())
                keyboard = create_keyboard()
                self.assertIsInstance(keyboard, UnavailableKeyboard)
                self.assertFalse(keyboard.target_active())
                with self.assertRaisesRegex(RuntimeError, "OpenBikeControl"):
                    keyboard.tap("K")
                desktop.battery_attention(Mock(), True)
