import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Descriptions,
  Empty,
  List,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  ClearOutlined,
  EyeOutlined,
  FileSearchOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  NodeIndexOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  CASE_CHANGED_EVENT,
  CASE_STORAGE_KEY,
  GraphExploreEdge,
  GraphExploreNode,
  GraphExplorePath,
  GraphExploreResponse,
  PersonInfo,
  type AnchorSuggestItem,
} from "../api";
import {
  createEdgeObservation,
  createNodeObservation,
  createPathObservation,
  loadGraphObservations,
  saveGraphObservations,
  type GraphObservationItem,
} from "../utils/graphObservationStorage";
import { useFusionRecordDrawers } from "../components/fusion/FusionRecordDrawers";
import {
  formatFusionAmount,
  recordsForGraphSelection,
  recordsFromEdge,
  recordsFromPath,
} from "../utils/graphRecordUtils";

const { Title, Text, Paragraph } = Typography;

const RELATION_OPTIONS = [
  { label: "银行", value: "bank_txn", color: "#e85d45" },
  { label: "微信转账", value: "wechat", color: "#52c41a" },
  { label: "通讯", value: "telecom", color: "#1890ff" },
  { label: "工商", value: "enterprise", color: "#722ed1" },
  { label: "商务", value: "commercial", color: "#fa8c16" },
  { label: "标识", value: "identifier", color: "#94a3b8" },
];

const RELATION_EDGE_COLORS: Record<string, string> = {
  bank_txn: "#e85d45",
  wechat: "#52c41a",
  telecom: "#1890ff",
  enterprise: "#722ed1",
  commercial: "#fa8c16",
  identifier: "#94a3b8",
};

const RELATION_LEGEND_LABELS: Record<string, string> = {
  bank_txn: "银行关系",
  wechat: "微信转账关系",
  telecom: "通讯关系",
  enterprise: "工商关系",
  commercial: "商务关系",
  identifier: "标识归属",
};

const EXTENSION_LEVEL_OPTIONS = [
  { label: "二级", value: 2 },
  { label: "三级", value: 3 },
  { label: "四级", value: 4 },
  { label: "无限", value: "unlimited" },
];

const MIN_WEIGHT_OPTIONS = Array.from({ length: 10 }, (_, index) => ({
  label: `${index + 1}+`,
  value: index + 1,
}));

const NODE_COLORS: Record<string, string> = {
  person: "#e85d45",
  phone: "#1890ff",
  bank_card: "#fa8c16",
  wechat: "#52c41a",
  enterprise: "#722ed1",
  commercial_event: "#f59e0b",
  unknown: "#94a3b8",
};

const NODE_LEGEND_ITEMS = [
  { key: "person", label: "人物" },
  { key: "phone", label: "手机" },
  { key: "bank_card", label: "银行卡" },
  { key: "wechat", label: "微信" },
  { key: "enterprise", label: "企业" },
  { key: "commercial_event", label: "商务事件" },
  { key: "unknown", label: "其他" },
] as const;

const ANCHOR_KIND_OPTIONS = [
  { value: "person", label: "人物" },
  { value: "person_name", label: "姓名" },
  { value: "bank_card", label: "银行卡/账号" },
  { value: "phone", label: "手机号" },
  { value: "wechat_name", label: "微信名" },
  { value: "enterprise_name", label: "企业" },
];

const ANCHOR_TYPE_LABELS: Record<string, string> = {
  auto: "自动",
  bank_card: "银行卡",
  bank_acct: "银行账号",
  phone: "手机号",
  wechat_name: "微信名",
  enterprise_name: "企业",
  person_name: "姓名",
};

type GraphAnchorSelection = {
  key: string;
  type: string;
  value: string;
  label: string;
  hint?: string;
};

function normalizeAnchorKind(type: string) {
  if (type === "bank_acct") return "bank_card";
  return type;
}

function anchorFromSuggestion(item: AnchorSuggestItem, kind: string): GraphAnchorSelection {
  if (kind === "person" && item.person_id) {
    return {
      key: `person:${item.person_id}`,
      type: "person",
      value: String(item.person_id),
      label: item.person_name || item.display_value,
      hint: item.person_name && item.display_value !== item.person_name ? item.display_value : undefined,
    };
  }

  const anchorType = normalizeAnchorKind(kind !== "person" ? kind : item.identifier_type);
  return {
    key: `${anchorType}:${item.identifier_norm}`,
    type: anchorType,
    value: item.identifier_norm,
    label: item.display_value,
    hint: item.person_name ? `关联人物 ${item.person_name}` : ANCHOR_TYPE_LABELS[anchorType],
  };
}

function anchorToPayload(anchor: GraphAnchorSelection) {
  return { type: anchor.type, value: anchor.value };
}

function personToAnchor(person: PersonInfo): GraphAnchorSelection {
  return {
    key: `person:${person.person_id}`,
    type: "person",
    value: String(person.person_id),
    label: person.display_name,
    hint: person.links.length ? `${person.links.length} 个已关联标识` : "人物",
  };
}

function anchorKindFromSelection(anchor: GraphAnchorSelection | null) {
  if (!anchor) return "person";
  if (anchor.type === "person") return "person";
  if (anchor.type in ANCHOR_TYPE_LABELS || ANCHOR_KIND_OPTIONS.some((item) => item.value === anchor.type)) {
    return anchor.type;
  }
  return "person";
}

interface AnchorSearchSelectProps {
  caseId: number | null;
  value: GraphAnchorSelection | null;
  onChange: (value: GraphAnchorSelection | null) => void;
  placeholder: string;
  disabled?: boolean;
  excludeKey?: string;
}

