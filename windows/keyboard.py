"""Windows scan-code input, restricted to the foreground target process."""
import ctypes
from ctypes import wintypes
import time
import sys
import asyncio


class UnavailableKeyboard:
    def target_active(self):
        return False

    def tap(self, key):
        raise RuntimeError("Keyboard output is currently Windows-only. Choose OpenBikeControl network.")


def create_keyboard():
    return Keyboard() if sys.platform == "win32" else UnavailableKeyboard()

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


class Keyboard:
    def __init__(self):
        self._held = set()
        self._active = set()
        self._pulsing = set()
        self._tap_tasks = {}
        self._tap_locks = {}
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user.SendInput.restype = wintypes.UINT

    def target_active(self):
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(self.user.GetForegroundWindow(), ctypes.byref(pid))
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            return bool(self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))) and path.value.split("\\")[-1].lower().startswith("mywhoosh")
        finally:
            self.kernel.CloseHandle(handle)

    def send(self, key, up=False):
        vk = {"SPACE": 32, "ENTER": 13, "ESC": 27, "UP": 38, "DOWN": 40,
              "LEFT": 37, "RIGHT": 39}.get(key, ord(key) if len(key) == 1 else 0)
        if not vk:
            raise ValueError("Unsupported key: " + key)
        scan = self.user.MapVirtualKeyW(vk, 0)
        flags = 8 | (2 if up else 0) | (1 if key in ("UP", "DOWN", "LEFT", "RIGHT") else 0)
        event = INPUT(type=1, u=INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))
        if self.user.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise OSError("Windows blocked SendInput. Check whether MyWhoosh runs as administrator.")

    def tap(self, key):
        self.send(key)
        try:
            time.sleep(0.06)
        finally:
            self.send(key, up=True)

    def hold(self, key, down):
        if down:
            if key not in self._active:
                self.send(key)
                self._active.add(key)
            self._held.add(key)
        else:
            self._held.discard(key)
            if key not in self._pulsing and key in self._active:
                self.send(key, up=True)
                self._active.discard(key)

    def queue_tap(self, key, allowed, owner=None):
        async def pulse():
            async with self._tap_locks.setdefault(key, asyncio.Lock()):
                if not allowed() or not self.target_active():
                    return
                self._pulsing.add(key)
                try:
                    self.send(key)
                    self._active.add(key)
                    await asyncio.sleep(.04)
                finally:
                    self._pulsing.discard(key)
                    if key not in self._held and key in self._active:
                        self.send(key, up=True)
                        self._active.discard(key)
        task = asyncio.create_task(pulse())
        self._tap_tasks[task] = owner
        def finished(completed):
            self._tap_tasks.pop(completed, None)
            if not completed.cancelled():
                error = completed.exception()
                if error:
                    import logging
                    logging.warning("Keyboard output failed: %s", error)
        task.add_done_callback(finished)

    async def clear(self):
        tasks = list(self._tap_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._held.clear()
        for key in list(self._active):
            self.send(key, up=True)
            self._active.discard(key)

    async def clear_device(self, owner):
        tasks = [task for task, device in self._tap_tasks.items() if device == owner]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def target_windows(self):
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        matches = []
        def inspect(hwnd, _):
            if not self.user.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = self.kernel.OpenProcess(0x1000, False, pid.value)
            if handle:
                try:
                    size = wintypes.DWORD(32768)
                    path = ctypes.create_unicode_buffer(size.value)
                    if self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) and path.value.split("\\")[-1].lower().startswith("mywhoosh"):
                        matches.append(hwnd)
                finally:
                    self.kernel.CloseHandle(handle)
            return True
        self.user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self.user.EnumWindows(callback_type(inspect), 0)
        return matches

    def focus_target(self):
        if self.target_active():
            return True
        matches = self.target_windows()
        if matches:
            self.user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user.SetForegroundWindow.argtypes = [wintypes.HWND]
            self.user.ShowWindow(matches[0], 9)
            self.user.SetForegroundWindow(matches[0])
        return self.target_active()
