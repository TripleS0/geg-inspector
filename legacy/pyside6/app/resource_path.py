"""Resource path helper for source run and PyInstaller onefile."""

from __future__ import annotations

import sys
from pathlib import Path


def get_resource_path(*parts: str) -> Path:
    """Return absolute resource path in dev and bundled runtime."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        return base.joinpath(*parts)
    return Path(__file__).resolve().parents[1].joinpath(*parts)

