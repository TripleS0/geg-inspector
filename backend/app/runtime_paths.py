"""Runtime path helpers for dev runs and Docker deployment."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the source tree root when running from Python sources."""
    return Path(__file__).resolve().parents[2]


def app_base_dir() -> Path:
    """Return the writable deployment directory.

    Uses ``GEG_INSPECTOR_HOME`` when set (Docker / custom runtime); otherwise the
    repository root in development. ``DATAFUSIONX_HOME`` is kept as a backward-compatible alias.
    """
    override = os.environ.get("GEG_INSPECTOR_HOME") or os.environ.get("DATAFUSIONX_HOME")
    if override:
        return Path(override).expanduser().resolve()
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
    override = os.environ.get("GEG_INSPECTOR_DB_PATH") or os.environ.get("DATAFUSIONX_DB_PATH")
    if override:
        path = Path(override).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return data_dir() / "geg-inspector.sqlite3"
