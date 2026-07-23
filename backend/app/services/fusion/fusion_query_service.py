"""Fusion cockpit query service across case-bound data sources."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from app.services.fusion.identifier_norm import (
    normalize_bank_name,
    normalize_identifier,
    parse_person_names_from_json_field,
    split_scoped_bank_account,
)
from app.services.fusion.person_link_service import PersonLinkService
from app.services.integration.commercial.ic_ingest_service import normalize_enterprise_name
from app.services.integration.telecom.phone_utils import normalize_phone
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass
class FusionRecord:
    record_type: str
    title: str
    time: str | None
    amount: float | None
    counterparty: str
    summary: str
    source_ref: dict[str, Any] = field(default_factory=dict)
    direction: str = ""
    batch_id: str = ""
    role_hint: str = ""
    counterparty_account: str = ""


class FusionQueryService:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self._person_links = PersonLinkService(self._client)

    def person_cockpit(self, case_id: int, person_id: int) -> dict[str, Any]:
        person = self._person_links.get_person(case_id, person_id)
        if person is None:
            raise ValueError("人物不存在")
        ids = self._person_links.get_identifier_sets(case_id, person_id)
        batch_ids = self._case_batch_ids(case_id)
        records = self._collect_records(batch_ids, ids)
        kpis = self._build_kpis(records)
        charts = self._build_person_charts(case_id, records, person.display_name)
        grouped = self._group_records(records)
        return {
            "profile": {
                "person_id": person.person_id,
                "display_name": person.display_name,
                "role_tag": person.role_tag,
                "notes": person.notes,
                "identifiers": person.links,
            },
            "kpis": kpis,
            "charts": charts,
            "records_by_type": grouped,
            "summary_text": self._person_summary(person.display_name, kpis, records),
        }

    def relation_cockpit(self, case_id: int, person_a_id: int, person_b_id: int) -> dict[str, Any]:
        if person_a_id == person_b_id:
            raise ValueError("请选择两个不同人物")
        person_a = self._person_links.get_person(case_id, person_a_id)
        person_b = self._person_links.get_person(case_id, person_b_id)
        if person_a is None or person_b is None:
            raise ValueError("人物不存在")
        ids_a = self._person_links.get_identifier_sets(case_id, person_a_id)
        ids_b = self._person_links.get_identifier_sets(case_id, person_b_id)
        batch_ids = self._case_batch_ids(case_id)
        records_a = self._collect_records(batch_ids, ids_a)
        records_b = self._collect_records(batch_ids, ids_b)
        direct = self._direct_relation_records(records_a, records_b, ids_a, ids_b, person_a.display_name, person_b.display_name)
        indirect = self._indirect_relations(batch_ids, ids_a, ids_b, person_a.display_name, person_b.display_name)
        charts = self._build_relation_charts(direct, person_a.display_name, person_b.display_name, indirect)
        return {
            "person_a": {"person_id": person_a.person_id, "display_name": person_a.display_name},
            "person_b": {"person_id": person_b.person_id, "display_name": person_b.display_name},
            "direct_records": [asdict(r) for r in direct],
            "indirect_relations": indirect,
            "charts": charts,
            "summary_text": self._relation_summary(person_a.display_name, person_b.display_name, direct, indirect),
        }

    def anchor_cockpit(self, case_id: int, anchor_type: str, anchor_value: str) -> dict[str, Any]:
        """按标识符锚点聚合跨源记录（卡号/手机/微信/企业/姓名）。"""
        resolved_type, anchor_norm = self._resolve_anchor(anchor_type, anchor_value)
        if not anchor_norm:
            raise ValueError("无法识别有效的检索标识")
        batch_ids = self._case_batch_ids(case_id)
        if not batch_ids:
            raise ValueError("当前案件未绑定任何数据批次")
        ids = self._build_ids_from_anchor(batch_ids, resolved_type, anchor_norm)
        records = self._collect_records(batch_ids, ids)
        linked_persons = self._find_linked_persons(case_id, resolved_type, anchor_norm)
        enterprise_roles = (
            self._enterprise_roles_for_anchor(batch_ids, anchor_norm)
            if resolved_type == "enterprise_name"
            else None
        )
        commercial_roles = self._commercial_roles_summary(records)
        anchor_label = self._anchor_display_label(resolved_type, anchor_value.strip(), anchor_norm)
        kpis = self._build_kpis(records)
        charts = self._build_anchor_charts(case_id, records, resolved_type, anchor_label, anchor_norm)
        grouped = self._group_records(records)
        return {
            "anchor": {
                "type": resolved_type,
                "value": anchor_value.strip(),
                "norm": anchor_norm,
                "label": anchor_label,
            },
            "linked_persons": linked_persons,
            "enterprise_roles": enterprise_roles,
            "commercial_roles": commercial_roles,
            "kpis": kpis,
            "charts": charts,
            "records_by_type": grouped,
            "summary_text": self._anchor_summary(
                anchor_label, resolved_type, kpis, records, linked_persons, enterprise_roles, commercial_roles
            ),
        }

    def suggest_anchors(
        self,
        case_id: int,
        query: str,
        *,
        limit: int = 20,
        anchor_type: str = "auto",
    ) -> list[dict[str, Any]]:
        """按关键词前缀/包含匹配案件内已关联标识符与候选标识符。"""
        needle = (query or "").strip().lower()
        limit = max(1, min(int(limit), 50))
        allowed_types = self._resolve_suggest_types(anchor_type)
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def _push(
            identifier_type: str,
            display_value: str,
            identifier_norm: str,
            *,
            person_id: int | None = None,
            person_name: str = "",
            source: str,
        ) -> None:
            if not identifier_norm or not display_value:
                return
            if allowed_types and identifier_type not in allowed_types:
                return
            key = (identifier_type, identifier_norm)
            if key in seen:
                return
            hay = f"{display_value} {identifier_norm}".lower()
            if needle and needle not in hay:
                return
            seen.add(key)
            items.append(
                {
                    "identifier_type": identifier_type,
                    "display_value": display_value,
                    "identifier_norm": identifier_norm,
                    "person_id": person_id,
                    "person_name": person_name,
                    "source": source,
                }
            )

        link_rows = self._client.query_all(
            """
            SELECT l.identifier_type, l.identifier_value, l.identifier_norm, p.person_id, p.display_name
            FROM std_person_link l
            JOIN std_person p ON p.person_id = l.person_id
            WHERE p.case_id=?
            ORDER BY l.identifier_type, l.identifier_value;
            """,
            (case_id,),
        )
        for row in link_rows:
            _push(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                person_id=int(row[3]),
                person_name=str(row[4]),
                source="linked",
            )

        candidate_rows = self._client.query_all(
            """
            SELECT identifier_type, display_value, identifier_norm, review_status
            FROM rel_identifier_candidate
            WHERE case_id=?
            ORDER BY CASE review_status WHEN 'linked' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                     identifier_type, display_value;
            """,
            (case_id,),
        )
        for row in candidate_rows:
            status = str(row[3] or "")
            if status == "no_match":
                continue
            _push(str(row[0]), str(row[1]), str(row[2]), source=status or "candidate")

        items.sort(key=lambda x: (0 if x["source"] == "linked" else 1, x["identifier_type"], x["display_value"]))
        return items[:limit]

    def _resolve_suggest_types(self, anchor_type: str) -> frozenset[str]:
        """Return allowed identifier types for suggestion filtering.

        「银行卡/账号」同时匹配 bank_card 与 bank_acct。
        """
        kind = (anchor_type or "auto").strip().lower()
        if kind == "auto":
            return frozenset()
        type_map: dict[str, frozenset[str]] = {
            "bank": frozenset({"bank_card", "bank_acct"}),
            "bank_card": frozenset({"bank_card", "bank_acct"}),
            "bank_acct": frozenset({"bank_card", "bank_acct"}),
            "card": frozenset({"bank_card", "bank_acct"}),
            "phone": frozenset({"phone"}),
            "mobile": frozenset({"phone"}),
            "wechat": frozenset({"wechat_name"}),
            "wechat_name": frozenset({"wechat_name"}),
            "enterprise": frozenset({"enterprise_name"}),
            "enterprise_name": frozenset({"enterprise_name"}),
            "company": frozenset({"enterprise_name"}),
            "person": frozenset({"person_name"}),
            "person_name": frozenset({"person_name"}),
            "name": frozenset({"person_name"}),
        }
        if kind in type_map:
            return type_map[kind]
        return frozenset({kind})

    def _resolve_suggest_type(self, anchor_type: str) -> str:
        """Backward-compatible single-type resolver (prefer ``_resolve_suggest_types``)."""
        allowed = self._resolve_suggest_types(anchor_type)
        if not allowed:
            return ""
        if allowed == frozenset({"bank_card", "bank_acct"}):
            return "bank_card"
        return next(iter(allowed))

    def _resolve_anchor(self, anchor_type: str, anchor_value: str) -> tuple[str, str]:
        text = (anchor_value or "").strip()
        if not text:
            raise ValueError("检索关键词不能为空")
        kind = (anchor_type or "auto").strip().lower()
        if kind == "auto":
            digits = re.sub(r"\D+", "", text)
            plain = text.replace(" ", "")
            if digits and len(digits) == 11 and digits == plain:
                return "phone", normalize_phone(text)
            if digits and 16 <= len(digits) <= 19 and digits == plain:
                norm = normalize_identifier("bank_card", text)
                return "bank_card", norm
            enterprise_hints = ("公司", "有限", "集团", "企业", "商行", "银行", "中心")
            if any(h in text for h in enterprise_hints):
                return "enterprise_name", normalize_enterprise_name(text)
            norm_name = normalize_identifier("person_name", text)
            return "person_name", norm_name
        type_map = {
            "bank": "bank_card",
            "bank_card": "bank_card",
            "bank_acct": "bank_acct",
            "card": "bank_card",
            "phone": "phone",
            "mobile": "phone",
            "wechat": "wechat_name",
            "wechat_name": "wechat_name",
            "enterprise": "enterprise_name",
            "enterprise_name": "enterprise_name",
            "company": "enterprise_name",
            "person": "person_name",
            "person_name": "person_name",
            "name": "person_name",
        }
        resolved = type_map.get(kind, kind)
        # Keep scoped bank norms like "建设银行|3328134432" so linked-person lookup still matches.
        if resolved in {"bank_card", "bank_acct"} and "|" in text:
            return resolved, text
        norm = normalize_identifier(resolved, text)
        if resolved == "enterprise_name":
            norm = normalize_enterprise_name(text)
        elif resolved == "phone":
            norm = normalize_phone(text)
        return resolved, norm

    def _build_ids_from_anchor(
        self,
        batch_ids: list[str],
        anchor_type: str,
        anchor_norm: str,
    ) -> dict[str, set[str]]:
        ids: dict[str, set[str]] = defaultdict(set)
        if anchor_type in {"bank_card", "bank_acct"}:
            ids["bank_card"].add(anchor_norm)
            ids["bank_acct"].add(anchor_norm)
        elif anchor_type == "phone":
            ids["phone"].add(anchor_norm)
        elif anchor_type == "wechat_name":
            ids["wechat_name"].add(anchor_norm)
        elif anchor_type == "enterprise_name":
            ids["enterprise_name"].add(anchor_norm)
            self._expand_enterprise_anchor_ids(batch_ids, anchor_norm, ids)
        elif anchor_type == "person_name":
            ids["person_name"].add(anchor_norm)
            ids["wechat_name"].add(anchor_norm)
        else:
            ids[anchor_type].add(anchor_norm)
        return dict(ids)

    def _expand_enterprise_anchor_ids(
        self,
        batch_ids: list[str],
        enterprise_norm: str,
        ids: dict[str, set[str]],
    ) -> None:
        for batch_id in batch_ids:
            if self._batch_source_type(batch_id) != "enterprise":
                continue
            rows = self._client.query_all(
                """
                SELECT legal_person, shareholders_json, key_persons_json
                FROM std_enterprise_profile
                WHERE import_batch_id=? AND enterprise_name_norm=?;
                """,
                (batch_id, enterprise_norm),
            )
            for row in rows:
                legal = normalize_identifier("person_name", str(row[0] or ""))
                if legal:
                    ids["person_name"].add(legal)
                for name in parse_person_names_from_json_field(str(row[1] or "")):
                    norm = normalize_identifier("person_name", name)
                    if norm:
                        ids["person_name"].add(norm)
                for name in parse_person_names_from_json_field(str(row[2] or "")):
                    norm = normalize_identifier("person_name", name)
                    if norm:
                        ids["person_name"].add(norm)

    def _find_linked_persons(self, case_id: int, anchor_type: str, anchor_norm: str) -> list[dict[str, Any]]:
        types = [anchor_type]
        if anchor_type == "bank_card":
            types = ["bank_card", "bank_acct"]
        elif anchor_type == "bank_acct":
            types = ["bank_acct", "bank_card"]
        elif anchor_type == "person_name":
            types = ["person_name", "wechat_name"]
        placeholders = ",".join("?" for _ in types)
        rows = self._client.query_all(
            f"""
            SELECT DISTINCT p.person_id, p.display_name, p.role_tag
            FROM std_person_link l
            JOIN std_person p ON p.person_id = l.person_id
            WHERE p.case_id=? AND l.identifier_type IN ({placeholders}) AND l.identifier_norm=?;
            """,
            (case_id, *types, anchor_norm),
        )
        return [
            {"person_id": int(row[0]), "display_name": str(row[1]), "role_tag": str(row[2])}
            for row in rows
        ]

    def _enterprise_roles_for_anchor(self, batch_ids: list[str], enterprise_norm: str) -> dict[str, Any] | None:
        legal_person = ""
        shareholders: list[str] = []
        key_persons: list[str] = []
        display_name = ""
        for batch_id in batch_ids:
            if self._batch_source_type(batch_id) != "enterprise":
                continue
            rows = self._client.query_all(
                """
                SELECT enterprise_name, legal_person, shareholders_json, key_persons_json
                FROM std_enterprise_profile
                WHERE import_batch_id=? AND enterprise_name_norm=?
                LIMIT 1;
                """,
                (batch_id, enterprise_norm),
            )
            if not rows:
                continue
            display_name = str(rows[0][0] or "")
            legal_person = str(rows[0][1] or "")
            for name in parse_person_names_from_json_field(str(rows[0][2] or "")):
                if name not in shareholders:
                    shareholders.append(name)
            for name in parse_person_names_from_json_field(str(rows[0][3] or "")):
                if name not in key_persons:
                    key_persons.append(name)
            break
        if not display_name and not legal_person:
            return None
        return {
            "enterprise_name": display_name or enterprise_norm,
            "legal_person": legal_person,
            "shareholders": shareholders,
            "key_persons": key_persons,
        }

    def _commercial_roles_summary(self, records: list[FusionRecord]) -> dict[str, int] | None:
        purchaser = winner = bidder = 0
        for rec in records:
            if rec.record_type != "commercial":
                continue
            hint = rec.role_hint or ""
            if "甲方采购" in hint:
                purchaser += 1
            if "中标供应商" in hint:
                winner += 1
            if "投标供应商" in hint:
                bidder += 1
        if purchaser + winner + bidder == 0:
            return None
        return {
            "purchaser_count": purchaser,
            "winner_count": winner,
            "bid_company_count": bidder,
        }

    @staticmethod
    def _anchor_display_label(anchor_type: str, raw_value: str, anchor_norm: str) -> str:
        if anchor_type in {"bank_card", "bank_acct"} and len(anchor_norm) >= 8:
            return f"{anchor_norm[:4]}****{anchor_norm[-4:]}"
        return raw_value or anchor_norm

    def _build_anchor_charts(
        self,
        case_id: int,
        records: list[FusionRecord],
        anchor_type: str,
        anchor_label: str,
        anchor_norm: str,
    ) -> dict[str, Any]:
        person_charts = self._build_person_charts(case_id, records, anchor_label)
        graph = self._build_anchor_graph(case_id, records, anchor_type, anchor_label, anchor_norm)
        person_charts["relation_graph"] = graph
        return person_charts

    def _build_anchor_graph(
        self,
        case_id: int,
        records: list[FusionRecord],
        anchor_type: str,
        anchor_label: str,
        anchor_norm: str,
    ) -> dict[str, Any]:
        center_id = f"anchor:{anchor_type}:{anchor_norm}"
        center_norm = anchor_norm if anchor_type == "enterprise_name" else normalize_identifier("person_name", anchor_label)
        name_index = self._case_person_name_index(case_id)
        phone_index = self._case_phone_index(case_id)
        nodes: dict[str, dict[str, Any]] = {
            center_id: {
                "id": center_id,
                "name": anchor_label,
                "category": 0,
                "symbolSize": 62,
                "isCenter": True,
                "stats": {},
            }
        }
        edge_buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for rec in records:
            target_id, label, category = self._graph_target_node(
                rec,
                center_norm=center_norm,
                name_index=name_index,
                phone_index=phone_index,
            )
            if not target_id or target_id == center_id:
                continue
            if target_id not in nodes:
                nodes[target_id] = {
                    "id": target_id,
                    "name": label,
                    "category": category,
                    "symbolSize": 46 if category == 1 else 34 if category == 2 else 28,
                    "stats": {},
                }
            bucket = edge_buckets.setdefault(
                (center_id, target_id),
                {"count": 0, "amount": 0.0, "channels": defaultdict(int), "records": []},
            )
            bucket["count"] += 1
            bucket["channels"][rec.record_type] += 1
            if rec.amount is not None:
                bucket["amount"] += abs(rec.amount)
            if len(bucket["records"]) < 20:
                bucket["records"].append(asdict(rec))
            node_stats = nodes[target_id].setdefault("stats", {})
            node_stats[rec.record_type] = int(node_stats.get(rec.record_type, 0)) + 1

        max_count = max((b["count"] for b in edge_buckets.values()), default=1)
        links: list[dict[str, Any]] = []
        for (source, target), bucket in edge_buckets.items():
            width = max(1.5, min(14.0, 1.5 + (bucket["count"] / max_count) * 12.0))
            links.append(
                {
                    "source": source,
                    "target": target,
                    "value": bucket["count"],
                    "lineWidth": round(width, 1),
                    "totalAmount": round(bucket["amount"], 2),
                    "channels": dict(bucket["channels"]),
                    "records": bucket["records"][:15],
                }
            )
        links.sort(key=lambda item: item["value"], reverse=True)
        return {
            "nodes": list(nodes.values()),
            "links": links,
            "categories": [
                {"name": "检索锚点"},
                {"name": "关联人物"},
                {"name": "企业/机构"},
                {"name": "号码/其他"},
            ],
        }

    def _anchor_summary(
        self,
        anchor_label: str,
        anchor_type: str,
        kpis: dict[str, Any],
        records: list[FusionRecord],
        linked_persons: list[dict[str, Any]],
        enterprise_roles: dict[str, Any] | None,
        commercial_roles: dict[str, int] | None,
    ) -> str:
        type_labels = {
            "bank_card": "银行卡",
            "bank_acct": "银行账号",
            "phone": "手机号",
            "wechat_name": "微信名",
            "enterprise_name": "企业",
            "person_name": "姓名",
        }
        lines = [
            f"以「{anchor_label}」（{type_labels.get(anchor_type, anchor_type)}）为锚点，"
            f"共命中 {kpis['total_records']} 条跨源记录。",
        ]
        if linked_persons:
            names = "、".join(p["display_name"] for p in linked_persons)
            lines.append(f"已关联人物：{names}。")
        if enterprise_roles:
            lp = enterprise_roles.get("legal_person") or "—"
            lines.append(f"企业法人：{lp}；股东 {len(enterprise_roles.get('shareholders') or [])} 人。")
        if commercial_roles:
            lines.append(
                f"商务角色：甲方采购 {commercial_roles.get('purchaser_count', 0)} 条，"
                f"中标 {commercial_roles.get('winner_count', 0)} 条，"
                f"投标 {commercial_roles.get('bid_company_count', 0)} 条。"
            )
        lines.append(
            f"银行 {kpis['bank_txn_count']} 笔，微信 {kpis['wechat_txn_count']} 笔，"
            f"通话 {kpis['telecom_call_count']} 次，企业 {kpis['enterprise_count']} 家，商务 {kpis['commercial_count']} 条。"
        )
        return "\n".join(lines)

    def _case_batch_ids(self, case_id: int) -> list[str]:
        rows = self._client.query_all(
            "SELECT import_batch_id FROM rel_case_batch WHERE case_id=? ORDER BY bound_at;",
            (case_id,),
        )
        return [str(row[0]) for row in rows if row and row[0]]

    def _collect_records(self, batch_ids: list[str], ids: dict[str, set[str]]) -> list[FusionRecord]:
        if not batch_ids:
            return []
        records: list[FusionRecord] = []
        names = ids.get("person_name", set())
        phones = ids.get("phone", set())
        wechats = ids.get("wechat_name", set())
        bank_accts = ids.get("bank_acct", set()) | ids.get("bank_card", set())
        enterprises = ids.get("enterprise_name", set())
        for batch_id in batch_ids:
            source_type = self._batch_source_type(batch_id)
            if source_type == "bank":
                records.extend(self._bank_records(batch_id, names, bank_accts))
            elif source_type == "wechat":
                records.extend(self._wechat_records(batch_id, wechats, names, bank_accts))
            elif source_type == "telecom":
                records.extend(self._telecom_records(batch_id, phones))
            elif source_type == "enterprise":
                records.extend(self._enterprise_records(batch_id, names, enterprises))
            elif source_type == "commercial":
                records.extend(self._commercial_records(batch_id, enterprises, names))
        records.sort(key=lambda r: (r.time or "", r.record_type), reverse=True)
        return records

    def _batch_source_type(self, batch_id: str) -> str:
        rows = self._client.query_all(
            "SELECT source_type FROM rel_case_batch WHERE import_batch_id=? LIMIT 1;",
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

    def _match_name(self, value: str, names: set[str]) -> bool:
        norm = normalize_identifier("person_name", value)
        return bool(norm and norm in names)

    def _match_acct(self, value: str, accts: set[str], bank_name: str = "") -> bool:
        norm = normalize_identifier("bank_acct", value)
        if not norm:
            return False
        bank_key = normalize_bank_name(bank_name)
        for stored in accts:
            stored_bank, stored_acct = split_scoped_bank_account(stored)
            if stored_acct != norm:
                continue
            # Only reject when both sides have a bank and they disagree.
            # Unknown counterparty bank must still match by account digits
            # (cross-bank transfers / scoped norms like 工商银行|6222087735).
            if stored_bank and bank_key and stored_bank != bank_key:
                continue
            return True
        return False

    def _match_phone(self, value: str, phones: set[str]) -> bool:
        norm = normalize_phone(value)
        return bool(norm and norm in phones)

    def _match_wechat(self, value: str, wechats: set[str]) -> bool:
        norm = normalize_identifier("wechat_name", value)
        return bool(norm and norm in wechats)

    def _match_enterprise(self, value: str, enterprises: set[str]) -> bool:
        norm = normalize_enterprise_name(value)
        return bool(norm and norm in enterprises)

    def _bank_records(self, batch_id: str, names: set[str], accts: set[str]) -> list[FusionRecord]:
        out: list[FusionRecord] = []
        rows = self._client.query_all(
            """
            SELECT std_id, bank_name, person_name, acct_no, txn_time, txn_amount, txn_direction,
                   counterparty_name, counterparty_account, summary, remark
            FROM std_bank_txn WHERE import_batch_id=?;
            """,
            (batch_id,),
        )
        for row in rows:
            bank_name = str(row[1] or "")
            person_name = str(row[2] or "")
            acct_no = str(row[3] or "")
            counterparty = str(row[7] or "")
            counterparty_acct = str(row[8] or "")
            if not (
                self._match_name(person_name, names)
                or self._match_acct(acct_no, accts, bank_name)
                or self._match_name(counterparty, names)
                or self._match_acct(counterparty_acct, accts, bank_name)
            ):
                continue
            amount = self._to_float(row[5])
            direction = str(row[6] or "")
            out.append(
                FusionRecord(
                    record_type="bank_txn",
                    title=f"银行流水 {person_name}",
                    time=str(row[4] or "") or None,
                    amount=amount,
                    counterparty=counterparty or counterparty_acct,
                    summary=str(row[9] or row[10] or ""),
                    direction=direction,
                    batch_id=batch_id,
                    counterparty_account=counterparty_acct,
                    source_ref={
                        "layer": "std",
                        "table": "std_bank_txn",
                        "pk": {"std_id": int(row[0])},
                        "batch_id": batch_id,
                    },
                )
            )
        return out

    def _wechat_records(
        self,
        batch_id: str,
        wechats: set[str],
        names: set[str],
        bank_accts: set[str],
    ) -> list[FusionRecord]:
        out: list[FusionRecord] = []
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "wechat"):
            user = self._raw_field(fields, "用户侧账号名称", "用户侧账户名称")
            peer = self._raw_field(fields, "对手侧账户名称", "对手方账户名称")
            user_card = self._raw_field(fields, "用户银行卡号", "用户侧银行卡号")
            if not (
                self._match_wechat(user, wechats)
                or self._match_wechat(peer, wechats)
                or self._match_name(user, names)
                or self._match_name(peer, names)
                or self._match_acct(user_card, bank_accts)
            ):
                continue
            amount_fen = self._to_float(
                self._raw_field(fields, "交易金额(分)", "交易金额（分）", "交易金额_分")
            )
            amount = amount_fen / 100.0 if amount_fen is not None else None
            out.append(
                FusionRecord(
                    record_type="wechat",
                    title=f"微信转账 {user}",
                    time=self._raw_field(fields, "交易时间") or None,
                    amount=amount,
                    counterparty=peer,
                    summary=self._raw_field(fields, "交易业务类型", "备注1", "备注2"),
                    direction=self._raw_field(fields, "借贷类型", "借贷标志"),
                    batch_id=batch_id,
                    source_ref={"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id},
                )
            )
        return out

    def _telecom_records(self, batch_id: str, phones: set[str]) -> list[FusionRecord]:
        out: list[FusionRecord] = []
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "telecom"):
            local = fields.get("本机号码", "")
            peer = fields.get("对方号码", "")
            if not (self._match_phone(local, phones) or self._match_phone(peer, phones)):
                continue
            duration = self._to_float(fields.get("呼叫时长", "")) or 0.0
            out.append(
                FusionRecord(
                    record_type="telecom",
                    title=f"通话 {local}",
                    time=fields.get("呼叫开始时间") or fields.get("短信发送接收时间") or None,
                    amount=duration,
                    counterparty=peer,
                    summary=fields.get("通话类型", "") or fields.get("话单类型", ""),
                    batch_id=batch_id,
                    source_ref={"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id},
                )
            )
        return out

    def _enterprise_records(
        self,
        batch_id: str,
        names: set[str],
        enterprises: set[str],
    ) -> list[FusionRecord]:
        out: list[FusionRecord] = []
        rows = self._client.query_all(
            """
            SELECT enterprise_id, enterprise_name, legal_person, reg_status, industry, shareholders_json, key_persons_json
            FROM std_enterprise_profile WHERE import_batch_id=?;
            """,
            (batch_id,),
        )
        for row in rows:
            ent_name = str(row[1] or "")
            legal = str(row[2] or "")
            matched = self._match_enterprise(ent_name, enterprises) or self._match_name(legal, names)
            if not matched:
                for name in parse_person_names_from_json_field(str(row[5] or "")) + parse_person_names_from_json_field(str(row[6] or "")):
                    if self._match_name(name, names):
                        matched = True
                        break
            if not matched:
                continue
            out.append(
                FusionRecord(
                    record_type="enterprise",
                    title=ent_name,
                    time=None,
                    amount=None,
                    counterparty=legal,
                    summary=f"{row[3] or ''} · {row[4] or ''}",
                    batch_id=batch_id,
                    source_ref={
                        "layer": "std",
                        "table": "std_enterprise_profile",
                        "pk": {"enterprise_id": int(row[0])},
                        "batch_id": batch_id,
                    },
                )
            )
        return out

    def _commercial_records(
        self,
        batch_id: str,
        enterprises: set[str],
        names: set[str],
    ) -> list[FusionRecord]:
        out: list[FusionRecord] = []
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "commercial"):
            company = fields.get("公司名称") or fields.get("供应商") or ""
            purchaser = fields.get("采购单位") or ""
            winner = fields.get("中标供应商") or ""
            role_hint = self._commercial_role_hint(company, purchaser, winner, enterprises)
            if not role_hint:
                continue
            summary_parts = [
                fields.get("物资名称") or fields.get("项目名称") or "",
                role_hint,
            ]
            if purchaser:
                summary_parts.append(f"采购方:{purchaser}")
            out.append(
                FusionRecord(
                    record_type="commercial",
                    title=fields.get("询价单号") or "商务网",
                    time=None,
                    amount=self._to_float(
                        fields.get("中标金额") or fields.get("中标金额(元)") or fields.get("含税单价")
                    ),
                    counterparty=company or winner or purchaser,
                    summary=" · ".join(part for part in summary_parts if part),
                    batch_id=batch_id,
                    role_hint=role_hint,
                    source_ref={"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id},
                )
            )
        return out

    def _commercial_role_hint(
        self,
        company: str,
        purchaser: str,
        winner: str,
        enterprises: set[str],
    ) -> str:
        roles: list[str] = []
        if self._match_enterprise(company, enterprises):
            roles.append("投标供应商")
        if self._match_enterprise(winner, enterprises):
            roles.append("中标供应商")
        if self._match_enterprise(purchaser, enterprises):
            roles.append("甲方采购")
        return " / ".join(roles)

    def _direct_relation_records(
        self,
        records_a: list[FusionRecord],
        records_b: list[FusionRecord],
        ids_a: dict[str, set[str]],
        ids_b: dict[str, set[str]],
        name_a: str,
        name_b: str,
    ) -> list[FusionRecord]:
        direct: list[FusionRecord] = []
        b_names = ids_b.get("person_name", set()) | ids_b.get("wechat_name", set())
        b_phones = ids_b.get("phone", set())
        b_accts = ids_b.get("bank_acct", set()) | ids_b.get("bank_card", set())
        a_names = ids_a.get("person_name", set()) | ids_a.get("wechat_name", set())
        a_phones = ids_a.get("phone", set())
        a_accts = ids_a.get("bank_acct", set()) | ids_a.get("bank_card", set())
        for rec in records_a:
            if rec.record_type == "bank_txn":
                if (
                    self._match_name(rec.counterparty, b_names)
                    or self._match_acct(rec.counterparty_account, b_accts)
                    or self._match_acct(rec.counterparty, b_accts)
                ):
                    direct.append(rec)
            elif rec.record_type == "wechat":
                if self._match_wechat(rec.counterparty, b_names) or self._match_name(rec.counterparty, b_names):
                    direct.append(rec)
            elif rec.record_type == "telecom":
                if self._match_phone(rec.counterparty, b_phones):
                    direct.append(rec)
        for rec in records_b:
            if rec.record_type == "bank_txn":
                if (
                    self._match_name(rec.counterparty, a_names)
                    or self._match_acct(rec.counterparty_account, a_accts)
                    or self._match_acct(rec.counterparty, a_accts)
                ):
                    direct.append(rec)
            elif rec.record_type == "wechat":
                if self._match_wechat(rec.counterparty, a_names) or self._match_name(rec.counterparty, a_names):
                    direct.append(rec)
            elif rec.record_type == "telecom":
                if self._match_phone(rec.counterparty, a_phones):
                    direct.append(rec)
        if not direct:
            return direct
        seen: set[str] = set()
        unique: list[FusionRecord] = []
        for rec in direct:
            key = json.dumps(asdict(rec), ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            unique.append(rec)
        unique.sort(key=lambda r: (r.time or ""), reverse=True)
        return unique

    def _indirect_relations(
        self,
        batch_ids: list[str],
        ids_a: dict[str, set[str]],
        ids_b: dict[str, set[str]],
        name_a: str,
        name_b: str,
    ) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        ent_a = self._enterprise_names_for_person(batch_ids, ids_a)
        ent_b = self._enterprise_names_for_person(batch_ids, ids_b)
        shared = sorted(ent_a & ent_b)
        for ent in shared:
            relations.append(
                {
                    "relation_type": "shared_enterprise",
                    "title": f"共同关联企业：{ent}",
                    "detail": f"{name_a} 与 {name_b} 均与 {ent} 存在工商/商务关联",
                }
            )
        commercial_batches = [b for b in batch_ids if self._batch_source_type(b) == "commercial"]
        for batch_id in commercial_batches:
            companies_a: set[str] = set()
            companies_b: set[str] = set()
            for table, _raw_id, fields in self._iter_raw_rows(batch_id, "commercial"):
                inquiry = fields.get("询价单号") or ""
                company = fields.get("公司名称") or ""
                norm = normalize_enterprise_name(company)
                if not inquiry or not norm:
                    continue
                if norm in ent_a:
                    companies_a.add((inquiry, norm))
                if norm in ent_b:
                    companies_b.add((inquiry, norm))
            for item in companies_a & companies_b:
                relations.append(
                    {
                        "relation_type": "commercial_co_bid",
                        "title": f"同场商务网询价 {item[0]}",
                        "detail": f"企业 {item[1]} 与 {name_a}/{name_b} 存在关联且共同参与询价",
                    }
                )
        return relations

    def _enterprise_names_for_person(self, batch_ids: list[str], ids: dict[str, set[str]]) -> set[str]:
        names = set(ids.get("enterprise_name", set()))
        person_names = ids.get("person_name", set())
        for batch_id in batch_ids:
            if self._batch_source_type(batch_id) != "enterprise":
                continue
            rows = self._client.query_all(
                """
                SELECT enterprise_name_norm, legal_person, shareholders_json, key_persons_json
                FROM std_enterprise_profile WHERE import_batch_id=?;
                """,
                (batch_id,),
            )
            for row in rows:
                legal = normalize_identifier("person_name", str(row[1] or ""))
                matched = legal in person_names
                if not matched:
                    for name in parse_person_names_from_json_field(str(row[2] or "")) + parse_person_names_from_json_field(str(row[3] or "")):
                        if normalize_identifier("person_name", name) in person_names:
                            matched = True
                            break
                if matched:
                    names.add(str(row[0]))
        return names

    def _build_kpis(self, records: list[FusionRecord]) -> dict[str, Any]:
        bank_in = bank_out = wechat_in = wechat_out = 0.0
        bank_count = wechat_count = telecom_count = enterprise_count = commercial_count = 0
        telecom_duration = 0.0
        for rec in records:
            if rec.record_type == "bank_txn":
                bank_count += 1
                if rec.amount is None:
                    continue
                if "收" in rec.direction:
                    bank_in += rec.amount
                elif "支" in rec.direction:
                    bank_out += rec.amount
            elif rec.record_type == "wechat":
                wechat_count += 1
                if rec.amount is None:
                    continue
                if rec.direction == "入":
                    wechat_in += rec.amount
                elif rec.direction == "出":
                    wechat_out += rec.amount
            elif rec.record_type == "telecom":
                telecom_count += 1
                telecom_duration += rec.amount or 0.0
            elif rec.record_type == "enterprise":
                enterprise_count += 1
            elif rec.record_type == "commercial":
                commercial_count += 1
        return {
            "bank_txn_count": bank_count,
            "bank_in_amount": round(bank_in, 2),
            "bank_out_amount": round(bank_out, 2),
            "wechat_txn_count": wechat_count,
            "wechat_in_amount": round(wechat_in, 2),
            "wechat_out_amount": round(wechat_out, 2),
            "telecom_call_count": telecom_count,
            "telecom_total_duration_sec": round(telecom_duration, 2),
            "enterprise_count": enterprise_count,
            "commercial_count": commercial_count,
            "total_records": len(records),
        }

    def _case_person_name_index(self, case_id: int) -> dict[str, str]:
        """Map normalized person/wechat name -> display name for case persons."""
        index: dict[str, str] = {}
        for person in self._person_links.list_persons(case_id):
            display = person.display_name.strip()
            for norm_key in (
                normalize_identifier("person_name", display),
                normalize_identifier("wechat_name", display),
            ):
                if norm_key:
                    index[norm_key] = display
            for link in person.links:
                if link["identifier_type"] in {"person_name", "wechat_name"}:
                    norm = str(link["identifier_norm"])
                    if norm:
                        index[norm] = display
        return index

    def _case_phone_index(self, case_id: int) -> dict[str, str]:
        index: dict[str, str] = {}
        for person in self._person_links.list_persons(case_id):
            for link in person.links:
                if link["identifier_type"] == "phone":
                    norm = str(link["identifier_norm"])
                    if norm:
                        index[norm] = person.display_name
        return index

    def _build_relation_graph(
        self,
        case_id: int,
        records: list[FusionRecord],
        person_name: str,
    ) -> dict[str, Any]:
        center_norm = normalize_identifier("person_name", person_name)
        center_id = f"p:{person_name}"
        name_index = self._case_person_name_index(case_id)
        phone_index = self._case_phone_index(case_id)
        nodes: dict[str, dict[str, Any]] = {
            center_id: {
                "id": center_id,
                "name": person_name,
                "category": 0,
                "symbolSize": 62,
                "isCenter": True,
                "stats": {},
            }
        }
        edge_buckets: dict[tuple[str, str], dict[str, Any]] = {}

        for rec in records:
            target_id, label, category = self._graph_target_node(
                rec,
                center_norm=center_norm,
                name_index=name_index,
                phone_index=phone_index,
            )
            if not target_id or target_id == center_id:
                continue
            if target_id not in nodes:
                nodes[target_id] = {
                    "id": target_id,
                    "name": label,
                    "category": category,
                    "symbolSize": 46 if category == 1 else 34 if category == 2 else 28,
                    "stats": {},
                }
            bucket = edge_buckets.setdefault(
                (center_id, target_id),
                {"count": 0, "amount": 0.0, "channels": defaultdict(int), "records": []},
            )
            bucket["count"] += 1
            bucket["channels"][rec.record_type] += 1
            if rec.amount is not None:
                bucket["amount"] += abs(rec.amount)
            if len(bucket["records"]) < 20:
                bucket["records"].append(asdict(rec))
            node_stats = nodes[target_id].setdefault("stats", {})
            node_stats[rec.record_type] = int(node_stats.get(rec.record_type, 0)) + 1

        max_count = max((b["count"] for b in edge_buckets.values()), default=1)
        links: list[dict[str, Any]] = []
        for (source, target), bucket in edge_buckets.items():
            width = max(1.5, min(14.0, 1.5 + (bucket["count"] / max_count) * 12.0))
            links.append(
                {
                    "source": source,
                    "target": target,
                    "value": bucket["count"],
                    "lineWidth": round(width, 1),
                    "totalAmount": round(bucket["amount"], 2),
                    "channels": dict(bucket["channels"]),
                    "records": bucket["records"][:15],
                }
            )
        links.sort(key=lambda item: item["value"], reverse=True)
        return {
            "nodes": list(nodes.values()),
            "links": links,
            "categories": [
                {"name": "中心人物"},
                {"name": "关联人物"},
                {"name": "企业/机构"},
                {"name": "号码/其他"},
            ],
        }

    def _graph_target_node(
        self,
        rec: FusionRecord,
        *,
        center_norm: str,
        name_index: dict[str, str],
        phone_index: dict[str, str],
    ) -> tuple[str, str, int]:
        if rec.record_type == "enterprise":
            label = rec.title.strip() or rec.counterparty.strip()
            norm = normalize_enterprise_name(label)
            if not norm:
                return "", "", 0
            return f"ent:{norm}", label, 2
        if rec.record_type == "commercial":
            label = (rec.counterparty or rec.title).strip()
            norm = normalize_enterprise_name(label)
            if not norm:
                return "", "", 0
            return f"ent:{norm}", label, 2

        counterparty = (rec.counterparty or "").strip()
        if not counterparty:
            return "", "", 0

        cp_norm = normalize_identifier("person_name", counterparty)
        if cp_norm and cp_norm == center_norm:
            return "", "", 0

        if cp_norm and cp_norm in name_index:
            display = name_index[cp_norm]
            return f"p:{display}", display, 1

        phone_norm = normalize_phone(counterparty)
        if phone_norm and len(phone_norm) >= 7:
            owner = phone_index.get(phone_norm)
            if owner and normalize_identifier("person_name", owner) != center_norm:
                return f"p:{owner}", owner, 1
            if not cp_norm:
                return f"ph:{phone_norm}", counterparty, 3

        enterprise_hints = ("公司", "有限", "集团", "商行", "企业", "中心", "银行")
        if any(h in counterparty for h in enterprise_hints):
            norm = normalize_enterprise_name(counterparty)
            return f"ent:{norm}", counterparty, 2

        if cp_norm and 2 <= len(counterparty) <= 8:
            chinese = sum(1 for ch in counterparty if "\u4e00" <= ch <= "\u9fff")
            if chinese >= 2:
                return f"p:{counterparty}", counterparty, 1

        return f"org:{counterparty}", counterparty, 3

    def _build_person_charts(self, case_id: int, records: list[FusionRecord], person_name: str) -> dict[str, Any]:
        timeline: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        hour_buckets: dict[int, int] = defaultdict(int)
        fund_pie = {"bank_in": 0.0, "bank_out": 0.0, "wechat_in": 0.0, "wechat_out": 0.0}
        for rec in records:
            day = self._day_key(rec.time)
            if day:
                timeline[day][rec.record_type] += 1
            hour = self._hour_key(rec.time)
            if hour is not None and rec.record_type == "telecom":
                hour_buckets[hour] += 1
            if rec.record_type == "bank_txn" and rec.amount is not None:
                if "收" in rec.direction:
                    fund_pie["bank_in"] += rec.amount
                elif "支" in rec.direction:
                    fund_pie["bank_out"] += rec.amount
            if rec.record_type == "wechat" and rec.amount is not None:
                if rec.direction == "入":
                    fund_pie["wechat_in"] += rec.amount
                elif rec.direction == "出":
                    fund_pie["wechat_out"] += rec.amount
        days = sorted(timeline.keys())
        types = ["bank_txn", "wechat", "telecom", "enterprise", "commercial"]
        return {
            "activity_timeline": {
                "days": days,
                "series": [
                    {"name": t, "data": [timeline[d].get(t, 0) for d in days]}
                    for t in types
                ],
            },
            "relation_graph": self._build_relation_graph(case_id, records, person_name),
            "fund_direction_pie": [
                {"name": "银行收入", "value": round(fund_pie["bank_in"], 2)},
                {"name": "银行支出", "value": round(fund_pie["bank_out"], 2)},
                {"name": "微信收入", "value": round(fund_pie["wechat_in"], 2)},
                {"name": "微信支出", "value": round(fund_pie["wechat_out"], 2)},
            ],
            "telecom_hourly": [{"hour": h, "count": hour_buckets.get(h, 0)} for h in range(24)],
        }

    def _build_relation_charts(
        self,
        direct: list[FusionRecord],
        name_a: str,
        name_b: str,
        indirect: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sankey_links: list[dict[str, Any]] = []
        timeline: dict[str, int] = defaultdict(int)
        bank_amount = wechat_amount = telecom_count = 0.0
        for rec in direct:
            day = self._day_key(rec.time)
            if day:
                timeline[day] += 1
            if rec.record_type == "bank_txn":
                bank_amount += abs(rec.amount or 0.0)
                sankey_links.append({"source": name_a, "target": name_b, "value": round(abs(rec.amount or 1.0), 2), "channel": "bank"})
            elif rec.record_type == "wechat":
                wechat_amount += abs(rec.amount or 0.0)
                sankey_links.append({"source": name_a, "target": name_b, "value": round(abs(rec.amount or 1.0), 2), "channel": "wechat"})
            elif rec.record_type == "telecom":
                telecom_count += 1.0
                sankey_links.append({"source": name_a, "target": name_b, "value": 1.0, "channel": "telecom"})
        path_nodes = [
            {"id": name_a, "name": name_a},
            {"id": name_b, "name": name_b},
        ]
        path_links: list[dict[str, Any]] = []
        for rel in indirect:
            mid = rel["title"]
            path_nodes.append({"id": mid, "name": mid})
            path_links.append({"source": name_a, "target": mid})
            path_links.append({"source": mid, "target": name_b})
        return {
            "sankey": {"links": sankey_links, "summary": {"bank_amount": round(bank_amount, 2), "wechat_amount": round(wechat_amount, 2), "telecom_count": int(telecom_count)}},
            "interaction_timeline": {"days": sorted(timeline.keys()), "counts": [timeline[d] for d in sorted(timeline.keys())]},
            "path_graph": {"nodes": path_nodes, "links": path_links},
        }

    def _group_records(self, records: list[FusionRecord]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rec in records:
            grouped[rec.record_type].append(asdict(rec))
        return dict(grouped)

    def _person_summary(self, name: str, kpis: dict[str, Any], records: list[FusionRecord]) -> str:
        lines = [
            f"{name} 在案件范围内共关联 {kpis['total_records']} 条跨源记录。",
            f"银行流水 {kpis['bank_txn_count']} 笔，收入 {kpis['bank_in_amount']:.2f} 元，支出 {kpis['bank_out_amount']:.2f} 元。",
            f"微信转账 {kpis['wechat_txn_count']} 笔，通话 {kpis['telecom_call_count']} 次。",
            f"关联企业 {kpis['enterprise_count']} 家，商务网记录 {kpis['commercial_count']} 条。",
        ]
        return "\n".join(lines)

    def _relation_summary(
        self,
        name_a: str,
        name_b: str,
        direct: list[FusionRecord],
        indirect: list[dict[str, Any]],
    ) -> str:
        bank = sum(1 for r in direct if r.record_type == "bank_txn")
        wechat = sum(1 for r in direct if r.record_type == "wechat")
        telecom = sum(1 for r in direct if r.record_type == "telecom")
        lines = [
            f"{name_a} 与 {name_b} 之间存在 {len(direct)} 条直接关系记录。",
            f"其中银行 {bank} 笔、微信 {wechat} 笔、通话 {telecom} 次。",
        ]
        if indirect:
            lines.append(f"另发现 {len(indirect)} 条间接关联（共同企业/同场商务等）。")
        return "\n".join(lines)

    def _iter_raw_rows(self, batch_id: str, source_type: str) -> list[tuple[str, int, dict[str, str]]]:
        output = self._iter_raw_rows_from_meta(batch_id, source_type)
        if output:
            return output
        return self._iter_raw_rows_fallback(batch_id, source_type)

    def _iter_raw_rows_from_meta(self, batch_id: str, source_type: str) -> list[tuple[str, int, dict[str, str]]]:
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
            output.extend(self._read_raw_table_rows(str(table_name), batch_id))
        return output

    def _iter_raw_rows_fallback(self, batch_id: str, source_type: str) -> list[tuple[str, int, dict[str, str]]]:
        output: list[tuple[str, int, dict[str, str]]] = []
        for (table_name,) in self._client.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'raw_%' ORDER BY name;"
        ):
            table = str(table_name)
            info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
            col_names = {str(row[1]) for row in info}
            if "import_batch_id" not in col_names:
                continue
            if "source_type" in col_names:
                count_rows = self._client.query_all(
                    f"""
                    SELECT COUNT(*) FROM {self._client.quote_ident(table)}
                    WHERE import_batch_id=? AND source_type=?;
                    """,
                    (batch_id, source_type),
                )
            else:
                count_rows = self._client.query_all(
                    f"SELECT COUNT(*) FROM {self._client.quote_ident(table)} WHERE import_batch_id=?;",
                    (batch_id,),
                )
            if not count_rows or int(count_rows[0][0] or 0) <= 0:
                continue
            output.extend(self._read_raw_table_rows(table, batch_id, source_type if "source_type" in col_names else None))
        return output

    def _read_raw_table_rows(
        self,
        table: str,
        batch_id: str,
        source_type: str | None = None,
    ) -> list[tuple[str, int, dict[str, str]]]:
        output: list[tuple[str, int, dict[str, str]]] = []
        info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
        src_cols = [str(x[1]) for x in info if str(x[1]).startswith("src_")]
        if not src_cols:
            return output
        sql_cols = ", ".join(self._client.quote_ident(c) for c in src_cols)
        if source_type:
            raw_rows = self._client.query_all(
                f"""
                SELECT raw_id, {sql_cols}
                FROM {self._client.quote_ident(table)}
                WHERE import_batch_id=? AND source_type=?
                ORDER BY raw_id;
                """,
                (batch_id, source_type),
            )
        else:
            raw_rows = self._client.query_all(
                f"""
                SELECT raw_id, {sql_cols}
                FROM {self._client.quote_ident(table)}
                WHERE import_batch_id=?
                ORDER BY raw_id;
                """,
                (batch_id,),
            )
        for row in raw_rows:
            raw_id = int(row[0])
            fields: dict[str, str] = {}
            for idx, col in enumerate(src_cols, start=1):
                label = col[4:] if col.startswith("src_") else col
                val = row[idx]
                fields[label] = "" if val is None else str(val).strip()
            output.append((table, raw_id, fields))
        return output

    @staticmethod
    def _normalize_field_key(key: str) -> str:
        return "".join(ch for ch in str(key or "").lower() if ch.isalnum())

    @classmethod
    def _raw_field(cls, fields: dict[str, str], *names: str) -> str:
        if not fields:
            return ""
        norm_map: dict[str, str] = {}
        for key, value in fields.items():
            norm = cls._normalize_field_key(key)
            if norm and norm not in norm_map:
                norm_map[norm] = str(value or "").strip()
        for name in names:
            direct = fields.get(name)
            if direct is not None and str(direct).strip():
                return str(direct).strip()
            normalized = cls._normalize_field_key(name)
            if normalized in norm_map and norm_map[normalized]:
                return norm_map[normalized]
        return ""

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            return float(match.group(0)) if match else None

    @staticmethod
    def _day_key(value: str | None) -> str:
        if not value:
            return ""
        text = value.strip().replace("/", "-")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[: len(fmt.replace("%", "0"))], fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        if len(text) >= 10:
            return text[:10]
        return ""

    @staticmethod
    def _hour_key(value: str | None) -> int | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(value.strip()[:19], fmt).hour
            except ValueError:
                continue
        return None


__all__ = ["FusionQueryService", "FusionRecord"]
