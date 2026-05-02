"""Re-inject the canonical launcher body into all three install scripts.

`src/launcher/posix.sh` is the source of truth for the bash launcher used by
`install-claude-free.sh` (Linux) and `install-claude-free-macos.sh` (macOS).
`src/launcher/windows.ps1` is the source of truth for the PowerShell launcher
used by `install-claude-free-windows.ps1`.

Each installer has the launcher body as a heredoc / here-string between known
markers. This script finds those regions and rewrites them with the canonical
source, so editing the launcher only happens in `src/launcher/`.

Run: `python tools/build_installers.py [--check]`

  --check    exit 1 if any installer is stale (CI use)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_POSIX = ROOT / "src" / "launcher" / "posix.sh"
LAUNCHER_WINDOWS = ROOT / "src" / "launcher" / "windows.ps1"

# Each entry: (installer file, launcher source, opening marker, closing marker)
TARGETS = [
    (
        ROOT / "install-claude-free.sh",
        LAUNCHER_POSIX,
        "<<'CLAUDE_FREE_EOF'\n",
        "\nCLAUDE_FREE_EOF\n",
    ),
    (
        ROOT / "install-claude-free-macos.sh",
        LAUNCHER_POSIX,
        "<<'CLAUDE_FREE_EOF'\n",
        "\nCLAUDE_FREE_EOF\n",
    ),
    (
        ROOT / "install-claude-free-windows.ps1",
        LAUNCHER_WINDOWS,
        "$launcher = @'\n",
        "\n'@\n",
    ),
]


def _splice(installer_text: str, opener: str, closer: str, body: str) -> str:
    """Replace the region between `opener` and `closer` with `body`."""
    try:
        start_idx = installer_text.index(opener) + len(opener)
    except ValueError:
        raise SystemExit(f"opener {opener!r} not found in installer")
    try:
        end_idx = installer_text.index(closer, start_idx)
    except ValueError:
        raise SystemExit(f"closer {closer!r} not found after opener")
    return installer_text[:start_idx] + body + installer_text[end_idx:]


def render(installer_path: Path, launcher_source_path: Path,
           opener: str, closer: str) -> str:
    installer_text = installer_path.read_text(encoding="utf-8")
    launcher_body = launcher_source_path.read_text(encoding="utf-8").rstrip("\n")
    return _splice(installer_text, opener, closer, launcher_body)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="exit 1 if any installer is stale")
    args = p.parse_args()

    drift = []
    for installer_path, launcher_path, opener, closer in TARGETS:
        rendered = render(installer_path, launcher_path, opener, closer)
        existing = installer_path.read_text(encoding="utf-8")
        if existing == rendered:
            print(f"  {installer_path.name}: up to date")
            continue
        if args.check:
            drift.append(installer_path.name)
            print(f"  {installer_path.name}: STALE — re-run `python tools/build_installers.py`")
        else:
            installer_path.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"  {installer_path.name}: re-rendered ({len(rendered)} bytes)")

    if drift:
        print(f"\n{len(drift)} installer(s) stale: {', '.join(drift)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
