"""Resolve original record details for fusion provenance."""

from __future__ import annotations

import json
from typing import Any

from app.services.shared.db.sqlite_client import SqliteClient


class RecordDetailService:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def get_detail(self, source_ref: dict[str, Any]) -> dict[str, Any]:
        layer = str(source_ref.get("layer") or "")
        table = str(source_ref.get("table") or "")
        pk = source_ref.get("pk") or {}
        if not table or not isinstance(pk, dict):
            raise ValueError("无效的 source_ref")
        if layer == "std":
            return self._load_std(table, pk)
        if layer == "raw":
            return self._load_raw(table, pk)
        raise ValueError(f"不支持的 layer: {layer}")

    def _load_std(self, table: str, pk: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "std_bank_txn": "std_id",
            "std_bank_account": "account_id",
            "std_enterprise_profile": "enterprise_id",
        }
        if table not in allowed:
            raise ValueError(f"不支持的 std 表: {table}")
        pk_col = allowed[table]
        pk_val = pk.get(pk_col)
        if pk_val is None:
            raise ValueError("缺少主键")
        rows = self._client.query_all(
            f"SELECT * FROM {self._client.quote_ident(table)} WHERE {self._client.quote_ident(pk_col)}=? LIMIT 1;",
            (pk_val,),
        )
        if not rows:
            raise ValueError("记录不存在")
        info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
        columns = [str(x[1]) for x in info]
        record = {columns[i]: rows[0][i] for i in range(len(columns))}
        raw_payload = record.get("raw_payload")
        parsed_payload: dict[str, Any] | list[Any] | str | None = None
        if raw_payload:
            try:
                parsed_payload = json.loads(str(raw_payload))
            except json.JSONDecodeError:
                parsed_payload = str(raw_payload)
        return {
            "layer": "std",
            "table": table,
            "pk": pk,
            "fields": record,
            "raw_payload": parsed_payload,
        }

    def _load_raw(self, table: str, pk: dict[str, Any]) -> dict[str, Any]:
        raw_id = pk.get("raw_id")
        if raw_id is None:
            raise ValueError("缺少 raw_id")
        info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
        columns = [str(x[1]) for x in info]
        rows = self._client.query_all(
            f"SELECT * FROM {self._client.quote_ident(table)} WHERE raw_id=? LIMIT 1;",
            (raw_id,),
        )
        if not rows:
            raise ValueError("记录不存在")
        record = {columns[i]: rows[0][i] for i in range(len(columns))}
        display_fields = {
            (col[4:] if col.startswith("src_") else col): record[col]
            for col in columns
            if col.startswith("src_") or col in {"raw_id", "row_no", "import_batch_id", "source_sheet"}
        }
        raw_payload = record.get("raw_payload")
        parsed_payload: dict[str, Any] | list[Any] | str | None = None
        if raw_payload:
            try:
                parsed_payload = json.loads(str(raw_payload))
            except json.JSONDecodeError:
                parsed_payload = str(raw_payload)
        return {
            "layer": "raw",
            "table": table,
            "pk": pk,
            "fields": display_fields,
            "raw_payload": parsed_payload,
        }


__all__ = ["RecordDetailService"]
