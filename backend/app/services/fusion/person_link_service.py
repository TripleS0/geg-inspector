"""Person and identifier link management within a case."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.services.fusion.identifier_norm import normalize_identifier
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass
class PersonInfo:
    person_id: int
    case_id: int
    display_name: str
    role_tag: str
    notes: str
    created_at: str
    updated_at: str
    links: list[dict[str, Any]]


class PersonLinkService:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def list_persons(self, case_id: int) -> list[PersonInfo]:
        rows = self._client.query_all(
            """
            SELECT person_id, case_id, display_name, role_tag, notes, created_at, updated_at
            FROM std_person WHERE case_id=? ORDER BY display_name, person_id;
            """,
            (case_id,),
        )
        return [self._person_with_links(row) for row in rows]

    def get_person(self, case_id: int, person_id: int) -> PersonInfo | None:
        rows = self._client.query_all(
            """
            SELECT person_id, case_id, display_name, role_tag, notes, created_at, updated_at
            FROM std_person WHERE case_id=? AND person_id=? LIMIT 1;
            """,
            (case_id, person_id),
        )
        if not rows:
            return None
        return self._person_with_links(rows[0])

    def create_person(
        self,
        case_id: int,
        *,
        display_name: str,
        role_tag: str = "unknown",
        notes: str = "",
    ) -> PersonInfo:
        self._ensure_case(case_id)
        name = display_name.strip()
        if not name:
            raise ValueError("display_name 不能为空")
        self._client.execute(
            """
            INSERT INTO std_person(case_id, display_name, role_tag, notes, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP);
            """,
            (case_id, name, role_tag or "unknown", notes or ""),
        )
        rows = self._client.query_all(
            "SELECT person_id FROM std_person WHERE case_id=? AND display_name=? ORDER BY person_id DESC LIMIT 1;",
            (case_id, name),
        )
        if not rows:
            raise ValueError("创建人物失败")
        pid = int(rows[0][0])
        person = self.get_person(case_id, pid)
        assert person is not None
        return person

    def update_person(
        self,
        case_id: int,
        person_id: int,
        *,
        display_name: str | None = None,
        role_tag: str | None = None,
        notes: str | None = None,
    ) -> PersonInfo:
        person = self.get_person(case_id, person_id)
        if person is None:
            raise ValueError("人物不存在")
        self._client.execute(
            """
            UPDATE std_person
            SET display_name=COALESCE(?, display_name),
                role_tag=COALESCE(?, role_tag),
                notes=COALESCE(?, notes),
                updated_at=CURRENT_TIMESTAMP
            WHERE person_id=? AND case_id=?;
            """,
            (
                display_name.strip() if display_name is not None else None,
                role_tag,
                notes,
                person_id,
                case_id,
            ),
        )
        updated = self.get_person(case_id, person_id)
        assert updated is not None
        return updated

    def delete_person(self, case_id: int, person_id: int) -> None:
        self._client.execute("DELETE FROM std_person WHERE case_id=? AND person_id=?;", (case_id, person_id))

    def list_candidates(self, case_id: int, review_status: str = "pending") -> list[dict[str, Any]]:
        rows = self._client.query_all(
            """
            SELECT candidate_id, identifier_type, identifier_norm, display_value,
                   source_type, source_batch_id, source_ref_json, review_status, created_at
            FROM rel_identifier_candidate
            WHERE case_id=? AND review_status=?
            ORDER BY identifier_type, display_value, candidate_id;
            """,
            (case_id, review_status),
        )
        return [self._candidate_dict(row) for row in rows]

    def link_candidate(
        self,
        case_id: int,
        candidate_id: int,
        person_id: int,
    ) -> PersonInfo:
        rows = self._client.query_all(
            """
            SELECT identifier_type, identifier_norm, display_value, source_type, source_ref_json, review_status
            FROM rel_identifier_candidate
            WHERE case_id=? AND candidate_id=? LIMIT 1;
            """,
            (case_id, candidate_id),
        )
        if not rows:
            raise ValueError("候选标识不存在")
        identifier_type, identifier_norm, display_value, source_type, source_ref_json, status = rows[0]
        if str(status) != "pending":
            raise ValueError("候选标识已处理")
        person = self.get_person(case_id, person_id)
        if person is None:
            raise ValueError("人物不存在")
        self._client.execute(
            """
            INSERT INTO std_person_link(
                person_id, identifier_type, identifier_value, identifier_norm, source_type, source_ref_json
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                person_id,
                str(identifier_type),
                str(display_value),
                str(identifier_norm),
                str(source_type or "manual"),
                str(source_ref_json or "{}"),
            ),
        )
        self._client.execute(
            """
            UPDATE rel_identifier_candidate
            SET review_status='linked', updated_at=CURRENT_TIMESTAMP
            WHERE candidate_id=? AND case_id=?;
            """,
            (candidate_id, case_id),
        )
        updated = self.get_person(case_id, person_id)
        assert updated is not None
        return updated

    def link_candidate_new_person(
        self,
        case_id: int,
        candidate_id: int,
        display_name: str | None = None,
        role_tag: str = "unknown",
    ) -> PersonInfo:
        rows = self._client.query_all(
            """
            SELECT display_value, identifier_type FROM rel_identifier_candidate
            WHERE case_id=? AND candidate_id=? LIMIT 1;
            """,
            (case_id, candidate_id),
        )
        if not rows:
            raise ValueError("候选标识不存在")
        name = (display_name or str(rows[0][0])).strip()
        person = self.create_person(case_id, display_name=name, role_tag=role_tag)
        return self.link_candidate(case_id, candidate_id, person.person_id)

    def mark_candidate_no_match(self, case_id: int, candidate_id: int) -> None:
        rows = self._client.query_all(
            """
            SELECT 1 FROM rel_identifier_candidate
            WHERE case_id=? AND candidate_id=? AND review_status='pending' LIMIT 1;
            """,
            (case_id, candidate_id),
        )
        if not rows:
            raise ValueError("候选标识不存在或已处理")
        self._client.execute(
            """
            UPDATE rel_identifier_candidate
            SET review_status='no_match', updated_at=CURRENT_TIMESTAMP
            WHERE case_id=? AND candidate_id=? AND review_status='pending';
            """,
            (case_id, candidate_id),
        )

    def add_manual_link(
        self,
        case_id: int,
        person_id: int,
        *,
        identifier_type: str,
        identifier_value: str,
    ) -> PersonInfo:
        person = self.get_person(case_id, person_id)
        if person is None:
            raise ValueError("人物不存在")
        norm = normalize_identifier(identifier_type, identifier_value)
        if not norm:
            raise ValueError("标识值无效")
        self._client.execute(
            """
            INSERT INTO std_person_link(
                person_id, identifier_type, identifier_value, identifier_norm, source_type, source_ref_json
            ) VALUES (?, ?, ?, ?, 'manual', '{}');
            """,
            (person_id, identifier_type, identifier_value.strip(), norm),
        )
        self._client.execute(
            """
            UPDATE rel_identifier_candidate
            SET review_status='linked', updated_at=CURRENT_TIMESTAMP
            WHERE case_id=? AND identifier_type=? AND identifier_norm=? AND review_status='pending';
            """,
            (case_id, identifier_type, norm),
        )
        updated = self.get_person(case_id, person_id)
        assert updated is not None
        return updated

    def remove_link(self, case_id: int, person_id: int, link_id: int) -> None:
        person = self.get_person(case_id, person_id)
        if person is None:
            raise ValueError("人物不存在")
        self._client.execute(
            "DELETE FROM std_person_link WHERE link_id=? AND person_id=?;",
            (link_id, person_id),
        )

    def get_identifier_sets(self, case_id: int, person_id: int) -> dict[str, set[str]]:
        rows = self._client.query_all(
            """
            SELECT l.identifier_type, l.identifier_norm
            FROM std_person_link l
            JOIN std_person p ON p.person_id=l.person_id
            WHERE p.case_id=? AND p.person_id=?;
            """,
            (case_id, person_id),
        )
        buckets: dict[str, set[str]] = {}
        for identifier_type, identifier_norm in rows:
            key = str(identifier_type)
            buckets.setdefault(key, set()).add(str(identifier_norm))
        display_rows = self._client.query_all(
            "SELECT display_name FROM std_person WHERE case_id=? AND person_id=? LIMIT 1;",
            (case_id, person_id),
        )
        if display_rows:
            display_name = str(display_rows[0][0])
            name = normalize_identifier("person_name", display_name)
            same_name_rows = self._client.query_all(
                "SELECT display_name FROM std_person WHERE case_id=?;",
                (case_id,),
            )
            same_name_count = sum(
                1
                for (other_name,) in same_name_rows
                if normalize_identifier("person_name", str(other_name or "")) == name
            )
            if name and same_name_count == 1:
                buckets.setdefault("person_name", set()).add(name)
        return buckets

    def _ensure_case(self, case_id: int) -> None:
        rows = self._client.query_all("SELECT 1 FROM std_case WHERE case_id=? LIMIT 1;", (case_id,))
        if not rows:
            raise ValueError("案件不存在")

    def _person_with_links(self, row: tuple[Any, ...]) -> PersonInfo:
        person_id = int(row[0])
        link_rows = self._client.query_all(
            """
            SELECT link_id, identifier_type, identifier_value, identifier_norm, source_type, source_ref_json, created_at
            FROM std_person_link WHERE person_id=? ORDER BY identifier_type, identifier_value;
            """,
            (person_id,),
        )
        links = [
            {
                "link_id": int(lr[0]),
                "identifier_type": str(lr[1]),
                "identifier_value": str(lr[2]),
                "identifier_norm": str(lr[3]),
                "source_type": str(lr[4]),
                "source_ref": self._parse_json(str(lr[5] or "{}")),
                "created_at": str(lr[6]),
            }
            for lr in link_rows
        ]
        return PersonInfo(
            person_id=person_id,
            case_id=int(row[1]),
            display_name=str(row[2]),
            role_tag=str(row[3]),
            notes=str(row[4]),
            created_at=str(row[5]),
            updated_at=str(row[6]),
            links=links,
        )

    def _candidate_dict(self, row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "candidate_id": int(row[0]),
            "identifier_type": str(row[1]),
            "identifier_norm": str(row[2]),
            "display_value": str(row[3]),
            "source_type": str(row[4]),
            "source_batch_id": str(row[5]),
            "source_ref": self._parse_json(str(row[6] or "{}")),
            "review_status": str(row[7]),
            "created_at": str(row[8]),
        }

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


__all__ = ["PersonInfo", "PersonLinkService"]
