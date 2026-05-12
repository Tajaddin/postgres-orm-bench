"""Top-level bench script — calls the CLI module directly."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orm_bench.cli import main


if __name__ == "__main__":
    main()
