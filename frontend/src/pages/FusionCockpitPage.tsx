import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Avatar,
  Button,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Card,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  BankOutlined,
  ForkOutlined,
  PhoneOutlined,
  ReloadOutlined,
  TeamOutlined,
  UserOutlined,
  WechatOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  CASE_CHANGED_EVENT,
  CASE_STORAGE_KEY,
  FusionRecord,
  PersonCockpitResponse,
  PersonInfo,
  RecordDetailResponse,
  RelationCockpitResponse,
  AnchorCockpitResponse,
  AnchorSuggestItem,
} from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT } from "../components/WorkflowGuide";
import { dataManageTablesPath } from "./DataManageLayout";
import { chartPalette } from "../theme";
import "dayjs/locale/zh-cn";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

const RECORD_TYPE_LABELS: Record<string, string> = {
  bank_txn: "银行流水",
  wechat: "微信转账",
  telecom: "通讯话单",
  enterprise: "工商主体",
  commercial: "商务网",
};

const RECORD_TYPE_COLORS: Record<string, string> = {
  bank_txn: "#e85d45",
  wechat: "#52c41a",
  telecom: "#1890ff",
  enterprise: "#722ed1",
  commercial: "#fa8c16",
};

const KPI_CONFIG = [
  { key: "bank", label: "银行流水", icon: <BankOutlined />, tone: "tone-bank" },
  { key: "wechat", label: "微信转账", icon: <WechatOutlined />, tone: "tone-wechat" },
  { key: "telecom", label: "通讯话单", icon: <PhoneOutlined />, tone: "tone-telecom" },
  { key: "other", label: "企业/商务", icon: <TeamOutlined />, tone: "tone-other" },
] as const;

