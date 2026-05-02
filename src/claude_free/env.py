"""Read and write KEY=VALUE entries in the free-claude-code .env file."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


def env_path() -> Path:
    """Default location of the free-claude-code .env file."""
    return Path.home() / "free-claude-code" / ".env"


def read_env_key(path: Path, key: str) -> Optional[str]:
    """Return the (unquoted, comment-stripped) value of `key` in `path`, or None."""
    if not path.exists():
        return None
    pat = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if not m:
            continue
        v = m.group(1)
        v = v.split("#", 1)[0].strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        return v
    return None


def write_env_key(path: Path, key: str, value: str) -> None:
    """In-place set `key="value"` in `path`. Creates the file if missing."""
    line = f'{key}="{value}"'
    if not path.exists():
        path.write_text(line + "\n", encoding="utf-8")
        return
    txt = path.read_text(encoding="utf-8")
    pat = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=.*$")
    if pat.search(txt):
        txt = pat.sub(line, txt)
    else:
        if not txt.endswith("\n"):
            txt += "\n"
        txt += line + "\n"
    path.write_text(txt, encoding="utf-8")


def resolve_api_key() -> Optional[str]:
    """Look up the NVIDIA key from env vars, then the .env file."""
    for var in ("NVIDIA_NIM_API_KEY", "NVIDIA_API_KEY"):
        v = os.environ.get(var)
        if v:
            return v
    return read_env_key(env_path(), "NVIDIA_NIM_API_KEY")
