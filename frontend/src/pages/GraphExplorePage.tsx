import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Collapse,
  Descriptions,
  Empty,
  List,
  Row,
  Segmented,
  Select,
  Slider,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  BranchesOutlined,
  ClearOutlined,
  EyeOutlined,
  FileSearchOutlined,
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
  GraphExploreResponse,
  PersonInfo,
} from "../api";
import {
  createEdgeObservation,
  createNodeObservation,
  loadGraphObservations,
  saveGraphObservations,
  type GraphObservationItem,
} from "../utils/graphObservationStorage";
import { useFusionRecordDrawers } from "../components/fusion/FusionRecordDrawers";
import {
  formatFusionAmount,
  recordsForGraphSelection,
  recordsForObservationItem,
  recordsFromEdge,
} from "../utils/graphRecordUtils";

const { Title, Text, Paragraph } = Typography;

const RELATION_OPTIONS = [
  { label: "资金", value: "bank_txn", color: "#e85d45" },
  { label: "微信", value: "wechat", color: "#52c41a" },
  { label: "通讯", value: "telecom", color: "#1890ff" },
  { label: "工商", value: "enterprise", color: "#722ed1" },
  { label: "商务", value: "commercial", color: "#fa8c16" },
  { label: "标识", value: "identifier", color: "#94a3b8" },
];

const NODE_COLORS: Record<string, string> = {
  person: "#e85d45",
  phone: "#1890ff",
  bank_card: "#fa8c16",
  wechat: "#52c41a",
  enterprise: "#722ed1",
  commercial_event: "#f59e0b",
  unknown: "#94a3b8",
};

function relationColor(type: string) {
  return RELATION_OPTIONS.find((item) => item.value === type)?.color || "#94a3b8";
}

function formatAmount(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return formatFusionAmount(value);
}

function ZoneLabel({ title }: { title: string }) {
  return <div className="graph-zone-label">{title}</div>;
}

