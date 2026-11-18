"""Collect installed dependency notices into the assets shipped with the app."""
from importlib import metadata
import json
from pathlib import Path
import sys


def license_name(path):
    return path.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE")) and path.suffix.lower() in ("", ".txt", ".md", ".rst")


def collect():
    root = Path(__file__).resolve().parent
    sections = ["ClickToWhoosh — olli.works\nThird-party license notices\n\n"
                "These notices describe installed build/runtime dependencies. Inclusion does not relicense them under the project MIT license.\n"]
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    for notice in sorted((root / "assets/notices").glob("*.txt")):
        sections.append(f"Adapted component notice: {notice.name}\n" + notice.read_text(encoding="utf-8"))
    if python_license.exists():
        sections.append("Python runtime\n" + python_license.read_text(encoding="utf-8", errors="replace"))
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get("Name", "").lower()):
        name = dist.metadata.get("Name", "Unknown")
        texts = []
        for file in dist.files or []:
            if license_name(Path(str(file))):
                path = Path(dist.locate_file(file))
                if path.is_file():
                    texts.append(f"{file}\n{path.read_text(encoding='utf-8', errors='replace')}")
        label = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See upstream package metadata"
        sections.append(f"Python package: {name} {dist.version}\nLicense metadata: {label}\n" + "\n\n".join(texts))
    frontend = root / "frontend"
    packages = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    for relative, package in sorted(packages.items()):
        if not relative:
            continue
        directory = frontend / relative
        if not directory.exists():  # platform-specific optional dependency
            continue
        texts = [f"{p.name}\n{p.read_text(encoding='utf-8', errors='replace')}"
                 for p in sorted(directory.iterdir()) if p.is_file() and license_name(p)]
        sections.append(f"JavaScript package: {relative} {package.get('version', '')}\n"
                        f"License metadata: {package.get('license', 'See upstream package metadata')}\n" + "\n\n".join(texts))
    target = root / "assets/legal"
    target.mkdir(parents=True, exist_ok=True)
    (target / "LICENSE.txt").write_text((root.parent / "LICENSE").read_text(encoding="utf-8"), encoding="utf-8")
    (target / "THIRD_PARTY_LICENSES.txt").write_text("\n\n" + ("\n\n" + "=" * 72 + "\n\n").join(sections), encoding="utf-8")
    print(f"Collected {len(sections)} notice sections in {target}")


if __name__ == "__main__":
    collect()