function AnchorSearchSelect({
  caseId,
  value,
  onChange,
  placeholder,
  disabled,
  excludeKey,
}: AnchorSearchSelectProps) {
  const [entityType, setEntityType] = useState(() => anchorKindFromSelection(value));
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<GraphAnchorSelection[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<number>();
  const requestIdRef = useRef(0);
  const personsCacheRef = useRef<PersonInfo[]>([]);

  const fetchSuggestions = useCallback(
    async (text: string, kind: string) => {
      if (!caseId) {
        setOptions([]);
        return;
      }
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setLoading(true);
      try {
        let items: GraphAnchorSelection[] = [];
        if (kind === "person") {
          if (!personsCacheRef.current.length) {
            const res = await api.listCasePersons(caseId);
            personsCacheRef.current = res.items;
          }
          const needle = text.trim().toLowerCase();
          items = personsCacheRef.current
            .filter((person) => {
              if (!needle) return true;
              if (person.display_name.toLowerCase().includes(needle)) return true;
              return person.links.some((link) =>
                `${link.identifier_value} ${link.identifier_norm}`.toLowerCase().includes(needle)
              );
            })
            .map(personToAnchor);
        } else {
          const res = await api.suggestAnchors(caseId, text, 30, kind);
          items = res.items.map((item) => anchorFromSuggestion(item, kind));
        }
        if (requestId !== requestIdRef.current) return;
        setOptions(items.filter((item) => item.key !== excludeKey));
      } catch {
        if (requestId === requestIdRef.current) setOptions([]);
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    },
    [caseId, excludeKey]
  );

  useEffect(() => {
    personsCacheRef.current = [];
    setQuery("");
    if (value) setEntityType(anchorKindFromSelection(value));
  }, [caseId, value?.key]);

  useEffect(() => {
    void fetchSuggestions("", entityType);
  }, [entityType, fetchSuggestions]);

  const handleSearch = (text: string) => {
    setQuery(text);
    window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      void fetchSuggestions(text, entityType);
    }, 220);
  };

  useEffect(
    () => () => {
      window.clearTimeout(debounceRef.current);
    },
    []
  );

  const selectOptions = useMemo(() => {
    const merged = new Map<string, GraphAnchorSelection>();
    if (value) merged.set(value.key, value);
    options.forEach((item) => merged.set(item.key, item));
    return Array.from(merged.values()).map((item) => ({
      value: item.key,
      label: item.label,
      anchor: item,
    }));
  }, [options, value]);

  const handleTypeChange = (kind: string) => {
    setEntityType(kind);
    onChange(null);
    setQuery("");
    personsCacheRef.current = [];
    void fetchSuggestions("", kind);
  };

  return (
    <div className="graph-anchor-inputs">
      <Select
        className="graph-anchor-type-select"
        disabled={disabled}
        value={entityType}
        options={ANCHOR_KIND_OPTIONS}
        onChange={handleTypeChange}
      />
      <Select
        showSearch
        allowClear
        disabled={disabled}
        className="graph-anchor-value-select"
        placeholder={placeholder}
        value={value?.key}
        loading={loading}
        filterOption={false}
        optionLabelProp="label"
        defaultActiveFirstOption={false}
        notFoundContent={query.trim() ? "暂无匹配对象" : "输入关键词搜索"}
        onDropdownVisibleChange={(open) => {
          if (open) void fetchSuggestions(query, entityType);
        }}
        onSearch={handleSearch}
        onChange={(key) => {
          if (!key) {
            onChange(null);
            setQuery("");
            void fetchSuggestions("", entityType);
            return;
          }
          const picked = selectOptions.find((item) => item.value === key)?.anchor;
          if (picked) onChange(picked);
        }}
        onClear={() => {
          onChange(null);
          setQuery("");
          void fetchSuggestions("", entityType);
        }}
        options={selectOptions.map((item) => ({
          value: item.value,
          label: item.label,
          anchor: item.anchor,
        }))}
        optionRender={(option) => {
          const anchor = (option.data as { anchor?: GraphAnchorSelection })?.anchor;
          if (!anchor) return option.label;
          return (
            <div className="graph-anchor-option">
              <div className="graph-anchor-option-main">{anchor.label}</div>
              {anchor.hint ? (
                <Text type="secondary" className="graph-anchor-option-hint">
                  {anchor.hint}
                </Text>
              ) : null}
            </div>
          );
        }}
      />
    </div>
  );
}

function relationColor(type: string) {
  return RELATION_EDGE_COLORS[type] || RELATION_OPTIONS.find((item) => item.value === type)?.color || "#94a3b8";
}

function relationShortLabel(type: string) {
  return RELATION_OPTIONS.find((item) => item.value === type)?.label || type;
}

