"""ANSI colour helpers. No-op when stdout isn't a TTY or NO_COLOR is set."""

from __future__ import annotations

import os
import sys


def colors() -> dict[str, str]:
    """Return a dict of ANSI escape codes, or empty strings if colour is off."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return {k: "" for k in ("B", "D", "G", "Y", "R", "N")}
    return {
        "B": "\033[1m",   # bold
        "D": "\033[2m",   # dim
        "G": "\033[0;32m",  # green
        "Y": "\033[0;33m",  # yellow
        "R": "\033[0;31m",  # red
        "N": "\033[0m",   # reset
    }
