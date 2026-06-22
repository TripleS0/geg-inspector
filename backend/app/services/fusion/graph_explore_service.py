"""Multi-hop graph exploration service for case-bound fusion data."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.fusion.fusion_query_service import FusionQueryService
from app.services.fusion.identifier_norm import normalize_identifier
from app.services.fusion.person_link_service import PersonLinkService
from app.services.integration.commercial.ic_ingest_service import normalize_enterprise_name
from app.services.integration.telecom.phone_utils import normalize_phone
from app.services.shared.db.sqlite_client import SqliteClient

RELATION_LABELS = {
    "bank_txn": "银行关系",
    "wechat": "微信转账关系",
    "telecom": "通讯关系",
    "enterprise": "工商关系",
    "commercial": "商务关系",
    "identifier": "标识归属",
}

NODE_LABELS = {
    "person": "人物",
    "phone": "手机号",
    "bank_card": "银行卡/账号",
    "wechat": "微信",
    "enterprise": "企业",
    "commercial_event": "商务事件",
    "unknown": "其他",
}

IDENTIFIER_LABELS = {
    "phone": "手机号",
    "bank_card": "银行卡",
    "bank_acct": "银行账号",
    "wechat_name": "微信名",
    "enterprise_name": "企业名称",
    "person_name": "姓名",
}

EDGE_RECORD_TYPES = {
    "bank_txn": "bank_txn",
    "wechat": "wechat",
    "telecom": "telecom",
    "enterprise": "enterprise",
    "commercial": "commercial",
}

DEFAULT_RELATION_TYPES = set(RELATION_LABELS)


@dataclass
class ExploreNode:
    id: str
    label: str
    type: str
    depth: int = 999
    is_anchor: bool = False
    anchor_index: int | None = None
    degree: int = 0
    stats: dict[str, int] = field(default_factory=dict)
    identifiers: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ExploreEdge:
    id: str
    source: str
    target: str
    type: str
    weight: int = 1
    amount: float | None = None
    duration_sec: float | None = None
    record_count: int = 1
    sample_records: list[dict[str, Any]] = field(default_factory=list)


class GraphExploreService:
    """Build an expandable graph from linked persons and cross-source records."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self._person_links = PersonLinkService(self._client)
        self._fusion = FusionQueryService(self._client)

    def explore(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        anchors_payload = payload.get("anchors") or []
        if not anchors_payload:
            raise ValueError("请至少选择一个中心对象")
        relation_types = set(payload.get("relation_types") or DEFAULT_RELATION_TYPES) & DEFAULT_RELATION_TYPES
        if not relation_types:
            raise ValueError("请至少选择一种关系类型")
        display_level = max(1, int(payload.get("display_level") or 2))
        unlimited = bool(payload.get("unlimited"))
        max_depth = 10 if unlimited else max(0, display_level - 1)
        max_nodes = max(1, min(int(payload.get("max_nodes") or 500), 1000))
        max_edges = max(1, min(int(payload.get("max_edges") or 1500), 3000))
        min_weight = max(1, int(payload.get("min_weight") or 1))
        include_sample_records = bool(payload.get("include_sample_records", True))

        batch_ids = self._case_batch_ids(case_id)
        if not batch_ids:
            return {
                "case_id": case_id,
                "anchors": [],
                "display_level": display_level,
                "unlimited": unlimited,
                "truncated": False,
                "truncated_reason": "该案件尚未绑定数据批次，无法构建关系图谱",
                "nodes": [],
                "edges": [],
                "paths": [],
                "common_neighbors": [],
                "summary": {
                    "node_count": 0,
                    "edge_count": 0,
                    "path_count": 0,
                    "common_neighbor_count": 0,
                    "relation_type_counts": {},
                    "depth_counts": {},
                },
            }

        all_nodes, all_edges = self._build_case_graph(case_id, relation_types, include_sample_records, batch_ids)
        anchor_ids = [self._resolve_anchor(case_id, item, all_nodes) for item in anchors_payload[:2]]
        anchor_ids = [node_id for node_id in anchor_ids if node_id]
        if not anchor_ids:
            raise ValueError("未找到有效中心对象")

        adjacency: dict[str, list[ExploreEdge]] = defaultdict(list)
        filtered_edges = [edge for edge in all_edges.values() if edge.weight >= min_weight]
        for edge in filtered_edges:
            adjacency[edge.source].append(edge)
            adjacency[edge.target].append(edge)

        visible_nodes: dict[str, ExploreNode] = {}
        visible_edges: dict[str, ExploreEdge] = {}
        q: deque[tuple[str, int]] = deque()
        for idx, node_id in enumerate(anchor_ids):
            if node_id in all_nodes:
                node = self._clone_node(all_nodes[node_id])
                node.depth = 0
                node.is_anchor = True
                node.anchor_index = idx
                visible_nodes[node_id] = node
                q.append((node_id, 0))

        truncated = False
        truncated_reason = ""
        visited_depth = {node_id: 0 for node_id in visible_nodes}
        while q:
            node_id, depth = q.popleft()
            if depth >= max_depth:
                continue
            if time.monotonic() - started > 5:
                truncated = True
                truncated_reason = "图谱扩张超过 5 秒安全限制"
                break
            for edge in adjacency.get(node_id, []):
                if len(visible_edges) >= max_edges:
                    truncated = True
                    truncated_reason = f"已达到关系上限 {max_edges}"
                    break
                other = edge.target if edge.source == node_id else edge.source
                visible_edges[edge.id] = edge
                if other not in visible_nodes:
                    if len(visible_nodes) >= max_nodes:
                        truncated = True
                        truncated_reason = f"已达到节点上限 {max_nodes}"
                        break
                    node = self._clone_node(all_nodes[other])
                    node.depth = depth + 1
                    visible_nodes[other] = node
                    visited_depth[other] = depth + 1
                    q.append((other, depth + 1))
                elif depth + 1 < visited_depth.get(other, 999):
                    visible_nodes[other].depth = depth + 1
                    visited_depth[other] = depth + 1
                    q.append((other, depth + 1))
            if truncated:
                break

        for edge in visible_edges.values():
            if edge.source in visible_nodes:
                self._bump_node_stats(visible_nodes[edge.source], edge.type)
            if edge.target in visible_nodes:
                self._bump_node_stats(visible_nodes[edge.target], edge.type)

        paths = self._find_paths(anchor_ids, visible_edges, max_depth=max(2, min(max_depth, 5))) if len(anchor_ids) >= 2 else []
        common_neighbors = self._common_neighbors(anchor_ids, visible_edges, visible_nodes) if len(anchor_ids) >= 2 else []

        nodes_payload = []
        for node in visible_nodes.values():
            node.degree = sum(1 for edge in visible_edges.values() if edge.source == node.id or edge.target == node.id)
            node.identifiers = self._resolve_node_identifiers(case_id, node.id, node.label)
            item = asdict(node)
            item["display_type"] = NODE_LABELS.get(node.type, node.type)
            nodes_payload.append(item)

        edges_payload = []
        for edge in visible_edges.values():
            item = asdict(edge)
            item["display_type"] = RELATION_LABELS.get(edge.type, edge.type)
            edges_payload.append(item)

        relation_counts = Counter(edge.type for edge in visible_edges.values())
        depth_counts = Counter(str(node.depth) for node in visible_nodes.values())
        return {
            "case_id": case_id,
            "anchors": anchor_ids,
            "display_level": display_level,
            "unlimited": unlimited,
            "truncated": truncated,
            "truncated_reason": truncated_reason or None,
            "nodes": sorted(nodes_payload, key=lambda x: (x["depth"], x["type"], x["label"])),
            "edges": sorted(edges_payload, key=lambda x: (x["type"], -x["weight"])),
            "paths": paths[:30],
            "common_neighbors": common_neighbors[:50],
            "summary": {
                "node_count": len(visible_nodes),
                "edge_count": len(visible_edges),
                "path_count": len(paths),
                "common_neighbor_count": len(common_neighbors),
                "relation_type_counts": dict(relation_counts),
                "depth_counts": dict(depth_counts),
            },
        }

    def selection_detail(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Return full records, identifiers and chart stats for a graph node or edge."""
        kind = str(payload.get("kind") or "").strip()
        date_from = str(payload.get("date_from") or "").strip()
        date_to = str(payload.get("date_to") or "").strip()
        batch_ids = self._case_batch_ids(case_id)
        if not batch_ids:
            raise ValueError("该案件尚未绑定数据批次")

        if kind == "node":
            node_id = str(payload.get("node_id") or "").strip()
            if not node_id:
                raise ValueError("缺少 node_id")
            identifiers = self._resolve_node_identifiers(case_id, node_id)
            label = self._node_display_label(case_id, node_id)
            ids = self._ids_for_node(case_id, node_id)
            records = self._fusion._collect_records(batch_ids, ids)
            records = self._filter_records_by_date(records, date_from, date_to)
            kpis = self._fusion._build_kpis(records)
            charts = self._fusion._build_person_charts(case_id, records, label)
            return {
                "kind": "node",
                "label": label,
                "identifiers": identifiers,
                "records": [asdict(rec) for rec in records],
                "charts": charts,
                "kpis": kpis,
            }

        if kind == "edge":
            source = str(payload.get("source") or "").strip()
            target = str(payload.get("target") or "").strip()
            edge_type = str(payload.get("edge_type") or "").strip()
            if not source or not target:
                raise ValueError("缺少 source 或 target")
            label_a = self._node_display_label(case_id, source)
            label_b = self._node_display_label(case_id, target)
            ids_a = self._ids_for_node(case_id, source)
            ids_b = self._ids_for_node(case_id, target)
            records_a = self._fusion._collect_records(batch_ids, ids_a)
            records_b = self._fusion._collect_records(batch_ids, ids_b)
            records = self._fusion._direct_relation_records(records_a, records_b, ids_a, ids_b, label_a, label_b)
            record_type = EDGE_RECORD_TYPES.get(edge_type)
            if record_type:
                records = [rec for rec in records if rec.record_type == record_type]
            records = self._filter_records_by_date(records, date_from, date_to)
            kpis = self._fusion._build_kpis(records)
            charts = self._fusion._build_relation_charts(records, label_a, label_b, [])
            return {
                "kind": "edge",
                "label": f"{label_a} → {label_b}",
                "identifiers": [],
                "records": [asdict(rec) for rec in records],
                "charts": charts,
                "kpis": kpis,
            }

        raise ValueError("kind 须为 node 或 edge")

    def _build_case_graph(
        self,
        case_id: int,
        relation_types: set[str],
        include_sample_records: bool,
        batch_ids: list[str] | None = None,
    ) -> tuple[dict[str, ExploreNode], dict[str, ExploreEdge]]:
        nodes: dict[str, ExploreNode] = {}
        edges: dict[str, ExploreEdge] = {}
        scoped_batch_ids = batch_ids if batch_ids is not None else self._case_batch_ids(case_id)
        if not scoped_batch_ids:
            return nodes, edges

        persons = self._person_links.list_persons(case_id)
        person_by_name: dict[str, str] = {}
        person_by_identifier: dict[tuple[str, str], str] = {}
        phone_to_person: dict[str, str] = {}

        def add_node(node_id: str, label: str, node_type: str) -> None:
            if node_id not in nodes:
                nodes[node_id] = ExploreNode(id=node_id, label=label or node_id, type=node_type)

        def resolve_phone_node(phone_norm: str) -> str:
            if not phone_norm:
                return ""
            person_id = phone_to_person.get(phone_norm) or person_by_identifier.get(("phone", phone_norm))
            if person_id:
                return person_id
            node_id = f"phone:{phone_norm}"
            add_node(node_id, phone_norm, "phone")
            return node_id

        def add_edge(source: str, target: str, relation_type: str, *, amount: float | None = None, duration: float | None = None, record: dict[str, Any] | None = None) -> None:
            if relation_type not in relation_types or not source or not target or source == target:
                return
            undirected = relation_type in {"identifier", "enterprise", "commercial", "bank_txn", "wechat", "telecom"}
            a, b = sorted([source, target]) if undirected else [source, target]
            edge_id = f"{relation_type}:{a}:{b}"
            edge = edges.get(edge_id)
            if edge is None:
                edge = ExploreEdge(id=edge_id, source=a, target=b, type=relation_type, amount=0.0 if amount is not None else None, duration_sec=0.0 if duration is not None else None, record_count=0)
                edges[edge_id] = edge
            edge.weight += 1 if edge.record_count else 0
            edge.record_count += 1
            if amount is not None:
                edge.amount = round((edge.amount or 0.0) + abs(amount), 2)
            if duration is not None:
                edge.duration_sec = round((edge.duration_sec or 0.0) + duration, 2)
            if include_sample_records and record and len(edge.sample_records) < 5:
                edge.sample_records.append(record)

        for person in persons:
            person_id = f"person:{person.person_id}"
            add_node(person_id, person.display_name, "person")
            person_by_name[normalize_identifier("person_name", person.display_name)] = person_id
            person_by_name[normalize_identifier("wechat_name", person.display_name)] = person_id
            for link in person.links:
                ltype = str(link.get("identifier_type") or "")
                norm = str(link.get("identifier_norm") or "")
                value = str(link.get("identifier_value") or norm)
                person_by_identifier[(ltype, norm)] = person_id
                if ltype == "phone":
                    node_id, ntype = f"phone:{norm}", "phone"
                elif ltype in {"bank_card", "bank_acct"}:
                    node_id, ntype = f"bank_card:{norm}", "bank_card"
                elif ltype == "wechat_name":
                    node_id, ntype = f"wechat:{norm}", "wechat"
                elif ltype == "enterprise_name":
                    node_id, ntype = f"enterprise:{norm}", "enterprise"
                else:
                    node_id, ntype = f"{ltype}:{norm}", "unknown"
                add_node(node_id, value, ntype)
                add_edge(person_id, node_id, "identifier")

        phone_to_person.update(self._build_phone_person_map(case_id, scoped_batch_ids, person_by_name, person_by_identifier))

        for batch_id in scoped_batch_ids:
            source_type = self._fusion._batch_source_type(batch_id)
            if source_type == "bank" and "bank_txn" in relation_types:
                self._add_bank_edges(batch_id, nodes, add_node, add_edge, person_by_name, person_by_identifier)
            elif source_type == "telecom" and "telecom" in relation_types:
                self._add_raw_pair_edges(batch_id, "telecom", add_node, add_edge, resolve_phone_node, phone_to_person, person_by_name)
            elif source_type == "wechat" and "wechat" in relation_types:
                self._add_wechat_edges(batch_id, nodes, add_node, add_edge, person_by_name, person_by_identifier)
            elif source_type == "enterprise" and "enterprise" in relation_types:
                self._add_enterprise_edges(batch_id, nodes, add_node, add_edge, person_by_name)
            elif source_type == "commercial" and "commercial" in relation_types:
                self._add_commercial_edges(batch_id, nodes, add_node, add_edge)
        return nodes, edges

    def _add_bank_edges(self, batch_id: str, nodes: dict[str, ExploreNode], add_node: Any, add_edge: Any, person_by_name: dict[str, str], person_by_identifier: dict[tuple[str, str], str]) -> None:
        rows = self._client.query_all("""
            SELECT std_id, person_name, acct_no, txn_time, txn_amount, txn_direction, counterparty_name, counterparty_account, summary
            FROM std_bank_txn WHERE import_batch_id=?;
        """, (batch_id,))
        for row in rows:
            left = self._person_or_bank(str(row[1] or ""), str(row[2] or ""), person_by_name, person_by_identifier, add_node)
            right = self._person_or_bank(str(row[6] or ""), str(row[7] or ""), person_by_name, person_by_identifier, add_node)
            amount = self._to_float(row[4])
            counterparty = str(row[6] or row[7] or "")
            record = {"record_type": "bank_txn", "time": str(row[3] or ""), "summary": str(row[8] or ""), "amount": amount, "counterparty": counterparty, "source_ref": {"layer": "std", "table": "std_bank_txn", "pk": {"std_id": int(row[0])}, "batch_id": batch_id}}
            add_edge(left, right, "bank_txn", amount=amount, record=record)

    def _add_wechat_edges(self, batch_id: str, nodes: dict[str, ExploreNode], add_node: Any, add_edge: Any, person_by_name: dict[str, str], person_by_identifier: dict[tuple[str, str], str]) -> None:
        for table, raw_id, fields in self._fusion._iter_raw_rows(batch_id, "wechat"):
            user = self._fusion._raw_field(fields, "用户侧账号名称", "用户侧账户名称")
            peer = self._fusion._raw_field(fields, "对手侧账户名称", "对手方账户名称")
            left = self._person_or_wechat(user, person_by_name, person_by_identifier, add_node)
            right = self._person_or_wechat(peer, person_by_name, person_by_identifier, add_node)
            amount_fen = self._to_float(self._fusion._raw_field(fields, "交易金额(分)", "交易金额（分）", "交易金额_分"))
            amount = amount_fen / 100.0 if amount_fen is not None else None
            record = {"record_type": "wechat", "time": self._fusion._raw_field(fields, "交易时间") or "", "summary": self._fusion._raw_field(fields, "交易业务类型") or "", "amount": amount, "counterparty": peer, "source_ref": {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}}
            add_edge(left, right, "wechat", amount=amount, record=record)

    def _add_raw_pair_edges(
        self,
        batch_id: str,
        source_type: str,
        add_node: Any,
        add_edge: Any,
        resolve_phone_node: Any,
        phone_to_person: dict[str, str],
        person_by_name: dict[str, str],
    ) -> None:
        for table, raw_id, fields in self._fusion._iter_raw_rows(batch_id, source_type):
            local = normalize_phone(self._fusion._raw_field(fields, "本机号码"))
            peer = normalize_phone(self._fusion._raw_field(fields, "对方号码"))
            if not local or not peer:
                continue
            owner = self._fusion._raw_field(fields, "机主姓名", "用户姓名", "姓名")
            if owner:
                owner_norm = normalize_identifier("person_name", owner)
                if owner_norm in person_by_name:
                    phone_to_person[local] = person_by_name[owner_norm]
            left = resolve_phone_node(local)
            right = resolve_phone_node(peer)
            duration = self._to_float(self._fusion._raw_field(fields, "呼叫时长")) or 0.0
            call_time = self._fusion._raw_field(fields, "呼叫开始时间", "短信发送接收时间")
            record = {"record_type": "telecom", "time": call_time, "summary": self._fusion._raw_field(fields, "通话类型", "话单类型") or "", "amount": duration, "counterparty": peer, "source_ref": {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}}
            add_edge(left, right, "telecom", duration=duration, record=record)

    def _add_enterprise_edges(self, batch_id: str, nodes: dict[str, ExploreNode], add_node: Any, add_edge: Any, person_by_name: dict[str, str]) -> None:
        rows = self._client.query_all("SELECT enterprise_id, enterprise_name, enterprise_name_norm, legal_person, shareholders_json, key_persons_json FROM std_enterprise_profile WHERE import_batch_id=?;", (batch_id,))
        for row in rows:
            ent_id = f"enterprise:{row[2]}"
            add_node(ent_id, str(row[1] or row[2]), "enterprise")
            names = [str(row[3] or "")]
            for raw in (str(row[4] or "[]"), str(row[5] or "[]")):
                try:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        names.extend(str(item.get("name") if isinstance(item, dict) else item) for item in data)
                except json.JSONDecodeError:
                    pass
            for name in names:
                norm = normalize_identifier("person_name", name)
                if not norm:
                    continue
                pid = person_by_name.get(norm, f"person_name:{norm}")
                add_node(pid, name, "person" if pid.startswith("person:") else "unknown")
                add_edge(pid, ent_id, "enterprise", record={"record_type": "enterprise", "summary": f"{name} 关联 {row[1]}", "source_ref": {"layer": "std", "table": "std_enterprise_profile", "pk": {"enterprise_id": int(row[0])}, "batch_id": batch_id}})

    def _add_commercial_edges(self, batch_id: str, nodes: dict[str, ExploreNode], add_node: Any, add_edge: Any) -> None:
        for table, raw_id, fields in self._fusion._iter_raw_rows(batch_id, "commercial"):
            event = fields.get("询价单号") or fields.get("项目名称") or f"商务记录{raw_id}"
            event_id = f"commercial_event:{normalize_identifier('person_name', event) or raw_id}"
            add_node(event_id, event, "commercial_event")
            for name in {fields.get("公司名称") or "", fields.get("供应商") or "", fields.get("采购单位") or "", fields.get("中标供应商") or ""}:
                norm = normalize_enterprise_name(name)
                if not norm:
                    continue
                ent_id = f"enterprise:{norm}"
                add_node(ent_id, name, "enterprise")
                add_edge(ent_id, event_id, "commercial", amount=self._to_float(fields.get("中标金额") or fields.get("中标金额(元)") or fields.get("含税单价")), record={"record_type": "commercial", "summary": event, "source_ref": {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}})

    def _person_or_bank(self, name: str, acct: str, person_by_name: dict[str, str], person_by_identifier: dict[tuple[str, str], str], add_node: Any) -> str:
        name_norm = normalize_identifier("person_name", name)
        acct_norm = normalize_identifier("bank_acct", acct)
        if name_norm in person_by_name:
            return person_by_name[name_norm]
        if acct_norm and ("bank_acct", acct_norm) in person_by_identifier:
            return person_by_identifier[("bank_acct", acct_norm)]
        if acct_norm and ("bank_card", acct_norm) in person_by_identifier:
            return person_by_identifier[("bank_card", acct_norm)]
        if acct_norm:
            add_node(f"bank_card:{acct_norm}", acct or name or acct_norm, "bank_card")
            return f"bank_card:{acct_norm}"
        if name_norm:
            add_node(f"person_name:{name_norm}", name, "unknown")
            return f"person_name:{name_norm}"
        return ""

    def _person_or_wechat(self, name: str, person_by_name: dict[str, str], person_by_identifier: dict[tuple[str, str], str], add_node: Any) -> str:
        norm = normalize_identifier("wechat_name", name)
        name_norm = normalize_identifier("person_name", name)
        person_id = person_by_name.get(norm) or person_by_name.get(name_norm) or person_by_identifier.get(("wechat_name", norm))
        if person_id:
            return person_id
        if norm:
            add_node(f"wechat:{norm}", name, "wechat")
            return f"wechat:{norm}"
        if name_norm:
            add_node(f"person_name:{name_norm}", name, "unknown")
            return f"person_name:{name_norm}"
        return ""

    def _resolve_anchor(self, case_id: int, item: dict[str, Any], nodes: dict[str, ExploreNode]) -> str:
        kind = str(item.get("type") or "person")
        value = str(item.get("value") or "").strip()
        if not value:
            return ""
        if kind == "person":
            node_id = f"person:{value}"
            if node_id in nodes:
                return node_id
        if value in nodes:
            return value
        norm = normalize_phone(value) if kind == "phone" else normalize_identifier(kind, value)
        candidates = [f"{kind}:{norm}", f"person_name:{norm}", f"wechat:{norm}", f"bank_card:{norm}"]
        return next((c for c in candidates if c in nodes), "")

    def _find_paths(self, anchors: list[str], edges: dict[str, ExploreEdge], max_depth: int) -> list[dict[str, Any]]:
        start, target = anchors[0], anchors[1]
        adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
        edge_map = {edge.id: edge for edge in edges.values()}
        for edge in edges.values():
            adjacency[edge.source].append((edge.target, edge.id))
            adjacency[edge.target].append((edge.source, edge.id))
        found: list[dict[str, Any]] = []
        q: deque[tuple[str, list[str], list[str]]] = deque([(start, [start], [])])
        while q and len(found) < 30:
            node, path_nodes, path_edges = q.popleft()
            if len(path_edges) >= max_depth:
                continue
            for nxt, edge_id in adjacency.get(node, []):
                if nxt in path_nodes:
                    continue
                next_nodes = path_nodes + [nxt]
                next_edges = path_edges + [edge_id]
                if nxt == target:
                    found.append({"id": f"path-{len(found) + 1}", "source_anchor": start, "target_anchor": target, "length": len(next_edges), "nodes": next_nodes, "edges": next_edges, "relation_types": sorted({edge_map[e].type for e in next_edges})})
                else:
                    q.append((nxt, next_nodes, next_edges))
        return found

    def _common_neighbors(self, anchors: list[str], edges: dict[str, ExploreEdge], nodes: dict[str, ExploreNode]) -> list[dict[str, Any]]:
        """两人共同关联的企业：仅统计双方均通过工商关系连到的企业节点。"""
        if len(anchors) < 2:
            return []

        def enterprise_neighbors(anchor: str) -> set[str]:
            linked: set[str] = set()
            for edge in edges.values():
                if edge.type != "enterprise":
                    continue
                other = ""
                if edge.source == anchor:
                    other = edge.target
                elif edge.target == anchor:
                    other = edge.source
                if not other:
                    continue
                other_node = nodes.get(other)
                if other_node and other_node.type == "enterprise":
                    linked.add(other)
            return linked

        ent_a = enterprise_neighbors(anchors[0])
        ent_b = enterprise_neighbors(anchors[1])
        common = sorted(ent_a & ent_b)
        result: list[dict[str, Any]] = []
        for node_id in common:
            if node_id not in nodes:
                continue
            node = nodes[node_id]
            result.append(
                {
                    "node_id": node_id,
                    "label": node.label,
                    "type": node.type,
                    "relation_types": ["enterprise"],
                    "paths": [[anchors[0], node_id, anchors[1]]],
                }
            )
        return result

    def _case_batch_ids(self, case_id: int) -> list[str]:
        return [str(row[0]) for row in self._client.query_all("SELECT import_batch_id FROM rel_case_batch WHERE case_id=? ORDER BY bound_at;", (case_id,))]

    def _batch_source_type(self, batch_id: str) -> str:
        return self._fusion._batch_source_type(batch_id)

    def _build_phone_person_map(
        self,
        case_id: int,
        batch_ids: list[str],
        person_by_name: dict[str, str],
        person_by_identifier: dict[tuple[str, str], str],
    ) -> dict[str, str]:
        phone_map: dict[str, str] = {}
        for (itype, norm), person_id in person_by_identifier.items():
            if itype == "phone" and norm:
                phone_map[norm] = person_id
        for batch_id in batch_ids:
            if self._fusion._batch_source_type(batch_id) != "bank":
                continue
            rows = self._client.query_all(
                """
                SELECT person_name, mobile FROM std_bank_account
                WHERE import_batch_id=? AND COALESCE(mobile, '') != '';
                """,
                (batch_id,),
            )
            for person_name, mobile in rows:
                phone_norm = normalize_phone(str(mobile or ""))
                name_norm = normalize_identifier("person_name", str(person_name or ""))
                if phone_norm and name_norm in person_by_name:
                    phone_map[phone_norm] = person_by_name[name_norm]
        return phone_map

    def _resolve_node_identifiers(self, case_id: int, node_id: str, label: str = "") -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if node_id.startswith("person:"):
            try:
                person_id = int(node_id.split(":", 1)[1])
            except ValueError:
                return out
            person = self._person_links.get_person(case_id, person_id)
            if person is None:
                return out
            for link in person.links:
                identifier_type = str(link.get("identifier_type") or "")
                out.append(
                    {
                        "identifier_type": identifier_type,
                        "identifier_value": str(link.get("identifier_value") or ""),
                        "display_label": IDENTIFIER_LABELS.get(identifier_type, identifier_type),
                    }
                )
            return out
        if ":" not in node_id:
            return out
        prefix, norm = node_id.split(":", 1)
        type_map = {
            "phone": "phone",
            "bank_card": "bank_card",
            "bank_acct": "bank_acct",
            "wechat": "wechat_name",
            "enterprise": "enterprise_name",
            "person_name": "person_name",
        }
        identifier_type = type_map.get(prefix, prefix)
        out.append(
            {
                "identifier_type": identifier_type,
                "identifier_value": label or norm,
                "display_label": IDENTIFIER_LABELS.get(identifier_type, identifier_type),
            }
        )
        return out

    def _ids_for_node(self, case_id: int, node_id: str) -> dict[str, set[str]]:
        if node_id.startswith("person:"):
            try:
                person_id = int(node_id.split(":", 1)[1])
            except ValueError:
                return defaultdict(set)
            return self._person_links.get_identifier_sets(case_id, person_id)
        ids: dict[str, set[str]] = defaultdict(set)
        if ":" not in node_id:
            return ids
        prefix, norm = node_id.split(":", 1)
        if prefix == "phone":
            ids["phone"].add(norm)
        elif prefix in {"bank_card", "bank_acct"}:
            ids["bank_card"].add(norm)
            ids["bank_acct"].add(norm)
        elif prefix == "wechat":
            ids["wechat_name"].add(norm)
        elif prefix == "enterprise":
            ids["enterprise_name"].add(norm)
        elif prefix == "person_name":
            ids["person_name"].add(norm)
        return ids

    def _node_display_label(self, case_id: int, node_id: str) -> str:
        if node_id.startswith("person:"):
            try:
                person_id = int(node_id.split(":", 1)[1])
                person = self._person_links.get_person(case_id, person_id)
                if person:
                    return person.display_name
            except ValueError:
                pass
        return node_id.split(":", 1)[-1] if ":" in node_id else node_id

    @staticmethod
    def _filter_records_by_date(records: list[Any], date_from: str, date_to: str) -> list[Any]:
        if not date_from and not date_to:
            return records
        filtered: list[Any] = []
        for rec in records:
            time_value = getattr(rec, "time", None) or ""
            day = str(time_value)[:10]
            if not day:
                continue
            if date_from and day < date_from:
                continue
            if date_to and day > date_to:
                continue
            filtered.append(rec)
        return filtered

    def _clone_node(self, node: ExploreNode) -> ExploreNode:
        return ExploreNode(
            id=node.id,
            label=node.label,
            type=node.type,
            depth=node.depth,
            is_anchor=node.is_anchor,
            anchor_index=node.anchor_index,
            degree=node.degree,
            stats=dict(node.stats),
            identifiers=list(node.identifiers),
        )

    def _bump_node_stats(self, node: ExploreNode, relation_type: str) -> None:
        node.stats[relation_type] = node.stats.get(relation_type, 0) + 1

    def _to_float(self, value: Any) -> float | None:
        try:
            text = str(value or "").replace(",", "").strip()
            return float(text) if text else None
        except (TypeError, ValueError):
            return None
