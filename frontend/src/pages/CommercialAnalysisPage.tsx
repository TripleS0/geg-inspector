import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AutoComplete,
  Button,
  Card,
  Col,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import type { TableColumnsType } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  BatchInfo,
  batchLabel,
  CommercialAnalysisFilter,
  CommercialAnalysisRecord,
  CommercialAnalysisResponse,
  CommercialCoBidAnalysisResponse,
  CommercialCoBidCompanion,
  CommercialCoBidInquiry,
  pollTask,
} from "../api";
import {
  AnalysisDateTimeFormFields,
  serializeAnalysisDateTimeFilters,
} from "../components/AnalysisDateTimeFilters";
import { chartPair, chartPalette } from "../theme";

type CommercialFilterForm = CommercialAnalysisFilter & AnalysisDateTimeFormFields;

type AnalysisViewMode = "stats" | "cobid";

interface CompanySummaryRow {
  company_name: string;
  company_norm?: string;
  participation_count: number;
  win_count: number;
  win_amount: number;
  risk_level: string;
  risk_score: number;
  risk_hit_count?: number;
}

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

const RISK_LEVEL_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const RISK_LEVEL_COLORS: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "gold",
};

const PATTERN_COLORS: Record<string, string> = {
  高频陪标: "blue",
  轮流中标: "red",
};

const PATTERN_DEFINITIONS: Record<string, string> = {
  高频陪标:
    "与目标企业在大量询价项目中反复同场出现，同场次数及占目标参标项目的比例超过阈值，疑似固定搭档一起参标。",
  轮流中标:
    "双方在同场询价中交替成为唯一中标方，中标轮换规律明显，疑似人为分配中标结果。",
};

function PatternHelpTag({ pattern }: { pattern: string }) {
  return (
    <Tooltip title={PATTERN_DEFINITIONS[pattern] || pattern}>
      <Tag color={PATTERN_COLORS[pattern] || "default"} className="commercial-pattern-tag">
        {pattern}
        <QuestionCircleOutlined className="commercial-pattern-help-icon" />
      </Tag>
    </Tooltip>
  );
}

type SharedWinOutcome = "target" | "partner" | "both" | "other" | "none";

function partnerWonInquiry(inquiry: CommercialCoBidInquiry, partnerCompany: string): boolean {
  return inquiry.winners.some((w) => w === partnerCompany || w.includes(partnerCompany));
}

function classifySharedOutcome(
  inquiry: CommercialCoBidInquiry,
  partnerCompany: string,
): SharedWinOutcome {
  if (!inquiry.winners.length) return "none";
  const partnerWin = partnerWonInquiry(inquiry, partnerCompany);
  if (inquiry.target_won && partnerWin) return "both";
  if (inquiry.target_won) return "target";
  if (partnerWin) return "partner";
  return "other";
}

const OUTCOME_LABELS: Record<SharedWinOutcome, string> = {
  target: "目标中标",
  partner: "对方中标",
  both: "共同中标",
  other: "第三方中标",
  none: "无中标/流标",
};

const OUTCOME_COLORS: Record<SharedWinOutcome, string> = {
  target: chartPalette[1],
  partner: chartPalette[4],
  both: chartPalette[2],
  other: chartPalette[6],
  none: "#c9cdd4",
};

const OUTCOME_TAG_COLORS: Record<SharedWinOutcome, string> = {
  target: "green",
  partner: "orange",
  both: "purple",
  other: "default",
  none: "default",
};

const OUTCOME_ORDER: SharedWinOutcome[] = ["target", "partner", "both", "other", "none"];

interface CoBidDrawerInquiryFilters {
  inquiryNo: string;
  winnerKeyword: string;
  outcome?: SharedWinOutcome;
  dateRange: [Dayjs, Dayjs] | null;
}

const EMPTY_CO_BID_DRAWER_FILTERS: CoBidDrawerInquiryFilters = {
  inquiryNo: "",
  winnerKeyword: "",
  outcome: undefined,
  dateRange: null,
};

function countCompanionBothWins(
  companion: CommercialCoBidCompanion,
  inquiries: CommercialCoBidInquiry[],
): number {
  const keys = new Set(companion.shared_inquiry_nos);
  let count = 0;
  for (const inquiry of inquiries) {
    if (!keys.has(inquiry.inquiry_no)) continue;
    if (classifySharedOutcome(inquiry, companion.company_name) === "both") count += 1;
  }
  return count;
}

function matchCoBidInquiryFilters(
  inquiry: CommercialCoBidInquiry,
  partnerCompany: string,
  filters: CoBidDrawerInquiryFilters,
): boolean {
  if (filters.inquiryNo.trim()) {
    const keyword = filters.inquiryNo.trim().toLowerCase();
    if (!inquiry.inquiry_no.toLowerCase().includes(keyword)) return false;
  }
  if (filters.winnerKeyword.trim()) {
    const keyword = filters.winnerKeyword.trim().toLowerCase();
    if (!inquiry.winners.some((winner) => winner.toLowerCase().includes(keyword))) return false;
  }
  if (filters.outcome) {
    if (classifySharedOutcome(inquiry, partnerCompany) !== filters.outcome) return false;
  }
  if (filters.dateRange?.[0] && filters.dateRange?.[1]) {
    const raw = inquiry.inquiry_time?.trim();
    if (!raw) return false;
    const parsed = dayjs(raw);
    if (!parsed.isValid()) return false;
    if (parsed.isBefore(filters.dateRange[0].startOf("day"))) return false;
    if (parsed.isAfter(filters.dateRange[1].endOf("day"))) return false;
  }
  return true;
}

function riskLevelLabel(level: string) {
  return RISK_LEVEL_LABELS[level] || level || "未分级";
}

