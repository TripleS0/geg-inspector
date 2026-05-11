"""Runtime path helpers for source, packaged backend and desktop shell runs."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    """Return the source tree root when running from Python sources."""
    return Path(__file__).resolve().parents[2]


def app_base_dir() -> Path:
    """Return the writable deployment directory.

    PyInstaller's ``_MEIPASS`` points to a temporary extraction directory, so it
    must not be used for persistent data. In frozen mode the executable folder
    is the stable base directory; in source mode the repository root is used.
    """
    override = os.environ.get("DATAFUSIONX_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return project_root()


def data_dir() -> Path:
    """Return the local data directory, creating it if needed."""
    path = app_base_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    """Return the local logs directory, creating it if needed."""
    path = app_base_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir() -> Path:
    """Return the local exports directory, creating it if needed."""
    path = app_base_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir() -> Path:
    """Return the local upload staging directory, creating it if needed."""
    path = data_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> Path:
    """Return the default SQLite database path."""
    override = os.environ.get("DATAFUSIONX_DB_PATH")
    if override:
        path = Path(override).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return data_dir() / "datafusionx.sqlite3"
