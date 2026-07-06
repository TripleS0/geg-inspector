import type { FusionRecord, GraphExploreEdge, GraphExploreNode } from "../api";

type GraphNodeLookup = Map<string, GraphExploreNode> | GraphExploreNode[];

function labelForNode(nodeId: string, nodes: GraphNodeLookup) {
  if (Array.isArray(nodes)) return nodes.find((node) => node.id === nodeId)?.label || nodeId;
  return nodes.get(nodeId)?.label || nodeId;
}

const RECORD_TYPE_LABELS: Record<string, string> = {
  bank_txn: "银行流水",
  wechat: "微信转账",
  telecom: "通讯话单",
  enterprise: "工商主体",
  commercial: "商务网",
};

export function graphRecordTypeLabel(recordType: string) {
  return RECORD_TYPE_LABELS[recordType] || recordType;
}

export function normalizeGraphSampleRecord(
  raw: Record<string, unknown>,
  context?: { edge?: GraphExploreEdge; nodeLabel?: string }
): FusionRecord | null {
  const sourceRef = raw.source_ref;
  if (!sourceRef || typeof sourceRef !== "object") return null;
  const recordType = String(raw.record_type || context?.edge?.type || "unknown");
  const summary = String(raw.summary || raw.title || context?.edge?.display_type || "记录");
  const amountRaw = raw.amount;
  const amount =
    typeof amountRaw === "number"
      ? amountRaw
      : amountRaw !== null && amountRaw !== undefined && amountRaw !== ""
        ? Number(amountRaw)
        : null;
  return {
    record_type: recordType,
    title: summary,
    time: raw.time ? String(raw.time) : null,
    amount: Number.isFinite(amount as number) ? (amount as number) : null,
    counterparty: String(raw.counterparty || context?.nodeLabel || ""),
    summary,
    source_ref: sourceRef as Record<string, unknown>,
    batch_id: raw.batch_id ? String(raw.batch_id) : undefined,
  };
}

export function recordsFromEdge(
  edge: GraphExploreEdge,
  parties?: { partyA?: string; partyB?: string }
): FusionRecord[] {
  const out: FusionRecord[] = [];
  const seen = new Set<string>();
  for (const raw of edge.sample_records || []) {
    const rec = normalizeGraphSampleRecord(raw as Record<string, unknown>, { edge });
    if (!rec) continue;
    const key = JSON.stringify(rec.source_ref);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ ...rec, flow_party_a: parties?.partyA, flow_party_b: parties?.partyB });
  }
  return out;
}

export function recordsFromPath(
  path: { nodes: string[]; edges: string[] },
  edges: GraphExploreEdge[],
  nodes: GraphNodeLookup
): FusionRecord[] {
  const edgeMap = new Map(edges.map((edge) => [edge.id, edge]));
  const out: FusionRecord[] = [];
  const seen = new Set<string>();
  path.edges.forEach((edgeId, hopIndex) => {
    const edge = edgeMap.get(edgeId);
    if (!edge) return;
    const partyA = labelForNode(path.nodes[hopIndex], nodes);
    const partyB = labelForNode(path.nodes[hopIndex + 1], nodes);
    for (const rec of recordsFromEdge(edge, { partyA, partyB })) {
      const key = `${edge.id}:${JSON.stringify(rec.source_ref)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(rec);
    }
  });
  return out;
}

export function recordsFromNode(node: GraphExploreNode, edges: GraphExploreEdge[]): FusionRecord[] {
  const out: FusionRecord[] = [];
  const seen = new Set<string>();
  for (const edge of edges) {
    if (edge.source !== node.id && edge.target !== node.id) continue;
    for (const raw of edge.sample_records || []) {
      const rec = normalizeGraphSampleRecord(raw as Record<string, unknown>, { edge, nodeLabel: node.label });
      if (!rec) continue;
      const key = JSON.stringify(rec.source_ref);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(rec);
    }
  }
  return out;
}

export function recordsForGraphSelection(input: {
  node?: GraphExploreNode | null;
  edge?: GraphExploreEdge | null;
  edges?: GraphExploreEdge[];
}): FusionRecord[] {
  if (input.edge) return recordsFromEdge(input.edge);
  if (input.node && input.edges) return recordsFromNode(input.node, input.edges);
  return [];
}

export function recordsForObservationItem(
  item: { kind: "node" | "edge"; node?: GraphExploreNode; edge?: GraphExploreEdge; records?: FusionRecord[] },
  edges?: GraphExploreEdge[]
): FusionRecord[] {
  if (item.records?.length) return item.records;
  if (item.kind === "edge" && item.edge) return recordsFromEdge(item.edge);
  if (item.kind === "node" && item.node && edges) return recordsFromNode(item.node, edges);
  return [];
}

export function formatFusionAmount(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