function GraphExplorePage({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [cases, setCases] = useState<Array<{ case_id: number; case_name: string; batch_count: number }>>([]);
  const [caseId, setCaseId] = useState<number | null>(null);
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [anchorA, setAnchorA] = useState<number | null>(null);
  const [anchorB, setAnchorB] = useState<number | null>(null);
  const [displayLevel, setDisplayLevel] = useState(2);
  const [unlimited, setUnlimited] = useState(false);
  const [relationTypes, setRelationTypes] = useState<string[]>(RELATION_OPTIONS.map((item) => item.value));
  const [minWeight, setMinWeight] = useState(1);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<GraphExploreResponse | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphExploreNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphExploreEdge | null>(null);
  const [selectedPathEdgeIds, setSelectedPathEdgeIds] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<"all" | "paths" | "common">("all");
  const [observations, setObservations] = useState<GraphObservationItem[]>([]);
  const { openRecords, drawers } = useFusionRecordDrawers(caseId);

  const refreshCases = useCallback(async () => {
    const res = await api.listCases();
    setCases(res.items);
    const paramCase = searchParams.get("case");
    const stored = localStorage.getItem(CASE_STORAGE_KEY);
    const next = paramCase ? Number(paramCase) : stored ? Number(stored) : res.items[0]?.case_id ?? null;
    setCaseId(res.items.some((item) => item.case_id === next) ? next : res.items[0]?.case_id ?? null);
  }, [searchParams]);

  useEffect(() => {
    void refreshCases().catch((err) => message.error((err as Error).message));
  }, [refreshCases]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId;
      if (nextCaseId) setCaseId(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, []);

  useEffect(() => {
    if (!caseId) return;
    localStorage.setItem(CASE_STORAGE_KEY, String(caseId));
    setObservations(loadGraphObservations(caseId));
    if (searchParams.get("case") !== String(caseId)) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set("case", String(caseId));
      setSearchParams(nextParams, { replace: true });
    }
  }, [caseId, searchParams, setSearchParams]);

  useEffect(() => {
    if (!caseId) return;
    setData(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    void api
      .listCasePersons(caseId)
      .then((res) => {
        setPersons(res.items);
        const personParam = searchParams.get("person");
        const preferred = personParam ? Number(personParam) : null;
        setAnchorA((current) =>
          current && res.items.some((p) => p.person_id === current)
            ? current
            : preferred && res.items.some((p) => p.person_id === preferred)
              ? preferred
              : res.items[0]?.person_id ?? null
        );
        setAnchorB(null);
      })
      .catch((err) => message.error((err as Error).message));
  }, [caseId, searchParams]);

  const persistObservations = useCallback(
    (items: GraphObservationItem[]) => {
      if (!caseId) return;
      setObservations(items);
      saveGraphObservations(caseId, items);
    },
    [caseId]
  );

  const backToJudgment = useCallback(() => {
    const query = caseId ? `?case=${caseId}&view=analysis&tab=open` : "?tab=open";
    navigate(`/fusion-cockpit${query}`);
  }, [caseId, navigate]);

  const personOptions = persons.map((p) => ({
    value: p.person_id,
    label: `${p.display_name}${p.links.length ? ` · ${p.links.length}个标识` : ""}`,
  }));

  const explore = useCallback(async () => {
    if (!caseId || !anchorA) return;
    setLoading(true);
    setSelectedNode(null);
    setSelectedEdge(null);
    setSelectedPathEdgeIds(new Set());
    try {
      const anchors = [{ type: "person", value: String(anchorA) }];
      if (anchorB && anchorB !== anchorA) anchors.push({ type: "person", value: String(anchorB) });
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
      setViewMode("all");
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [anchorA, anchorB, caseId, displayLevel, minWeight, relationTypes, unlimited]);

  const visibleEdgeIds = useMemo(() => {
    if (!data) return new Set<string>();
    if (viewMode === "paths") return new Set(data.paths.flatMap((path) => path.edges));
    if (viewMode === "common") {
      const common = new Set(data.common_neighbors.map((item) => item.node_id));
      return new Set(data.edges.filter((edge) => common.has(edge.source) || common.has(edge.target)).map((edge) => edge.id));
    }
    return new Set(data.edges.map((edge) => edge.id));
  }, [data, viewMode]);

  const chartOption = useMemo(() => {
    if (!data?.nodes.length) return null;
    const visibleNodeIds = new Set<string>();
    data.edges.forEach((edge) => {
      if (visibleEdgeIds.has(edge.id)) {
        visibleNodeIds.add(edge.source);
        visibleNodeIds.add(edge.target);
      }
    });
    data.anchors.forEach((id) => visibleNodeIds.add(id));
    const nodes = data.nodes.filter((node) => visibleNodeIds.has(node.id)).map((node) => ({
      ...node,
      name: node.label,
      category: node.type,
      symbolSize: node.is_anchor ? 68 : Math.max(24, 48 - node.depth * 4),
      cursor: "pointer",
      itemStyle: {
        color: NODE_COLORS[node.type] || NODE_COLORS.unknown,
        borderColor:
          selectedNode?.id === node.id
            ? "#111827"
            : node.is_anchor
              ? "#fff"
              : node.depth <= 1
                ? "rgba(255,255,255,0.9)"
                : "rgba(255,255,255,0.55)",
        borderWidth: selectedNode?.id === node.id ? 5 : node.is_anchor ? 4 : 2,
        shadowBlur: selectedNode?.id === node.id ? 28 : node.is_anchor ? 18 : 8,
        shadowColor: selectedNode?.id === node.id ? "rgba(17,24,39,0.32)" : "rgba(15,23,42,0.18)",
      },
      label: { show: node.depth <= 2 || node.is_anchor || selectedNode?.id === node.id, fontWeight: node.is_anchor ? 700 : 500 },
    }));
    const links = data.edges.filter((edge) => visibleEdgeIds.has(edge.id)).map((edge) => {
      const isSelected = selectedEdge?.id === edge.id || selectedPathEdgeIds.has(edge.id);
      return {
        ...edge,
        value: edge.weight,
        cursor: "pointer",
        lineStyle: {
          width: isSelected ? Math.max(5, Math.min(14, 2.5 + Math.sqrt(edge.weight) * 2.2)) : Math.max(1.5, Math.min(12, 1.5 + Math.sqrt(edge.weight) * 1.8)),
          color: isSelected ? "#111827" : relationColor(edge.type),
          opacity: isSelected ? 1 : viewMode === "all" ? 0.72 : 0.95,
          curveness: 0.12,
          type: edge.type === "identifier" ? "dashed" : "solid",
        },
        label: { show: isSelected, formatter: edge.display_type, color: "#111827", fontWeight: 700 },
      };
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
            const edge = item as GraphExploreEdge;
            return `<strong>${edge.display_type}</strong><br/>强度 ${edge.weight} · 记录 ${edge.record_count}<br/>金额 ${formatAmount(edge.amount)}<br/>点击查看明细`;
          }
          const node = item as GraphExploreNode;
          return `<strong>${node.label}</strong><br/>${node.display_type} · 第 ${node.depth + 1} 级<br/>关系数 ${node.degree}`;
        },
      },
      legend: [
        {
          bottom: 4,
          data: Object.keys(NODE_COLORS),
          formatter: (name: string) =>
            ({ person: "人物", phone: "手机", bank_card: "银行卡", wechat: "微信", enterprise: "企业", commercial_event: "商务事件", unknown: "其他" }[name] || name),
        },
      ],
      series: [
        {
          type: "graph",
          layout: "force",
          cursor: "pointer",
          roam: true,
          draggable: true,
          focusNodeAdjacency: true,
          categories: Object.keys(NODE_COLORS).map((name) => ({ name })),
          data: nodes,
          links,
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: [0, 8],
          force: { repulsion: 620, gravity: 0.045, edgeLength: [110, 230], friction: 0.32, layoutAnimation: true },
          emphasis: { focus: "adjacency", scale: 1.08 },
        },
      ],
    };
  }, [data, selectedEdge?.id, selectedNode?.id, selectedPathEdgeIds, viewMode, visibleEdgeIds]);

  const selectNodeById = useCallback(
    (nodeId: string) => {
      const node = data?.nodes.find((item) => item.id === nodeId);
      if (!node) return;
      setSelectedNode(node);
      setSelectedEdge(null);
      setSelectedPathEdgeIds(new Set());
    },
    [data]
  );

  const selectEdgeById = useCallback(
    (edgeId: string) => {
      const edge = data?.edges.find((item) => item.id === edgeId);
      if (!edge) return;
      setSelectedEdge(edge);
      setSelectedNode(null);
      setSelectedPathEdgeIds(new Set());
    },
    [data]
  );

  const graphEvents = useMemo(
    () => ({
      click: (params: { dataType?: string; data?: GraphExploreNode & GraphExploreEdge }) => {
        if (!params.data) return;
        setSelectedPathEdgeIds(new Set());
        if (params.dataType === "edge") {
          const edgeId = String((params.data as GraphExploreEdge).id || "");
          selectEdgeById(edgeId);
          return;
        }
        const nodeId = String((params.data as GraphExploreNode).id || "");
        selectNodeById(nodeId);
      },
    }),
    [selectEdgeById, selectNodeById]
  );

  const selectPath = useCallback((edgeIds: string[]) => {
    setSelectedPathEdgeIds(new Set(edgeIds));
    setSelectedNode(null);
    setSelectedEdge(null);
    setViewMode("paths");
  }, []);

  const observationKeys = useMemo(() => new Set(observations.map((item) => item.key)), [observations]);

  const addSelectionToObservation = useCallback(() => {
    if (!caseId) return;
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
  }, [caseId, data?.edges, data?.nodes, observationKeys, observations, persistObservations, selectedEdge, selectedNode]);

  const openSelectionRecords = useCallback(() => {
    if (selectedNode) {
      const records = recordsForGraphSelection({ node: selectedNode, edges: data?.edges || [] });
      const meta: Record<string, string> = {
        节点类型: selectedNode.display_type,
        所在层级: `第 ${selectedNode.depth + 1} 级`,
        关系数量: `${selectedNode.degree} 条`,
        样例记录: `${records.length} 条`,
      };
      openRecords(selectedNode.label, records, meta);
      return;
    }
    if (selectedEdge) {
      const records = recordsFromEdge(selectedEdge);
      const source = data?.nodes.find((node) => node.id === selectedEdge.source);
      const target = data?.nodes.find((node) => node.id === selectedEdge.target);
      const meta: Record<string, string> = {
        关系类型: selectedEdge.display_type,
        关系强度: String(selectedEdge.weight),
        记录总数: `${selectedEdge.record_count} 条`,
        样例记录: `${records.length} 条`,
      };
      openRecords(`${source?.label || selectedEdge.source} → ${target?.label || selectedEdge.target}`, records, meta);
    }
  }, [data?.edges, data?.nodes, openRecords, selectedEdge, selectedNode]);

  const openObservationRecords = useCallback(
    (item: GraphObservationItem) => {
      const records = recordsForObservationItem(item, data?.edges || []);
      let meta: Record<string, string> = { 样例记录: `${records.length} 条` };
      if (item.kind === "node" && item.node) {
        meta = {
          节点类型: item.node.display_type,
          所在层级: `第 ${item.node.depth + 1} 级`,
          样例记录: `${records.length} 条`,
        };
      } else if (item.edge) {
        meta = {
          关系类型: item.edge.display_type,
          记录总数: `${item.edge.record_count} 条`,
          样例记录: `${records.length} 条`,
        };
      }
      openRecords(item.label, records, meta);
    },
    [data?.edges, openRecords]
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
      if (item.kind === "node" && item.node) {
        selectNodeById(item.node.id);
        return;
      }
      if (item.kind === "edge" && item.edge) {
        selectEdgeById(item.edge.id);
      }
    },
    [selectEdgeById, selectNodeById]
  );

  const selectedCase = cases.find((item) => item.case_id === caseId);
  const canAddObservation = Boolean(selectedNode || selectedEdge);
  const selectionInObservation = Boolean(
    (selectedNode && observationKeys.has(`node:${selectedNode.id}`)) ||
      (selectedEdge && observationKeys.has(`edge:${selectedEdge.id}`))
  );

  return (
    <div className="graph-explore-page">
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
            <Paragraph>筛选区设定分析范围，图谱区点击节点或关系查看详情，观察区持久保存关注对象。</Paragraph>
          </div>
          <Space wrap>
            <Tag color="volcano">{selectedCase?.case_name || "请选择案件"}</Tag>
            <Tag icon={<EyeOutlined />}>观察区 {observations.length}</Tag>
          </Space>
        </div>
      </div>

      <section className="graph-zone graph-zone-filter">
        <ZoneLabel title="筛选区" />
        <Card className="graph-query-card">
          <Row gutter={[14, 14]} align="middle">
            <Col xs={24} md={5}>
              <Text strong>中心对象 A</Text>
              <Select showSearch optionFilterProp="label" style={{ width: "100%", marginTop: 8 }} placeholder="选择人物 A" value={anchorA ?? undefined} options={personOptions} onChange={setAnchorA} />
            </Col>
            <Col xs={24} md={5}>
              <Text strong>加入对象 B</Text>
              <Select allowClear showSearch optionFilterProp="label" style={{ width: "100%", marginTop: 8 }} placeholder="可选" value={anchorB ?? undefined} options={personOptions.filter((p) => p.value !== anchorA)} onChange={(value) => setAnchorB(value ?? null)} />
            </Col>
            <Col xs={24} md={7}>
              <Text strong>扩张层级</Text>
              <Segmented
                block
                style={{ marginTop: 8 }}
                value={unlimited ? "unlimited" : displayLevel}
                onChange={(value) => {
                  if (value === "unlimited") setUnlimited(true);
                  else {
                    setUnlimited(false);
                    setDisplayLevel(Number(value));
                  }
                }}
                options={[
                  { label: "一级", value: 1 },
                  { label: "二级", value: 2 },
                  { label: "三级", value: 3 },
                  { label: "四级", value: 4 },
                  { label: "无限", value: "unlimited" },
                ]}
              />
            </Col>
            <Col xs={24} md={4}>
              <Text strong>强度：{minWeight}+</Text>
              <Slider min={1} max={10} value={minWeight} onChange={setMinWeight} />
            </Col>
            <Col xs={24} md={3}>
              <Button block type="primary" icon={<SearchOutlined />} onClick={() => void explore()} disabled={!anchorA || !caseId || !relationTypes.length}>
                分析
              </Button>
            </Col>
            <Col xs={24}>
              <div className="graph-query-actions compact">
                <Text type="secondary">关系类型</Text>
                <Checkbox.Group value={relationTypes} onChange={(values) => setRelationTypes(values.map(String))} options={RELATION_OPTIONS.map((item) => ({ label: item.label, value: item.value }))} />
              </div>
            </Col>
          </Row>

          {data ? (
            <Collapse
              ghost
              className="graph-filter-collapse"
              items={[
                {
                  key: "summary",
                  label: `探索概要 · 节点 ${data.summary.node_count} · 关系 ${data.summary.edge_count}`,
                  children: (
                    <div className="graph-filter-summary">
                      <Row gutter={[10, 10]}>
                        <Col span={6}><Statistic title="路径" value={data.summary.path_count} /></Col>
                        <Col span={6}><Statistic title="共同关联" value={data.summary.common_neighbor_count} /></Col>
                      </Row>
                      <List
                        size="small"
                        header="A-B 关键路径"
                        dataSource={data.paths}
                        locale={{ emptyText: "选择 B 后显示路径" }}
                        renderItem={(path) => (
                          <List.Item className="graph-clickable-row" onClick={() => selectPath(path.edges)}>
                            <BranchesOutlined />
                            <Text ellipsis>{path.nodes.map((nodeId) => data.nodes.find((node) => node.id === nodeId)?.label || nodeId).join(" → ")}</Text>
                            <Tag>{path.length}跳</Tag>
                          </List.Item>
                        )}
                      />
                      <List
                        size="small"
                        header="共同关联"
                        dataSource={data.common_neighbors}
                        locale={{ emptyText: "暂无共同邻居" }}
                        renderItem={(item) => (
                          <List.Item className="graph-clickable-row" onClick={() => selectNodeById(item.node_id)}>
                            <Text strong>{item.label}</Text>
                            {item.relation_types.map((type) => (
                              <Tag key={type}>{RELATION_OPTIONS.find((r) => r.value === type)?.label || type}</Tag>
                            ))}
                          </List.Item>
                        )}
                      />
                    </div>
                  ),
                },
              ]}
            />
          ) : null}
        </Card>
      </section>

      {data?.truncated ? <Alert type="warning" showIcon message={data.truncated_reason || "图谱结果已截断"} /> : null}

      <Spin spinning={loading}>
        <Row gutter={[16, 16]} className="graph-workbench">
          <Col xs={24} xl={15}>
            <section className="graph-zone graph-zone-canvas">
              <ZoneLabel title="图谱区" />
              <Card
                className="graph-canvas-card"
                title={
                  <Space>
                    <NodeIndexOutlined />
                    关系图谱
                  </Space>
                }
                extra={
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
                }
              >
                {chartOption ? (
                  <ReactECharts option={chartOption} style={{ height: 620 }} notMerge lazyUpdate onEvents={graphEvents} />
                ) : (
                  <div className="graph-empty">
                    <Empty description="请在筛选区选择中心对象并开始分析" />
                  </div>
                )}
              </Card>
            </section>
          </Col>

          <Col xs={24} xl={9}>
            <div className="graph-side-stack">
              <section className="graph-zone graph-zone-selection">
                <ZoneLabel title="当前选中" />
                <Card className="graph-selection-card" size="small">
                  {selectedNode ? (
                    <div className="graph-detail-box">
                      <Title level={5}>{selectedNode.label}</Title>
                      <Descriptions column={1} size="small" bordered>
                        <Descriptions.Item label="类型">
                          <Tag color={NODE_COLORS[selectedNode.type]}>{selectedNode.display_type}</Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="层级">第 {selectedNode.depth + 1} 级</Descriptions.Item>
                        <Descriptions.Item label="关系数">{selectedNode.degree} 条</Descriptions.Item>
                      </Descriptions>
                      <List
                        size="small"
                        header="相关关系"
                        dataSource={(data?.edges || []).filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).slice(0, 6)}
                        locale={{ emptyText: "暂无" }}
                        renderItem={(edge) => {
                          const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
                          const other = data?.nodes.find((node) => node.id === otherId);
                          return (
                            <List.Item className="graph-clickable-row" onClick={() => selectEdgeById(edge.id)}>
                              <Tag color={relationColor(edge.type)}>{edge.display_type}</Tag>
                              <Text ellipsis>{other?.label || otherId}</Text>
                            </List.Item>
                          );
                        }}
                      />
                    </div>
                  ) : selectedEdge ? (
                    <div className="graph-detail-box">
                      <Title level={5}>{selectedEdge.display_type}</Title>
                      <Descriptions column={1} size="small" bordered>
                        <Descriptions.Item label="强度">{selectedEdge.weight}</Descriptions.Item>
                        <Descriptions.Item label="记录">{selectedEdge.record_count} 条</Descriptions.Item>
                        <Descriptions.Item label="金额">{formatAmount(selectedEdge.amount)}</Descriptions.Item>
                      </Descriptions>
                    </div>
                  ) : selectedPathEdgeIds.size ? (
                    <Paragraph type="secondary">已高亮 {selectedPathEdgeIds.size} 条路径关系，点击图中节点或连线查看详情。</Paragraph>
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击图谱中的节点或关系" />
                  )}

                  <div className="graph-selection-actions">
                    <Space wrap>
                      <Button
                        icon={<FileSearchOutlined />}
                        disabled={!canAddObservation}
                        onClick={openSelectionRecords}
                      >
                        查看详情数据
                      </Button>
                      <Button type="primary" icon={<PlusOutlined />} disabled={!canAddObservation || selectionInObservation} onClick={addSelectionToObservation}>
                        {selectionInObservation ? "已在观察区" : "加入观察区"}
                      </Button>
                    </Space>
                  </div>
                </Card>
              </section>

              <section className="graph-zone graph-zone-observation">
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
                  <Paragraph type="secondary" className="graph-observation-hint">
                    观察区在本案件分析过程中持久保存，可随时回看已关注节点与关系。
                  </Paragraph>
                  <List
                    size="small"
                    dataSource={observations}
                    locale={{ emptyText: "暂无观察对象，选中节点或关系后加入" }}
                    renderItem={(item) => (
                      <List.Item
                        className="graph-observation-item"
                        actions={[
                          <Button key="detail" type="link" size="small" icon={<FileSearchOutlined />} onClick={() => openObservationRecords(item)}>
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
                          title={
                            <Space>
                              <Tag color={item.kind === "node" ? "blue" : "orange"}>{item.kind === "node" ? "节点" : "关系"}</Tag>
                              <Text strong>{item.label}</Text>
                            </Space>
                          }
                          description={item.subLabel}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </section>
            </div>
          </Col>
        </Row>
      </Spin>
      {drawers}
    </div>
  );
}

export default GraphExplorePage;
