import type { FusionRecord, GraphExploreEdge, GraphExploreNode, GraphExplorePath } from "../api";

export type GraphObservationKind = "node" | "edge" | "path";

export interface GraphObservationItem {
  key: string;
  kind: GraphObservationKind;
  refId: string;
  label: string;
  subLabel: string;
  addedAt: string;
  node?: GraphExploreNode;
  edge?: GraphExploreEdge;
  path?: GraphExplorePath;
  pathNodes?: GraphExploreNode[];
  pathEdges?: GraphExploreEdge[];
  records?: FusionRecord[];
}

const STORAGE_PREFIX = "datafusionx.graphObservation";

function storageKey(caseId: number) {
  return `${STORAGE_PREFIX}.${caseId}`;
}

export function loadGraphObservations(caseId: number): GraphObservationItem[] {
  if (!caseId) return [];
  try {
    const raw = localStorage.getItem(storageKey(caseId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as GraphObservationItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveGraphObservations(caseId: number, items: GraphObservationItem[]) {
  if (!caseId) return;
  localStorage.setItem(storageKey(caseId), JSON.stringify(items));
}

export function buildObservationKey(kind: GraphObservationKind, refId: string) {
  return `${kind}:${refId}`;
}

export function createNodeObservation(node: GraphExploreNode, records: FusionRecord[] = []): GraphObservationItem {
  return {
    key: buildObservationKey("node", node.id),
    kind: "node",
    refId: node.id,
    label: node.label,
    subLabel: `${node.display_type} · 第 ${node.depth + 1} 级 · ${node.degree} 条关系`,
    addedAt: new Date().toISOString(),
    node,
    records,
  };
}

export function createPathObservation(
  path: GraphExplorePath,
  nodes: GraphExploreNode[],
  edges: GraphExploreEdge[],
  records: FusionRecord[] = []
): GraphObservationItem {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const pathNodes = path.nodes.map((id) => nodeMap.get(id)).filter(Boolean) as GraphExploreNode[];
  const label = pathNodes.map((node) => node.label).join(" → ") || "A-B 路径";
  return {
    key: buildObservationKey("path", path.id),
    kind: "path",
    refId: path.id,
    label,
    subLabel: `${path.length} 跳 · ${path.edges.length} 条关系 · ${pathNodes.length} 个节点`,
    addedAt: new Date().toISOString(),
    path,
    pathNodes,
    pathEdges: edges,
    records,
  };
}

export function createEdgeObservation(
  edge: GraphExploreEdge,
  sourceLabel: string,
  targetLabel: string,
  records: FusionRecord[] = []
): GraphObservationItem {
  return {
    key: buildObservationKey("edge", edge.id),
    kind: "edge",
    refId: edge.id,
    label: edge.display_type,
    subLabel: `${sourceLabel} → ${targetLabel} · ${edge.record_count} 条记录`,
    addedAt: new Date().toISOString(),
    edge,
    records,
  };
}
