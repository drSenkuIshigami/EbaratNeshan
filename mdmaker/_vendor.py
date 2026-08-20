"""Prefer packages bundled in vendor/libs so conversion works fully offline."""

from __future__ import annotations

import sys
from pathlib import Path


def setup() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    libs = root / "vendor" / "libs"
    if libs.is_dir():
        path = str(libs)
        if path not in sys.path:
            sys.path.insert(0, path)
        return libs
    return None
