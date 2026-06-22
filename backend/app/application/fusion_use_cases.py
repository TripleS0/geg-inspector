"""Fusion cockpit and person linking use cases."""

from __future__ import annotations

import json
from typing import Any

from app.application.bootstrap import bootstrap_database
from app.services.fusion.auto_link_service import AutoLinkService
from app.services.fusion.fusion_event_service import FusionEventService
from app.services.fusion.fusion_model_service import FusionModelService
from app.services.fusion.fusion_query_service import FusionQueryService
from app.services.fusion.graph_explore_service import GraphExploreService
from app.services.fusion.identifier_discovery_service import IdentifierDiscoveryService
from app.services.fusion.person_link_service import PersonLinkService
from app.services.fusion.record_detail_service import RecordDetailService
from app.services.shared.db.sqlite_client import SqliteClient


class FusionUseCase:
    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)
        self._discovery = IdentifierDiscoveryService(self._client)
        self._person_links = PersonLinkService(self._client)
        self._auto_link = AutoLinkService(self._client)
        self._fusion = FusionQueryService(self._client)
        self._graph_explore = GraphExploreService(self._client)
        self._records = RecordDetailService(self._client)
        self._models = FusionModelService(self._client)
        self._events = FusionEventService(self._client)

    def list_fusion_models(self, case_id: int) -> dict[str, Any]:
        return self._models.list_models(case_id)

    def save_fusion_models(self, case_id: int, updates: list[dict[str, Any]]) -> dict[str, Any]:
        return self._models.save_models(case_id, updates)

    def scan_fusion_events(
        self,
        case_id: int,
        *,
        start_date: str = "",
        end_date: str = "",
        keyword: str = "",
        event_type: str = "",
    ) -> dict[str, Any]:
        return self._events.scan_events(
            case_id,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            event_type=event_type,
        )

    def discover(self, case_id: int) -> dict[str, Any]:
        result = self._discovery.discover(case_id)
        return {"case_id": result.case_id, "inserted": result.inserted, "skipped": result.skipped}

    def auto_link(self, case_id: int, *, rediscover: bool = True) -> dict[str, Any]:
        result = self._auto_link.auto_link(case_id, rediscover=rediscover)
        return {
            "case_id": result.case_id,
            "persons_created": result.persons_created,
            "links_created": result.links_created,
            "skipped": result.skipped,
            "unresolved_pending": result.unresolved_pending,
            "person_names": result.person_names,
        }

    def list_persons(self, case_id: int) -> list[dict[str, Any]]:
        return [self._person_dict(p) for p in self._person_links.list_persons(case_id)]

    def get_person(self, case_id: int, person_id: int) -> dict[str, Any]:
        person = self._person_links.get_person(case_id, person_id)
        if person is None:
            raise ValueError("人物不存在")
        return self._person_dict(person)

    def create_person(
        self,
        case_id: int,
        *,
        display_name: str,
        role_tag: str = "unknown",
        notes: str = "",
    ) -> dict[str, Any]:
        person = self._person_links.create_person(case_id, display_name=display_name, role_tag=role_tag, notes=notes)
        return self._person_dict(person)

    def update_person(
        self,
        case_id: int,
        person_id: int,
        *,
        display_name: str | None = None,
        role_tag: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        person = self._person_links.update_person(
            case_id,
            person_id,
            display_name=display_name,
            role_tag=role_tag,
            notes=notes,
        )
        return self._person_dict(person)

    def delete_person(self, case_id: int, person_id: int) -> None:
        self._person_links.delete_person(case_id, person_id)

    def list_candidates(self, case_id: int, review_status: str = "pending") -> list[dict[str, Any]]:
        return self._person_links.list_candidates(case_id, review_status=review_status)

    def link_candidate(self, case_id: int, candidate_id: int, person_id: int) -> dict[str, Any]:
        person = self._person_links.link_candidate(case_id, candidate_id, person_id)
        return self._person_dict(person)

    def link_candidate_new_person(
        self,
        case_id: int,
        candidate_id: int,
        display_name: str | None = None,
        role_tag: str = "unknown",
    ) -> dict[str, Any]:
        person = self._person_links.link_candidate_new_person(
            case_id,
            candidate_id,
            display_name=display_name,
            role_tag=role_tag,
        )
        return self._person_dict(person)

    def mark_candidate_no_match(self, case_id: int, candidate_id: int) -> None:
        self._person_links.mark_candidate_no_match(case_id, candidate_id)

    def add_manual_link(
        self,
        case_id: int,
        person_id: int,
        *,
        identifier_type: str,
        identifier_value: str,
    ) -> dict[str, Any]:
        person = self._person_links.add_manual_link(
            case_id,
            person_id,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
        )
        return self._person_dict(person)

    def remove_link(self, case_id: int, person_id: int, link_id: int) -> None:
        self._person_links.remove_link(case_id, person_id, link_id)

    def person_cockpit(self, case_id: int, person_id: int) -> dict[str, Any]:
        return self._fusion.person_cockpit(case_id, person_id)

    def relation_cockpit(self, case_id: int, person_a_id: int, person_b_id: int) -> dict[str, Any]:
        return self._fusion.relation_cockpit(case_id, person_a_id, person_b_id)

    def anchor_cockpit(self, case_id: int, anchor_type: str, anchor_value: str) -> dict[str, Any]:
        return self._fusion.anchor_cockpit(case_id, anchor_type, anchor_value)

    def suggest_anchors(
        self,
        case_id: int,
        query: str,
        *,
        limit: int = 20,
        anchor_type: str = "auto",
    ) -> dict[str, Any]:
        return {"items": self._fusion.suggest_anchors(case_id, query, limit=limit, anchor_type=anchor_type)}

    def explore_graph(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._graph_explore.explore(case_id, payload)

    def graph_selection_detail(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._graph_explore.selection_detail(case_id, payload)

    def record_detail(self, source_ref_json: str) -> dict[str, Any]:
        try:
            source_ref = json.loads(source_ref_json)
        except json.JSONDecodeError as err:
            raise ValueError("ref 参数须为 JSON") from err
        if not isinstance(source_ref, dict):
            raise ValueError("ref 参数须为 JSON 对象")
        return self._records.get_detail(source_ref)

    @staticmethod
    def _person_dict(person: Any) -> dict[str, Any]:
        return {
            "person_id": person.person_id,
            "case_id": person.case_id,
            "display_name": person.display_name,
            "role_tag": person.role_tag,
            "notes": person.notes,
            "created_at": person.created_at,
            "updated_at": person.updated_at,
            "links": person.links,
        }


__all__ = ["FusionUseCase"]