function PathTraceView({
  path,
  nodes,
  edges,
  compact = false,
}: {
  path: GraphExplorePath;
  nodes: GraphExploreNode[];
  edges: GraphExploreEdge[];
  compact?: boolean;
}) {
  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const edgeMap = useMemo(() => new Map(edges.map((edge) => [edge.id, edge])), [edges]);
  const pathType = path.relation_types.length === 1 ? path.relation_types[0] : null;

  return (
    <div className={`graph-path-trace${compact ? " graph-path-trace--compact" : ""}`}>
      {pathType ? (
        <Tag color={relationColor(pathType)} className="graph-path-trace-badge">
          {relationShortLabel(pathType)}
        </Tag>
      ) : null}
      <div className="graph-path-trace-chain">
        {path.nodes.map((nodeId, index) => {
          const label = nodeMap.get(nodeId)?.label || nodeId;
          const edge = index > 0 ? edgeMap.get(path.edges[index - 1]) : null;
          return (
            <span key={`${path.id}-${nodeId}-${index}`} className="graph-path-trace-step">
              {index > 0 && edge ? (
                <span className="graph-path-hop">
                  <span className="graph-path-hop-arrow" aria-hidden />
                  <Tag color={relationColor(edge.type)} className="graph-path-hop-tag">
                    {edge.display_type}
                  </Tag>
                </span>
              ) : null}
              <span className="graph-path-node">{label}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

const RELATION_CURVE_ORDER = ["bank_txn", "wechat", "telecom", "enterprise", "commercial", "identifier"] as const;

/** 各关系类型默认占据不同弧道；同向时再叠加序号偏移 */
const RELATION_TYPE_CURVENESS: Record<string, number> = {
  bank_txn: 0.38,
  wechat: -0.38,
  telecom: 0.28,
  enterprise: 0.16,
  commercial: -0.28,
  identifier: 0.08,
};

const MAX_EDGE_CURVENESS = 0.52;
const PARALLEL_LANE_STEP = 0.16;

function clampCurveness(value: number) {
  return Number(Math.max(-MAX_EDGE_CURVENESS, Math.min(MAX_EDGE_CURVENESS, value)).toFixed(3));
}

interface EdgeLayoutHint {
  curveness: number;
  widthScale: number;
}

/** 同一对节点间有多条关系时，按类型 + 方向 + 序号分配曲率，避免重叠 */
function buildEdgeLayoutMap(edges: GraphExploreEdge[]) {
  const groups = new Map<string, GraphExploreEdge[]>();
  for (const edge of edges) {
    const key = [edge.source, edge.target].sort().join("||");
    const list = groups.get(key) || [];
    list.push(edge);
    groups.set(key, list);
  }

  const layoutMap = new Map<string, EdgeLayoutHint>();
  for (const group of groups.values()) {
    const count = group.length;
    const widthScale = count <= 1 ? 1 : count === 2 ? 0.82 : count === 3 ? 0.72 : 0.62;

    const sorted = [...group].sort((a, b) => {
      const ai = RELATION_CURVE_ORDER.indexOf(a.type as (typeof RELATION_CURVE_ORDER)[number]);
      const bi = RELATION_CURVE_ORDER.indexOf(b.type as (typeof RELATION_CURVE_ORDER)[number]);
      if (ai !== bi) return ai - bi;
      const as = `${a.source}->${a.target}`;
      const bs = `${b.source}->${b.target}`;
      return as.localeCompare(bs);
    });

    const assignedCurves: number[] = [];
    sorted.forEach((edge, index) => {
      let curve = RELATION_TYPE_CURVENESS[edge.type] ?? 0.18;
      const forward = edge.source.localeCompare(edge.target) < 0;
      if (!forward) curve = -curve;

      if (count > 1) {
        const laneOffset = (index - (count - 1) / 2) * PARALLEL_LANE_STEP;
        curve += laneOffset;
      }

      // 若与已分配曲率过近，再微调错开
      while (assignedCurves.some((existing) => Math.abs(existing - curve) < 0.12)) {
        curve += forward ? 0.12 : -0.12;
      }
      curve = clampCurveness(curve);
      assignedCurves.push(curve);
      layoutMap.set(edge.id, { curveness: curve, widthScale });
    });
  }
  return layoutMap;
}

const UNDIRECTED_EDGE_TYPES = new Set(["identifier", "enterprise", "commercial", "bank_txn", "wechat", "telecom"]);

function buildGraphLink(
  edge: GraphExploreEdge,
  isSelected: boolean,
  viewMode: "all" | "paths" | "common",
  layout: EdgeLayoutHint,
  isPathEdge = false
) {
  const style = edgeLineStyle(edge, isSelected, viewMode, isPathEdge);
  const color = relationColor(edge.type);
  const width = Math.max(isSelected ? style.width : 1.2, style.width * layout.widthScale);
  const curveness = layout.curveness;
  const undirected = UNDIRECTED_EDGE_TYPES.has(edge.type);
  return {
    source: edge.source,
    target: edge.target,
    value: edge.weight,
    id: edge.id,
    edgeType: edge.type,
    display_type: edge.display_type,
    weight: edge.weight,
    record_count: edge.record_count,
    amount: edge.amount,
    duration_sec: edge.duration_sec,
    symbol: undirected ? ["none", "none"] : ["none", "arrow"],
    lineStyle: {
      color,
      width,
      opacity: style.opacity,
      curveness,
      type: style.type,
    },
    emphasis: {
      lineStyle: {
        color: isSelected ? "#111827" : color,
        width: Math.min(width + 1, 12),
        opacity: 1,
        curveness,
      },
    },
    label: {
      show: isSelected || isPathEdge,
      formatter: edge.display_type,
      color: relationColor(edge.type),
      fontWeight: 700,
      fontSize: 11,
      backgroundColor: "rgba(255,255,255,0.92)",
      padding: [2, 4],
      borderRadius: 4,
    },
  };
}

function edgeLineStyle(
  edge: GraphExploreEdge,
  isSelected: boolean,
  mode: "all" | "paths" | "common",
  isPathEdge = false
) {
  const highlighted = isSelected || isPathEdge;
  const isIdentifier = edge.type === "identifier";
  const isCoreInteraction = edge.type === "bank_txn" || edge.type === "wechat" || edge.type === "telecom";
  const baseWidth = highlighted
    ? Math.max(5, Math.min(14, 2.5 + Math.sqrt(edge.weight) * 2.2))
    : isIdentifier
      ? 1
      : isCoreInteraction
        ? Math.max(2.8, Math.min(12, 2.2 + Math.sqrt(edge.weight) * 2.4))
        : Math.max(1.5, Math.min(10, 1.5 + Math.sqrt(edge.weight) * 1.8));
  return {
    width: baseWidth,
    color: highlighted ? "#111827" : relationColor(edge.type),
    opacity: highlighted ? 1 : isIdentifier ? 0.28 : mode === "all" ? 0.88 : 0.95,
    type: isIdentifier ? ("dashed" as const) : ("solid" as const),
  };
}

function formatAmount(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return formatFusionAmount(value);
}

function ZoneLabel({ title }: { title: string }) {
  return <div className="graph-zone-label">{title}</div>;
}

function GraphExplorePage({ embedded = false, cockpitMode = false }: { embedded?: boolean; cockpitMode?: boolean }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [cases, setCases] = useState<Array<{ case_id: number; case_name: string; batch_count: number }>>([]);
  const [caseId, setCaseId] = useState<number | null>(null);
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [anchorCenter, setAnchorCenter] = useState<GraphAnchorSelection | null>(null);
  const [anchorTarget, setAnchorTarget] = useState<GraphAnchorSelection | null>(null);
  const [displayLevel, setDisplayLevel] = useState(2);
  const [unlimited, setUnlimited] = useState(false);
  const [relationTypes, setRelationTypes] = useState<string[]>(RELATION_OPTIONS.map((item) => item.value));
  const [minWeight, setMinWeight] = useState(1);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<GraphExploreResponse | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphExploreNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphExploreEdge | null>(null);
  const [selectedPathEdgeIds, setSelectedPathEdgeIds] = useState<Set<string>>(new Set());
  const [activePath, setActivePath] = useState<GraphExplorePath | null>(null);
  const [viewMode, setViewMode] = useState<"all" | "paths" | "common">("all");
  const [pathHopFilter, setPathHopFilter] = useState<string>("all");
  const [observations, setObservations] = useState<GraphObservationItem[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [graphFullscreen, setGraphFullscreen] = useState(false);
  const prevRelationTypesRef = useRef<string[]>(RELATION_OPTIONS.map((item) => item.value));
  const prevExploreParamsRef = useRef({ displayLevel: 2, unlimited: false, minWeight: 1 });
  const graphChartRef = useRef<ReactECharts>(null);
  const { openRecords, drawers } = useFusionRecordDrawers(caseId);

  const refreshCases = useCallback(async (preferredId?: number | null) => {
    const res = await api.listCases();
    setCases(res.items);
    const paramCase = searchParams.get("case");
    const stored = localStorage.getItem(CASE_STORAGE_KEY);
    const fallback = paramCase ? Number(paramCase) : stored ? Number(stored) : res.items[0]?.case_id ?? null;
    const preferred = preferredId ?? fallback;
    const next = res.items.some((item) => item.case_id === preferred) ? preferred : res.items[0]?.case_id ?? null;
    setCaseId(next);
    setObservations(next ? loadGraphObservations(next) : []);
    setData(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setAnchorCenter(null);
    setAnchorTarget(null);
    setPersons([]);
  }, [searchParams]);

  useEffect(() => {
    void refreshCases().catch((err) => message.error((err as Error).message));
  }, [refreshCases]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number | null }>).detail?.caseId ?? null;
      void refreshCases(nextCaseId).catch((err) => message.error((err as Error).message));
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, [refreshCases]);

  const selectedCase = cases.find((item) => item.case_id === caseId);
  const hasBoundBatch = (selectedCase?.batch_count ?? 0) > 0;

  useEffect(() => {
    if (!caseId) {
      setObservations([]);
      return;
    }
    localStorage.setItem(CASE_STORAGE_KEY, String(caseId));
    setObservations(loadGraphObservations(caseId));
    if (searchParams.get("case") !== String(caseId)) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set("case", String(caseId));
      setSearchParams(nextParams, { replace: true });
    }
  }, [caseId, searchParams, setSearchParams]);

  useEffect(() => {
    setData(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setSelectedPathEdgeIds(new Set());
    setActivePath(null);
    setViewMode("all");
    setPathHopFilter("all");

    if (!caseId || !hasBoundBatch) {
      setPersons([]);
      setAnchorCenter(null);
      setAnchorTarget(null);
      return;
    }
    void api
      .listCasePersons(caseId)
      .then((res) => {
        setPersons(res.items);
        const personParam = searchParams.get("person");
        const preferred = personParam ? Number(personParam) : null;
        setAnchorCenter((current) => {
          if (current && res.items.some((p) => current.key === `person:${p.person_id}`)) return current;
          const person =
            (preferred && res.items.find((p) => p.person_id === preferred)) || res.items[0] || null;
          return person ? personToAnchor(person) : null;
        });
        setAnchorTarget(null);
      })
      .catch((err) => message.error((err as Error).message));
  }, [caseId, hasBoundBatch, searchParams]);

  const persistObservations = useCallback(
    (items: GraphObservationItem[]) => {
      if (!caseId) return;
      setObservations(items);
      saveGraphObservations(caseId, items);
    },
    [caseId]
  );

  const backToJudgment = useCallback(() => {
    const query = caseId ? `?case=${caseId}` : "";
    navigate(`/fusion-cockpit${query}`);
  }, [caseId, navigate]);

  const explore = useCallback(async () => {
    if (!caseId || !anchorCenter || !hasBoundBatch) return;
    setLoading(true);
    setSelectedNode(null);
    setSelectedEdge(null);
    setSelectedPathEdgeIds(new Set());
    setActivePath(null);
    try {
      const anchors = [anchorToPayload(anchorCenter)];
      if (anchorTarget && anchorTarget.key !== anchorCenter.key) {
        anchors.push(anchorToPayload(anchorTarget));
      }
      const res = await api.exploreGraph(caseId, {
        anchors,
        display_level: displayLevel,
        unlimited,
        relation_types: relationTypes,
        min_weight: minWeight,
        max_nodes: unlimited ? 500 : 300,
        max_edges: unlimited ? 1500 : 900,
        include_sample_records: true,
      });
      setData(res);
      setPathHopFilter("all");
      if (anchorTarget && anchorTarget.key !== anchorCenter.key && res.paths.length) {
        const firstPath = res.paths[0];
        setActivePath(firstPath);
        setSelectedPathEdgeIds(new Set(firstPath.edges));
        setViewMode("paths");
        setPathHopFilter(String(firstPath.length));
      } else {
        setActivePath(null);
        setSelectedPathEdgeIds(new Set());
        setViewMode("all");
      }
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [anchorCenter, anchorTarget, caseId, displayLevel, hasBoundBatch, minWeight, relationTypes, unlimited]);

  useEffect(() => {
    if (!data || !caseId || !anchorCenter || !hasBoundBatch || !relationTypes.length) return;
    const prev = prevRelationTypesRef.current;
    const changed =
      prev.length !== relationTypes.length || prev.some((type, index) => type !== relationTypes[index]);
    prevRelationTypesRef.current = [...relationTypes];
    if (!changed) return;
    void explore();
  }, [anchorCenter, caseId, data, explore, hasBoundBatch, relationTypes]);

  useEffect(() => {
    if (!data || !caseId || !anchorCenter || !hasBoundBatch) return;
    const prev = prevExploreParamsRef.current;
    if (
      prev.displayLevel === displayLevel &&
      prev.unlimited === unlimited &&
      prev.minWeight === minWeight
    ) {
      return;
    }
    prevExploreParamsRef.current = { displayLevel, unlimited, minWeight };
    void explore();
  }, [anchorCenter, anchorTarget, caseId, data, displayLevel, explore, hasBoundBatch, minWeight, unlimited]);

  const extensionLevelValue = unlimited ? "unlimited" : displayLevel;

  const onExtensionLevelChange = (value: number | "unlimited") => {
    if (value === "unlimited") {
      setUnlimited(true);
      return;
    }
    setUnlimited(false);
    setDisplayLevel(value);
  };

  const extensionLevelControl = (
    <Space wrap className="graph-extension-control" align="center">
      <Text type="secondary">拓展级别</Text>
      <Select
        size="small"
        style={{ width: 108 }}
        value={extensionLevelValue}
        options={EXTENSION_LEVEL_OPTIONS}
        onChange={onExtensionLevelChange}
        disabled={!hasBoundBatch}
        popupClassName="graph-extension-select-dropdown"
        getPopupContainer={(trigger) => trigger.closest(".graph-zone-canvas") ?? document.body}
      />
    </Space>
  );

  const visibleEdgeIds = useMemo(() => {
    if (!data) return new Set<string>();
    if (viewMode === "paths") {
      const path = activePath || data.paths[0];
      return path ? new Set(path.edges) : new Set<string>();
    }
    if (viewMode === "common") {
      const commonIds = new Set(data.common_neighbors.map((item) => item.node_id));
      const anchorIds = new Set(data.anchors);
      return new Set(
        data.edges
          .filter((edge) => {
            if (edge.type !== "enterprise") return false;
            return (
              (commonIds.has(edge.source) && anchorIds.has(edge.target)) ||
              (commonIds.has(edge.target) && anchorIds.has(edge.source))
            );
          })
          .map((edge) => edge.id)
      );
    }
    return new Set(data.edges.map((edge) => edge.id));
  }, [activePath, data, viewMode]);

  const activePathNodeIds = useMemo(() => {
    if (!data) return new Set<string>();
    const path = activePath || (viewMode === "paths" ? data.paths[0] : null);
    return path ? new Set(path.nodes) : new Set<string>();
  }, [activePath, data, viewMode]);

  const selectedNodeInteractionEdges = useMemo(() => {
    if (!selectedNode || !data) return [] as GraphExploreEdge[];
    return data.edges.filter(
      (edge) =>
        (edge.source === selectedNode.id || edge.target === selectedNode.id) && edge.type !== "identifier"
    );
  }, [data, selectedNode]);

  const relationEdgeColumns = useMemo(
    () => [
      {
        title: "类型",
        dataIndex: "type",
        width: 108,
        render: (_: string, edge: GraphExploreEdge) => (
          <Tag color={relationColor(edge.type)}>{edge.display_type}</Tag>
        ),
      },
      {
        title: "关联对象",
        key: "other",
        ellipsis: true,
        render: (_: unknown, edge: GraphExploreEdge) => {
          if (!selectedNode) return "—";
          const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
          const other = data?.nodes.find((node) => node.id === otherId);
          return other?.label || otherId;
        },
      },
      {
        title: "记录",
        dataIndex: "record_count",
        width: 56,
        render: (v: number) => `${v} 条`,
      },
    ],
    [data?.nodes, selectedNode]
  );

  const chartOption = useMemo(() => {
    if (!data?.nodes.length || !caseId || !hasBoundBatch) return null;
    const visibleNodeIds = new Set<string>();
    data.edges.forEach((edge) => {
      if (visibleEdgeIds.has(edge.id)) {
        visibleNodeIds.add(edge.source);
        visibleNodeIds.add(edge.target);
      }
    });
    data.anchors.forEach((id) => visibleNodeIds.add(id));
    const nodes = data.nodes.filter((node) => visibleNodeIds.has(node.id)).map((node) => {
      const isPathNode = activePathNodeIds.has(node.id);
      const isFocused = selectedNode?.id === node.id;
      return {
      id: node.id,
      name: node.label,
      symbolSize: node.is_anchor ? 68 : isPathNode ? Math.max(30, 52 - node.depth * 3) : Math.max(24, 48 - node.depth * 4),
      itemStyle: {
        color: NODE_COLORS[node.type] || NODE_COLORS.unknown,
        borderColor: isFocused
          ? "#111827"
          : isPathNode
            ? "#9a3412"
          : node.is_anchor
            ? "#fff"
            : node.depth <= 1
              ? "rgba(255,255,255,0.9)"
              : "rgba(255,255,255,0.55)",
        borderWidth: isFocused ? 5 : isPathNode ? 4 : node.is_anchor ? 4 : 2,
        shadowBlur: isFocused ? 28 : isPathNode ? 20 : node.is_anchor ? 18 : 8,
        shadowColor: isFocused ? "rgba(17,24,39,0.32)" : isPathNode ? "rgba(154,52,18,0.28)" : "rgba(15,23,42,0.18)",
      },
      label: {
        show: isPathNode || node.depth <= 2 || node.is_anchor || isFocused,
        fontWeight: node.is_anchor || isPathNode ? 700 : 500,
        color: isPathNode ? "#9a3412" : undefined,
      },
      // 供 tooltip / 点击回查
      graphNodeId: node.id,
      display_type: node.display_type,
      depth: node.depth,
      degree: node.degree,
      labelText: node.label,
    };
    });
    const visibleEdges = data.edges.filter((edge) => visibleEdgeIds.has(edge.id));
    const edgeLayoutMap = buildEdgeLayoutMap(visibleEdges);
    const links = visibleEdges.map((edge) => {
      const isPathEdge = viewMode === "paths" && activePathNodeIds.size > 0;
      const isSelected = selectedEdge?.id === edge.id || selectedPathEdgeIds.has(edge.id);
      const layout = edgeLayoutMap.get(edge.id) || { curveness: 0.14, widthScale: 1 };
      return buildGraphLink(edge, isSelected, viewMode, layout, isPathEdge);
    });
    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        confine: true,
        formatter: (params: { dataType?: string; data?: GraphExploreNode & GraphExploreEdge }) => {
          const item = params.data;
          if (!item) return "";
          if (params.dataType === "edge") {
            const edge = item as GraphExploreEdge & { edgeType?: string };
            const edgeKind = edge.edgeType || edge.type;
            const amountLine =
              edgeKind === "telecom"
                ? `通话时长 ${edge.duration_sec ?? 0} 秒`
                : `金额 ${formatAmount(edge.amount)}`;
            return `<strong>${edge.display_type}</strong><br/>强度 ${edge.weight} · 记录 ${edge.record_count}<br/>${amountLine}<br/>点击查看明细`;
          }
          const node = item as GraphExploreNode & { labelText?: string; graphNodeId?: string };
          const label = node.labelText || node.label;
          return `<strong>${label}</strong><br/>${node.display_type} · 第 ${node.depth + 1} 级<br/>关系数 ${node.degree}`;
        },
      },
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          focusNodeAdjacency: true,
          color: [],
          data: nodes,
          links,
          lineStyle: {
            opacity: 0.88,
            width: 2,
          },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: [0, 7],
          force: {
            repulsion: 620,
            gravity: 0.06,
            edgeLength: [130, 250],
            friction: 0.52,
            layoutAnimation: true,
          },
          emphasis: {
            focus: viewMode === "paths" ? "none" : "adjacency",
            scale: 1.05,
            lineStyle: { opacity: 1 },
          },
          blur: {
            itemStyle: { opacity: 0.15 },
            lineStyle: { opacity: 0.08 },
          },
        },
      ],
    };
  }, [activePathNodeIds, data, selectedEdge?.id, selectedNode?.id, selectedPathEdgeIds, viewMode, visibleEdgeIds]);

  const selectNodeById = useCallback(
    (nodeId: string) => {
      const node = data?.nodes.find((item) => item.id === nodeId);
      if (!node) return;
      setSelectedNode(node);
      setSelectedEdge(null);
    },
    [data]
  );

  const selectEdgeById = useCallback(
    (edgeId: string) => {
      const edge = data?.edges.find((item) => item.id === edgeId);
      if (!edge) return;
      setSelectedEdge(edge);
      setSelectedNode(null);
    },
    [data]
  );

  const graphEvents = useMemo(
    () => ({
      click: (params: { dataType?: string; data?: GraphExploreNode & GraphExploreEdge }) => {
        if (!params.data) return;
        if (params.dataType === "edge") {
          const edgeId = String((params.data as GraphExploreEdge).id || "");
          selectEdgeById(edgeId);
          return;
        }
        const nodeId = String((params.data as GraphExploreNode & { graphNodeId?: string }).graphNodeId || (params.data as GraphExploreNode).id || "");
        selectNodeById(nodeId);
      },
    }),
    [selectEdgeById, selectNodeById]
  );

  const graphChartStyle = graphFullscreen
    ? { flex: 1, width: "100%", minHeight: 0 }
    : { height: 620, width: "100%" };

  useEffect(() => {
    const chart = graphChartRef.current?.getEchartsInstance();
    if (!chart) return;
    const timer = window.setTimeout(() => chart.resize(), 80);
    return () => window.clearTimeout(timer);
  }, [graphFullscreen, data, loading]);

  useEffect(() => {
    if (!graphFullscreen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setGraphFullscreen(false);
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [graphFullscreen]);

  const selectPath = useCallback((path: GraphExplorePath) => {
    setActivePath(path);
    setSelectedPathEdgeIds(new Set(path.edges));
    setSelectedNode(null);
    setSelectedEdge(null);
    setViewMode("paths");
    setPathHopFilter(String(path.length));
  }, []);

  useEffect(() => {
    if (viewMode !== "paths" || !data?.paths.length) return;
    if (!activePath || !data.paths.some((path) => path.id === activePath.id)) {
      selectPath(data.paths[0]);
    }
  }, [activePath, data?.paths, selectPath, viewMode]);

  const observationKeys = useMemo(() => new Set(observations.map((item) => item.key)), [observations]);

  const displayPaths = useMemo(() => {
    if (!data?.paths.length) return [] as GraphExplorePath[];
    const seen = new Set<string>();
    const result: GraphExplorePath[] = [];
    for (const path of data.paths) {
      if (path.relation_types.length !== 1) continue;
      const relationType = path.relation_types[0];
      const key = `${relationType}::${path.nodes.join("->")}`;
      if (seen.has(key)) continue;
      seen.add(key);
      result.push(path);
    }
    return result;
  }, [data?.paths]);

  const summaryPaths = useMemo(() => {
    if (!displayPaths.length) return [] as GraphExplorePath[];
    const hop = pathHopFilter === "all" ? null : Number(pathHopFilter);
    if (!hop || Number.isNaN(hop)) return displayPaths;
    return displayPaths.filter((path) => path.length === hop);
  }, [displayPaths, pathHopFilter]);

  const summaryHopOptions = useMemo(() => {
    if (!displayPaths.length) return [{ label: "全部跳数", value: "all" }];
    const hops = Array.from(new Set(displayPaths.map((path) => path.length))).sort((a, b) => a - b);
    return [{ label: "全部跳数", value: "all" }, ...hops.map((hop) => ({ label: `${hop} 跳`, value: String(hop) }))];
  }, [displayPaths]);

  const addSelectionToObservation = useCallback(() => {
    if (!caseId || !data) return;
    if (activePath && viewMode === "paths" && !selectedNode && !selectedEdge) {
      const pathEdges = data.edges.filter((edge) => activePath.edges.includes(edge.id));
      const records = recordsFromPath(activePath, data.edges, data.nodes);
      const item = createPathObservation(activePath, data.nodes, pathEdges, records);
      if (observationKeys.has(item.key)) {
        message.info("该路径已在观察区");
        return;
      }
      persistObservations([item, ...observations]);
      message.success("已将整条路径加入观察区");
      return;
    }
    if (selectedNode) {
      const records = recordsForGraphSelection({ node: selectedNode, edges: data?.edges || [] });
      const item = createNodeObservation(selectedNode, records);
      if (observationKeys.has(item.key)) {
        message.info("该节点已在观察区");
        return;
      }
      persistObservations([item, ...observations]);
      message.success("已加入观察区");
      return;
    }
    if (selectedEdge) {
      const source = data?.nodes.find((node) => node.id === selectedEdge.source);
      const target = data?.nodes.find((node) => node.id === selectedEdge.target);
      const records = recordsFromEdge(selectedEdge);
      const item = createEdgeObservation(
        selectedEdge,
        source?.label || selectedEdge.source,
        target?.label || selectedEdge.target,
        records
      );
      if (observationKeys.has(item.key)) {
        message.info("该关系已在观察区");
        return;
      }
      persistObservations([item, ...observations]);
      message.success("已加入观察区");
    }
  }, [activePath, caseId, data, observationKeys, observations, persistObservations, selectedEdge, selectedNode, viewMode]);

  const openSelectionRecords = useCallback(async () => {
    if (!caseId) return;
    setDetailLoading(true);
    try {
      if (selectedNode) {
        const detail = await api.graphSelectionDetail(caseId, { kind: "node", node_id: selectedNode.id });
        const meta: Record<string, string> = {
          节点类型: selectedNode.display_type,
          所在层级: `第 ${selectedNode.depth + 1} 级`,
          关系数量: `${selectedNode.degree} 条`,
          记录总数: `${detail.records.length} 条`,
        };
        openRecords(selectedNode.label, detail.records, meta, {
          identifiers: detail.identifiers,
          detailKind: "node",
          selection: { kind: "node", node_id: selectedNode.id },
        });
        return;
      }
      if (selectedEdge) {
        const source = data?.nodes.find((node) => node.id === selectedEdge.source);
        const target = data?.nodes.find((node) => node.id === selectedEdge.target);
        const detail = await api.graphSelectionDetail(caseId, {
          kind: "edge",
          source: selectedEdge.source,
          target: selectedEdge.target,
          edge_type: selectedEdge.type,
        });
        const meta: Record<string, string> = {
          关系类型: selectedEdge.display_type,
          关系强度: String(selectedEdge.weight),
          记录总数: `${detail.records.length} 条`,
        };
        openRecords(`${source?.label || selectedEdge.source} → ${target?.label || selectedEdge.target}`, detail.records, meta, {
          detailKind: "edge",
          relationType: selectedEdge.type,
          partyA: source?.label || selectedEdge.source,
          partyB: target?.label || selectedEdge.target,
          selection: {
            kind: "edge",
            source: selectedEdge.source,
            target: selectedEdge.target,
            edge_type: selectedEdge.type,
          },
        });
        return;
      }
      if (activePath && data && viewMode === "paths") {
        const records = recordsFromPath(activePath, data.edges, data.nodes);
        const pathLabels = activePath.nodes.map(
          (nodeId) => data.nodes.find((node) => node.id === nodeId)?.label || nodeId
        );
        const label = pathLabels.join(" → ") || "A-B 路径";
        const firstLabel = pathLabels[0] || "";
        const lastLabel = pathLabels[pathLabels.length - 1] || "";
        openRecords(label, records, {
          路径跳数: `${activePath.length} 跳`,
          关系数量: `${activePath.edges.length} 条`,
          节点数量: `${activePath.nodes.length} 个`,
        }, {
          detailKind: "edge",
          partyA: firstLabel,
          partyB: lastLabel !== firstLabel ? lastLabel : "",
          pathParties: pathLabels,
        });
      }
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setDetailLoading(false);
    }
  }, [activePath, caseId, data, openRecords, selectedEdge, selectedNode, viewMode]);

  const openObservationRecords = useCallback(
    async (item: GraphObservationItem) => {
      if (!caseId) return;
      setDetailLoading(true);
      try {
        if (item.kind === "node" && item.node) {
          const detail = await api.graphSelectionDetail(caseId, { kind: "node", node_id: item.node.id });
          openRecords(item.label, detail.records, {
            节点类型: item.node.display_type,
            所在层级: `第 ${item.node.depth + 1} 级`,
            记录总数: `${detail.records.length} 条`,
          }, {
            identifiers: detail.identifiers,
            detailKind: "node",
          });
          return;
        }
        if (item.kind === "edge" && item.edge) {
          const source = data?.nodes.find((node) => node.id === item.edge?.source);
          const target = data?.nodes.find((node) => node.id === item.edge?.target);
          const detail = await api.graphSelectionDetail(caseId, {
            kind: "edge",
            source: item.edge.source,
            target: item.edge.target,
            edge_type: item.edge.type,
          });
          openRecords(item.label, detail.records, {
            关系类型: item.edge.display_type,
            记录总数: `${detail.records.length} 条`,
          }, {
            detailKind: "edge",
            relationType: item.edge.type,
            partyA: source?.label || item.edge.source,
            partyB: target?.label || item.edge.target,
          });
          return;
        }
        if (item.kind === "path" && item.path) {
          const records =
            data?.edges && data?.nodes
              ? recordsFromPath(item.path, data.edges, data.nodes)
              : item.records && item.records.length
                ? item.records
                : (item.pathEdges || data?.edges.filter((edge) => item.path?.edges.includes(edge.id)) || []).flatMap(
                    (edge) => {
                      const source = data?.nodes.find((node) => node.id === edge.source);
                      const target = data?.nodes.find((node) => node.id === edge.target);
                      return recordsFromEdge(edge, {
                        partyA: source?.label || edge.source,
                        partyB: target?.label || edge.target,
                      });
                    }
                  );
          const pathLabels =
            item.pathNodes?.map((node) => node.label) ||
            item.path.nodes.map(
              (nodeId) => data?.nodes.find((node) => node.id === nodeId)?.label || nodeId
            ) || [];
          const firstLabel = pathLabels[0] || "";
          const lastLabel = pathLabels[pathLabels.length - 1] || "";
          openRecords(item.label, records, {
            路径跳数: `${item.path.length} 跳`,
            关系数量: `${item.path.edges.length} 条`,
            节点数量: `${item.path.nodes.length} 个`,
          }, {
            detailKind: "edge",
            partyA: firstLabel,
            partyB: lastLabel !== firstLabel ? lastLabel : "",
            pathParties: pathLabels,
          });
        }
      } catch (err) {
        message.error((err as Error).message);
      } finally {
        setDetailLoading(false);
      }
    },
    [caseId, data?.edges, data?.nodes, openRecords]
  );

  const removeObservation = useCallback(
    (key: string) => {
      persistObservations(observations.filter((item) => item.key !== key));
    },
    [observations, persistObservations]
  );

  const clearObservations = useCallback(() => {
    persistObservations([]);
    message.success("观察区已清空");
  }, [persistObservations]);

  const focusObservation = useCallback(
    (item: GraphObservationItem) => {
      if (item.kind === "path" && item.path) {
        selectPath(item.path);
        return;
      }
      if (item.kind === "node" && item.node) {
        selectNodeById(item.node.id);
        return;
      }
      if (item.kind === "edge" && item.edge) {
        selectEdgeById(item.edge.id);
      }
    },
    [selectEdgeById, selectNodeById, selectPath]
  );

  const canAddObservation = Boolean(selectedNode || selectedEdge || (activePath && viewMode === "paths"));
  const selectionInObservation = Boolean(
    (selectedNode && observationKeys.has(`node:${selectedNode.id}`)) ||
      (selectedEdge && observationKeys.has(`edge:${selectedEdge.id}`)) ||
      (activePath && viewMode === "paths" && observationKeys.has(`path:${activePath.id}`))
  );

  const showHero = !cockpitMode && !embedded;
  const showSummaryPanel = Boolean(data && (anchorTarget || data.paths.length > 0) && anchorCenter);
  const shouldHideSummaryDetails = Boolean(!anchorTarget && anchorCenter && !data?.paths.length);

  const graphEmptyDescription = !caseId
    ? "请先选择案件"
    : !hasBoundBatch
      ? "当前案件无绑定批次，暂无图谱数据"
      : "请在筛选区选择中心对象并开始分析";

  return (
    <div className={`graph-explore-page${cockpitMode ? " graph-explore-cockpit" : ""}`}>
      {showHero ? (
      <div className="graph-explore-hero">
        {embedded ? (
          <div className="graph-explore-hero-nav">
            <Button type="default" className="graph-back-btn" icon={<ArrowLeftOutlined />} onClick={backToJudgment}>
              返回综合研判
            </Button>
            <Text className="graph-breadcrumb">综合研判 · 图谱探索</Text>
          </div>
        ) : null}
        <div className="graph-explore-hero-body">
          <div>
            <Text className="cockpit-hero-kicker">融合分析驾驶舱</Text>
            <Title level={3}>图谱探索</Title>
            <Paragraph>筛选区设定分析范围；上方左侧为图谱区、右侧为观察区；下方选中区展示当前点击的节点或关系详情。</Paragraph>
          </div>
          <Space wrap>
            <Tag color="volcano">{selectedCase?.case_name || "请选择案件"}</Tag>
            <Tag icon={<EyeOutlined />}>观察区 {observations.length}</Tag>
          </Space>
        </div>
      </div>
      ) : null}

      {caseId && !hasBoundBatch ? (
        <Alert
          type="warning"
          showIcon
          message="当前案件尚未绑定数据批次"
          description="图谱与研判仅基于已绑定批次的数据。请点击顶部「新建案件」导入并绑定数据，或通过「打开案件」为现有案件添加批次。"
          style={{ marginBottom: 16 }}
        />
      ) : null}

      <section className="graph-zone graph-zone-filter">
        <ZoneLabel title="筛选区" />
        <Card className="graph-query-card">
          <Row gutter={[14, 14]} align="middle">
            <Col xs={24} md={8}>
              <div className="graph-anchor-field">
                <Text strong>中心对象</Text>
                <AnchorSearchSelect
                  caseId={caseId}
                  value={anchorCenter}
                  onChange={setAnchorCenter}
                  placeholder="搜索姓名、卡号、手机号…"
                  disabled={!hasBoundBatch}
                  excludeKey={anchorTarget?.key}
                />
              </div>
            </Col>
            <Col xs={24} md={8}>
              <div className="graph-anchor-field">
                <Text strong>路径终点（可选）</Text>
                <AnchorSearchSelect
                  caseId={caseId}
                  value={anchorTarget}
                  onChange={setAnchorTarget}
                  placeholder="搜索第二个对象"
                  disabled={!hasBoundBatch}
                  excludeKey={anchorCenter?.key}
                />
              </div>
            </Col>
            <Col xs={24} md={4}>
              <Text strong>强度</Text>
              <Select
                style={{ width: "100%", marginTop: 8 }}
                value={minWeight}
                options={MIN_WEIGHT_OPTIONS}
                onChange={setMinWeight}
                disabled={!hasBoundBatch}
              />
            </Col>
            <Col xs={24} md={4}>
              <Text strong aria-hidden style={{ visibility: "hidden" }}>
                分析
              </Text>
              <Button
                block
                type="primary"
                icon={<SearchOutlined />}
                style={{ marginTop: 8 }}
                onClick={() => void explore()}
                disabled={!anchorCenter || !caseId || !hasBoundBatch || !relationTypes.length}
              >
                分析
              </Button>
            </Col>
            <Col xs={24}>
              <Paragraph type="secondary" className="graph-filter-hint">
                仅填中心对象：以该节点向外拓展关系网。同时填写路径终点：呈现两点间路径，并在「共同关联」中仅展示两人共同关联的企业。
              </Paragraph>
            </Col>
            <Col xs={24}>
              <div className="graph-query-actions compact">
                <Text type="secondary">关系类型</Text>
                <Checkbox.Group value={relationTypes} onChange={(values) => setRelationTypes(values.map(String))} options={RELATION_OPTIONS.map((item) => ({ label: item.label, value: item.value }))} />
              </div>
            </Col>
          </Row>

          {showSummaryPanel && data ? (
            <div className="graph-summary-shell">
              <div className="graph-summary-header">
                <div className="graph-summary-header-main">
                  <Text className="graph-summary-kicker">探索概要</Text>
                  <div className="graph-summary-title-row">
                    {anchorTarget ? (
                      <Text strong className="graph-summary-route">
                        {anchorCenter?.label || "中心"} ↔ {anchorTarget.label}
                      </Text>
                    ) : (
                      <Text strong>{anchorCenter?.label || "中心对象"}</Text>
                    )}
                  </div>
                  <div className="graph-summary-stats">
                    {displayPaths.length ? <span>{displayPaths.length} 路径</span> : null}
                    {displayPaths.length ? <span className="graph-summary-stats-dot">·</span> : null}
                    <span>{data.summary.node_count} 节点</span>
                    <span className="graph-summary-stats-dot">·</span>
                    <span>{data.summary.common_neighbor_count} 共同关联</span>
                  </div>
                </div>
                {anchorTarget && displayPaths.length ? (
                  <Select
                    size="small"
                    className="graph-summary-hop-filter"
                    value={pathHopFilter}
                    onChange={setPathHopFilter}
                    options={summaryHopOptions}
                    popupMatchSelectWidth={120}
                  />
                ) : null}
              </div>

              <div className="graph-summary-body">
                {shouldHideSummaryDetails ? (
                  <Empty
                    className="graph-summary-single-empty"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="仅选择中心对象，暂无路径"
                  />
                ) : anchorTarget ? (
                  <>
                    {summaryPaths.length ? (
                      <div className="graph-summary-path-list">
                        {summaryPaths.map((path) => (
                          <button
                            key={path.id}
                            type="button"
                            className={`graph-summary-path-card${activePath?.id === path.id ? " graph-summary-path-card--active" : ""}`}
                            onClick={() => selectPath(path)}
                          >
                            <PathTraceView path={path} nodes={data.nodes} edges={data.edges} compact />
                            <Tag className="graph-summary-path-hop">{path.length} 跳</Tag>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <Empty
                        className="graph-summary-single-empty"
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={pathHopFilter === "all" ? "两点之间暂无同类型连通路径" : "当前跳数下暂无路径"}
                      />
                    )}

                    {data.common_neighbors.length ? (
                      <>
                        <Divider className="graph-summary-divider" />
                        <div className="graph-summary-common-block">
                          <Text strong className="graph-summary-common-title">共同关联</Text>
                          <div className="graph-summary-common-list">
                            {data.common_neighbors.map((item) => (
                              <button
                                key={item.node_id}
                                type="button"
                                className="graph-summary-common-chip"
                                onClick={() => {
                                  selectNodeById(item.node_id);
                                  setViewMode("common");
                                }}
                              >
                                <span>{item.label}</span>
                                {item.relation_types.map((type) => (
                                  <Tag key={type} color={relationColor(type)}>
                                    {relationShortLabel(type)}
                                  </Tag>
                                ))}
                              </button>
                            ))}
                          </div>
                        </div>
                      </>
                    ) : null}
                  </>
                ) : null}
              </div>
            </div>
          ) : null}
        </Card>
      </section>

      {data?.truncated ? <Alert type="warning" showIcon message={data.truncated_reason || "图谱结果已截断"} /> : null}

      <Spin spinning={loading}>
        <Row gutter={[16, 16]} className="graph-workbench-top">
          <Col xs={24} xl={17}>
            <section className={`graph-zone graph-zone-canvas${graphFullscreen ? " graph-canvas-fullscreen" : ""}`}>
              <ZoneLabel title="图谱区" />
              <Card
                className="graph-canvas-card"
                title={
                  <Space>
                    <NodeIndexOutlined />
                    {caseId ? `关系图谱 · ${selectedCase?.case_name || "未命名案件"}` : "关系图谱"}
                  </Space>
                }
                extra={
                  <Space wrap>
                    <Segmented
                      size="small"
                      value={viewMode}
                      onChange={(v) => setViewMode(v as "all" | "paths" | "common")}
                      options={[
                        { label: "全部", value: "all" },
                        { label: "A-B路径", value: "paths", disabled: !data?.paths.length },
                        { label: "共同关联", value: "common", disabled: !data?.common_neighbors.length },
                      ]}
                    />
                    <Button
                      size="small"
                      icon={graphFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                      onClick={() => setGraphFullscreen((value) => !value)}
                    >
                      {graphFullscreen ? "退出全屏" : "全屏"}
                    </Button>
                  </Space>
                }
              >
                {chartOption ? (
                  <>
                    <ReactECharts
                      ref={graphChartRef}
                      option={chartOption}
                      style={graphChartStyle}
                      notMerge
                      lazyUpdate={false}
                      onEvents={graphEvents}
                    />
                    <div className="graph-canvas-footer">
                      <div className="graph-canvas-legends">
                        <div className="graph-legend-group">
                          <Text type="secondary">节点图例：</Text>
                          {NODE_LEGEND_ITEMS.map((item) => (
                            <span key={item.key} className="graph-node-legend-item">
                              <span
                                className="graph-node-legend-swatch"
                                style={{ backgroundColor: NODE_COLORS[item.key] }}
                              />
                              {item.label}
                            </span>
                          ))}
                        </div>
                        <div className="graph-legend-group">
                          <Text type="secondary">关系图例：</Text>
                          {RELATION_OPTIONS.filter((item) => relationTypes.includes(item.value)).map((item) => (
                            <span key={item.value} className="graph-relation-legend-item">
                              <span
                                className="graph-relation-legend-swatch"
                                style={{
                                  borderTopColor: item.color,
                                  borderTopStyle: item.value === "identifier" ? "dashed" : "solid",
                                }}
                              />
                              {RELATION_LEGEND_LABELS[item.value] || item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      {extensionLevelControl}
                    </div>
                  </>
                ) : (
                  <div className="graph-empty" style={{ minHeight: graphFullscreen ? "calc(100vh - 148px)" : 620, flex: graphFullscreen ? 1 : undefined }}>
                    <Empty description={graphEmptyDescription} />
                    <div className="graph-canvas-footer graph-canvas-footer--empty">{extensionLevelControl}</div>
                  </div>
                )}
              </Card>
            </section>
          </Col>

          <Col xs={24} xl={7}>
            <section className="graph-zone graph-zone-observation graph-observation-column">
              <ZoneLabel title="观察区" />
              <Card
                className="graph-observation-card"
                size="small"
                extra={
                  observations.length ? (
                    <Button size="small" danger icon={<ClearOutlined />} onClick={clearObservations}>
                      清空
                    </Button>
                  ) : null
                }
              >
                <List
                  size="small"
                  dataSource={observations}
                  locale={{ emptyText: caseId ? "暂无观察对象，选中节点或关系后加入" : "请选择案件后查看观察区" }}
                  renderItem={(item) => (
                    <List.Item
                      className="graph-observation-item"
                      actions={[
                        <Button key="detail" type="link" size="small" icon={<FileSearchOutlined />} onClick={() => void openObservationRecords(item)}>
                          详情
                        </Button>,
                        <Button key="focus" type="link" size="small" onClick={() => focusObservation(item)}>
                          定位
                        </Button>,
                        <Button key="remove" type="link" size="small" danger onClick={() => removeObservation(item.key)}>
                          移除
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={<Text strong>{item.label}</Text>}
                        description={item.subLabel}
                      />
                    </List.Item>
                  )}
                />
              </Card>
            </section>
          </Col>
        </Row>

        <Row gutter={[16, 16]} className="graph-workbench-bottom">
          <Col xs={24}>
            <section className="graph-zone graph-zone-selection">
              <ZoneLabel title="选中区" />
              <Card className="graph-selection-card" size="small">
                {selectedNode ? (
                  <Row gutter={[20, 12]} className="graph-selection-layout" align="top">
                    <Col xs={24} lg={7} xl={6}>
                      <div className="graph-detail-box graph-selection-profile">
                        <Title level={5}>{selectedNode.label}</Title>
                        <Descriptions column={1} size="small" bordered>
                          <Descriptions.Item label="类型">
                            <Tag color={NODE_COLORS[selectedNode.type]}>{selectedNode.display_type}</Tag>
                          </Descriptions.Item>
                          <Descriptions.Item label="层级">第 {selectedNode.depth + 1} 级</Descriptions.Item>
                          <Descriptions.Item label="关系数">{selectedNode.degree} 条</Descriptions.Item>
                        </Descriptions>
                        {selectedNode.identifiers?.length ? (
                          <Table
                            size="small"
                            title={() => <Text strong>节点标识</Text>}
                            pagination={false}
                            rowKey={(_, idx) => `sel-id-${idx}`}
                            columns={[
                              { title: "类型", dataIndex: "display_label", width: 88 },
                              { title: "标识", dataIndex: "identifier_value", ellipsis: true },
                            ]}
                            dataSource={selectedNode.identifiers}
                            style={{ marginTop: 12 }}
                          />
                        ) : null}
                        {Object.keys(selectedNode.stats || {}).length ? (
                          <div className="graph-node-stats">
                            {Object.entries(selectedNode.stats).map(([type, count]) => (
                              <Tag key={type} color={relationColor(type)}>
                                {RELATION_OPTIONS.find((r) => r.value === type)?.label || type} {count}
                              </Tag>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </Col>
                    <Col xs={24} lg={17} xl={18}>
                      <Table
                        className="graph-selection-relations-table"
                        size="small"
                        title={() => <Text strong>往来关系（银行 / 微信转账 / 通讯等）</Text>}
                        pagination={selectedNodeInteractionEdges.length > 8 ? { pageSize: 8, size: "small" } : false}
                        rowKey="id"
                        columns={relationEdgeColumns}
                        dataSource={selectedNodeInteractionEdges}
                        locale={{ emptyText: "暂无往来关系" }}
                        scroll={{ x: 480 }}
                        onRow={(edge) => ({
                          onClick: () => selectEdgeById(edge.id),
                          className: "graph-clickable-row",
                        })}
                      />
                    </Col>
                  </Row>
                ) : selectedEdge ? (
                    <div className="graph-detail-box">
                      <Title level={5}>{selectedEdge.display_type}</Title>
                      <Descriptions column={1} size="small" bordered>
                        <Descriptions.Item label="强度">{selectedEdge.weight}</Descriptions.Item>
                        <Descriptions.Item label="记录">{selectedEdge.record_count} 条</Descriptions.Item>
                        <Descriptions.Item label={selectedEdge.type === "telecom" ? "通话时长" : "金额"}>
                          {selectedEdge.type === "telecom"
                            ? `${selectedEdge.duration_sec ?? 0} 秒`
                            : formatAmount(selectedEdge.amount)}
                        </Descriptions.Item>
                      </Descriptions>
                    </div>
                  ) : activePath && viewMode === "paths" ? (
                    <div className="graph-detail-box">
                      <Title level={5}>A-B 路径</Title>
                      <div className="graph-path-detail-trace">
                        <PathTraceView path={activePath} nodes={data?.nodes || []} edges={data?.edges || []} />
                      </div>
                      <Descriptions column={2} size="small" bordered style={{ marginTop: 12 }}>
                        <Descriptions.Item label="跳数">{activePath.length} 跳</Descriptions.Item>
                        <Descriptions.Item label="关系">{activePath.edges.length} 条</Descriptions.Item>
                      </Descriptions>
                      <List
                        size="small"
                        style={{ marginTop: 12 }}
                        dataSource={activePath.edges.map((edgeId) => data?.edges.find((edge) => edge.id === edgeId)).filter(Boolean) as GraphExploreEdge[]}
                        locale={{ emptyText: "路径关系为空" }}
                        renderItem={(edge) => {
                          const source = data?.nodes.find((node) => node.id === edge.source);
                          const target = data?.nodes.find((node) => node.id === edge.target);
                          return (
                            <List.Item className="graph-clickable-row" onClick={() => selectEdgeById(edge.id)}>
                              <Tag color={relationColor(edge.type)}>{edge.display_type}</Tag>
                              <Text>{source?.label || edge.source} → {target?.label || edge.target}</Text>
                            </List.Item>
                          );
                        }}
                      />
                    </div>
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击图谱中的节点或关系" />
                  )}

                <div className="graph-selection-actions">
                  <Space wrap>
                    <Button
                      icon={<FileSearchOutlined />}
                      disabled={!canAddObservation}
                      loading={detailLoading}
                      onClick={() => void openSelectionRecords()}
                    >
                      查看详情数据
                    </Button>
                    <Button type="primary" icon={<PlusOutlined />} disabled={!canAddObservation || selectionInObservation} onClick={addSelectionToObservation}>
                      {selectionInObservation
                        ? "已在观察区"
                        : activePath && viewMode === "paths" && !selectedNode && !selectedEdge
                          ? "整条路径加入观察区"
                          : "加入观察区"}
                    </Button>
                  </Space>
                </div>
              </Card>
            </section>
          </Col>
        </Row>
      </Spin>
      {drawers}
    </div>
  );
}

export default GraphExplorePage;
