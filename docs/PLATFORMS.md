# One source, multiple platforms

ClickToWhoosh should share its React interface, controller decoding, battery policy, settings schema and connection lifecycle across desktop platforms. Native integration belongs behind small platform adapters. `windows/desktop.py` now owns data directories, folder opening and optional Windows alerts; keyboard construction is platform-gated and pywebview selects its native backend.

## Current support

Windows x64 is the only packaged and ride-tested implementation. The shared Python/React code has a network-only path on macOS and Linux, with native CI tests; GUI/Bluetooth hardware acceptance and packaging remain outstanding. Mac, Linux and mobile releases do not exist yet.

[Bleak](https://bleak.readthedocs.io/en/latest/) supplies platform BLE backends. [pywebview](https://pywebview.flowrl.com/guide/installation.html) supplies native web windows on Windows, macOS and Linux. This makes a shared desktop codebase feasible; it does not make Windows API calls portable automatically.

## Port boundaries

| Concern | Windows today | macOS port | Linux port |
| --- | --- | --- | --- |
| Bluetooth | Bleak / WinRT | Bleak / CoreBluetooth, Bluetooth permission | Bleak / BlueZ and system permissions |
| UI window | WebView2 / pythonnet | WebKit native backend | GTK/WebKit or Qt backend |
| Keyboard fallback | Win32 foreground check and SendInput | Foreground-app check and Accessibility-approved event injection | Desktop/session-specific focus and input; Wayland differs from X11 |
| Local files | LOCALAPPDATA | Application Support | XDG state/config directories |
| Alerts / folder opening | Win32, winsound, os.startfile | Native notifications and file opener | Desktop notification and file opener |
| Packaging | PyInstaller EXE | Native Mac build, signing/notarization for distribution | Native Linux build, AppImage/deb dependencies |

The present lockfile includes Windows-specific dependencies; each platform needs resolved runtime dependencies and native build jobs. Cross-compiling a Windows `.exe` does not produce a Mac or Linux app.

## Recommended direction

1. Keep a shared controller engine and UI, separating platform services and output transports.
2. Validate the experimental OpenBikeControl mDNS/TCP connection before making it preferred for MyWhoosh. This removes the need for native key injection on that route; the app can still run on the same device as MyWhoosh.
3. Retain explicit keyboard fallback on platforms where it is implemented and tested.
4. Add native CI packaging and real-device acceptance tests per platform. Publish downloads only after those gates pass.

Mobile would require additional lifecycle, permissions, Bluetooth and packaging work. Do not infer mobile support from reuse of the web interface. Linux companion support also does not imply that MyWhoosh itself runs natively on Linux.

See the [OpenBikeControl decision](OPENBIKECONTROL.md) for transport details and acceptance criteria.

## Source-level network testing on macOS / Linux

After installing Python 3.11+ and Node.js 24, create a virtual environment and install `windows/requirements-shared.txt`. Generate the frontend assets with `npm ci` and `npm run build` in `windows/frontend`, then run `windows/app.py` with that environment’s Python. Linux additionally needs a supported pywebview GUI backend (GTK/WebKit or Qt) and its system libraries; consult pywebview’s installation guide. This is an unvalidated developer path, not a supported end-user install.

On these platforms the keyboard choice is unavailable. Start network pairing explicitly on first use. Settings use Application Support on macOS and XDG state storage on Linux. Battery banners remain available; sound/taskbar flashing is Windows-specific.
