"""`python -m claude_free [args...]` entry point."""

from __future__ import annotations

import sys

from claude_free.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