function formatAmount(value: unknown) {
  const n = Number(value || 0);
  return n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCompactAmount(value: unknown) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`;
  if (Math.abs(n) >= 1e4) return `${(n / 1e4).toFixed(2)} 万`;
  return formatAmount(n);
}

function winRate(participation: number, wins: number) {
  if (!participation) return 0;
  return Math.round((wins / participation) * 1000) / 10;
}

type SortField = "participation_count" | "win_count" | "win_rate" | "win_amount" | "risk_score";

const DEFAULT_SORT: { field: SortField; order: "ascend" | "descend" } = {
  field: "win_amount",
  order: "descend",
};

/** 降序 ↔ 升序循环，不出现取消排序（Ant Design 需 3 项，第三项与首项相同） */
const SORT_DIRECTIONS: ("ascend" | "descend")[] = ["descend", "ascend", "descend"];

function normalizeCompanyRow(row: Record<string, unknown>): CompanySummaryRow {
  return {
    company_name: String(row.company_name || ""),
    company_norm: row.company_norm ? String(row.company_norm) : undefined,
    participation_count: Number(row.participation_count) || 0,
    win_count: Number(row.win_count) || 0,
    win_amount: Number(row.win_amount) || 0,
    risk_level: String(row.risk_level || ""),
    risk_score: Number(row.risk_score) || 0,
    risk_hit_count: Number(row.risk_hit_count) || 0,
  };
}

function compareCompanyRows(a: CompanySummaryRow, b: CompanySummaryRow, field: SortField): number {
  switch (field) {
    case "participation_count":
      return a.participation_count - b.participation_count;
    case "win_count":
      return a.win_count - b.win_count;
    case "win_rate":
      return winRate(a.participation_count, a.win_count) - winRate(b.participation_count, b.win_count);
    case "win_amount":
      return a.win_amount - b.win_amount;
    case "risk_score":
      return a.risk_score - b.risk_score;
    default:
      return 0;
  }
}

function CommercialAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<CommercialFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<CommercialAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [viewMode, setViewMode] = useState<AnalysisViewMode>("stats");
  const [riskLevelFilter, setRiskLevelFilter] = useState<string | undefined>();
  const [sortState, setSortState] = useState(DEFAULT_SORT);
  const [tablePage, setTablePage] = useState(1);
  const [tablePageSize, setTablePageSize] = useState(20);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailCompany, setDetailCompany] = useState<CompanySummaryRow | null>(null);
  const [detailRecords, setDetailRecords] = useState<CommercialAnalysisRecord[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailDrawerPage, setDetailDrawerPage] = useState(1);
  const [detailDrawerPageSize, setDetailDrawerPageSize] = useState(20);
  const [coBidLoading, setCoBidLoading] = useState(false);
  const [coBidResult, setCoBidResult] = useState<CommercialCoBidAnalysisResponse | null>(null);
  const [coBidDrawerOpen, setCoBidDrawerOpen] = useState(false);
  const [coBidDrawerCompanion, setCoBidDrawerCompanion] = useState<CommercialCoBidCompanion | null>(null);
  const [coBidDrawerPage, setCoBidDrawerPage] = useState(1);
  const [coBidDrawerPageSize, setCoBidDrawerPageSize] = useState(10);
  const [coBidDrawerFilters, setCoBidDrawerFilters] = useState<CoBidDrawerInquiryFilters>(
    EMPTY_CO_BID_DRAWER_FILTERS,
  );
  const [coBidCompanionPage, setCoBidCompanionPage] = useState(1);
  const [coBidCompanionPageSize, setCoBidCompanionPageSize] = useState(10);
  const coBidChartRef = useRef<React.ComponentRef<typeof ReactECharts>>(null);

  useEffect(() => {
    setTablePage(1);
  }, [riskLevelFilter, viewMode]);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.listBatches("commercial");
        setBatches(data.items);
        const param = searchParams.get("batch") || "";
        setBatchId(param || data.items[0]?.import_batch_id || "");
      } catch (err) {
        message.error((err as Error).message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!batchId) return;
    setSearchParams({ batch: batchId });
    setRiskLevelFilter(undefined);
    setSortState(DEFAULT_SORT);
    setTablePage(1);
    setViewMode("stats");
    setDetailOpen(false);
    setDetailCompany(null);
    setCoBidResult(null);
    void api.commercialAnalysisFilterOptions(batchId).then(setFilterOptions).catch(() => setFilterOptions({}));
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runQuery = async () => {
    if (!batchId) return;
    setLoading(true);
    setDetailOpen(false);
    setDetailCompany(null);
    try {
      const values = await filter.validateFields();
      const data = await api.commercialAnalysisRecords(batchId, serializeAnalysisDateTimeFilters(values || {}));
      setRecords(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const exportReport = async () => {
    if (!batchId) return;
    setExporting(true);
    try {
      message.loading({ content: "正在导出商务网统计 Word 报告…", key: "commercial-analysis-export" });
      const { task_id } = await api.exportCommercialAnalysisReport(batchId);
      const status = await pollTask(task_id);
      message.success({
        content: `导出完成：${(status.result as { output_path?: string }).output_path}`,
        key: "commercial-analysis-export",
        duration: 6,
      });
    } catch (err) {
      message.error({ content: (err as Error).message, key: "commercial-analysis-export" });
    } finally {
      setExporting(false);
    }
  };

  const companySummary = useMemo(
    () => (records?.summary.company_summary || []).map((row) => normalizeCompanyRow(row as Record<string, unknown>)),
    [records]
  );

  const filteredCompanySummary = useMemo(() => {
    return companySummary.filter((row) => {
      if (riskLevelFilter === "__none__") {
        return !row.risk_level;
      }
      if (riskLevelFilter && row.risk_level !== riskLevelFilter) {
        return false;
      }
      return true;
    });
  }, [companySummary, riskLevelFilter]);

  const sortedCompanySummary = useMemo(() => {
    const rows = [...filteredCompanySummary];
    const dir = sortState.order === "ascend" ? 1 : -1;
    rows.sort((a, b) => {
      const cmp = compareCompanyRows(a, b, sortState.field);
      if (cmp !== 0) return dir * cmp;
      return a.company_name.localeCompare(b.company_name, "zh-CN");
    });
    return rows;
  }, [filteredCompanySummary, sortState]);

  const openCompanyDetail = useCallback(
    async (row: CompanySummaryRow) => {
      if (!batchId) return;
      setDetailCompany(row);
      setDetailOpen(true);
      setDetailDrawerPage(1);
      setDetailLoading(true);
      setDetailRecords([]);
      try {
        const values = filter.getFieldsValue();
        const data = await api.commercialAnalysisRecords(
          batchId,
          serializeAnalysisDateTimeFilters({
            ...values,
            company_name: row.company_name,
            only_winners: true,
          }),
        );
        const wins = data.records
          .filter((r) => r.is_winner)
          .sort(
            (a, b) =>
              Number(b.win_amount || 0) - Number(a.win_amount || 0) ||
              String(a.inquiry_no).localeCompare(String(b.inquiry_no), "zh-CN"),
          );
        setDetailRecords(wins);
      } catch (err) {
        message.error((err as Error).message);
        setDetailOpen(false);
        setDetailCompany(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [batchId, filter],
  );

  const runCoBidAnalysis = useCallback(
    async (companyName?: string) => {
      if (!batchId) return;
      const values = filter.getFieldsValue();
      const target = (companyName || values.company_name || "").trim();
      if (!target) {
        message.warning("请在筛选条件中填写目标企业名称");
        return;
      }
      if (companyName) {
        filter.setFieldValue("company_name", companyName);
      }
      setCoBidLoading(true);
      try {
        const dateFilters = serializeAnalysisDateTimeFilters(values || {});
        const data = await api.commercialCoBidAnalysis(batchId, {
          company_name: target,
          purchaser: values.purchaser,
          start_time: dateFilters.start_time,
          end_time: dateFilters.end_time,
        });
        setCoBidResult(data);
        if (!data.participation_count) {
          message.info(data.description || "未找到参标记录");
        }
      } catch (err) {
        message.error((err as Error).message);
        setCoBidResult(null);
      } finally {
        setCoBidLoading(false);
      }
    },
    [batchId, filter],
  );

  const runMainQuery = async () => {
    if (viewMode === "cobid") {
      await runCoBidAnalysis();
      return;
    }
    await runQuery();
  };

  const switchToCoBid = (companyName: string) => {
    filter.setFieldValue("company_name", companyName);
    setViewMode("cobid");
    void runCoBidAnalysis(companyName);
  };

  const openCoBidCompanionDrawer = useCallback(
    (companion: CommercialCoBidCompanion) => {
      setCoBidDrawerCompanion(companion);
      setCoBidDrawerPage(1);
      setCoBidDrawerFilters(EMPTY_CO_BID_DRAWER_FILTERS);
      setCoBidDrawerOpen(true);
    },
    [],
  );

  const openCoBidRelationByNorm = useCallback(
    (partnerNorm: string) => {
      if (!coBidResult || partnerNorm === coBidResult.target_company_norm) return;
      const companion = coBidResult.companions.find((row) => row.company_norm === partnerNorm);
      if (companion) openCoBidCompanionDrawer(companion);
    },
    [coBidResult, openCoBidCompanionDrawer],
  );

  const handleCoBidGraphClick = useCallback(
    (params: { dataType?: string; data?: { id?: string; source?: string; target?: string } }) => {
      const targetNorm = coBidResult?.target_company_norm;
      if (!targetNorm || !params.data) return;
      if (params.dataType === "edge") {
        const partner =
          params.data.source === targetNorm ? params.data.target : params.data.source;
        if (partner) openCoBidRelationByNorm(String(partner));
        return;
      }
      const nodeId = params.data.id;
      if (nodeId && nodeId !== targetNorm) {
        openCoBidRelationByNorm(String(nodeId));
      }
    },
    [coBidResult, openCoBidRelationByNorm],
  );

  const coBidSharedInquiries = useMemo(() => {
    if (!coBidResult || !coBidDrawerCompanion) return [] as CommercialCoBidInquiry[];
    const keys = new Set(coBidDrawerCompanion.shared_inquiry_nos);
    const partnerName = coBidDrawerCompanion.company_name;
    const fromKeys = coBidResult.inquiries.filter((row) => keys.has(row.inquiry_no));
    if (fromKeys.length >= coBidDrawerCompanion.shared_inquiries) {
      return fromKeys;
    }
    return coBidResult.inquiries.filter((row) =>
      row.participants.some((name) => name === partnerName || name.includes(partnerName)),
    );
  }, [coBidResult, coBidDrawerCompanion]);

  const coBidFilteredInquiries = useMemo(() => {
    if (!coBidDrawerCompanion) return coBidSharedInquiries;
    return coBidSharedInquiries.filter((row) =>
      matchCoBidInquiryFilters(row, coBidDrawerCompanion.company_name, coBidDrawerFilters),
    );
  }, [coBidSharedInquiries, coBidDrawerCompanion, coBidDrawerFilters]);

  const coBidOutcomeCounts = useMemo(() => {
    const counts: Record<SharedWinOutcome, number> = {
      target: 0,
      partner: 0,
      both: 0,
      other: 0,
      none: 0,
    };
    if (!coBidDrawerCompanion) return counts;
    const partnerName = coBidDrawerCompanion.company_name;
    for (const inquiry of coBidSharedInquiries) {
      counts[classifySharedOutcome(inquiry, partnerName)] += 1;
    }
    return counts;
  }, [coBidSharedInquiries, coBidDrawerCompanion]);

  const updateCoBidDrawerFilters = useCallback((patch: Partial<CoBidDrawerInquiryFilters>) => {
    setCoBidDrawerFilters((prev) => ({ ...prev, ...patch }));
    setCoBidDrawerPage(1);
  }, []);

  const coBidDrawerCharts = useMemo(() => {
    if (!coBidDrawerCompanion || !coBidResult) {
      return { pieOption: null, compareOption: null };
    }
    const partnerName = coBidDrawerCompanion.company_name;
    const outcomes: Record<SharedWinOutcome, number> = {
      target: 0,
      partner: 0,
      both: 0,
      other: 0,
      none: 0,
    };
    for (const inquiry of coBidFilteredInquiries) {
      outcomes[classifySharedOutcome(inquiry, partnerName)] += 1;
    }
    const pieOption = {
      color: OUTCOME_ORDER.map((key) => OUTCOME_COLORS[key]),
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, type: "scroll" },
      series: [
        {
          type: "pie",
          radius: ["42%", "68%"],
          center: ["50%", "44%"],
          data: OUTCOME_ORDER.filter((key) => outcomes[key] > 0).map((key) => ({
            name: OUTCOME_LABELS[key],
            value: outcomes[key],
          })),
          label: { formatter: "{b}\n{d}%" },
        },
      ],
    };
    const compareOption = {
      color: OUTCOME_ORDER.map((key) => OUTCOME_COLORS[key]),
      tooltip: { trigger: "axis" },
      grid: { left: 12, right: 12, top: 24, bottom: 56, containLabel: true },
      xAxis: {
        type: "category",
        data: OUTCOME_ORDER.map((key) => OUTCOME_LABELS[key]),
        axisLabel: {
          interval: 0,
          rotate: 28,
          fontSize: 11,
          hideOverlap: false,
        },
      },
      yAxis: { type: "value", minInterval: 1 },
      series: [
        {
          type: "bar",
          barMaxWidth: 48,
          data: OUTCOME_ORDER.map((key) => outcomes[key]),
          itemStyle: { borderRadius: [6, 6, 0, 0] },
        },
      ],
    };
    return { pieOption, compareOption };
  }, [coBidDrawerCompanion, coBidResult, coBidFilteredInquiries]);

  const coBidDrawerInquiryColumns = useMemo<TableColumnsType<CommercialCoBidInquiry>>(
    () => [
      { title: "询价单号", dataIndex: "inquiry_no", width: 130, ellipsis: true },
      { title: "日期", dataIndex: "inquiry_time", width: 100, render: (v: string) => v || "-" },
      { title: "采购单位", dataIndex: "purchaser", ellipsis: true },
      {
        title: "中标方",
        dataIndex: "winners",
        width: 140,
        ellipsis: true,
        render: (list: string[]) => (list.length ? list.join("、") : "无"),
      },
      {
        title: "同场结果",
        key: "outcome",
        width: 100,
        render: (_v, row) => {
          if (!coBidDrawerCompanion) return "-";
          const outcome = classifySharedOutcome(row, coBidDrawerCompanion.company_name);
          return <Tag color={OUTCOME_TAG_COLORS[outcome]}>{OUTCOME_LABELS[outcome]}</Tag>;
        },
      },
    ],
    [coBidDrawerCompanion],
  );

  const coBidGraphOption = useMemo(() => {
    if (!coBidResult?.graph?.nodes?.length) return null;
    const { nodes, links, categories } = coBidResult.graph;
    return {
      tooltip: {
        trigger: "item",
        confine: true,
        formatter: (params: { dataType?: string; data?: Record<string, unknown> }) => {
          const d = params.data;
          if (!d) return "";
          if (params.dataType === "edge") {
            const label = d.label as { formatter?: string } | undefined;
            return `${String(d.source)} → ${String(d.target)}<br/>${label?.formatter || `同场 ${d.value} 次`}`;
          }
          const patterns = (d.patterns as string[] | undefined) || [];
          return [
            `<strong>${String(d.name)}</strong>`,
            patterns.length ? `模式：${patterns.join("、")}` : `同场 ${d.value} 次`,
          ].join("<br/>");
        },
      },
      color: chartPalette,
      legend: [{ data: (categories || []).map((c) => c.name), bottom: 0, textStyle: { color: "#64748b" } }],
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          categories,
          data: nodes,
          links,
          label: { show: true, fontSize: 11 },
          emphasis: { focus: "adjacency", lineStyle: { width: 4 } },
          force: { repulsion: 420, gravity: 0.05, edgeLength: [100, 220], friction: 0.35 },
          lineStyle: { color: "source", curveness: 0.12, opacity: 0.75 },
        },
      ],
    };
  }, [coBidResult]);

  const coBidFlaggedCompanions = useMemo(
    () => (coBidResult?.companions || []).filter((row) => row.patterns.length > 0),
    [coBidResult],
  );

  const coBidCompanionBothWins = useMemo(() => {
    const map = new Map<string, number>();
    if (!coBidResult) return map;
    for (const companion of coBidResult.companions) {
      map.set(companion.company_norm, countCompanionBothWins(companion, coBidResult.inquiries));
    }
    return map;
  }, [coBidResult]);

  const coBidCompanionColumns = useMemo<TableColumnsType<CommercialCoBidCompanion>>(
    () => [
      {
        title: "关联企业",
        dataIndex: "company_name",
        ellipsis: true,
        render: (name: string) => <Text strong className="commercial-company-link">{name}</Text>,
      },
      {
        title: "同场次数",
        dataIndex: "shared_inquiries",
        width: 96,
        align: "right",
        sorter: (a, b) => a.shared_inquiries - b.shared_inquiries,
        defaultSortOrder: "descend",
      },
      {
        title: "同场占比",
        dataIndex: "co_rate",
        width: 96,
        align: "right",
        render: (v: number) => `${Math.round(v * 1000) / 10}%`,
        sorter: (a, b) => a.co_rate - b.co_rate,
      },
      {
        title: "目标中标",
        dataIndex: "target_wins_together",
        width: 88,
        align: "right",
      },
      {
        title: "对方中标",
        dataIndex: "partner_wins_together",
        width: 88,
        align: "right",
      },
      {
        title: "共同中标",
        key: "both_wins_together",
        width: 88,
        align: "right",
        sorter: (a, b) =>
          (coBidCompanionBothWins.get(a.company_norm) || 0) - (coBidCompanionBothWins.get(b.company_norm) || 0),
        render: (_v, row) => coBidCompanionBothWins.get(row.company_norm) || 0,
      },
      {
        title: "双方未中",
        dataIndex: "both_lose_together",
        width: 88,
        align: "right",
      },
      {
        title: "可疑模式",
        dataIndex: "patterns",
        width: 200,
        render: (patterns: string[]) =>
          patterns.length ? (
            <Space size={[4, 4]} wrap>
              {patterns.map((p) => (
                <PatternHelpTag key={p} pattern={p} />
              ))}
            </Space>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
    ],
    [coBidCompanionBothWins],
  );

  const detailColumns = useMemo<TableColumnsType<CommercialAnalysisRecord>>(
    () => [
      { title: "询价单号", dataIndex: "inquiry_no", width: 140, ellipsis: true },
      { title: "采购单位", dataIndex: "purchaser", width: 160, ellipsis: true },
      {
        title: "中标金额",
        dataIndex: "win_amount",
        width: 120,
        align: "right",
        render: (v: number) => <Text className="commercial-amount">{formatAmount(v)}</Text>,
      },
      { title: "物资/项目", dataIndex: "item_name", ellipsis: true },
      {
        title: "中标状态",
        dataIndex: "bid_status",
        width: 100,
        render: (v: string) => (v ? <Tag color="green">{v}</Tag> : "-"),
      },
      { title: "询价日期", dataIndex: "inquiry_time", width: 120, ellipsis: true, render: (v: string) => v || "-" },
      { title: "来源定位", dataIndex: "source", width: 260, ellipsis: true },
    ],
    [],
  );

  const detailTotalAmount = useMemo(
    () => detailRecords.reduce((sum, row) => sum + Number(row.win_amount || 0), 0),
    [detailRecords],
  );

  const companyColumns = useMemo<TableColumnsType<CompanySummaryRow>>(
    () => [
      {
        title: "排名",
        width: 64,
        align: "center",
        render: (_v, _r, index) => (
          <span className="commercial-rank">{(tablePage - 1) * tablePageSize + index + 1}</span>
        ),
      },
      {
        title: "企业",
        dataIndex: "company_name",
        ellipsis: true,
        render: (name: string) => <Text strong className="commercial-company-link">{name}</Text>,
      },
      {
        title: "参标次数",
        key: "participation_count",
        dataIndex: "participation_count",
        width: 108,
        align: "right",
        sorter: true,
        sortDirections: SORT_DIRECTIONS,
        sortOrder: sortState.field === "participation_count" ? sortState.order : null,
      },
      {
        title: "中标次数",
        key: "win_count",
        dataIndex: "win_count",
        width: 108,
        align: "right",
        sorter: true,
        sortDirections: SORT_DIRECTIONS,
        sortOrder: sortState.field === "win_count" ? sortState.order : null,
        render: (v: number) => <span className={v > 0 ? "commercial-win-count" : ""}>{v}</span>,
      },
      {
        title: "中标率",
        key: "win_rate",
        width: 120,
        align: "center",
        sorter: true,
        sortDirections: SORT_DIRECTIONS,
        sortOrder: sortState.field === "win_rate" ? sortState.order : null,
        render: (_v, row) => {
          const rate = winRate(row.participation_count, row.win_count);
          return (
            <div className="commercial-win-rate">
              <Progress
                percent={rate}
                size="small"
                showInfo={false}
                strokeColor={rate >= 50 ? "#d94832" : rate >= 20 ? "#e8954a" : "#c9a227"}
              />
              <span>{rate}%</span>
            </div>
          );
        },
      },
      {
        title: "中标金额",
        key: "win_amount",
        dataIndex: "win_amount",
        width: 140,
        align: "right",
        sorter: true,
        sortDirections: SORT_DIRECTIONS,
        sortOrder: sortState.field === "win_amount" ? sortState.order : null,
        render: (v: number) => <Text className="commercial-amount">{formatAmount(v)}</Text>,
      },
      {
        title: "风险等级",
        dataIndex: "risk_level",
        width: 96,
        align: "center",
        filters: [
          { text: "高", value: "high" },
          { text: "中", value: "medium" },
          { text: "低", value: "low" },
          { text: "未分级", value: "" },
        ],
        onFilter: (value, record) => (record.risk_level || "") === value,
        render: (v: string) =>
          v ? (
            <Tag color={RISK_LEVEL_COLORS[v] || "default"}>{riskLevelLabel(v)}</Tag>
          ) : (
            <Tag>未分级</Tag>
          ),
      },
      {
        title: "风险分",
        key: "risk_score",
        dataIndex: "risk_score",
        width: 88,
        align: "right",
        sorter: true,
        sortDirections: SORT_DIRECTIONS,
        sortOrder: sortState.field === "risk_score" ? sortState.order : null,
        render: (v: number) => (v ? <Text type={v >= 60 ? "danger" : undefined}>{v}</Text> : "-"),
      },
      {
        title: "操作",
        key: "actions",
        width: 96,
        align: "center",
        render: (_v, row) => (
          <Button
            type="link"
            size="small"
            className="commercial-co-bid-link"
            onClick={(e) => {
              e.stopPropagation();
              switchToCoBid(row.company_name);
            }}
          >
            陪标分析
          </Button>
        ),
      },
    ],
    [sortState, tablePage, tablePageSize]
  );

  const companyAmountOption = useMemo(() => {
    const top = records?.summary.top_company_amounts || [];
    if (!top.length) return null;
    return {
      color: [chartPair.primary],
      tooltip: {
        trigger: "axis",
        formatter: (params: Array<{ name: string; value: number }>) => {
          const item = params[0];
          return `${item.name}<br/>中标金额：${formatAmount(item.value)} 元`;
        },
      },
      grid: { top: 12, left: 12, right: 36, bottom: 28, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: {
          formatter: (v: number) => {
            if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}亿`;
            if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
            return String(v);
          },
        },
      },
      yAxis: {
        type: "category",
        data: top.map(([name]) => name).reverse(),
        axisLabel: { width: 140, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          data: top.map(([, val]) => val).reverse(),
          itemStyle: { borderRadius: [0, 6, 6, 0], color: chartPair.primary },
          label: { show: true, position: "right", formatter: ({ value }: { value: number }) => formatCompactAmount(value) },
        },
      ],
    };
  }, [records]);

  const purchaserAmountOption = useMemo(() => {
    const top = records?.summary.top_purchaser_amounts || [];
    if (!top.length) return null;
    return {
      color: chartPalette,
      tooltip: {
        trigger: "item",
        formatter: ({ name, value, percent }: { name: string; value: number; percent: number }) =>
          `${name}<br/>${formatAmount(value)} 元 (${percent}%)`,
      },
      legend: { bottom: 0, type: "scroll" },
      series: [
        {
          type: "pie",
          radius: ["42%", "68%"],
          center: ["50%", "44%"],
          data: top.map(([name, value]) => ({ name, value })),
          label: { formatter: "{b}\n{d}%" },
        },
      ],
    };
  }, [records]);

  const handleTableChange = (
    pagination: { current?: number; pageSize?: number },
    _filters: unknown,
    sorter: unknown
  ) => {
    if (pagination.current) setTablePage(pagination.current);
    if (pagination.pageSize) setTablePageSize(pagination.pageSize);
    const item = (Array.isArray(sorter) ? sorter[0] : sorter) as {
      columnKey?: SortField;
      field?: SortField;
      order?: "ascend" | "descend" | null;
    };
    const field = (item?.columnKey || item?.field) as SortField | undefined;
    if (!field) return;
    setSortState((prev) => {
      const order: "ascend" | "descend" =
        item?.order === "ascend" || item?.order === "descend"
          ? item.order
          : prev.field === field && prev.order === "descend"
            ? "ascend"
            : "descend";
      return { field, order };
    });
    setTablePage(1);
  };

  return (
    <Card className="app-card commercial-analysis-page" bordered={false}>
      <div className="commercial-analysis-header">
        <div>
          <Title level={4} style={{ margin: 0 }}>商务网分析</Title>
          <Paragraph className="commercial-analysis-subtitle">
            切换分析视图：企业中标统计，或针对单一企业的陪标关联分析（阈值在「模型管理 → 陪标关联分析」中配置）。
          </Paragraph>
        </div>
        <Space wrap align="start">
          <Segmented<AnalysisViewMode>
            value={viewMode}
            onChange={(val) => setViewMode(val)}
            options={[
              { label: "企业中标统计", value: "stats" },
              { label: "陪标关联分析", value: "cobid" },
            ]}
          />
          <span>商务网批次：</span>
          <Select
            style={{ minWidth: 300 }}
            value={batchId || undefined}
            onChange={(val) => setBatchId(val)}
            options={batches.map((b) => ({
              value: b.import_batch_id,
              label: `${batchLabel(b)} (${b.file_count} 文件 · ${b.imported_at})`,
            }))}
          />
          <Button loading={exporting} disabled={viewMode !== "stats"} onClick={() => void exportReport()}>
            导出统计 Word
          </Button>
        </Space>
      </div>

      <Card className="commercial-filter-card" size="small" title="筛选条件">
        <Form layout="vertical" form={filter} initialValues={{ only_winners: false }}>
          <Row gutter={[16, 0]}>
            <Col xs={24} md={8} lg={6}>
              <Form.Item
                name="company_name"
                label={viewMode === "cobid" ? "目标企业" : "企业名称"}
                rules={viewMode === "cobid" ? [{ required: true, message: "请填写目标企业" }] : []}
              >
                <AutoComplete
                  allowClear
                  placeholder={viewMode === "cobid" ? "输入或选择企业（支持模糊匹配）" : "支持模糊匹配，可留空"}
                  options={(filterOptions.company_name || []).map((v) => ({ value: v }))}
                  filterOption={(input, option) =>
                    String(option?.value || "").toLowerCase().includes(input.toLowerCase())
                  }
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="purchaser" label="采购单位">
                <Select
                  allowClear
                  showSearch
                  placeholder="全部"
                  options={(filterOptions.purchaser || []).map((v) => ({ value: v, label: v }))}
                />
              </Form.Item>
            </Col>
            {viewMode === "stats" && (
              <>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="inquiry_no" label="询价单号">
                <Select
                  allowClear
                  showSearch
                  placeholder="全部"
                  options={(filterOptions.inquiry_no || []).map((v) => ({ value: v, label: v }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="winner" label="中标供应商">
                <Select
                  allowClear
                  showSearch
                  placeholder="全部"
                  options={(filterOptions.winner || []).map((v) => ({ value: v, label: v }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="participation_min" label="参标次数下限">
                <InputNumber min={1} precision={0} style={{ width: "100%" }} placeholder="不限" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="amount_min" label="中标金额下限">
                <InputNumber min={0} style={{ width: "100%" }} placeholder="不限" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="amount_max" label="中标金额上限">
                <InputNumber min={0} style={{ width: "100%" }} placeholder="不限" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="only_winners" label="仅看中标记录" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
              </>
            )}
            <Col xs={24} md={12} lg={8}>
              <Form.Item name="date_range" label="询价日期段">
                <RangePicker
                  style={{ width: "100%" }}
                  allowClear
                  format="YYYY-MM-DD"
                  placeholder={["开始日期", "结束日期"]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Space>
            <Button
              type="primary"
              loading={viewMode === "cobid" ? coBidLoading : loading}
              onClick={() => void runMainQuery()}
            >
              {viewMode === "cobid" ? "分析陪标关联" : "查询统计"}
            </Button>
            <Button
              onClick={() => {
                filter.resetFields();
                setRiskLevelFilter(undefined);
                setSortState(DEFAULT_SORT);
                setTablePage(1);
                setCoBidResult(null);
              }}
            >
              重置
            </Button>
          </Space>
        </Form>
      </Card>

      {viewMode === "stats" && records && (
        <>
          <Row gutter={[16, 16]} className="commercial-kpi-row">
            <Col xs={12} md={6}>
              <div className="commercial-kpi-tile">
                <div className="label">询价单数量</div>
                <div className="value">{records.summary.inquiry_count}</div>
              </div>
            </Col>
            <Col xs={12} md={6}>
              <div className="commercial-kpi-tile commercial-kpi-tile-alt">
                <div className="label">参与企业数</div>
                <div className="value">{records.summary.company_count}</div>
              </div>
            </Col>
            <Col xs={12} md={6}>
              <div className="commercial-kpi-tile commercial-kpi-tile-warm">
                <div className="label">中标企业数</div>
                <div className="value">{records.summary.winner_company_count}</div>
              </div>
            </Col>
            <Col xs={12} md={6}>
              <div className="commercial-kpi-tile commercial-kpi-tile-gold">
                <div className="label">中标金额合计</div>
                <div className="value">{formatCompactAmount(records.summary.total_win_amount)}</div>
                <div className="hint">{formatAmount(records.summary.total_win_amount)} 元</div>
              </div>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={14}>
              <Card className="commercial-chart-card" size="small" title="企业中标金额 Top 10">
                {companyAmountOption ? (
                  <ReactECharts option={companyAmountOption} style={{ height: 300 }} />
                ) : (
                  <Paragraph className="analysis-empty">暂无数据</Paragraph>
                )}
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card className="commercial-chart-card" size="small" title="采购单位关联中标金额">
                {purchaserAmountOption ? (
                  <ReactECharts option={purchaserAmountOption} style={{ height: 300 }} />
                ) : (
                  <Paragraph className="analysis-empty">暂无数据</Paragraph>
                )}
              </Card>
            </Col>
          </Row>

          <Card className="commercial-company-card" size="small" title="企业中标统计">
            <div className="commercial-company-toolbar">
              <Select
                allowClear
                placeholder="风险等级"
                style={{ width: 140 }}
                value={riskLevelFilter}
                onChange={setRiskLevelFilter}
                options={[
                  { value: "high", label: "高风险" },
                  { value: "medium", label: "中风险" },
                  { value: "low", label: "低风险" },
                  { value: "__none__", label: "未分级" },
                ]}
              />
              <Text type="secondary">
                共 {filteredCompanySummary.length} 家企业
                {companySummary.length !== filteredCompanySummary.length ? `（已筛选，原始 ${companySummary.length} 家）` : ""}
                {" · "}点击企业行查看中标明细，或点「陪标分析」切换视图
              </Text>
            </div>
            <Table<CompanySummaryRow>
              className="commercial-company-table"
              rowKey={(r) => String(r.company_norm || r.company_name)}
              size="middle"
              loading={loading}
              scroll={{ x: "max-content" }}
              columns={companyColumns}
              dataSource={sortedCompanySummary}
              sortDirections={SORT_DIRECTIONS}
              showSorterTooltip
              onChange={handleTableChange}
              rowClassName={(record) =>
                detailCompany?.company_norm === record.company_norm ||
                (detailCompany?.company_name === record.company_name && detailOpen)
                  ? "commercial-company-row-active"
                  : "commercial-company-row-clickable"
              }
              onRow={(record) => ({
                onClick: () => void openCompanyDetail(record),
              })}
              pagination={{
                current: tablePage,
                pageSize: tablePageSize,
                showSizeChanger: true,
                pageSizeOptions: ["10", "20", "50", "100"],
                showTotal: (total) => `共 ${total} 条`,
              }}
            />
          </Card>
        </>
      )}

      {viewMode === "cobid" && (
        <Card className="commercial-co-bid-card" size="small" title="陪标关联分析结果">
          {!coBidResult && !coBidLoading ? (
            <Paragraph type="secondary" className="commercial-co-bid-intro">
              在上方填写目标企业后点击「分析陪标关联」。项目标识为询价单号（旧网=项目编码，新网=寻源单号）；判定阈值请在「模型管理 → 陪标关联分析」中调整。
            </Paragraph>
          ) : null}
          {coBidResult ? (
            <div className="commercial-co-bid-result">
              <div className="commercial-co-bid-hero">
                <div className="commercial-co-bid-hero-main">
                  <span className="commercial-co-bid-hero-label">分析目标</span>
                  <div className="commercial-co-bid-hero-name">{coBidResult.target_company}</div>
                  <div className="commercial-co-bid-pattern-legend">
                    <Text type="secondary">模式说明：</Text>
                    <PatternHelpTag pattern="高频陪标" />
                    <PatternHelpTag pattern="轮流中标" />
                  </div>
                </div>
                <Row gutter={[12, 12]} className="commercial-co-bid-kpi-row">
                  <Col xs={12} sm={6}>
                    <div className="commercial-co-bid-kpi">
                      <span className="label">参标项目</span>
                      <span className="value">{coBidResult.participation_count}</span>
                    </div>
                  </Col>
                  <Col xs={12} sm={6}>
                    <div className="commercial-co-bid-kpi commercial-co-bid-kpi-win">
                      <span className="label">中标项目</span>
                      <span className="value">{coBidResult.win_count}</span>
                    </div>
                  </Col>
                  <Col xs={12} sm={6}>
                    <div className="commercial-co-bid-kpi">
                      <span className="label">同场关联企业</span>
                      <span className="value">{coBidResult.companions.length}</span>
                    </div>
                  </Col>
                  <Col xs={12} sm={6}>
                    <div className="commercial-co-bid-kpi commercial-co-bid-kpi-alert">
                      <span className="label">可疑模式企业</span>
                      <span className="value">{coBidFlaggedCompanions.length}</span>
                    </div>
                  </Col>
                </Row>
              </div>

              <div className="commercial-co-bid-insight">
                <Paragraph className="commercial-co-bid-description">{coBidResult.description}</Paragraph>
                {coBidFlaggedCompanions.length > 0 ? (
                  <div className="commercial-co-bid-flagged">
                    <Text type="secondary">触发可疑模式：</Text>
                    <Space size={[6, 6]} wrap>
                      {coBidFlaggedCompanions.slice(0, 12).map((row) => (
                        <span
                          key={row.company_norm || row.company_name}
                          className="commercial-co-bid-flagged-item commercial-co-bid-flagged-clickable"
                          onClick={() => openCoBidCompanionDrawer(row)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") openCoBidCompanionDrawer(row);
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <Text strong>{row.company_name}</Text>
                          {row.patterns.map((p) => (
                            <PatternHelpTag key={`${row.company_name}-${p}`} pattern={p} />
                          ))}
                        </span>
                      ))}
                      {coBidFlaggedCompanions.length > 12 ? (
                        <Text type="secondary">等 {coBidFlaggedCompanions.length} 家</Text>
                      ) : null}
                    </Space>
                  </div>
                ) : null}
              </div>

              <Card
                size="small"
                className="commercial-chart-card commercial-co-bid-graph-card"
                title="陪标关联网络图"
                extra={<Text type="secondary" className="commercial-co-bid-graph-hint">点击节点、连线或下方列表查看同场明细</Text>}
              >
                {coBidGraphOption ? (
                  <ReactECharts
                    ref={coBidChartRef}
                    option={coBidGraphOption}
                    style={{ height: 520 }}
                    onEvents={{ click: handleCoBidGraphClick }}
                  />
                ) : (
                  <Paragraph className="analysis-empty">暂无关联网络数据</Paragraph>
                )}
              </Card>

              <Card className="commercial-co-bid-table-card" size="small" title="同场关联企业">
                <Text type="secondary" className="commercial-co-bid-table-hint">
                  共 {coBidResult.companions.length} 家达到同场阈值的企业 · 点击行查看图表明细
                </Text>
                <Table<CommercialCoBidCompanion>
                  className="commercial-co-bid-companion-table"
                  rowKey={(r) => r.company_norm || r.company_name}
                  size="middle"
                  loading={coBidLoading}
                  columns={coBidCompanionColumns}
                  dataSource={coBidResult.companions}
                  scroll={{ x: "max-content" }}
                  showSorterTooltip
                  rowClassName={(record) =>
                    coBidDrawerOpen &&
                    coBidDrawerCompanion?.company_norm === record.company_norm
                      ? "commercial-company-row-active"
                      : "commercial-company-row-clickable"
                  }
                  onRow={(record) => ({
                    onClick: () => openCoBidCompanionDrawer(record),
                  })}
                  pagination={{
                    current: coBidCompanionPage,
                    pageSize: coBidCompanionPageSize,
                    showSizeChanger: true,
                    pageSizeOptions: ["10", "20", "50", "100"],
                    showTotal: (total) => `共 ${total} 家`,
                    onChange: (page, pageSize) => {
                      setCoBidCompanionPage(page);
                      setCoBidCompanionPageSize(pageSize);
                    },
                  }}
                  locale={{ emptyText: "未达到同场次数阈值的企业" }}
                />
              </Card>
            </div>
          ) : null}
        </Card>
      )}

      <Drawer
        className="commercial-co-bid-drawer"
        title={
          coBidDrawerCompanion && coBidResult
            ? `${coBidResult.target_company} ↔ ${coBidDrawerCompanion.company_name}`
            : "同场关联明细"
        }
        width={Math.min(880, typeof window !== "undefined" ? window.innerWidth - 48 : 880)}
        open={coBidDrawerOpen}
        onClose={() => {
          setCoBidDrawerOpen(false);
          setCoBidDrawerCompanion(null);
        }}
        destroyOnClose
      >
        {coBidDrawerCompanion && coBidResult ? (
          <>
            <div className="commercial-co-bid-drawer-summary">
              <div className="commercial-co-bid-drawer-stat">
                <span className="label">同场次数</span>
                <span className="value">{coBidDrawerCompanion.shared_inquiries}</span>
              </div>
              <div className="commercial-co-bid-drawer-stat">
                <span className="label">同场占比</span>
                <span className="value">{Math.round(coBidDrawerCompanion.co_rate * 1000) / 10}%</span>
              </div>
              <div className="commercial-co-bid-drawer-stat">
                <span className="label">目标中标</span>
                <span className="value">{coBidOutcomeCounts.target}</span>
              </div>
              <div className="commercial-co-bid-drawer-stat">
                <span className="label">对方中标</span>
                <span className="value">{coBidOutcomeCounts.partner}</span>
              </div>
              <div className="commercial-co-bid-drawer-stat">
                <span className="label">共同中标</span>
                <span className="value">{coBidOutcomeCounts.both}</span>
              </div>
              <div className="commercial-co-bid-drawer-stat">
                <span className="label">同场占比进度</span>
                <Progress
                  percent={Math.round(coBidDrawerCompanion.co_rate * 1000) / 10}
                  size="small"
                  strokeColor="#d94832"
                  style={{ minWidth: 120 }}
                />
              </div>
            </div>
            {coBidDrawerCompanion.patterns.length ? (
              <div className="commercial-co-bid-drawer-patterns">
                {coBidDrawerCompanion.patterns.map((p) => (
                  <PatternHelpTag key={p} pattern={p} />
                ))}
              </div>
            ) : null}

            <Row gutter={[12, 12]}>
              <Col xs={24} md={12}>
                <Card size="small" className="commercial-co-bid-drawer-chart" title="同场中标结果分布">
                  {coBidDrawerCharts.pieOption ? (
                    <ReactECharts option={coBidDrawerCharts.pieOption} style={{ height: 260 }} />
                  ) : (
                    <Paragraph className="analysis-empty">暂无数据</Paragraph>
                  )}
                </Card>
              </Col>
              <Col xs={24} md={12}>
                <Card size="small" className="commercial-co-bid-drawer-chart" title="同场中标次数对比">
                  {coBidDrawerCharts.compareOption ? (
                    <ReactECharts option={coBidDrawerCharts.compareOption} style={{ height: 260 }} />
                  ) : (
                    <Paragraph className="analysis-empty">暂无数据</Paragraph>
                  )}
                </Card>
              </Col>
            </Row>

            <Card
              size="small"
              className="commercial-co-bid-drawer-table"
              title={`同场项目明细（${coBidFilteredInquiries.length}${coBidFilteredInquiries.length !== coBidSharedInquiries.length ? ` / ${coBidSharedInquiries.length}` : ""} 项）`}
            >
              <div className="commercial-co-bid-drawer-filters">
                <Row gutter={[8, 8]}>
                  <Col xs={24} sm={12} md={6}>
                    <Input
                      allowClear
                      placeholder="询价单号"
                      value={coBidDrawerFilters.inquiryNo}
                      onChange={(e) => updateCoBidDrawerFilters({ inquiryNo: e.target.value })}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={8}>
                    <RangePicker
                      allowClear
                      style={{ width: "100%" }}
                      format="YYYY-MM-DD"
                      placeholder={["开始日期", "结束日期"]}
                      value={coBidDrawerFilters.dateRange}
                      onChange={(range) =>
                        updateCoBidDrawerFilters({
                          dateRange: range?.[0] && range?.[1] ? [range[0], range[1]] : null,
                        })
                      }
                    />
                  </Col>
                  <Col xs={24} sm={12} md={5}>
                    <Input
                      allowClear
                      placeholder="中标方（模糊）"
                      value={coBidDrawerFilters.winnerKeyword}
                      onChange={(e) => updateCoBidDrawerFilters({ winnerKeyword: e.target.value })}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={5}>
                    <Select
                      allowClear
                      style={{ width: "100%" }}
                      placeholder="同场结果"
                      value={coBidDrawerFilters.outcome}
                      options={OUTCOME_ORDER.map((key) => ({
                        value: key,
                        label: OUTCOME_LABELS[key],
                      }))}
                      onChange={(value) => updateCoBidDrawerFilters({ outcome: value })}
                    />
                  </Col>
                </Row>
              </div>
              <Table<CommercialCoBidInquiry>
                rowKey="inquiry_no"
                size="small"
                columns={coBidDrawerInquiryColumns}
                dataSource={coBidFilteredInquiries}
                scroll={{ x: "max-content" }}
                pagination={{
                  current: coBidDrawerPage,
                  pageSize: coBidDrawerPageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ["10", "20", "50", "100"],
                  showTotal: (total) => `共 ${total} 条`,
                  onChange: (page, pageSize) => {
                    setCoBidDrawerPage(page);
                    setCoBidDrawerPageSize(pageSize);
                  },
                }}
              />
            </Card>
          </>
        ) : null}
      </Drawer>

      <Drawer
            className="commercial-detail-drawer"
            title={detailCompany?.company_name || "中标明细"}
            width={Math.min(920, typeof window !== "undefined" ? window.innerWidth - 48 : 920)}
            open={detailOpen}
            onClose={() => {
              setDetailOpen(false);
              setDetailCompany(null);
            }}
            destroyOnClose
          >
            {detailCompany && (
              <>
                <div className="commercial-detail-summary">
                  <div className="commercial-detail-stat">
                    <span className="label">参标次数</span>
                    <span className="value">{detailCompany.participation_count}</span>
                  </div>
                  <div className="commercial-detail-stat">
                    <span className="label">中标次数</span>
                    <span className="value commercial-win-count">{detailCompany.win_count}</span>
                  </div>
                  <div className="commercial-detail-stat">
                    <span className="label">中标率</span>
                    <span className="value">{winRate(detailCompany.participation_count, detailCompany.win_count)}%</span>
                  </div>
                  <div className="commercial-detail-stat">
                    <span className="label">中标金额合计</span>
                    <span className="value commercial-amount">{formatAmount(detailCompany.win_amount)}</span>
                  </div>
                  {detailCompany.risk_level ? (
                    <div className="commercial-detail-stat">
                      <span className="label">风险等级</span>
                      <span className="value">
                        <Tag color={RISK_LEVEL_COLORS[detailCompany.risk_level] || "default"}>
                          {riskLevelLabel(detailCompany.risk_level)}
                        </Tag>
                      </span>
                    </div>
                  ) : null}
                </div>
                <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                  以下展示当前筛选条件下该企业的中标记录，共 {detailRecords.length} 条，明细金额合计 {formatAmount(detailTotalAmount)} 元
                </Paragraph>
                <Table<CommercialAnalysisRecord>
                  rowKey={(r, idx) => `${r.inquiry_no}-${r.item_name}-${r.win_amount}-${idx}`}
                  size="small"
                  loading={detailLoading}
                  columns={detailColumns}
                  dataSource={detailRecords}
                  scroll={{ x: "max-content" }}
                  locale={{ emptyText: detailCompany.win_count > 0 ? "暂无中标明细数据" : "该企业暂无中标记录" }}
                  pagination={{
                    current: detailDrawerPage,
                    pageSize: detailDrawerPageSize,
                    showSizeChanger: true,
                    pageSizeOptions: ["10", "20", "50", "100"],
                    showTotal: (total) => `共 ${total} 条`,
                    onChange: (page, pageSize) => {
                      setDetailDrawerPage(page);
                      setDetailDrawerPageSize(pageSize);
                    },
                  }}
                />
              </>
            )}
          </Drawer>
    </Card>
  );
}

export default CommercialAnalysisPage;
