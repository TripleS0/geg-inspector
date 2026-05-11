"""Bootstrap SQLite tables for local integration storage."""

from __future__ import annotations

from pathlib import Path

from app.services.shared.db.sqlite_client import SqliteClient


def load_bootstrap_sql() -> str:
    """Load sqlite bootstrap SQL from resources."""
    sql_path = Path(__file__).resolve().parents[3] / "resources" / "sql" / "bootstrap_sqlite.sql"
    return sql_path.read_text(encoding="utf-8")


def run_bootstrap(client: SqliteClient) -> None:
    """Run bootstrap SQL statements sequentially."""
    sql_text = load_bootstrap_sql()
    statements = [statement.strip() for statement in sql_text.split(";") if statement.strip()]
    for statement in statements:
        client.execute(f"{statement};")
