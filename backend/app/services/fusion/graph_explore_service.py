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
    "bank_txn": "资金关系",
    "wechat": "微信关系",
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

        all_nodes, all_edges = self._build_case_graph(case_id, relation_types, include_sample_records)
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

    def _build_case_graph(
        self,
        case_id: int,
        relation_types: set[str],
        include_sample_records: bool,
    ) -> tuple[dict[str, ExploreNode], dict[str, ExploreEdge]]:
        nodes: dict[str, ExploreNode] = {}
        edges: dict[str, ExploreEdge] = {}
        persons = self._person_links.list_persons(case_id)
        person_by_name: dict[str, str] = {}
        person_by_identifier: dict[tuple[str, str], str] = {}

        def add_node(node_id: str, label: str, node_type: str) -> None:
            if node_id not in nodes:
                nodes[node_id] = ExploreNode(id=node_id, label=label or node_id, type=node_type)

        def add_edge(source: str, target: str, relation_type: str, *, amount: float | None = None, duration: float | None = None, record: dict[str, Any] | None = None) -> None:
            if relation_type not in relation_types or not source or not target or source == target:
                return
            a, b = sorted([source, target]) if relation_type in {"identifier", "enterprise", "commercial"} else [source, target]
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

        batch_ids = self._case_batch_ids(case_id)
        for batch_id in batch_ids:
            source_type = self._batch_source_type(batch_id)
            if source_type == "bank" and "bank_txn" in relation_types:
                self._add_bank_edges(batch_id, nodes, add_node, add_edge, person_by_name, person_by_identifier)
            elif source_type == "telecom" and "telecom" in relation_types:
                self._add_raw_pair_edges(batch_id, "telecom", nodes, add_node, add_edge, person_by_identifier)
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
            record = {"record_type": "bank_txn", "time": str(row[3] or ""), "summary": str(row[8] or ""), "amount": amount, "source_ref": {"layer": "std", "table": "std_bank_txn", "pk": {"std_id": int(row[0])}, "batch_id": batch_id}}
            add_edge(left, right, "bank_txn", amount=amount, record=record)

    def _add_wechat_edges(self, batch_id: str, nodes: dict[str, ExploreNode], add_node: Any, add_edge: Any, person_by_name: dict[str, str], person_by_identifier: dict[tuple[str, str], str]) -> None:
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "wechat"):
            user = fields.get("用户侧账号名称") or fields.get("用户侧账户名称") or ""
            peer = fields.get("对手侧账户名称") or fields.get("对手方账户名称") or ""
            left = self._person_or_wechat(user, person_by_name, person_by_identifier, add_node)
            right = self._person_or_wechat(peer, person_by_name, person_by_identifier, add_node)
            amount_fen = self._to_float(fields.get("交易金额(分)") or fields.get("交易金额（分）") or fields.get("交易金额_分"))
            amount = amount_fen / 100.0 if amount_fen is not None else None
            record = {"record_type": "wechat", "time": fields.get("交易时间") or "", "summary": fields.get("交易业务类型") or "", "amount": amount, "source_ref": {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}}
            add_edge(left, right, "wechat", amount=amount, record=record)

    def _add_raw_pair_edges(self, batch_id: str, source_type: str, nodes: dict[str, ExploreNode], add_node: Any, add_edge: Any, person_by_identifier: dict[tuple[str, str], str]) -> None:
        for table, raw_id, fields in self._iter_raw_rows(batch_id, source_type):
            local = normalize_phone(str(fields.get("本机号码") or ""))
            peer = normalize_phone(str(fields.get("对方号码") or ""))
            if not local or not peer:
                continue
            left = person_by_identifier.get(("phone", local), f"phone:{local}")
            right = person_by_identifier.get(("phone", peer), f"phone:{peer}")
            add_node(f"phone:{local}", local, "phone")
            add_node(f"phone:{peer}", peer, "phone")
            duration = self._to_float(fields.get("呼叫时长")) or 0.0
            record = {"record_type": "telecom", "time": fields.get("呼叫开始时间") or fields.get("短信发送接收时间") or "", "summary": fields.get("通话类型") or fields.get("话单类型") or "", "amount": duration, "source_ref": {"layer": "raw", "table": table, "pk": {"raw_id": raw_id}, "batch_id": batch_id}}
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
        for table, raw_id, fields in self._iter_raw_rows(batch_id, "commercial"):
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
        person_id = person_by_name.get(norm) or person_by_identifier.get(("wechat_name", norm))
        if person_id:
            return person_id
        if norm:
            add_node(f"wechat:{norm}", name, "wechat")
            return f"wechat:{norm}"
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
        neigh: list[set[str]] = []
        rel_types: dict[str, set[str]] = defaultdict(set)
        for anchor in anchors[:2]:
            current = set()
            for edge in edges.values():
                other = ""
                if edge.source == anchor:
                    other = edge.target
                elif edge.target == anchor:
                    other = edge.source
                if other:
                    current.add(other)
                    rel_types[other].add(edge.type)
            neigh.append(current)
        common = sorted(neigh[0] & neigh[1]) if len(neigh) == 2 else []
        return [{"node_id": node_id, "label": nodes[node_id].label, "type": nodes[node_id].type, "relation_types": sorted(rel_types[node_id]), "paths": [[anchors[0], node_id, anchors[1]]]} for node_id in common if node_id in nodes]

    def _case_batch_ids(self, case_id: int) -> list[str]:
        return [str(row[0]) for row in self._client.query_all("SELECT import_batch_id FROM rel_case_batch WHERE case_id=? ORDER BY bound_at;", (case_id,))]

    def _batch_source_type(self, batch_id: str) -> str:
        rows = self._client.query_all("SELECT source_type FROM rel_case_batch WHERE import_batch_id=? LIMIT 1;", (batch_id,))
        return str(rows[0][0] or "") if rows else ""

    def _iter_raw_rows(self, batch_id: str, source_type: str):
        tables = self._client.query_all(
            "SELECT raw_table_name FROM meta_schema_registry WHERE source_type=?;",
            (source_type,),
        )
        for (table,) in tables:
            table_name = str(table)
            columns = {str(row[1]) for row in self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table_name)});")}
            if "import_batch_id" not in columns or "raw_payload" not in columns:
                continue
            sql = f"SELECT raw_id, raw_payload FROM {self._client.quote_ident(table_name)} WHERE import_batch_id=?;"
            for raw_id, raw_payload in self._client.query_all(sql, (batch_id,)):
                try:
                    fields = json.loads(str(raw_payload or "{}"))
                except json.JSONDecodeError:
                    fields = {}
                if isinstance(fields, dict):
                    yield table_name, int(raw_id), {str(k): str(v or "") for k, v in fields.items()}

    def _clone_node(self, node: ExploreNode) -> ExploreNode:
        return ExploreNode(id=node.id, label=node.label, type=node.type, depth=node.depth, is_anchor=node.is_anchor, anchor_index=node.anchor_index, degree=node.degree, stats=dict(node.stats))

    def _bump_node_stats(self, node: ExploreNode, relation_type: str) -> None:
        node.stats[relation_type] = node.stats.get(relation_type, 0) + 1

    def _to_float(self, value: Any) -> float | None:
        try:
            text = str(value or "").replace(",", "").strip()
            return float(text) if text else None
        except (TypeError, ValueError):
            return None
