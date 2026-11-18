"""Small native-service boundary for the shared desktop engine and UI."""
import os
from pathlib import Path
import subprocess
import sys


def data_directory():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ClickToWhoosh"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/ClickToWhoosh"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "clicktowhoosh"


def keyboard_available():
    return sys.platform == "win32"


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def battery_attention(window, sound):
    # Other platforms retain the in-app banner. Native sounds/taskbar effects
    # are optional Windows enhancements, never a dependency of the BLE engine.
    if sys.platform != "win32":
        return
    if sound:
        import winsound
        winsound.MessageBeep()
    if window:
        try:
            import ctypes
            from ctypes import wintypes
            class FlashInfo(ctypes.Structure):
                _fields_ = [("size", wintypes.UINT), ("hwnd", wintypes.HWND), ("flags", wintypes.DWORD),
                            ("count", wintypes.UINT), ("timeout", wintypes.DWORD)]
            info = FlashInfo(ctypes.sizeof(FlashInfo), window.native.Handle.ToInt64(), 3, 3, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception:
            pass
