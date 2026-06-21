"""Data center use cases."""

from __future__ import annotations

from typing import Any

from app.application.bootstrap import bootstrap_database
from app.services.data_center.data_center_service import DataCenterService
from app.services.shared.db.sqlite_client import SqliteClient


class DataCenterUseCase:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)
        self._service = DataCenterService(self._client)

    def list_records(
        self,
        *,
        case_id: int | None = None,
        batch_id: str | None = None,
        source_type: str | None = None,
        keyword: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._service.list_records(
            case_id=case_id,
            batch_id=batch_id,
            source_type=source_type,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )

    def delete_records(self, items: list[dict[str, Any]]) -> dict[str, int]:
        if not items:
            raise ValueError("请选择要删除的数据")
        return self._service.delete_records(items)

    def get_dashboard(self, case_id: int | None = None) -> dict[str, Any]:
        return self._service.get_dashboard(case_id)


__all__ = ["DataCenterUseCase"]
