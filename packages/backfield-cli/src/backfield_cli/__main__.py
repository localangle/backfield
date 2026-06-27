"""Support ``python -m backfield_cli`` (used by scripts/backfield)."""

from __future__ import annotations

import sys

from backfield_cli.main import main

if __name__ == "__main__":
    sys.exit(main())