function formatAmount(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function personInitial(name: string) {
  return (name || "?").slice(0, 1);
}

function buildPersonOption(p: PersonInfo) {
  const phones = p.links.filter((l) => l.identifier_type === "phone").length;
  const banks = p.links.filter((l) => l.identifier_type === "bank_card" || l.identifier_type === "bank_acct").length;
  const hint = [phones ? `${phones}手机` : "", banks ? `${banks}卡` : ""].filter(Boolean).join(" · ");
  return {
    value: p.person_id,
    label: p.display_name,
    hint,
  };
}

function channelLabel(channels: Record<string, number> | undefined) {
  if (!channels) return "—";
  return Object.entries(channels)
    .map(([k, v]) => `${RECORD_TYPE_LABELS[k] || k} ${v}`)
    .join(" · ");
}

interface GraphNode {
  id: string;
  name: string;
  category: number;
  symbolSize?: number;
  isCenter?: boolean;
  stats?: Record<string, number>;
}

interface GraphLink {
  source: string;
  target: string;
  value: number;
  lineWidth?: number;
  totalAmount?: number;
  channels?: Record<string, number>;
  records?: FusionRecord[];
}

const ANCHOR_TYPE_OPTIONS = [
  { value: "auto", label: "自动识别" },
  { value: "bank_card", label: "银行卡/账号" },
  { value: "phone", label: "手机号" },
  { value: "wechat_name", label: "微信名" },
  { value: "enterprise_name", label: "企业名称" },
  { value: "person_name", label: "姓名" },
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

interface FusionCockpitPageProps {
  embeddedInHub?: boolean;
  caseIdOverride?: number | null;
  onBackToOpenList?: () => void;
}

function FusionCockpitPage({ embeddedInHub = false, caseIdOverride = null, onBackToOpenList }: FusionCockpitPageProps) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [mode, setMode] = useState<"person" | "relation" | "anchor">("person");
  const [cases, setCases] = useState<Array<{ case_id: number; case_name: string; batch_count: number }>>([]);
  const [caseId, setCaseId] = useState<number | null>(null);
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [personId, setPersonId] = useState<number | null>(null);
  const [personBId, setPersonBId] = useState<number | null>(null);
  const [personData, setPersonData] = useState<PersonCockpitResponse | null>(null);
  const [relationData, setRelationData] = useState<RelationCockpitResponse | null>(null);
  const [anchorData, setAnchorData] = useState<AnchorCockpitResponse | null>(null);
  const [anchorType, setAnchorType] = useState("auto");
  const [anchorQuery, setAnchorQuery] = useState("");
  const [anchorSuggestions, setAnchorSuggestions] = useState<AnchorSuggestItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRecord, setDetailRecord] = useState<FusionRecord | null>(null);
  const [rawDetail, setRawDetail] = useState<RecordDetailResponse | null>(null);
  const [rawLoading, setRawLoading] = useState(false);
  const [graphDetailOpen, setGraphDetailOpen] = useState(false);
  const [graphDetailPlacement, setGraphDetailPlacement] = useState<"left" | "right">("right");
  const [graphDetailTitle, setGraphDetailTitle] = useState("");
  const [telecomDateRange, setTelecomDateRange] = useState<[string, string] | null>(null);
  const [graphDetailRecords, setGraphDetailRecords] = useState<FusionRecord[]>([]);
  const [graphDetailMeta, setGraphDetailMeta] = useState<Record<string, string>>({});
  const graphChartRef = useRef<ReactECharts>(null);

  const selectedPerson = useMemo(() => persons.find((p) => p.person_id === personId) || null, [persons, personId]);
  const selectedPersonB = useMemo(() => persons.find((p) => p.person_id === personBId) || null, [persons, personBId]);
  const personOptions = useMemo(() => persons.map(buildPersonOption), [persons]);
  const overviewData = mode === "anchor" ? anchorData : personData;

  const syncCaseQuery = useCallback(
    (id: number) => {
      if (embeddedInHub) {
        const next = new URLSearchParams(searchParams);
        next.set("case", String(id));
        next.set("view", "analysis");
        next.set("tab", "open");
        setSearchParams(next, { replace: true });
      } else {
        setSearchParams({ case: String(id) });
      }
    },
    [embeddedInHub, searchParams, setSearchParams]
  );

  const refreshCases = useCallback(async () => {
    const data = await api.listCases();
    setCases(data.items.map((c) => ({ case_id: c.case_id, case_name: c.case_name, batch_count: c.batch_count })));
    const param = searchParams.get("case");
    const stored = localStorage.getItem(CASE_STORAGE_KEY);
    const preferred = caseIdOverride ?? (param ? Number(param) : stored ? Number(stored) : null);
    const next =
      preferred && data.items.some((c) => c.case_id === preferred)
        ? preferred
        : embeddedInHub
          ? caseIdOverride ?? null
          : data.items[0]?.case_id ?? null;
    setCaseId(next);
  }, [caseIdOverride, embeddedInHub, searchParams]);

  const refreshPersons = useCallback(async (id: number) => {
    try {
      const data = await api.listCasePersons(id);
      setPersons(data.items);
      if (data.items.length) {
        if (!data.items.some((p) => p.person_id === personId)) {
          setPersonId(data.items[0].person_id);
        }
        if (!data.items.some((p) => p.person_id === personBId)) {
          setPersonBId(data.items[1]?.person_id ?? data.items[0].person_id);
        }
      } else {
        setPersonId(null);
        setPersonBId(null);
      }
    } catch (err) {
      const msg = (err as Error).message || "";
      if (msg.startsWith("404")) {
        const caseList = await api.listCases();
        const items = caseList.items.map((c) => ({ case_id: c.case_id, case_name: c.case_name, batch_count: c.batch_count }));
        setCases(items);
        const next = items[0]?.case_id ?? null;
        if (next && next !== id) {
          message.warning("当前案件已失效，已切换到最新案件");
          setCaseId(next);
          return;
        }
      }
      message.error(msg);
    }
  }, [personId, personBId]);

  useEffect(() => {
    void refreshCases().catch((err) => message.error((err as Error).message));
  }, [refreshCases]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId;
      if (nextCaseId && nextCaseId !== caseId) {
        setCaseId(nextCaseId);
        syncCaseQuery(nextCaseId);
        setPersonId(null);
        setPersonBId(null);
        setPersons([]);
        setPersonData(null);
        setRelationData(null);
        setAnchorData(null);
      }
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, [caseId, syncCaseQuery]);

  useEffect(() => {
    if (!caseId) return;
    localStorage.setItem(CASE_STORAGE_KEY, String(caseId));
    if (!embeddedInHub || searchParams.get("case") !== String(caseId)) {
      syncCaseQuery(caseId);
    }
    void refreshPersons(caseId).catch((err) => message.error((err as Error).message));
  }, [caseId, embeddedInHub, refreshPersons, searchParams, syncCaseQuery]);

  const loadPersonCockpit = useCallback(async () => {
    if (!caseId || !personId || !persons.some((item) => item.person_id === personId)) return;
    setLoading(true);
    try {
      const data = await api.personCockpit(caseId, personId);
      setPersonData(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId, personId, persons]);

  const loadRelationCockpit = useCallback(async () => {
    if (
      !caseId ||
      !personId ||
      !personBId ||
      personId === personBId ||
      !persons.some((item) => item.person_id === personId) ||
      !persons.some((item) => item.person_id === personBId)
    ) return;
    setLoading(true);
    try {
      const data = await api.relationCockpit(caseId, personId, personBId);
      setRelationData(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId, personId, personBId]);

  const loadAnchorCockpit = useCallback(async (query?: string) => {
    const value = (query ?? anchorQuery).trim();
    if (!caseId || !value) return;
    setLoading(true);
    try {
      const data = await api.anchorCockpit(caseId, value, anchorType);
      setAnchorData(data);
      setAnchorQuery(value);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId, anchorQuery, anchorType]);

  const fetchAnchorSuggestions = useCallback(async (text = "", nextAnchorType = anchorType) => {
    if (!caseId) return;
    try {
      const data = await api.suggestAnchors(caseId, text.trim(), 30, nextAnchorType);
      setAnchorSuggestions(data.items);
    } catch {
      setAnchorSuggestions([]);
    }
  }, [caseId, anchorType]);

  useEffect(() => {
    if (mode === "person" && personId) void loadPersonCockpit();
  }, [mode, personId, loadPersonCockpit]);

  useEffect(() => {
    if (mode === "relation" && personId && personBId && personId !== personBId) void loadRelationCockpit();
  }, [mode, personId, personBId, loadRelationCockpit]);

  const openDetail = (record: FusionRecord) => {
    setDetailRecord(record);
    setRawDetail(null);
    setDetailOpen(true);
  };

  useEffect(() => {
    if (!detailOpen || !caseId || !detailRecord?.source_ref) return;
    let cancelled = false;
    setRawLoading(true);
    void api
      .recordDetail(caseId, detailRecord.source_ref)
      .then((data) => {
        if (!cancelled) setRawDetail(data);
      })
      .catch((err) => {
        if (!cancelled) message.error((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setRawLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, detailOpen, detailRecord]);

  const gotoRawTable = () => {
    if (!rawDetail) return;
    const pk = rawDetail.pk as { raw_id?: number };
    if (rawDetail.layer === "raw" && pk.raw_id) {
      navigate(dataManageTablesPath({ table: rawDetail.table, highlight: pk.raw_id }));
    } else {
      navigate(dataManageTablesPath({ table: rawDetail.table }));
    }
  };

  const recordColumns = useMemo(
    () => [
      {
        title: "类型",
        dataIndex: "record_type",
        width: 96,
        render: (v: string) => <Tag color={RECORD_TYPE_COLORS[v] || "default"}>{RECORD_TYPE_LABELS[v] || v}</Tag>,
      },
      { title: "时间", dataIndex: "time", width: 158, render: (v: string | null) => v || "—" },
      { title: "摘要", dataIndex: "summary", ellipsis: true },
      {
        title: "角色",
        dataIndex: "role_hint",
        width: 120,
        ellipsis: true,
        render: (v: string) => (v ? <Tag>{v}</Tag> : "—"),
      },
      { title: "对手/关联", dataIndex: "counterparty", ellipsis: true, width: 140 },
      {
        title: "金额/时长",
        dataIndex: "amount",
        width: 110,
        render: (v: number | null, row: FusionRecord) =>
          row.record_type === "telecom" ? `${v ?? 0} 秒` : formatAmount(v),
      },
    ],
    []
  );

  const chartBase = {
    textStyle: { fontFamily: "inherit" },
    grid: { left: 48, right: 20, top: 48, bottom: 32 },
  };

  const timelineOption = useMemo(() => {
    const chart = overviewData?.charts?.activity_timeline as
      | { days?: string[]; series?: Array<{ name: string; data: number[] }> }
      | undefined;
    if (!chart?.days?.length) return null;
    return {
      ...chartBase,
      color: chartPalette,
      tooltip: { trigger: "axis" },
      legend: { top: 8, icon: "roundRect" },
      xAxis: { type: "category", data: chart.days, axisLine: { lineStyle: { color: "#ddd" } } },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { type: "dashed", color: "#f0f0f0" } } },
      series: (chart.series || []).map((s) => ({
        name: RECORD_TYPE_LABELS[s.name] || s.name,
        type: "bar",
        stack: "total",
        barMaxWidth: 28,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: s.data,
      })),
    };
  }, [overviewData]);

  const graphData = useMemo(() => {
    return overviewData?.charts?.relation_graph as
      | { nodes?: GraphNode[]; links?: GraphLink[]; categories?: Array<{ name: string }> }
      | undefined;
  }, [overviewData]);

  const graphOption = useMemo(() => {
    if (!graphData?.nodes?.length) return null;
    const nodes = graphData.nodes.map((n) => ({
      ...n,
      label: {
        show: true,
        fontSize: n.isCenter ? 14 : 12,
        fontWeight: n.isCenter ? 600 : 500,
        color: n.isCenter ? "#1a1a2e" : "#334155",
      },
      itemStyle: {
        borderWidth: n.isCenter ? 3 : 2,
        borderColor: n.isCenter ? "#fff" : "rgba(255,255,255,0.85)",
        shadowBlur: n.isCenter ? 18 : 8,
        shadowColor: "rgba(0,0,0,0.15)",
      },
    }));
    const links = (graphData.links || []).map((l) => ({
      ...l,
      lineStyle: {
        width: l.lineWidth ?? Math.max(1.5, Math.min(12, 1.5 + Math.sqrt(l.value) * 1.8)),
        curveness: 0.18,
        opacity: 0.72,
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 1,
          y2: 0,
          colorStops: [
            { offset: 0, color: "#e85d45" },
            { offset: 1, color: "#1890ff" },
          ],
        },
      },
      emphasis: { lineStyle: { width: (l.lineWidth ?? 4) + 2, opacity: 1 } },
    }));
    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        confine: true,
        formatter: (params: { dataType?: string; data?: GraphNode & GraphLink & { source?: string; target?: string } }) => {
          const d = params.data;
          if (!d) return "";
          if (params.dataType === "edge") {
            const edge = d as GraphLink;
            const src = graphData.nodes?.find((n) => n.id === edge.source)?.name || edge.source;
            const tgt = graphData.nodes?.find((n) => n.id === edge.target)?.name || edge.target;
            return [
              `<strong>${src} → ${tgt}</strong>`,
              `交互 ${edge.value} 次`,
              edge.totalAmount ? `金额合计 ¥${formatAmount(edge.totalAmount)}` : "",
              channelLabel(edge.channels),
              "<span style='color:#888'>点击查看明细</span>",
            ]
              .filter(Boolean)
              .join("<br/>");
          }
          const node = d as GraphNode;
          const stats = node.stats ? channelLabel(node.stats) : "";
          return [
            `<strong>${node.name}${node.isCenter ? "（中心）" : ""}</strong>`,
            stats ? `关联：${stats}` : "",
            "<span style='color:#888'>点击查看相关记录</span>",
          ]
            .filter(Boolean)
            .join("<br/>");
        },
      },
      color: ["#e85d45", "#52c41a", "#722ed1", "#94a3b8"],
      legend: [{ data: (graphData.categories || []).map((c) => c.name), bottom: 4, textStyle: { color: "#64748b" } }],
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          focusNodeAdjacency: true,
          categories: graphData.categories,
          data: nodes,
          links,
          label: { show: true },
          emphasis: {
            focus: "adjacency",
            scale: 1.08,
            lineStyle: { opacity: 1 },
          },
          force: {
            repulsion: 520,
            gravity: 0.06,
            edgeLength: [120, 220],
            friction: 0.35,
            layoutAnimation: true,
          },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: [0, 10],
        },
      ],
    };
  }, [graphData]);

  const openGraphDetail = useCallback(
    (title: string, records: FusionRecord[], meta: Record<string, string>, placement: "left" | "right" = "right") => {
      setGraphDetailTitle(title);
      setGraphDetailPlacement(placement);
      setGraphDetailRecords(records);
      setGraphDetailMeta(meta);
      setGraphDetailOpen(true);
    },
    []
  );

  const handleGraphClick = useCallback(
    (params: { dataType?: string; data?: GraphNode & GraphLink }) => {
      const d = params.data;
      if (!d || !graphData?.nodes) return;
      if (params.dataType === "edge") {
        const edge = d as GraphLink;
        const src = graphData.nodes.find((n) => n.id === edge.source)?.name || edge.source || "";
        const tgt = graphData.nodes.find((n) => n.id === edge.target)?.name || edge.target || "";
        openGraphDetail(`${src} → ${tgt}`, edge.records || [], {
          交互次数: String(edge.value),
          金额合计: edge.totalAmount ? `¥${formatAmount(edge.totalAmount)}` : "—",
          渠道分布: channelLabel(edge.channels),
        });
        return;
      }
      const node = d as GraphNode;
      const allRecords = Object.values(overviewData?.records_by_type || {}).flat();
      const matched = allRecords.filter((rec) => {
        const cp = rec.counterparty || "";
        if (node.id.startsWith("p:")) return cp === node.name || rec.title.includes(node.name);
        if (node.id.startsWith("ent:")) return cp === node.name || rec.title === node.name;
        if (node.id.startsWith("ph:")) return cp.includes(node.name.replace(/\D/g, "").slice(-4));
        return cp === node.name || rec.title.includes(node.name);
      });
      openGraphDetail(node.isCenter ? `${node.name} · 全部关联` : node.name, matched.slice(0, 50), {
        节点类型: node.isCenter ? "中心人物" : (graphData.categories || [])[node.category]?.name || "关联",
        关联统计: channelLabel(node.stats),
      });
    },
    [graphData, openGraphDetail, overviewData?.records_by_type]
  );

  const graphEvents = useMemo(() => ({ click: handleGraphClick }), [handleGraphClick]);

  const fundPieOption = useMemo(() => {
    const data = (overviewData?.charts?.fund_direction_pie as Array<{ name: string; value: number }>) || [];
    const filtered = data.filter((d) => d.value > 0);
    if (!filtered.length) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, icon: "circle" },
      series: [
        {
          type: "pie",
          radius: ["42%", "68%"],
          center: ["50%", "46%"],
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
          label: { formatter: "{b}\n{d}%" },
          data: filtered,
        },
      ],
    };
  }, [overviewData]);

  const telecomRecords = useMemo(() => {
    return ((overviewData?.records_by_type?.telecom as FusionRecord[] | undefined) || [])
      .filter((record) => {
        if (!record.time) return false;
        if (!telecomDateRange) return true;
        const date = record.time.slice(0, 10);
        return date >= telecomDateRange[0] && date <= telecomDateRange[1];
      });
  }, [overviewData, telecomDateRange]);

  const telecomHourOption = useMemo(() => {
    const counts = Array.from({ length: 24 }, (_, hour) => ({ hour, count: 0 }));
    telecomRecords.forEach((record) => {
      const hourMatch = record.time?.match(/(?:T|\s)(\d{1,2}):/);
      const hour = hourMatch ? Number(hourMatch[1]) : Number.NaN;
      if (Number.isInteger(hour) && hour >= 0 && hour <= 23) counts[hour].count += 1;
    });
    return {
      ...chartBase,
      grid: { left: 42, right: 24, top: 40, bottom: 36 },
      color: [chartPalette[2]],
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: counts.map((d) => `${d.hour}时`) },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { type: "dashed", color: "#f0f0f0" } } },
      series: [
        {
          type: "bar",
          data: counts.map((d) => d.count),
          barMaxWidth: 34,
          itemStyle: {
            borderRadius: [6, 6, 0, 0],
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "#6eb5ff" },
                { offset: 1, color: "#1890ff" },
              ],
            },
          },
        },
      ],
    };
  }, [telecomRecords]);

  const handleTelecomHourClick = useCallback((params: { name?: string; dataIndex?: number }) => {
    const hour = typeof params.dataIndex === "number" ? params.dataIndex : Number(String(params.name || "").replace("时", ""));
    if (!Number.isInteger(hour) || hour < 0 || hour > 23) return;
    const matched = telecomRecords.filter((record) => {
      const hourMatch = record.time?.match(/(?:T|\s)(\d{1,2}):/);
      return hourMatch ? Number(hourMatch[1]) === hour : false;
    });
    openGraphDetail(`${hour}时通话细则`, matched, {
      日期范围: telecomDateRange ? `${telecomDateRange[0]} 至 ${telecomDateRange[1]}` : "全部日期",
      时段: `${hour}:00 - ${hour}:59`,
      记录数: `${matched.length} 条`,
    });
  }, [openGraphDetail, telecomDateRange, telecomRecords]);

  const telecomHourEvents = useMemo(() => ({ click: handleTelecomHourClick }), [handleTelecomHourClick]);

  const relationTimelineOption = useMemo(() => {
    const chart = relationData?.charts?.interaction_timeline as { days?: string[]; counts?: number[] } | undefined;
    if (!chart?.days?.length) return null;
    return {
      ...chartBase,
      color: [chartPalette[0]],
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: chart.days },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { type: "dashed" } } },
      series: [{ type: "line", smooth: true, symbolSize: 8, areaStyle: { opacity: 0.12 }, data: chart.counts }],
    };
  }, [relationData]);

  const sankeyOption = useMemo(() => {
    const links =
      (relationData?.charts?.sankey as { links?: Array<{ source: string; target: string; value: number; channel: string }> })
        ?.links || [];
    if (!links.length) return null;
    const nodes = Array.from(new Set(links.flatMap((l) => [l.source, l.target]))).map((name) => ({ name }));
    return {
      tooltip: { trigger: "item" },
      series: [
        {
          type: "sankey",
          layout: "none",
          emphasis: { focus: "adjacency" },
          lineStyle: { color: "gradient", curveness: 0.5, opacity: 0.45 },
          data: nodes,
          links: links.map((l) => ({ source: l.source, target: l.target, value: Math.max(l.value, 1) })),
        },
      ],
    };
  }, [relationData]);

  const kpiTiles = overviewData?.kpis;
  const selectedCase = cases.find((c) => c.case_id === caseId) ?? null;
  const caseName = selectedCase?.case_name || "";
  const linkedIdentifierCount = persons.reduce((sum, item) => sum + item.links.length, 0);
  const hasBoundBatch = (selectedCase?.batch_count ?? 0) > 0;
  const hasLinkedPerson = persons.length > 0 && linkedIdentifierCount > 0;
  const cockpitBlocked = !caseId || !hasBoundBatch || !hasLinkedPerson;
  const cockpitBlockTitle = !caseId ? "请先选择案件" : !hasBoundBatch ? "当前案件还没有绑定批次" : "当前案件还没有完成人物关联";
  const cockpitBlockDesc = !caseId
    ? "请在顶部选择一个案件，或通过「打开案件」进入已有案件。"
    : !hasBoundBatch
      ? "融合分析必须基于当前案件的数据范围，请通过「打开案件」为当前案件绑定导入批次。"
      : "融合分析必须基于人物标识关联结果，请先进入人物关联，扫描候选并关联人物。";
  const cockpitBlockAction = !caseId
    ? { label: embeddedInHub ? "去打开案件" : "去打开案件", to: "/fusion-cockpit/open" }
    : !hasBoundBatch
      ? { label: embeddedInHub ? "去新建案件" : "去打开案件", to: embeddedInHub ? "/fusion-cockpit/new" : "/fusion-cockpit/open" }
      : { label: "去人物关联", to: `/person-linking?case=${caseId}` };
  const guideSteps = buildWorkflowSteps({
    ...DEFAULT_WORKFLOW_SNAPSHOT,
    caseCount: cases.length,
    batchCount: selectedCase?.batch_count ?? 0,
    boundBatchCount: selectedCase?.batch_count ?? 0,
    personCount: persons.length,
    linkedIdentifierCount,
    selectedCaseId: caseId,
  });

  const openGraphExplore = useCallback(
    (personOverride?: number | null) => {
      const targetPerson = personOverride ?? personId;
      const query = new URLSearchParams();
      if (caseId) query.set("case", String(caseId));
      if (targetPerson) query.set("person", String(targetPerson));
      navigate(`/fusion-cockpit/graph?${query.toString()}`);
    },
    [caseId, navigate, personId]
  );

  const renderKpiValue = (key: string) => {
    if (!kpiTiles) return { main: "—", sub: "" };
    if (key === "bank") {
      return {
        main: String(kpiTiles.bank_txn_count),
        sub: `收 ${formatAmount(kpiTiles.bank_in_amount)} / 支 ${formatAmount(kpiTiles.bank_out_amount)}`,
      };
    }
    if (key === "wechat") {
      return {
        main: String(kpiTiles.wechat_txn_count),
        sub: `收 ${formatAmount(kpiTiles.wechat_in_amount)} / 支 ${formatAmount(kpiTiles.wechat_out_amount)}`,
      };
    }
    if (key === "telecom") {
      return {
        main: String(kpiTiles.telecom_call_count),
        sub: `时长 ${kpiTiles.telecom_total_duration_sec} 秒`,
      };
    }
    return {
      main: String(kpiTiles.enterprise_count + kpiTiles.commercial_count),
      sub: `共 ${kpiTiles.total_records} 条跨源记录`,
    };
  };

  const renderChartCard = (title: string, option: object | null, height = 300) => (
    <div className="cockpit-chart-card">
      <div className="cockpit-chart-head">{title}</div>
      {option ? (
        <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />
      ) : (
        <div className="cockpit-chart-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
        </div>
      )}
    </div>
  );

  return (
    <div className="cockpit-page">
      {!embeddedInHub ? <WorkflowGuide steps={guideSteps} currentKey="fusion-cockpit" compact /> : null}
      <div className="cockpit-hero">
        <div className="cockpit-hero-bg" />
        <div className="cockpit-hero-content">
          <div>
            <Text className="cockpit-hero-kicker">FUSION COCKPIT</Text>
            <Title level={3} style={{ margin: "4px 0 8px", color: "#fff" }}>
              融合分析驾驶舱
            </Title>
            <Text style={{ color: "rgba(255,255,255,0.82)" }}>
              {caseName || "请先在顶部选择当前案件"} · 综合研判 · 基于人物关联结果跨源聚合分析
            </Text>
          </div>
          <Space wrap className="cockpit-hero-controls">
            {embeddedInHub && onBackToOpenList ? (
              <Button ghost icon={<ArrowLeftOutlined />} onClick={onBackToOpenList}>
                返回打开案件
              </Button>
            ) : null}
            <Segmented
              className="cockpit-mode-segment"
              value={mode}
              onChange={(v) => setMode(v as "person" | "relation" | "anchor")}
              options={[
                { value: "person", label: "单人全景" },
                { value: "relation", label: "双人关系" },
                { value: "anchor", label: "自由检索" },
              ]}
            />
            <Button ghost icon={<ForkOutlined />} onClick={() => openGraphExplore()}>
              图谱探索
            </Button>
          </Space>
        </div>
      </div>

      {cockpitBlocked ? (
        <div className="app-card cockpit-blocked-state">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div>
                <Title level={4}>{cockpitBlockTitle}</Title>
                <Paragraph style={{ color: "#7c6d67" }}>{cockpitBlockDesc}</Paragraph>
              </div>
            }
          />
          <Space wrap>
            <Button type="primary" onClick={() => navigate(cockpitBlockAction.to)}>{cockpitBlockAction.label}</Button>
            <Button onClick={() => navigate("/fusion-cockpit")}>返回驾驶舱</Button>
          </Space>
        </div>
      ) : (
      <Spin spinning={loading}>
        {mode === "relation" ? (
          <>
            <div className="cockpit-toolbar app-card">
              <Space wrap size="middle" align="center">
                <Select
                  showSearch
                  optionFilterProp="label"
                  style={{ minWidth: 180 }}
                  placeholder="人物 A"
                  value={personId ?? undefined}
                  onChange={setPersonId}
                  options={personOptions.map((o) => ({ value: o.value, label: o.label }))}
                />
                <ArrowRightOutlined style={{ color: "#d94832", fontSize: 18 }} />
                <Select
                  showSearch
                  optionFilterProp="label"
                  style={{ minWidth: 180 }}
                  placeholder="人物 B"
                  value={personBId ?? undefined}
                  onChange={setPersonBId}
                  options={personOptions
                    .filter((o) => o.value !== personId)
                    .map((o) => ({ value: o.value, label: o.label }))}
                />
                <Button type="primary" icon={<ReloadOutlined />} onClick={() => void loadRelationCockpit()}>
                  分析关系
                </Button>
              </Space>
              {selectedPerson && selectedPersonB && (
                <div className="cockpit-relation-banner">
                  <Tag color="volcano">{selectedPerson.display_name}</Tag>
                  <ArrowRightOutlined />
                  <Tag color="blue">{selectedPersonB.display_name}</Tag>
                </div>
              )}
            </div>

            {relationData?.summary_text && (
              <div className="app-card cockpit-summary">{relationData.summary_text}</div>
            )}

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} lg={12}>{renderChartCard("关系资金流向", sankeyOption, 320)}</Col>
              <Col xs={24} lg={12}>{renderChartCard("交互时间轴", relationTimelineOption, 320)}</Col>
            </Row>

            {!!relationData?.indirect_relations?.length && (
              <div className="app-card cockpit-indirect">
                <Title level={5}>间接关联</Title>
                <Row gutter={[12, 12]}>
                  {relationData.indirect_relations.map((item, idx) => (
                    <Col xs={24} md={12} key={idx}>
                      <div className="cockpit-indirect-item">
                        <Text strong>{item.title}</Text>
                        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>{item.detail}</Paragraph>
                      </div>
                    </Col>
                  ))}
                </Row>
              </div>
            )}

            <div className="app-card cockpit-records-panel" style={{ marginTop: 16 }}>
              <Title level={5}>直接关系明细</Title>
              <Table
                rowKey={(_, idx) => `rel-${idx}`}
                size="small"
                columns={recordColumns}
                dataSource={relationData?.direct_records || []}
                onRow={(row) => ({ onClick: () => openDetail(row), className: "cockpit-record-row" })}
                pagination={{ pageSize: 10 }}
                locale={{ emptyText: "未发现直接关系，请确认人物关联是否完整" }}
              />
            </div>
          </>
        ) : (
          <>
            <div className="cockpit-toolbar app-card">
              {mode === "person" ? (
                <Space wrap size="middle">
                  <Text strong>分析对象</Text>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    style={{ minWidth: 220 }}
                    placeholder="选择人物姓名"
                    value={personId ?? undefined}
                    onChange={setPersonId}
                    options={personOptions.map((o) => ({
                      value: o.value,
                      label: (
                        <Space>
                          <span>{o.label}</span>
                          {o.hint && <Text type="secondary" style={{ fontSize: 12 }}>{o.hint}</Text>}
                        </Space>
                      ),
                    }))}
                    notFoundContent={
                      <Empty description="请先在人物关联页建立人物">
                        <Button size="small" type="link" onClick={() => navigate("/person-linking")}>
                          去关联
                        </Button>
                      </Empty>
                    }
                  />
                  <Button icon={<ReloadOutlined />} onClick={() => void loadPersonCockpit()}>
                    刷新
                  </Button>
                </Space>
              ) : (
                <Space wrap size="middle" align="start">
                  <Text strong>检索标识</Text>
                  <Select
                    style={{ width: 140 }}
                    value={anchorType}
                    onChange={(value) => {
                      setAnchorType(value);
                      setAnchorQuery("");
                      void fetchAnchorSuggestions("", value);
                    }}
                    options={ANCHOR_TYPE_OPTIONS}
                  />
                  <Select
                    showSearch
                    allowClear
                    style={{ minWidth: 320 }}
                    value={anchorQuery || undefined}
                    placeholder="选择或输入卡号 / 手机号 / 微信名 / 企业名 / 姓名"
                    filterOption={false}
                    defaultActiveFirstOption={false}
                    showArrow
                    notFoundContent={anchorType === "auto" && !anchorQuery.trim() ? "输入关键词后选择标识" : "暂无匹配标识"}
                    onDropdownVisibleChange={(open) => {
                      if (open) void fetchAnchorSuggestions(anchorQuery);
                    }}
                    onSearch={(text) => {
                      setAnchorQuery(text);
                      void fetchAnchorSuggestions(text);
                    }}
                    onChange={(val) => {
                      const next = val ? String(val) : "";
                      setAnchorQuery(next);
                      if (next) void loadAnchorCockpit(next);
                    }}
                    onClear={() => {
                      setAnchorQuery("");
                      void fetchAnchorSuggestions("");
                    }}
                    options={anchorSuggestions.map((item) => ({
                      value: item.display_value,
                      label: (
                        <Space>
                          <Tag>{ANCHOR_TYPE_LABELS[item.identifier_type] || item.identifier_type}</Tag>
                          <span>{item.display_value}</span>
                          {item.person_name && (
                            <Text type="secondary" style={{ fontSize: 12 }}>→ {item.person_name}</Text>
                          )}
                        </Space>
                      ),
                    }))}
                  />
                  <Button type="primary" onClick={() => void loadAnchorCockpit()} disabled={!anchorQuery.trim()}>
                    检索
                  </Button>
                </Space>
              )}

              {mode === "person" && selectedPerson && (
                <div className="cockpit-profile-banner">
                  <Avatar size={56} className="cockpit-avatar">
                    {personInitial(selectedPerson.display_name)}
                  </Avatar>
                  <div className="cockpit-profile-main">
                    <Title level={4} style={{ margin: 0 }}>
                      {selectedPerson.display_name}
                    </Title>
                    <Space size={[6, 6]} wrap style={{ marginTop: 8 }}>
                      {selectedPerson.links.slice(0, 8).map((link) => (
                        <Tag key={link.link_id} className="cockpit-id-tag">
                          {link.identifier_value}
                        </Tag>
                      ))}
                      {selectedPerson.links.length > 8 && (
                        <Tag>+{selectedPerson.links.length - 8}</Tag>
                      )}
                    </Space>
                  </div>
                </div>
              )}

              {mode === "anchor" && anchorData && (
                <div className="cockpit-profile-banner">
                  <Avatar size={56} className="cockpit-avatar">
                    {(ANCHOR_TYPE_LABELS[anchorData.anchor.type] || "?").slice(0, 1)}
                  </Avatar>
                  <div className="cockpit-profile-main">
                    <Title level={4} style={{ margin: 0 }}>
                      {anchorData.anchor.label}
                    </Title>
                    <Space size={[6, 6]} wrap style={{ marginTop: 8 }}>
                      <Tag color="volcano">{ANCHOR_TYPE_LABELS[anchorData.anchor.type] || anchorData.anchor.type}</Tag>
                      {anchorData.linked_persons.map((p) => (
                        <Tag
                          key={p.person_id}
                          className="cockpit-id-tag"
                          style={{ cursor: "pointer" }}
                          onClick={() => {
                            setMode("person");
                            setPersonId(p.person_id);
                          }}
                        >
                          已关联：{p.display_name}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                </div>
              )}
            </div>

            {mode === "anchor" && anchorData?.enterprise_roles && (
              <div className="app-card" style={{ marginTop: 16 }}>
                <Title level={5}>企业角色</Title>
                <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }}>
                  <Descriptions.Item label="企业名称">{anchorData.enterprise_roles.enterprise_name}</Descriptions.Item>
                  <Descriptions.Item label="法人">{anchorData.enterprise_roles.legal_person || "—"}</Descriptions.Item>
                  <Descriptions.Item label="股东">
                    {(anchorData.enterprise_roles.shareholders || []).join("、") || "—"}
                  </Descriptions.Item>
                  <Descriptions.Item label="主要人员">
                    {(anchorData.enterprise_roles.key_persons || []).join("、") || "—"}
                  </Descriptions.Item>
                </Descriptions>
              </div>
            )}

            {mode === "anchor" && anchorData?.commercial_roles && (
              <Row gutter={[14, 14]} style={{ marginTop: 16 }}>
                <Col xs={8}>
                  <Card size="small" title="甲方采购">
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{anchorData.commercial_roles.purchaser_count}</div>
                  </Card>
                </Col>
                <Col xs={8}>
                  <Card size="small" title="中标供应商">
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{anchorData.commercial_roles.winner_count}</div>
                  </Card>
                </Col>
                <Col xs={8}>
                  <Card size="small" title="投标供应商">
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{anchorData.commercial_roles.bid_company_count}</div>
                  </Card>
                </Col>
              </Row>
            )}

            {kpiTiles && (
              <Row gutter={[14, 14]} className="cockpit-kpi-row">
                {KPI_CONFIG.map((cfg) => {
                  const { main, sub } = renderKpiValue(cfg.key);
                  return (
                    <Col xs={12} md={6} key={cfg.key}>
                      <div className={`cockpit-kpi-card ${cfg.tone}`}>
                        <div className="cockpit-kpi-icon">{cfg.icon}</div>
                        <div className="cockpit-kpi-label">{cfg.label}</div>
                        <div className="cockpit-kpi-value">{main}</div>
                        <div className="cockpit-kpi-sub">{sub}</div>
                      </div>
                    </Col>
                  );
                })}
              </Row>
            )}

            {overviewData?.summary_text && (
              <div className="app-card cockpit-summary">{overviewData.summary_text.split("\n").map((line, i) => (
                <Paragraph key={i} style={{ margin: i ? "8px 0 0" : 0 }}>{line}</Paragraph>
              ))}</div>
            )}

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} lg={12}>{renderChartCard("跨源活动时间轴", timelineOption)}</Col>
              <Col xs={24} lg={12}>{renderChartCard("资金收付结构", fundPieOption)}</Col>
              <Col xs={24}>
                <div className="cockpit-chart-card cockpit-graph-card">
                  <div className="cockpit-chart-head">
                    <Space>
                      <span>关系网络图谱</span>
                      <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                        连线粗细 = 交互强度 · 点击节点/连线查看明细
                      </Text>
                    </Space>
                    {graphOption ? (
                      <Button type="link" size="small" icon={<ForkOutlined />} onClick={() => openGraphExplore()}>
                        深入探索
                      </Button>
                    ) : null}
                  </div>
                  {graphOption ? (
                    <ReactECharts
                      ref={graphChartRef}
                      option={graphOption}
                      style={{ height: 520 }}
                      notMerge
                      lazyUpdate
                      onEvents={graphEvents}
                    />
                  ) : (
                    <div className="cockpit-chart-empty" style={{ minHeight: 520 }}>
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无关系数据" />
                    </div>
                  )}
                </div>
              </Col>
              <Col xs={24}>
                <div className="cockpit-chart-card cockpit-telecom-hour-card">
                  <div className="cockpit-chart-head cockpit-chart-head-with-actions">
                    <Space>
                      <span>通联时段分布</span>
                      <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                        {telecomDateRange ? `${telecomDateRange[0]} 至 ${telecomDateRange[1]}` : "全部日期"} · {telecomRecords.length} 条
                      </Text>
                    </Space>
                    <RangePicker
                      size="small"
                      allowClear
                      locale={zhCN}
                      format="YYYY年MM月DD日"
                      placeholder={["开始日期", "结束日期"]}
                      onChange={(_, dateStrings) => {
                        const [start, end] = dateStrings;
                        setTelecomDateRange(start && end ? [start, end] : null);
                      }}
                    />
                  </div>
                  {telecomRecords.length ? (
                    <ReactECharts option={telecomHourOption} style={{ height: 360 }} notMerge lazyUpdate onEvents={telecomHourEvents} />
                  ) : (
                    <div className="cockpit-chart-empty" style={{ minHeight: 360 }}>
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前日期范围暂无通联记录" />
                    </div>
                  )}
                </div>
              </Col>
            </Row>

            {overviewData?.records_by_type && Object.keys(overviewData.records_by_type).length > 0 && (
              <div className="app-card cockpit-records-panel">
                <Title level={5} style={{ marginBottom: 12 }}>明细记录</Title>
                <Tabs
                  items={Object.entries(overviewData.records_by_type).map(([type, records]) => ({
                    key: type,
                    label: (
                      <Space size={4}>
                        <span
                          className="cockpit-tab-dot"
                          style={{ background: RECORD_TYPE_COLORS[type] || "#999" }}
                        />
                        {RECORD_TYPE_LABELS[type] || type}
                        <Tag bordered={false}>{records.length}</Tag>
                      </Space>
                    ),
                    children: (
                      <Table
                        rowKey={(row, idx) => `${type}-${idx}`}
                        size="small"
                        columns={recordColumns}
                        dataSource={records}
                        onRow={(row) => ({
                          onClick: () => openDetail(row),
                          className: "cockpit-record-row",
                        })}
                        pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
                      />
                    ),
                  }))}
                />
              </div>
            )}
          </>
        )}
      </Spin>
      )}

      <Drawer
        title={graphDetailTitle || "图谱明细"}
        width={640}
        placement={graphDetailPlacement}
        open={graphDetailOpen}
        onClose={() => setGraphDetailOpen(false)}
      >
        {Object.keys(graphDetailMeta).length > 0 && (
          <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
            {Object.entries(graphDetailMeta).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {v}
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}
        <Table
          rowKey={(_, idx) => `graph-${idx}`}
          size="small"
          columns={recordColumns}
          dataSource={graphDetailRecords}
          onRow={(row) => ({ onClick: () => openDetail(row), className: "cockpit-record-row" })}
          pagination={{ pageSize: 8, showTotal: (t) => `共 ${t} 条` }}
          locale={{ emptyText: "暂无匹配记录" }}
        />
      </Drawer>

      <Drawer
        title="记录详情"
        width={580}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        loading={rawLoading}
      >
        {detailRecord && (
          <>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="类型">
                <Tag color={RECORD_TYPE_COLORS[detailRecord.record_type]}>
                  {RECORD_TYPE_LABELS[detailRecord.record_type] || detailRecord.record_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="标题">{detailRecord.title}</Descriptions.Item>
              <Descriptions.Item label="时间">{detailRecord.time || "—"}</Descriptions.Item>
              <Descriptions.Item label="金额/时长">
                {detailRecord.record_type === "telecom"
                  ? `${detailRecord.amount ?? 0} 秒`
                  : formatAmount(detailRecord.amount)}
              </Descriptions.Item>
              <Descriptions.Item label="对手/关联">{detailRecord.counterparty || "—"}</Descriptions.Item>
              <Descriptions.Item label="摘要">{detailRecord.summary || "—"}</Descriptions.Item>
            </Descriptions>
            {rawDetail && (
              <>
                <Title level={5} style={{ marginTop: 16 }}>原始字段</Title>
                <Descriptions column={1} size="small" bordered>
                  {Object.entries(rawDetail.fields || {}).map(([key, val]) => (
                    <Descriptions.Item key={key} label={key}>
                      {val === null || val === undefined ? "—" : String(val)}
                    </Descriptions.Item>
                  ))}
                </Descriptions>
                <Button type="primary" style={{ marginTop: 12 }} onClick={gotoRawTable}>
                  定位原始数据
                </Button>
              </>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}

export default FusionCockpitPage;
