import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Progress,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { TableColumnsType } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  BatchInfo,
  batchLabel,
  CommercialAnalysisFilter,
  CommercialAnalysisResponse,
  pollTask,
} from "../api";
import {
  AnalysisDateTimeFormFields,
  serializeAnalysisDateTimeFilters,
} from "../components/AnalysisDateTimeFilters";
import { chartPair, chartPalette } from "../theme";

type CommercialFilterForm = CommercialAnalysisFilter & AnalysisDateTimeFormFields;

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

function CommercialAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<CommercialFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<CommercialAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [companySearch, setCompanySearch] = useState("");
  const [riskLevelFilter, setRiskLevelFilter] = useState<string | undefined>();

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
    setCompanySearch("");
    setRiskLevelFilter(undefined);
    void api.commercialAnalysisFilterOptions(batchId).then(setFilterOptions).catch(() => setFilterOptions({}));
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runQuery = async () => {
    if (!batchId) return;
    setLoading(true);
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
    () => (records?.summary.company_summary || []) as unknown as CompanySummaryRow[],
    [records]
  );

  const filteredCompanySummary = useMemo(() => {
    const keyword = companySearch.trim().toLowerCase();
    return companySummary.filter((row) => {
      if (keyword && !String(row.company_name || "").toLowerCase().includes(keyword)) {
        return false;
      }
      if (riskLevelFilter === "__none__") {
        return !row.risk_level;
      }
      if (riskLevelFilter && row.risk_level !== riskLevelFilter) {
        return false;
      }
      return true;
    });
  }, [companySummary, companySearch, riskLevelFilter]);

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

  const companyColumns = useMemo<TableColumnsType<CompanySummaryRow>>(
    () => [
      {
        title: "排名",
        width: 64,
        align: "center",
        render: (_v, _r, index) => <span className="commercial-rank">{index + 1}</span>,
      },
      {
        title: "企业",
        dataIndex: "company_name",
        ellipsis: true,
        render: (name: string) => <Text strong>{name}</Text>,
      },
      {
        title: "参标次数",
        dataIndex: "participation_count",
        width: 108,
        align: "right",
        sorter: (a, b) => a.participation_count - b.participation_count,
        defaultSortOrder: undefined,
      },
      {
        title: "中标次数",
        dataIndex: "win_count",
        width: 108,
        align: "right",
        sorter: (a, b) => a.win_count - b.win_count,
        render: (v: number) => <span className={v > 0 ? "commercial-win-count" : ""}>{v}</span>,
      },
      {
        title: "中标率",
        width: 120,
        align: "center",
        sorter: (a, b) => winRate(a.participation_count, a.win_count) - winRate(b.participation_count, b.win_count),
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
        dataIndex: "win_amount",
        width: 140,
        align: "right",
        sorter: (a, b) => a.win_amount - b.win_amount,
        defaultSortOrder: "descend",
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
        dataIndex: "risk_score",
        width: 88,
        align: "right",
        sorter: (a, b) => Number(a.risk_score || 0) - Number(b.risk_score || 0),
        render: (v: number) => (v ? <Text type={v >= 60 ? "danger" : undefined}>{v}</Text> : "-"),
      },
    ],
    []
  );

  return (
    <Card className="app-card commercial-analysis-page" bordered={false}>
      <div className="commercial-analysis-header">
        <div>
          <Title level={4} style={{ margin: 0 }}>商务网分析</Title>
          <Paragraph className="commercial-analysis-subtitle">
            按批次统计企业参标与中标情况，支持多维度筛选与排序；风险规则详见「商务网风险」页面。
          </Paragraph>
        </div>
        <Space wrap>
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
          <Button loading={exporting} onClick={() => void exportReport()}>导出统计 Word</Button>
        </Space>
      </div>

      <Card className="commercial-filter-card" size="small" title="筛选条件">
        <Form layout="vertical" form={filter} initialValues={{ only_winners: false }}>
          <Row gutter={[16, 0]}>
            <Col xs={24} md={8} lg={6}>
              <Form.Item name="company_name" label="企业名称">
                <Input allowClear placeholder="支持模糊匹配" prefix={<SearchOutlined />} />
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
            <Button type="primary" loading={loading} onClick={() => void runQuery()}>查询统计</Button>
            <Button
              onClick={() => {
                filter.resetFields();
                setCompanySearch("");
                setRiskLevelFilter(undefined);
              }}
            >
              重置
            </Button>
          </Space>
        </Form>
      </Card>

      {records && (
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
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="搜索企业名称"
                value={companySearch}
                onChange={(e) => setCompanySearch(e.target.value)}
                style={{ width: 260 }}
              />
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
              </Text>
            </div>
            <Table<CompanySummaryRow>
              className="commercial-company-table"
              rowKey={(r) => String(r.company_norm || r.company_name)}
              size="middle"
              loading={loading}
              scroll={{ x: "max-content" }}
              columns={companyColumns}
              dataSource={filteredCompanySummary}
              pagination={{
                pageSize: 20,
                showSizeChanger: true,
                pageSizeOptions: ["10", "20", "50", "100"],
                showTotal: (total) => `共 ${total} 条`,
              }}
            />
          </Card>
        </>
      )}
    </Card>
  );
}

export default CommercialAnalysisPage;
