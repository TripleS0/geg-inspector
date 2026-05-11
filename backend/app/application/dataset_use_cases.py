"""Dataset, batch and table preview use cases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from app.application.bootstrap import bootstrap_database
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass(frozen=True)
class BatchInfo:
    """A persisted import batch."""

    import_batch_id: str
    source_type: str
    file_count: int
    imported_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TablePreview:
    """Preview data for one user-upload table."""

    table_name: str
    columns: list[str]
    rowids: list[int]
    rows: list[list[Any]]
    total_rows: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DatasetUseCase:
    """Read and manage persisted datasets without Qt dialogs."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def list_batches(self, source_type: str | None = None, limit: int = 80) -> list[BatchInfo]:
        """Return recent batches from import metadata."""
        params: list[object] = []
        where = ""
        if source_type:
            where = "WHERE source_type=?"
            params.append(source_type)
        params.append(max(1, min(int(limit), 500)))
        rows = self._client.query_all(
            f"""
            SELECT import_batch_id, source_type, COUNT(*), MAX(imported_at)
            FROM meta_bank_files
            {where}
            GROUP BY import_batch_id, source_type
            ORDER BY MAX(imported_at) DESC
            LIMIT ?;
            """,
            tuple(params),
        )
        return [
            BatchInfo(str(row[0]), str(row[1]), int(row[2]), str(row[3] or ""))
            for row in rows
        ]

    def list_enterprise_batches(self, limit: int = 40) -> list[BatchInfo]:
        """Return recent enterprise-profile import batches."""
        rows = self._client.query_all(
            """
            SELECT import_batch_id, COUNT(*), MAX(imported_at)
            FROM std_enterprise_profile
            GROUP BY import_batch_id
            ORDER BY MAX(imported_at) DESC
            LIMIT ?;
            """,
            (max(1, min(int(limit), 500)),),
        )
        return [
            BatchInfo(str(row[0]), "enterprise", int(row[1]), str(row[2] or ""))
            for row in rows
        ]

    def list_batches_merged(self, limit: int = 80) -> list[BatchInfo]:
        """银行/商务网（meta_bank_files）与工商（std_enterprise_profile）合并，按导入时间倒序。"""
        lim = max(1, min(int(limit), 500))
        meta = self.list_batches(None, limit=500)
        ent = self.list_enterprise_batches(limit=500)
        merged = list(meta) + list(ent)
        merged.sort(key=lambda b: b.imported_at or "", reverse=True)
        return merged[:lim]

    def resolve_batch_kind(self, import_batch_id: str) -> Optional[str]:
        """识别批次类型：bank / commercial / enterprise，不存在则 None。"""
        bid = (import_batch_id or "").strip()
        if not bid:
            return None
        rows = self._client.query_all(
            "SELECT source_type FROM meta_bank_files WHERE import_batch_id=? LIMIT 1;",
            (bid,),
        )
        if rows:
            return str(rows[0][0])
        rows = self._client.query_all(
            "SELECT 1 FROM std_enterprise_profile WHERE import_batch_id=? LIMIT 1;",
            (bid,),
        )
        if rows:
            return "enterprise"
        return None

    def delete_import_batch(self, import_batch_id: str) -> dict[str, Any]:
        """删除整批导入数据（含 raw/std 行、元数据；商务网另删匹配与风险结果；工商另删关联匹配行）。"""
        bid = (import_batch_id or "").strip()
        if not bid:
            raise ValueError("批次编号不能为空")
        kind = self.resolve_batch_kind(bid)
        if kind is None:
            raise ValueError("未找到该批次")

        with self._client.transaction() as cursor:
            if kind in ("bank", "commercial"):
                cursor.execute(
                    "SELECT file_id FROM meta_bank_files WHERE import_batch_id=?;",
                    (bid,),
                )
                file_ids = [int(row[0]) for row in cursor.fetchall()]
                raw_tables: list[str] = []
                if file_ids:
                    ph = ",".join("?" * len(file_ids))
                    cursor.execute(
                        f"SELECT DISTINCT raw_table_name FROM meta_bank_sheets WHERE file_id IN ({ph});",
                        tuple(file_ids),
                    )
                    raw_tables = [str(row[0]) for row in cursor.fetchall()]
                for tbl in raw_tables:
                    cursor.execute(
                        f"DELETE FROM {self._client.quote_ident(tbl)} WHERE import_batch_id=?;",
                        (bid,),
                    )
                if file_ids:
                    ph2 = ",".join("?" * len(file_ids))
                    cursor.execute(f"DELETE FROM meta_bank_sheets WHERE file_id IN ({ph2});", tuple(file_ids))
                cursor.execute("DELETE FROM meta_bank_files WHERE import_batch_id=?;", (bid,))
                cursor.execute("DELETE FROM meta_ingest_logs WHERE import_batch_id=?;", (bid,))
                cursor.execute("DELETE FROM std_bank_txn WHERE import_batch_id=?;", (bid,))
                cursor.execute("DELETE FROM std_bank_account WHERE import_batch_id=?;", (bid,))
                cursor.execute("DELETE FROM std_bank_account_conflict WHERE import_batch_id=?;", (bid,))
                if kind == "commercial":
                    cursor.execute("DELETE FROM rel_biz_enterprise_match WHERE import_batch_id=?;", (bid,))
                    cursor.execute("DELETE FROM ana_risk_event WHERE import_batch_id=?;", (bid,))
                    cursor.execute("DELETE FROM ana_risk_summary WHERE import_batch_id=?;", (bid,))
            else:
                cursor.execute(
                    """
                    DELETE FROM rel_biz_enterprise_match
                    WHERE enterprise_id IN (
                        SELECT enterprise_id FROM std_enterprise_profile WHERE import_batch_id=?
                    );
                    """,
                    (bid,),
                )
                cursor.execute("DELETE FROM std_enterprise_profile WHERE import_batch_id=?;", (bid,))

        return {"status": "ok", "import_batch_id": bid, "source_type": kind}

    def list_tables(self) -> list[str]:
        """Return user upload tables registered in metadata."""
        return self._client.list_user_upload_tables()

    def preview_table(
        self,
        table_name: str,
        *,
        limit: int = 200,
        offset: int = 0,
        source_columns_only: bool = True,
    ) -> TablePreview:
        """Return a safe preview of one registered upload table."""
        columns, rowids, rows = self._client.fetch_table_preview_with_rowids(
            table_name,
            limit=limit,
            offset=offset,
            source_columns_only=source_columns_only,
        )
        return TablePreview(
            table_name=table_name,
            columns=columns,
            rowids=rowids,
            rows=[list(row) for row in rows],
            total_rows=self._client.count_table_rows(table_name),
        )

    def delete_rows(self, table_name: str, rowids: list[int]) -> dict[str, int]:
        """Delete selected rows from a registered upload table."""
        return {"deleted": self._client.delete_rows_by_rowid(table_name, rowids)}

    def drop_table(self, table_name: str) -> dict[str, str]:
        """Drop a registered upload table and its metadata."""
        self._client.drop_user_upload_table(table_name)
        return {"status": "ok"}
