"""Scan case-bound batches and populate identifier candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.services.fusion.identifier_norm import normalize_identifier, parse_person_names_from_json_field
from app.services.shared.db.sqlite_client import SqliteClient

_SOURCE_PRIORITY = {"enterprise": 3, "bank": 2, "commercial": 1, "wechat": 1, "telecom": 1}


@dataclass
class DiscoveryResult:
    case_id: int
    inserted: int
    skipped: int


class IdentifierDiscoveryService:
    """Discover linkable identifiers within a case scope."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def discover(self, case_id: int) -> DiscoveryResult:
        batch_ids = self._case_batch_ids(case_id)
        if not batch_ids:
            return DiscoveryResult(case_id=case_id, inserted=0, skipped=0)
        inserted = 0
        skipped = 0
        seen: set[tuple[str, str]] = set()
        for batch_id in batch_ids:
            source_type = self._batch_source_type(batch_id)
            if source_type == "bank":
                for item in self._scan_bank(batch_id):
                    if self._upsert_candidate(case_id, item, seen):
                        inserted += 1
                    else:
                        skipped += 1
            elif source_type == "wechat":
                for item in self._scan_wechat(batch_id):
                    if self._upsert_candidate(case_id, item, seen):
                        inserted += 1
                    else:
                        skipped += 1
            elif source_type == "telecom":
                for item in self._scan_telecom(batch_id):
                    if self._upsert_candidate(case_id, item, seen):
                        inserted += 1
                    else:
                        skipped += 1
            elif source_type == "enterprise":
                for item in self._scan_enterprise(batch_id):
                    if self._upsert_candidate(case_id, item, seen):
                        inserted += 1
                    else:
                        skipped += 1
            elif source_type == "commercial":
                for item in self._scan_commercial(batch_id):
                    if self._upsert_candidate(case_id, item, seen):
                        inserted += 1
                    else:
                        skipped += 1
        return DiscoveryResult(case_id=case_id, inserted=inserted, skipped=skipped)

    def _case_batch_ids(self, case_id: int) -> list[str]:
        rows = self._client.query_all(
            "SELECT import_batch_id FROM rel_case_batch WHERE case_id=? ORDER BY bound_at;",
            (case_id,),
        )
        return [str(row[0]) for row in rows if row and row[0]]

    def _batch_source_type(self, batch_id: str) -> str:
        rows = self._client.query_all(
            """
            SELECT source_type FROM rel_case_batch WHERE import_batch_id=? LIMIT 1;
            """,
            (batch_id,),
        )
        if rows and rows[0][0]:
            return str(rows[0][0])
        rows = self._client.query_all(
            "SELECT source_type FROM meta_bank_files WHERE import_batch_id=? LIMIT 1;",
            (batch_id,),
        )
        if rows and rows[0][0]:
            return str(rows[0][0])
        rows = self._client.query_all(
            "SELECT 1 FROM std_enterprise_profile WHERE import_batch_id=? LIMIT 1;",
            (batch_id,),
        )
        return "enterprise" if rows else ""

    def _upsert_candidate(
        self,
        case_id: int,
        item: dict[str, Any],
        seen: set[tuple[str, str]],
    ) -> bool:
        identifier_type = str(item["identifier_type"])
        identifier_norm = str(item["identifier_norm"])
        if not identifier_norm:
            return False
        key = (identifier_type, identifier_norm)
        if key in seen:
            return False
        seen.add(key)
        if self._is_already_linked(case_id, identifier_type, identifier_norm):
            return False
        existing = self._client.query_all(
            """
            SELECT candidate_id, review_status, source_type, source_ref_json
            FROM rel_identifier_candidate
            WHERE case_id=? AND identifier_type=? AND identifier_norm=?;
            """,
            (case_id, identifier_type, identifier_norm),
        )
        if existing:
            status = str(existing[0][1])
            if status in {"linked", "no_match"}:
                return False
            new_source = str(item.get("source_type") or "")
            old_source = str(existing[0][2] or "")
            if self._should_upgrade_candidate_source(identifier_type, old_source, new_source):
                self._client.execute(
                    """
                    UPDATE rel_identifier_candidate
                    SET display_value=?, source_type=?, source_batch_id=?, source_ref_json=?
                    WHERE candidate_id=?;
                    """,
                    (
                        str(item.get("display_value") or identifier_norm),
                        new_source,
                        str(item.get("source_batch_id") or ""),
                        json.dumps(item.get("source_ref") or {}, ensure_ascii=False),
                        int(existing[0][0]),
                    ),
                )
                return True
            return False
        self._client.execute(
            """
            INSERT INTO rel_identifier_candidate(
                case_id, identifier_type, identifier_norm, display_value,
                source_type, source_batch_id, source_ref_json, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending');
            """,
            (
                case_id,
                identifier_type,
                identifier_norm,
                str(item.get("display_value") or identifier_norm),
                str(item.get("source_type") or ""),
                str(item.get("source_batch_id") or ""),
                json.dumps(item.get("source_ref") or {}, ensure_ascii=False),
            ),
        )
        return True

    def _should_upgrade_candidate_source(
        self,
        identifier_type: str,
        old_source: str,
        new_source: str,
    ) -> bool:
        if identifier_type != "enterprise_name":
            return False
        old_rank = _SOURCE_PRIORITY.get(old_source, 0)
        new_rank = _SOURCE_PRIORITY.get(new_source, 0)
        return new_rank > old_rank

    def _is_already_linked(self, case_id: int, identifier_type: str, identifier_norm: str) -> bool:
        rows = self._client.query_all(
            """
            SELECT 1 FROM std_person_link l
            JOIN std_person p ON p.person_id=l.person_id
            WHERE p.case_id=? AND l.identifier_type=? AND l.identifier_norm=?
            LIMIT 1;
            """,
            (case_id, identifier_type, identifier_norm),
        )
        return bool(rows)

    def _add_item(
        self,
        items: list[dict[str, Any]],
        *,
        identifier_type: str,
        value: str,
        source_type: str,
        batch_id: str,
        source_ref: dict[str, Any],
    ) -> None:
        norm = normalize_identifier(identifier_type, value)
        if not norm:
            return
        items.append(
            {
                "identifier_type": identifier_type,
                "identifier_norm": norm,
                "display_value": value.strip(),
                "source_type": source_type,
                "source_batch_id": batch_id,
                "source_ref": source_ref,
            }
        )

    def _scan_bank(self, batch_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self._client.query_all(
            """
            SELECT account_id, person_name, acct_no, mobile, id_no, source_file_id, source_sheet
            FROM std_bank_account WHERE import_batch_id=?;
            """,
            (batch_id,),
        ):
            ref = {
                "layer": "std",
                "table": "std_bank_account",
                "pk": {"account_id": int(row[0])},
                "batch_id": batch_id,
            }
            self._add_item(items, identifier_type="person_name", value=str(row[1] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="bank_acct", value=str(row[2] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="phone", value=str(row[3] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="id_no", value=str(row[4] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
        for row in self._client.query_all(
            """
            SELECT std_id, person_name, acct_no, counterparty_name, counterparty_account
            FROM std_bank_txn WHERE import_batch_id=?;
            """,
            (batch_id,),
        ):
            ref = {"layer": "std", "table": "std_bank_txn", "pk": {"std_id": int(row[0])}, "batch_id": batch_id}
            self._add_item(items, identifier_type="person_name", value=str(row[1] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="bank_acct", value=str(row[2] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="person_name", value=str(row[3] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="bank_acct", value=str(row[4] or ""), source_type="bank", batch_id=batch_id, source_ref=ref)
        return items

    def _scan_wechat(self, batch_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "wechat"):
            ref = {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}
            self._add_item(items, identifier_type="wechat_name", value=fields.get("用户侧账号名称", ""), source_type="wechat", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="bank_card", value=fields.get("用户银行卡号", ""), source_type="wechat", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="wechat_name", value=fields.get("对手侧账户名称", ""), source_type="wechat", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="bank_card", value=fields.get("对手方银行卡号", ""), source_type="wechat", batch_id=batch_id, source_ref=ref)
        return items

    def _scan_telecom(self, batch_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "telecom"):
            ref = {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}
            self._add_item(items, identifier_type="phone", value=fields.get("本机号码", ""), source_type="telecom", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="phone", value=fields.get("对方号码", ""), source_type="telecom", batch_id=batch_id, source_ref=ref)
            owner = fields.get("机主姓名") or fields.get("用户姓名") or fields.get("姓名") or ""
            self._add_item(items, identifier_type="person_name", value=owner, source_type="telecom", batch_id=batch_id, source_ref=ref)
        return items

    def _scan_enterprise(self, batch_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self._client.query_all(
            """
            SELECT enterprise_id, enterprise_name, legal_person, shareholders_json, key_persons_json
            FROM std_enterprise_profile WHERE import_batch_id=?;
            """,
            (batch_id,),
        ):
            ref = {"layer": "std", "table": "std_enterprise_profile", "pk": {"enterprise_id": int(row[0])}, "batch_id": batch_id}
            self._add_item(items, identifier_type="enterprise_name", value=str(row[1] or ""), source_type="enterprise", batch_id=batch_id, source_ref=ref)
            self._add_item(items, identifier_type="person_name", value=str(row[2] or ""), source_type="enterprise", batch_id=batch_id, source_ref=ref)
            for name in parse_person_names_from_json_field(str(row[3] or "")):
                self._add_item(items, identifier_type="person_name", value=name, source_type="enterprise", batch_id=batch_id, source_ref=ref)
            for name in parse_person_names_from_json_field(str(row[4] or "")):
                self._add_item(items, identifier_type="person_name", value=name, source_type="enterprise", batch_id=batch_id, source_ref=ref)
        return items

    def _scan_commercial(self, batch_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "commercial"):
            ref = {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}
            company = fields.get("公司名称") or fields.get("供应商") or ""
            self._add_item(items, identifier_type="enterprise_name", value=company, source_type="commercial", batch_id=batch_id, source_ref=ref)
        match_rows = self._client.query_all(
            """
            SELECT enterprise_id, enterprise_name FROM rel_biz_enterprise_match
            WHERE import_batch_id=?;
            """,
            (batch_id,),
        )
        for row in match_rows:
            ent_id = int(row[0])
            ent_rows = self._client.query_all(
                """
                SELECT legal_person, shareholders_json, key_persons_json
                FROM std_enterprise_profile WHERE enterprise_id=? LIMIT 1;
                """,
                (ent_id,),
            )
            if not ent_rows:
                continue
            ref = {"layer": "std", "table": "std_enterprise_profile", "pk": {"enterprise_id": ent_id}, "batch_id": batch_id}
            self._add_item(items, identifier_type="person_name", value=str(ent_rows[0][0] or ""), source_type="commercial", batch_id=batch_id, source_ref=ref)
            for name in parse_person_names_from_json_field(str(ent_rows[0][1] or "")):
                self._add_item(items, identifier_type="person_name", value=name, source_type="commercial", batch_id=batch_id, source_ref=ref)
            for name in parse_person_names_from_json_field(str(ent_rows[0][2] or "")):
                self._add_item(items, identifier_type="person_name", value=name, source_type="commercial", batch_id=batch_id, source_ref=ref)
        return items

    def _iter_raw_rows(
        self,
        batch_id: str,
        source_type: str,
    ) -> list[tuple[str, int, dict[str, str]]]:
        output: list[tuple[str, int, dict[str, str]]] = []
        sheet_rows = self._client.query_all(
            """
            SELECT DISTINCT s.raw_table_name
            FROM meta_bank_sheets s
            JOIN meta_bank_files f ON f.file_id=s.file_id
            WHERE f.import_batch_id=? AND f.source_type=?
            ORDER BY s.raw_table_name;
            """,
            (batch_id, source_type),
        )
        for (table_name,) in sheet_rows:
            table = str(table_name)
            info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
            src_cols = [str(x[1]) for x in info if str(x[1]).startswith("src_")]
            if not src_cols:
                continue
            sql_cols = ", ".join(self._client.quote_ident(c) for c in src_cols)
            raw_rows = self._client.query_all(
                f"""
                SELECT raw_id, row_no, {sql_cols}
                FROM {self._client.quote_ident(table)}
                WHERE import_batch_id=?
                ORDER BY raw_id;
                """,
                (batch_id,),
            )
            for row in raw_rows:
                raw_id = int(row[0])
                fields: dict[str, str] = {}
                for idx, col in enumerate(src_cols, start=2):
                    label = col[4:] if col.startswith("src_") else col
                    val = row[idx]
                    fields[label] = "" if val is None else str(val).strip()
                output.append((table, raw_id, fields))
        return output


__all__ = ["DiscoveryResult", "IdentifierDiscoveryService"]
