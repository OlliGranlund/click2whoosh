# Development

[ClickToWhoosh](../README.md) is a free olli.works project. The current maintained implementation is under `windows/`; the shared network engine and UI are being validated across desktop platforms. Packaged releases currently target Windows.

## Build Windows

Install 64-bit Python 3.11+ and Node.js 24. From the repository root in PowerShell:

```powershell
./windows/build.ps1
```

The script installs locked frontend and Python dependencies, runs frontend and Python tests, builds static interface assets, generates the icon, and packages the portable app. Outputs:

- `windows/dist/ClickToWhoosh.exe`
- `windows/dist/ClickToWhoosh-Windows-x64.zip`
- `windows/dist/SHA256SUMS.txt`

Builds are unsigned. The runtime requires Edge WebView2 and .NET Framework 4.8. Check downloaded executables against the checksum from the same release:

```powershell
Get-FileHash ./ClickToWhoosh.exe -Algorithm SHA256
```

## Run source

After a build, run:

```powershell
./windows/.venv/Scripts/python windows/app.py
```

The app loads generated assets from `windows/assets/web/`. After editing React source, regenerate only those assets with `npm run build` in `windows/frontend/`. This is separate from rebuilding the executable.

## Device-free checks

```powershell
Push-Location windows
./.venv/Scripts/python -m unittest discover -s tests -v
Pop-Location
Push-Location windows/frontend
npm test
Pop-Location
./windows/.venv/Scripts/python windows/app.py --ui-smoke windows/ui-smoke.json
./windows/.venv/Scripts/python windows/app.py --transport-smoke windows/ui-smoke-transport.json
```

UI smoke mode disables device commands and keyboard output, loads the actual WebView interface, and verifies its tabs and bridge. Transport smoke imports the packaged Zeroconf stack and exercises a TCP button transition on loopback, without mDNS advertisement or Bluetooth. Tests cover captured Click packets, malformed data, duplicate filtering, foreground restrictions, battery alerts, recovery cancellation, low-battery cutoff and short-tap visual feedback. Simulations do not establish hardware compatibility or real power consumption. Use the [release acceptance checklist](ACCEPTANCE.md) for live MyWhoosh validation.

## Source map

| Path | Responsibility |
| --- | --- |
| `windows/app.py` | BLE discovery, sessions, reconnect, event routing |
| `windows/protocol.py` | Zwift controller message decoding |
| `windows/keyboard.py` | Windows foreground detection and scan-code output |
| `windows/gestures.py` | Tap, hold and exclusive long-press state machine |
| `windows/zwift_unlock.py` | Optional Zwift challenge exchange and DPAPI session storage |
| `windows/openbikecontrol.py` | Shared experimental mDNS/TCP transport and action routing |
| `windows/desktop.py` | Platform data paths, folder opening and optional native alerts |
| `windows/battery.py` | Battery decoding and alert thresholds |
| `windows/web_ui.py` | Desktop window, settings and validated UI bridge |
| `windows/frontend/src/` | Shared React interface and controller SVGs |
| `windows/tests/` | Backend and captured-packet regression tests |

## Releases

The **Build and release** workflow (`.github/workflows/windows.yml`) builds on `master` pushes, `v*` tags, pull requests and manual dispatch. A passing Windows build on `master` updates the rolling **preview** prerelease. Version tags such as **v2.0.0-beta.1** identify fixed source milestones shared by every platform. Published versioned assets are preserved on reruns, and tags containing a hyphen are marked prerelease. Windows x64 is currently the only packaged target. Shared runtime checks run independently on macOS and Linux. Publishing requires the Windows tests, package and smoke checks to pass, and only the separate publishing job has write permission. Pull requests do not publish.

The old platform-named `windows-latest` rolling release is retired after the new preview assets upload successfully. Existing links containing that old tag must be updated. Use the README download link for the moving preview, or a versioned release for a reproducible bug report. Publishing a milestone is explicit: tag the intended commit with `vMAJOR.MINOR.PATCH[-beta.N]` and push that tag. A rebuild alone does not create a new app version.

Artifact bundles include the executable, setup documentation and checksums. Repository visibility determines who can download releases. A GitHub release and a supported hardware configuration are separate claims: document testing evidence and limitations honestly.

## Contributions

Use the project MIT license for original contributions. Retain dependency notices and do not copy BikeControl's restricted application code into this project. Report the controller model, firmware, OS, Bluetooth adapter, connection method and reproduction steps with issues. Remove device addresses and personal paths from shared logs.
