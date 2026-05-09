"""SQLite client utilities for standalone local deployment."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

# raw 层系统列（预览时默认不向最终用户展示）
_RAW_INTERNAL_COLUMNS = frozenset(
    {
        "raw_id",
        "import_batch_id",
        "bank_name",
        "source_type",
        "source_file_id",
        "source_sheet",
        "template_fingerprint",
        "row_no",
        "raw_payload",
    }
)


class SqliteClient:
    """Thin SQLite helper with transaction context manager."""

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize sqlite database path."""
        default_path = Path(__file__).resolve().parents[4] / "datafusionx.sqlite3"
        self._db_path = Path(db_path) if db_path else default_path

    @property
    def db_path(self) -> Path:
        """Resolved SQLite file path (for UI display)."""
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        """Create sqlite connection."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self):
        """Provide cursor in transaction, commit on success."""
        conn = self._connect()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        """Execute one SQL statement."""
        with self.transaction() as cursor:
            cursor.execute(sql, params or ())

    def executemany(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
        """Execute SQL for multiple rows."""
        with self.transaction() as cursor:
            cursor.executemany(sql, list(rows))

    def query_all(self, sql: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        """Query all rows and return tuples."""
        with self.transaction() as cursor:
            cursor.execute(sql, params or ())
            data = cursor.fetchall()
            return [tuple(row) for row in data]

    @staticmethod
    def quote_ident(ident: str) -> str:
        """Quote SQLite identifier (table/column) safely."""
        return '"' + ident.replace('"', '""') + '"'

    def list_user_tables(self) -> list[str]:
        """List non-internal tables (excludes sqlite_*)."""
        rows = self.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' ORDER BY name;"
        )
        return [str(row[0]) for row in rows]

    def list_user_upload_tables(self) -> list[str]:
        """仅用户导入产生的数据表：登记在 meta_schema_registry 中的 raw 表名（不展示 meta/std 等）。"""
        rows = self.query_all(
            """
            SELECT DISTINCT raw_table_name
            FROM meta_schema_registry
            ORDER BY raw_table_name;
            """
        )
        return [str(row[0]) for row in rows]

    def count_table_rows(self, table: str) -> int:
        """Return row count for a user-upload data table (must be registered in meta_schema_registry)."""
        allowed = set(self.list_user_upload_tables())
        if table not in allowed:
            raise ValueError("只能统计您导入的数据表，或该表未在库中登记。")
        sql = f"SELECT COUNT(*) FROM {self.quote_ident(table)};"
        rows = self.query_all(sql)
        return int(rows[0][0])

    def fetch_table_preview(
        self,
        table: str,
        *,
        limit: int = 200,
        offset: int = 0,
        source_columns_only: bool = True,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Fetch up to ``limit`` rows with column names; table must exist in sqlite_master."""
        cols, _rowids, rows = self.fetch_table_preview_with_rowids(
            table, limit=limit, offset=offset, source_columns_only=source_columns_only
        )
        return cols, rows

    def _preview_column_names(self, table: str, *, source_columns_only: bool) -> list[str]:
        """列顺序与建表一致；默认仅 src_ 业务列，无 src_ 时退化为排除系统列后的其余列。"""
        info = self.query_all(f"PRAGMA table_info({self.quote_ident(table)});")
        ordered = [str(row[1]) for row in info]
        if not source_columns_only:
            return ordered
        src_cols = [n for n in ordered if n.startswith("src_")]
        if src_cols:
            return src_cols
        return [n for n in ordered if n not in _RAW_INTERNAL_COLUMNS]

    def fetch_table_preview_with_rowids(
        self,
        table: str,
        *,
        limit: int = 200,
        offset: int = 0,
        source_columns_only: bool = True,
    ) -> tuple[list[str], list[int], list[tuple[Any, ...]]]:
        """预览行；默认只查用户导入的源字段列（src_*），不含 raw_payload 等系统列。rowid 仍用于删除。"""
        allowed = set(self.list_user_upload_tables())
        if table not in allowed:
            raise ValueError("只能预览您导入的数据表，或该表未在库中登记。")
        lim = max(1, min(int(limit), 5000))
        off = max(0, int(offset))
        colnames = self._preview_column_names(table, source_columns_only=source_columns_only)
        if not colnames:
            raise ValueError("该表没有可展示的列。")
        quoted = ", ".join(self.quote_ident(name) for name in colnames)
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT rowid AS __dfx_rid__, {quoted} FROM {self.quote_ident(table)} "
                f"LIMIT ? OFFSET ?;",
                (lim, off),
            )
            raw_rows = [tuple(row) for row in cursor.fetchall()]
            rowids = [int(r[0]) for r in raw_rows]
            data_rows = [r[1:] for r in raw_rows]
            return colnames, rowids, data_rows
        finally:
            cursor.close()
            conn.close()

    def delete_rows_by_rowid(self, table: str, rowids: list[int]) -> int:
        """Delete rows by SQLite rowid; returns deleted row count."""
        allowed = set(self.list_user_upload_tables())
        if table not in allowed:
            raise ValueError("只能删除您导入的数据表中的行，或该表未在库中登记。")
        if not rowids:
            return 0
        ids = sorted({int(r) for r in rowids})
        if len(ids) > 5000:
            raise ValueError("单次删除行数不能超过 5000，请分批操作")
        placeholders = ",".join("?" * len(ids))
        sql = f"DELETE FROM {self.quote_ident(table)} WHERE rowid IN ({placeholders});"
        with self.transaction() as cursor:
            cursor.execute(sql, tuple(ids))
            return int(cursor.rowcount or 0)

    def drop_user_upload_table(self, table: str) -> None:
        """删除用户导入的数据表（DROP TABLE），并清理与之关联的登记信息（不含 std_bank_txn 历史行）。"""
        allowed = set(self.list_user_upload_tables())
        if table not in allowed:
            raise ValueError("只能删除您导入的数据表，或该表未在库中登记。")

        fingerprints = self.query_all(
            "SELECT template_fingerprint FROM meta_schema_registry WHERE raw_table_name=?;",
            (table,),
        )
        fp_list = [str(row[0]) for row in fingerprints]

        with self.transaction() as cursor:
            for fp in fp_list:
                cursor.execute(
                    "DELETE FROM meta_field_mapping WHERE template_fingerprint=?;",
                    (fp,),
                )
            cursor.execute("DELETE FROM meta_bank_sheets WHERE raw_table_name=?;", (table,))
            cursor.execute("DELETE FROM meta_schema_registry WHERE raw_table_name=?;", (table,))
            cursor.execute(f"DROP TABLE {self.quote_ident(table)};")
