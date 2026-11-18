# Acknowledgments

ClickToWhoosh is an olli.works project by Oliver Granlund. The project MIT license applies to its original code and artwork. Dependencies and bundled assets retain their respective licenses and copyright notices.

## Protocol references

- [OpenBikeControl / BikeControl](https://github.com/OpenBikeControl/bikecontrol): inspiration, public controller identities, protocol descriptions and MyWhoosh mappings. The Windows implementation is independently written. No BikeControl application source, contour artwork, private `prop` implementation or release binaries are redistributed here. Its license does not become MIT through this project's license.
- [OpenBikeControl protocol specification](https://github.com/OpenBikeControl/openbikecontrol-protocol): the open, MIT-licensed app-control protocol used by the independently written experimental network transport. Details are documented in [the architecture decision](docs/OPENBIKECONTROL.md).
- [orsic/ftms_trainer](https://github.com/orsic/ftms_trainer/blob/main/trainer/click.py): reference for plain RideOn startup and right-controller keep-alive behavior.
- [ZwiftBoard](https://github.com/thomaschampagne/zwiftboard), copyright 2026 Thomas Champagne, MIT: informed the optional Zwift server-signed challenge exchange, held-key reference counting, fresh-advertisement reconnect gate and ride automation. These features are adapted to this project's Python/React architecture. Its full [MIT notice](windows/assets/notices/zwiftboard-LICENSE.txt) is retained and embedded in the executable.

Downloaded investigation material under the ignored `reference/` directory is not part of the source release or app package.

## Runtime and interface

Python, Bleak, Zeroconf, ifaddr, pywebview, pythonnet and their dependencies power the desktop runtime. React, React DOM, Radix UI, Lucide, clsx and tailwind-merge power the interface. Tailwind CSS, Vite, PyInstaller and their dependencies support the build. Their own license texts apply; installed package metadata and the npm lockfile identify the versions used. The build collects available installed-package notices into `legal/THIRD_PARTY_LICENSES.txt` in the ZIP and embeds the same legal directory in the executable.

The current Windows runtime uses Microsoft Edge WebView2 and .NET Framework, subject to Microsoft's terms. These are platform prerequisites, not software relicensed by this project.

Urbanist and DM Mono fonts are distributed under the SIL Open Font License. Full font notices are retained in [windows/assets/fonts](windows/assets/fonts) and bundled with app assets.

Click v2 illustrations are original SVG artwork. Zwift's product photography was used as a visual reference and is not bundled. The README uses a cycling emoji rendered by the reader's platform; no emoji image asset is bundled.

Zwift and MyWhoosh names identify compatibility. No affiliation or endorsement is claimed.
