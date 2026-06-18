"""Case management use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.bootstrap import bootstrap_database
from app.application.dataset_use_cases import DatasetUseCase
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass
class CaseInfo:
    case_id: int
    case_name: str
    description: str
    status: str
    created_at: str
    updated_at: str
    batch_count: int = 0


@dataclass
class CaseBatchInfo:
    import_batch_id: str
    source_type: str
    bound_at: str


class CaseUseCase:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def list_cases(self) -> list[CaseInfo]:
        rows = self._client.query_all(
            """
            SELECT c.case_id, c.case_name, c.description, c.status, c.created_at, c.updated_at,
                   COUNT(b.rel_id) AS batch_count
            FROM std_case c
            LEFT JOIN rel_case_batch b ON b.case_id=c.case_id
            GROUP BY c.case_id
            ORDER BY c.updated_at DESC, c.case_id DESC;
            """
        )
        return [
            CaseInfo(
                case_id=int(row[0]),
                case_name=str(row[1]),
                description=str(row[2]),
                status=str(row[3]),
                created_at=str(row[4]),
                updated_at=str(row[5]),
                batch_count=int(row[6] or 0),
            )
            for row in rows
        ]

    def get_case(self, case_id: int) -> CaseInfo | None:
        rows = self._client.query_all(
            """
            SELECT c.case_id, c.case_name, c.description, c.status, c.created_at, c.updated_at,
                   COUNT(b.rel_id) AS batch_count
            FROM std_case c
            LEFT JOIN rel_case_batch b ON b.case_id=c.case_id
            WHERE c.case_id=?
            GROUP BY c.case_id;
            """,
            (case_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return CaseInfo(
            case_id=int(row[0]),
            case_name=str(row[1]),
            description=str(row[2]),
            status=str(row[3]),
            created_at=str(row[4]),
            updated_at=str(row[5]),
            batch_count=int(row[6] or 0),
        )

    def create_case(self, *, case_name: str, description: str = "", status: str = "active") -> CaseInfo:
        name = case_name.strip()
        if not name:
            raise ValueError("case_name 不能为空")
        self._client.execute(
            """
            INSERT INTO std_case(case_name, description, status, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP);
            """,
            (name, description or "", status or "active"),
        )
        rows = self._client.query_all(
            "SELECT case_id FROM std_case WHERE case_name=? ORDER BY case_id DESC LIMIT 1;",
            (name,),
        )
        if not rows:
            raise ValueError("创建案件失败")
        case_id = int(rows[0][0])
        case = self.get_case(case_id)
        assert case is not None
        return case

    def update_case(
        self,
        case_id: int,
        *,
        case_name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> CaseInfo:
        if self.get_case(case_id) is None:
            raise ValueError("案件不存在")
        self._client.execute(
            """
            UPDATE std_case
            SET case_name=COALESCE(?, case_name),
                description=COALESCE(?, description),
                status=COALESCE(?, status),
                updated_at=CURRENT_TIMESTAMP
            WHERE case_id=?;
            """,
            (
                case_name.strip() if case_name is not None else None,
                description,
                status,
                case_id,
            ),
        )
        updated = self.get_case(case_id)
        assert updated is not None
        return updated

    def delete_case(self, case_id: int) -> None:
        self._client.execute("DELETE FROM std_case WHERE case_id=?;", (case_id,))

    def list_case_batches(self, case_id: int) -> list[CaseBatchInfo]:
        rows = self._client.query_all(
            """
            SELECT import_batch_id, source_type, bound_at
            FROM rel_case_batch WHERE case_id=? ORDER BY bound_at DESC;
            """,
            (case_id,),
        )
        dataset = DatasetUseCase(self._client)
        result: list[CaseBatchInfo] = []
        for row in rows:
            batch_id = str(row[0])
            if dataset.resolve_batch_kind(batch_id) is None:
                self._client.execute(
                    "DELETE FROM rel_case_batch WHERE case_id=? AND import_batch_id=?;",
                    (case_id, batch_id),
                )
                continue
            result.append(
                CaseBatchInfo(
                    import_batch_id=batch_id,
                    source_type=str(row[1]),
                    bound_at=str(row[2]),
                )
            )
        return result

    def bind_batches(self, case_id: int, import_batch_ids: list[str]) -> list[CaseBatchInfo]:
        if self.get_case(case_id) is None:
            raise ValueError("案件不存在")
        dataset = DatasetUseCase(self._client)
        for batch_id in import_batch_ids:
            batch_id = batch_id.strip()
            if not batch_id:
                continue
            kind = dataset.resolve_batch_kind(batch_id)
            if not kind:
                raise ValueError(f"批次不存在: {batch_id}")
            existing = self._client.query_all(
                "SELECT case_id FROM rel_case_batch WHERE import_batch_id=? LIMIT 1;",
                (batch_id,),
            )
            if existing and int(existing[0][0]) != case_id:
                raise ValueError(f"批次 {batch_id} 已归属其他案件")
            if existing:
                continue
            self._client.execute(
                """
                INSERT INTO rel_case_batch(case_id, import_batch_id, source_type)
                VALUES (?, ?, ?);
                """,
                (case_id, batch_id, kind),
            )
        self._client.execute(
            "UPDATE std_case SET updated_at=CURRENT_TIMESTAMP WHERE case_id=?;",
            (case_id,),
        )
        return self.list_case_batches(case_id)

    def unbind_batch(self, case_id: int, import_batch_id: str) -> None:
        self._client.execute(
            "DELETE FROM rel_case_batch WHERE case_id=? AND import_batch_id=?;",
            (case_id, import_batch_id.strip()),
        )
        self._client.execute(
            "UPDATE std_case SET updated_at=CURRENT_TIMESTAMP WHERE case_id=?;",
            (case_id,),
        )

    def list_unbound_batches(self) -> list[dict[str, Any]]:
        dataset = DatasetUseCase(self._client)
        all_batches = dataset.list_batches_merged(limit=500)
        bound_rows = self._client.query_all("SELECT import_batch_id FROM rel_case_batch;")
        bound = {str(row[0]) for row in bound_rows}
        items = []
        for batch in all_batches:
            if batch.import_batch_id in bound:
                continue
            items.append(
                {
                    "import_batch_id": batch.import_batch_id,
                    "source_type": batch.source_type,
                    "file_count": batch.file_count,
                    "imported_at": batch.imported_at,
                }
            )
        return items

    def batch_case_map(self) -> dict[str, dict[str, Any]]:
        rows = self._client.query_all(
            """
            SELECT b.import_batch_id, b.case_id, c.case_name
            FROM rel_case_batch b
            JOIN std_case c ON c.case_id=b.case_id;
            """
        )
        return {
            str(row[0]): {"case_id": int(row[1]), "case_name": str(row[2])}
            for row in rows
        }


__all__ = ["CaseBatchInfo", "CaseInfo", "CaseUseCase"]
