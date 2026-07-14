"""Persistence for user-defined bank mapping templates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.services.integration.bank.template_library import BankTemplate
from app.services.shared.db.sqlite_client import SqliteClient


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class UserBankTemplateRecord:
    """One row from meta_user_bank_template."""

    id: int
    template_id: str
    display_name: str
    template_type: str
    bank_display_name: str
    bank_keywords: list[str]
    sheet_keywords: list[str]
    field_map: dict[str, list[str]]
    signature_columns: list[str]
    header_row_0based: int | None
    match_priority: int
    template_group_id: str | None
    direction_rules: dict[str, str]
    datetime_patterns: dict[str, Any] | None
    is_active: int
    created_at: str
    updated_at: str


def _parse_json_list(raw: str | None, default: list[str]) -> list[str]:
    if not raw:
        return list(default)
    data = json.loads(raw)
    if isinstance(data, list):
        return [str(x) for x in data]
    return list(default)


def _parse_json_dict_str(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _parse_field_map(raw: str) -> dict[str, list[str]]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in data.items():
        std = str(k)
        if isinstance(v, str):
            out[std] = [v]
        elif isinstance(v, list):
            out[std] = [str(x) for x in v if str(x).strip()]
        else:
            continue
    return out


def record_to_bank_template(rec: UserBankTemplateRecord) -> BankTemplate:
    """Convert DB record to BankTemplate for matching and seeding."""
    field_map: dict[str, tuple[str, ...]] = {}
    for std, aliases in rec.field_map.items():
        field_map[std] = tuple(aliases)
    sig = tuple(rec.signature_columns) if rec.signature_columns else tuple()
    if not sig:
        # derive from first alias per field for column signature matching
        sig = tuple(next(iter(v), "") for v in rec.field_map.values() if v)
        sig = tuple(s for s in sig if s)[:8]
    return BankTemplate(
        template_id=rec.template_id,
        bank_display_name=rec.bank_display_name,
        bank_keywords=tuple(rec.bank_keywords),
        sheet_keywords=tuple(rec.sheet_keywords),
        header_row_hint=rec.header_row_0based,
        field_map=field_map,
        signature_columns=sig,
        user_template_id=rec.template_id,
        template_type=rec.template_type,
        direction_rules=dict(rec.direction_rules),
        datetime_patterns=rec.datetime_patterns,
    )


def _row_to_record(row: tuple[Any, ...]) -> UserBankTemplateRecord:
    return UserBankTemplateRecord(
        id=int(row[0]),
        template_id=str(row[1]),
        display_name=str(row[2]),
        template_type=str(row[3]),
        bank_display_name=str(row[4]),
        bank_keywords=_parse_json_list(str(row[5]) if row[5] else "[]", []),
        sheet_keywords=_parse_json_list(str(row[6]) if row[6] else "[]", []),
        field_map=_parse_field_map(str(row[7])),
        signature_columns=_parse_json_list(str(row[8]) if row[8] else "[]", []),
        header_row_0based=int(row[9]) if row[9] is not None else None,
        match_priority=int(row[10] or 0),
        template_group_id=str(row[11]) if row[11] else None,
        direction_rules=_parse_json_dict_str(str(row[12]) if row[12] else None),
        datetime_patterns=json.loads(str(row[13])) if row[13] else None,
        is_active=int(row[14] if row[14] is not None else 1),
        created_at=str(row[15] or ""),
        updated_at=str(row[16] or ""),
    )


class UserBankTemplateRepository:
    """CRUD for meta_user_bank_template."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def ensure_table(self) -> None:
        """Idempotent: create table if missing (for DBs created before migration)."""
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_user_bank_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                template_type TEXT NOT NULL,
                bank_display_name TEXT NOT NULL,
                bank_keywords_json TEXT NOT NULL,
                sheet_keywords_json TEXT NOT NULL,
                field_map_json TEXT NOT NULL,
                signature_columns_json TEXT NOT NULL DEFAULT '[]',
                header_row_0based INTEGER,
                match_priority INTEGER NOT NULL DEFAULT 0,
                template_group_id TEXT,
                direction_rules_json TEXT,
                datetime_patterns_json TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    def list_active_ordered(self) -> list[UserBankTemplateRecord]:
        self.ensure_table()
        rows = self._client.query_all(
            """
            SELECT id, template_id, display_name, template_type, bank_display_name,
                   bank_keywords_json, sheet_keywords_json, field_map_json, signature_columns_json,
                   header_row_0based, match_priority, template_group_id,
                   direction_rules_json, datetime_patterns_json, is_active, created_at, updated_at
            FROM meta_user_bank_template
            WHERE is_active=1
            ORDER BY match_priority DESC, id ASC;
            """
        )
        return [_row_to_record(r) for r in rows]

    def list_all(self) -> list[UserBankTemplateRecord]:
        self.ensure_table()
        rows = self._client.query_all(
            """
            SELECT id, template_id, display_name, template_type, bank_display_name,
                   bank_keywords_json, sheet_keywords_json, field_map_json, signature_columns_json,
                   header_row_0based, match_priority, template_group_id,
                   direction_rules_json, datetime_patterns_json, is_active, created_at, updated_at
            FROM meta_user_bank_template
            ORDER BY match_priority DESC, id ASC;
            """
        )
        return [_row_to_record(r) for r in rows]

    def get_by_template_id(self, template_id: str) -> UserBankTemplateRecord | None:
        self.ensure_table()
        rows = self._client.query_all(
            """
            SELECT id, template_id, display_name, template_type, bank_display_name,
                   bank_keywords_json, sheet_keywords_json, field_map_json, signature_columns_json,
                   header_row_0based, match_priority, template_group_id,
                   direction_rules_json, datetime_patterns_json, is_active, created_at, updated_at
            FROM meta_user_bank_template
            WHERE template_id=?
            LIMIT 1;
            """,
            (template_id,),
        )
        return _row_to_record(rows[0]) if rows else None

    def get_transform_rules(self, template_id: str) -> tuple[dict[str, str], dict[str, Any] | None]:
        rec = self.get_by_template_id(template_id)
        if not rec:
            return {}, None
        return rec.direction_rules, rec.datetime_patterns

    def create(
        self,
        *,
        display_name: str,
        template_type: str,
        bank_display_name: str,
        bank_keywords: list[str],
        sheet_keywords: list[str],
        field_map: dict[str, list[str]],
        signature_columns: list[str] | None = None,
        header_row_0based: int | None = None,
        match_priority: int = 0,
        template_group_id: str | None = None,
        direction_rules: dict[str, str] | None = None,
        datetime_patterns: dict[str, Any] | None = None,
        template_id: str | None = None,
    ) -> str:
        self.ensure_table()
        tid = template_id or f"user_{uuid4().hex[:12]}"
        now = _utc_now_iso()
        self._client.execute(
            """
            INSERT INTO meta_user_bank_template (
                template_id, display_name, template_type, bank_display_name,
                bank_keywords_json, sheet_keywords_json, field_map_json, signature_columns_json,
                header_row_0based, match_priority, template_group_id,
                direction_rules_json, datetime_patterns_json, is_active, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?);
            """,
            (
                tid,
                display_name,
                template_type,
                bank_display_name,
                json.dumps(bank_keywords, ensure_ascii=False),
                json.dumps(sheet_keywords, ensure_ascii=False),
                json.dumps(field_map, ensure_ascii=False),
                json.dumps(signature_columns or [], ensure_ascii=False),
                header_row_0based,
                match_priority,
                template_group_id,
                json.dumps(direction_rules or {}, ensure_ascii=False),
                json.dumps(datetime_patterns, ensure_ascii=False) if datetime_patterns is not None else None,
                now,
                now,
            ),
        )
        invalidate_template_cache()
        return tid

    def update(
        self,
        template_id: str,
        *,
        display_name: str | None = None,
        template_type: str | None = None,
        bank_display_name: str | None = None,
        bank_keywords: list[str] | None = None,
        sheet_keywords: list[str] | None = None,
        field_map: dict[str, list[str]] | None = None,
        signature_columns: list[str] | None = None,
        header_row_0based: int | None = None,
        match_priority: int | None = None,
        template_group_id: str | None = None,
        direction_rules: dict[str, str] | None = None,
        datetime_patterns: dict[str, Any] | None = None,
        is_active: int | None = None,
    ) -> bool:
        self.ensure_table()
        rec = self.get_by_template_id(template_id)
        if not rec:
            return False
        display_name = display_name if display_name is not None else rec.display_name
        template_type = template_type if template_type is not None else rec.template_type
        bank_display_name = bank_display_name if bank_display_name is not None else rec.bank_display_name
        bank_keywords = bank_keywords if bank_keywords is not None else rec.bank_keywords
        sheet_keywords = sheet_keywords if sheet_keywords is not None else rec.sheet_keywords
        field_map = field_map if field_map is not None else rec.field_map
        signature_columns = signature_columns if signature_columns is not None else rec.signature_columns
        hdr = rec.header_row_0based if header_row_0based is None else header_row_0based
        match_priority = match_priority if match_priority is not None else rec.match_priority
        template_group_id = template_group_id if template_group_id is not None else rec.template_group_id
        direction_rules = direction_rules if direction_rules is not None else rec.direction_rules
        datetime_patterns = datetime_patterns if datetime_patterns is not None else rec.datetime_patterns
        is_act = is_active if is_active is not None else rec.is_active
        now = _utc_now_iso()
        self._client.execute(
            """
            UPDATE meta_user_bank_template SET
                display_name=?, template_type=?, bank_display_name=?,
                bank_keywords_json=?, sheet_keywords_json=?, field_map_json=?, signature_columns_json=?,
                header_row_0based=?, match_priority=?, template_group_id=?,
                direction_rules_json=?, datetime_patterns_json=?, is_active=?, updated_at=?
            WHERE template_id=?;
            """,
            (
                display_name,
                template_type,
                bank_display_name,
                json.dumps(bank_keywords, ensure_ascii=False),
                json.dumps(sheet_keywords, ensure_ascii=False),
                json.dumps(field_map, ensure_ascii=False),
                json.dumps(signature_columns, ensure_ascii=False),
                hdr,
                match_priority,
                template_group_id,
                json.dumps(direction_rules, ensure_ascii=False),
                json.dumps(datetime_patterns, ensure_ascii=False) if datetime_patterns is not None else None,
                is_act,
                now,
                template_id,
            ),
        )
        invalidate_template_cache()
        return True

    def delete(self, template_id: str) -> bool:
        self.ensure_table()
        before = self.get_by_template_id(template_id)
        if not before:
            return False
        self._client.execute("DELETE FROM meta_user_bank_template WHERE template_id=?;", (template_id,))
        invalidate_template_cache()
        return True


def invalidate_template_cache() -> None:
    """Clear merged template cache after mutations."""
    from app.services.integration.bank import template_library as tl

    tl.clear_template_cache()
