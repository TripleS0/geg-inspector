"""Application bootstrap helpers."""

from __future__ import annotations

from app.services.integration.common.bootstrap import run_bootstrap
from app.services.shared.db.sqlite_client import SqliteClient


def bootstrap_database(client: SqliteClient | None = None) -> SqliteClient:
    """Ensure the local database exists and has the current schema."""
    db_client = client or SqliteClient()
    run_bootstrap(db_client)
    return db_client
