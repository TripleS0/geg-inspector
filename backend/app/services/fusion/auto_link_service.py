"""Heuristic auto-linking of identifier candidates to persons within a case."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.services.fusion.identifier_discovery_service import IdentifierDiscoveryService
from app.services.fusion.identifier_norm import normalize_identifier
from app.services.fusion.person_link_service import PersonLinkService
from app.services.shared.db.sqlite_client import SqliteClient

_ENTERPRISE_HINTS = ("公司", "有限", "集团", "商行", "企业", "中心", "部门", "银行")
_NAME_TYPES = frozenset({"person_name", "wechat_name"})
_PROPAGATE_TYPES = frozenset({"phone", "bank_acct", "bank_card", "id_no"})


@dataclass
class AutoLinkResult:
    case_id: int
    persons_created: int = 0
    links_created: int = 0
    skipped: int = 0
    unresolved_pending: int = 0
    person_names: list[str] = field(default_factory=list)


class AutoLinkService:
    """Cluster pending candidates by name and source record, then link to persons."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self._discovery = IdentifierDiscoveryService(self._client)
        self._person_links = PersonLinkService(self._client)

    def auto_link(self, case_id: int, *, rediscover: bool = True) -> AutoLinkResult:
        rows = self._client.query_all("SELECT 1 FROM std_case WHERE case_id=? LIMIT 1;", (case_id,))
        if not rows:
            raise ValueError("案件不存在")
        if rediscover:
            self._discovery.discover(case_id)

        result = AutoLinkResult(case_id=case_id)
        candidates = self._person_links.list_candidates(case_id, review_status="pending")
        if not candidates:
            return result

        name_display = self._collect_person_names(candidates)
        name_to_person = self._ensure_persons(case_id, name_display, result)

        linked_ids: set[int] = set()

        # Pass 1: same source record bundle (须先于姓名直配，避免 anchor 已被移出 pending)
        groups = self._group_by_source_ref(candidates)
        for group in groups.values():
            anchor_norm = self._group_anchor_name(group)
            if not anchor_norm:
                continue
            person_id = name_to_person.get(anchor_norm)
            if person_id is None:
                continue
            for cand in group:
                if cand["candidate_id"] in linked_ids:
                    continue
                itype = str(cand["identifier_type"])
                if itype in _NAME_TYPES:
                    cand_norm = normalize_identifier("person_name", str(cand["display_value"]))
                    if not cand_norm or cand_norm != anchor_norm:
                        continue
                if self._try_link(case_id, cand["candidate_id"], person_id, linked_ids):
                    result.links_created += 1

        # Pass 2: direct name / wechat match
        for cand in candidates:
            if cand["candidate_id"] in linked_ids:
                continue
            itype = str(cand["identifier_type"])
            if itype not in _NAME_TYPES:
                continue
            if not self._is_probable_person_name(str(cand["display_value"])):
                continue
            norm = str(cand["identifier_norm"])
            person_id = name_to_person.get(norm)
            if person_id is None:
                continue
            if self._try_link(case_id, cand["candidate_id"], person_id, linked_ids):
                result.links_created += 1

        # Pass 3: counterparty person_name matching known persons
        for cand in candidates:
            if cand["candidate_id"] in linked_ids:
                continue
            if str(cand["identifier_type"]) != "person_name":
                continue
            norm = str(cand["identifier_norm"])
            person_id = name_to_person.get(norm)
            if person_id is None:
                continue
            if self._try_link(case_id, cand["candidate_id"], person_id, linked_ids):
                result.links_created += 1

        # Pass 4: propagate phone / bank / id by already-linked norms on same person
        norm_to_person = self._build_norm_index(case_id)
        for cand in candidates:
            if cand["candidate_id"] in linked_ids:
                continue
            itype = str(cand["identifier_type"])
            if itype not in _PROPAGATE_TYPES:
                continue
            norm = str(cand["identifier_norm"])
            person_id = norm_to_person.get((itype, norm))
            if person_id is None and itype == "phone":
                person_id = norm_to_person.get(("phone", norm))
            if person_id is None:
                continue
            if self._try_link(case_id, cand["candidate_id"], person_id, linked_ids):
                result.links_created += 1
                norm_to_person[(itype, norm)] = person_id

        # Pass 5: phone seen in bank-linked set matches telecom local phone
        phone_person = {
            norm: pid for (typ, norm), pid in norm_to_person.items() if typ == "phone"
        }
        for cand in candidates:
            if cand["candidate_id"] in linked_ids:
                continue
            if str(cand["identifier_type"]) != "phone":
                continue
            person_id = phone_person.get(str(cand["identifier_norm"]))
            if person_id is None:
                continue
            if self._try_link(case_id, cand["candidate_id"], person_id, linked_ids):
                result.links_created += 1

        result.person_names = sorted(
            {p.display_name for p in self._person_links.list_persons(case_id)}
        )
        remaining = self._person_links.list_candidates(case_id, review_status="pending")
        result.unresolved_pending = len(remaining)
        result.skipped = result.unresolved_pending
        return result

    def _collect_person_names(self, candidates: list[dict]) -> dict[str, str]:
        """Map name_norm -> best display label."""
        out: dict[str, str] = {}
        for cand in candidates:
            itype = str(cand["identifier_type"])
            if itype not in _NAME_TYPES:
                continue
            display = str(cand["display_value"]).strip()
            if not self._is_probable_person_name(display):
                continue
            norm = normalize_identifier("person_name", display)
            if not norm:
                continue
            if itype == "person_name" or norm not in out:
                out[norm] = display
        return out

    def _ensure_persons(
        self,
        case_id: int,
        name_display: dict[str, str],
        result: AutoLinkResult,
    ) -> dict[str, int]:
        existing = {
            normalize_identifier("person_name", p.display_name): p.person_id
            for p in self._person_links.list_persons(case_id)
        }
        name_to_person = dict(existing)
        for norm, display in sorted(name_display.items()):
            if norm in name_to_person:
                continue
            person = self._person_links.create_person(case_id, display_name=display, role_tag="unknown")
            name_to_person[norm] = person.person_id
            result.persons_created += 1
        return name_to_person

    def _group_by_source_ref(self, candidates: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for cand in candidates:
            ref = cand.get("source_ref") or {}
            key = self._ref_key(ref)
            if not key:
                continue
            groups.setdefault(key, []).append(cand)
        return groups

    def _group_anchor_name(self, group: list[dict]) -> str:
        ref = (group[0].get("source_ref") or {}) if group else {}
        table = str(ref.get("table") or "")
        pk = ref.get("pk") or {}
        if table == "std_bank_txn" and isinstance(pk, dict) and pk.get("std_id") is not None:
            rows = self._client.query_all(
                "SELECT person_name FROM std_bank_txn WHERE std_id=? LIMIT 1;",
                (int(pk["std_id"]),),
            )
            if rows:
                norm = normalize_identifier("person_name", str(rows[0][0] or ""))
                if norm:
                    return norm
        if table == "std_bank_account" and isinstance(pk, dict) and pk.get("account_id") is not None:
            rows = self._client.query_all(
                "SELECT person_name FROM std_bank_account WHERE account_id=? LIMIT 1;",
                (int(pk["account_id"]),),
            )
            if rows:
                norm = normalize_identifier("person_name", str(rows[0][0] or ""))
                if norm:
                    return norm
        if table.startswith("raw_") and isinstance(pk, dict) and pk.get("raw_id") is not None:
            owner = self._raw_owner_name(table, int(pk["raw_id"]))
            if owner:
                return owner
        for cand in group:
            itype = str(cand["identifier_type"])
            if itype not in _NAME_TYPES:
                continue
            display = str(cand["display_value"]).strip()
            if self._is_probable_person_name(display):
                return normalize_identifier("person_name", display)
        for cand in group:
            if str(cand["identifier_type"]) == "person_name":
                display = str(cand["display_value"]).strip()
                norm = normalize_identifier("person_name", display)
                if norm:
                    return norm
        return ""

    def _raw_owner_name(self, table: str, raw_id: int) -> str:
        info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
        cols = {str(row[1]) for row in info}
        for col in ("src_用户侧账号名称", "src_客户名称", "src_账户名称"):
            if col not in cols:
                continue
            rows = self._client.query_all(
                f"SELECT {self._client.quote_ident(col)} FROM {self._client.quote_ident(table)} WHERE raw_id=? LIMIT 1;",
                (raw_id,),
            )
            if not rows or rows[0][0] is None:
                continue
            norm = normalize_identifier("person_name", str(rows[0][0]).strip())
            if norm:
                return norm
        return ""

    def _build_norm_index(self, case_id: int) -> dict[tuple[str, str], int]:
        index: dict[tuple[str, str], int] = {}
        for person in self._person_links.list_persons(case_id):
            for link in person.links:
                key = (str(link["identifier_type"]), str(link["identifier_norm"]))
                index[key] = person.person_id
            name_norm = normalize_identifier("person_name", person.display_name)
            if name_norm:
                index[("person_name", name_norm)] = person.person_id
        return index

    def _try_link(
        self,
        case_id: int,
        candidate_id: int,
        person_id: int,
        linked_ids: set[int],
    ) -> bool:
        try:
            self._person_links.link_candidate(case_id, candidate_id, person_id)
            linked_ids.add(candidate_id)
            return True
        except ValueError:
            return False

    @staticmethod
    def _ref_key(source_ref: dict) -> str:
        if not source_ref:
            return ""
        table = str(source_ref.get("table") or "")
        pk = source_ref.get("pk") or {}
        if not table or not isinstance(pk, dict):
            return ""
        return f"{table}:{json.dumps(pk, sort_keys=True, ensure_ascii=False)}"

    @staticmethod
    def _is_probable_person_name(value: str) -> bool:
        text = (value or "").strip()
        if not text or len(text) > 8:
            return False
        if any(h in text for h in _ENTERPRISE_HINTS):
            return False
        if re.search(r"\d{5,}", text):
            return False
        chinese = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        return chinese >= 2 and chinese >= len(text) * 0.5


__all__ = ["AutoLinkResult", "AutoLinkService"]
