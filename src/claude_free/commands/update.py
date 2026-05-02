"""`claude-free update` — refresh the audit script from GitHub.

Note: in the bundled-deployment model, this command is implemented in the
shell launcher (it has to overwrite its own file, which is awkward from
inside Python). This module exists so `python -m claude_free update` from
a development checkout still does something sensible — it just prints
the curl/Invoke-WebRequest one-liners.
"""

from __future__ import annotations

URL = "https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py"


def run_update(_args, _provider) -> int:
    print(
        "claude-free update -- in development mode, run one of these to refresh "
        "the deployed single-file artifact:\n\n"
        f"  Linux/macOS: curl -fsSL {URL} -o ~/.local/bin/claude-free-audit.py\n"
        f"  Windows:     iwr {URL} -OutFile $HOME\\.local\\bin\\claude-free-audit.py\n\n"
        "Or, in a development checkout, regenerate it locally:\n\n"
        "  python tools/build.py\n"
    )
    return 0
