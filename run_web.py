"""Offline launcher: python run_web.py  (opens a local browser page)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIBS = ROOT / "vendor" / "libs"
if LIBS.is_dir():
    sys.path.insert(0, str(LIBS))
sys.path.insert(0, str(ROOT))

from mdmaker.web import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
