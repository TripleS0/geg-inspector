import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { DownloadOutlined, DownOutlined, SearchOutlined, UpOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import { api, BatchInfo, batchLabel, WechatAnalysisFilter, WechatAnalysisRecord, WechatAnalysisResponse } from "../api";
import { chartPair, chartPalette } from "../theme";
import { AnalysisDateTimeFilterFields, AnalysisDateTimeFormFields, serializeAnalysisDateTimeFilters } from "../components/AnalysisDateTimeFilters";

type WechatFilterForm = WechatAnalysisFilter & AnalysisDateTimeFormFields;

const { Title, Paragraph } = Typography;

function formatAmount(value: unknown) {
  const n = Number(value || 0);
  return n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function recordMatchesKeyword(row: WechatAnalysisRecord, keyword: string) {
  const tokens = keyword.trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const haystack = [
    row.user_name,
    row.debit_credit_type,
    row.business_type,
    row.purpose_type,
    row.counterparty_name,
    row.counterparty_bank_name,
    row.remark1,
    row.remark2,
    row.txn_no,
  ].join(" ");
  return tokens.every((token) => haystack.includes(token));
}

function WechatAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<WechatFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<WechatAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [tableKeyword, setTableKeyword] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.listBatches("wechat");
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
    void api.wechatAnalysisFilterOptions(batchId).then(setFilterOptions).catch(() => setFilterOptions({}));
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runQuery = async () => {
    if (!batchId) return;
    setLoading(true);
    try {
      const values = await filter.validateFields();
      const data = await api.wechatAnalysisRecords(batchId, serializeAnalysisDateTimeFilters(values));
      setRecords(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const directionOption = useMemo(() => {
    if (!records) return null;
    const summary = records.summary;
    return {
      color: [chartPair.primary, chartPair.secondary],
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          data: [
            { name: "收入", value: summary.in_total },
            { name: "支出", value: summary.out_total },
          ],
        },
      ],
    };
  }, [records]);

  const counterpartyOption = useMemo(() => {
    const top = records?.summary.top_counterparties || [];
    if (!top.length) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "axis" },
      grid: { top: 12, left: 12, right: 36, bottom: 28, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: {
          formatter: (v: number) => {
            if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
            return String(v);
          },
        },
      },
      yAxis: {
        type: "category",
        data: top.map(([name]) => name).reverse(),
        axisLabel: { width: 100, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          data: top.map(([, val]) => val).reverse(),
          itemStyle: { color: chartPair.primary, borderRadius: [0, 6, 6, 0] },
        },
      ],
    };
  }, [records]);

  const purposeOption = useMemo(() => {
    const top = records?.summary.top_purpose_types || [];
    if (!top.length) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [{ type: "pie", radius: ["45%", "70%"], data: top.map(([name, value]) => ({ name, value })) }],
    };
  }, [records]);

  const recordColumns = useMemo(
    () => [
      {
        title: "交易时间",
        dataIndex: "txn_time",
        width: 170,
        ellipsis: true,
        sorter: (a: WechatAnalysisRecord, b: WechatAnalysisRecord) => a.txn_time.localeCompare(b.txn_time),
      },
      { title: "用户", dataIndex: "user_name", width: 100, ellipsis: true },
      {
        title: "借贷类型",
        dataIndex: "debit_credit_type",
        width: 90,
        render: (v: string) => {
          const incomeTypes = records?.summary.income_types || ["入"];
          const color = incomeTypes.includes(v) ? "green" : "red";
          return <Tag color={color}>{v || "-"}</Tag>;
        },
      },
      { title: "业务类型", dataIndex: "business_type", width: 100, ellipsis: true },
      { title: "用途类型", dataIndex: "purpose_type", width: 90, ellipsis: true },
      {
        title: "金额(元)",
        dataIndex: "amount_yuan",
        width: 110,
        sorter: (a: WechatAnalysisRecord, b: WechatAnalysisRecord) => Number(a.amount_yuan || 0) - Number(b.amount_yuan || 0),
        render: (value: number) => <span className="analysis-table-amount">{formatAmount(value)}</span>,
      },
      {
        title: "余额(元)",
        dataIndex: "balance_yuan",
        width: 110,
        sorter: (a: WechatAnalysisRecord, b: WechatAnalysisRecord) => Number(a.balance_yuan || 0) - Number(b.balance_yuan || 0),
        render: (value: number) => <span className="analysis-table-amount">{formatAmount(value)}</span>,
      },
      { title: "对手", dataIndex: "counterparty_name", width: 140, ellipsis: true },
      { title: "对手银行", dataIndex: "counterparty_bank_name", width: 120, ellipsis: true },
      { title: "备注1", dataIndex: "remark1", width: 120, ellipsis: true },
      { title: "备注2", dataIndex: "remark2", width: 120, ellipsis: true },
      { title: "交易单号", dataIndex: "txn_no", width: 180, ellipsis: true },
    ],
    [records]
  );

  const filteredRecords = useMemo(
    () => (records?.records || []).filter((row) => recordMatchesKeyword(row, tableKeyword)),
    [records, tableKeyword]
  );

  const exportRecords = async () => {
    if (!filteredRecords.length) {
      message.warning("当前没有可导出的明细");
      return;
    }
    try {
      const currentBatch = batches.find((item) => item.import_batch_id === batchId);
      const fileName = `${batchLabel(currentBatch || { import_batch_id: batchId })}_微信明细`;
      const blob = await api.exportRowsToExcel(
        filteredRecords as unknown as Record<string, unknown>[],
        [
          { key: "txn_time", title: "交易时间" },
          { key: "user_name", title: "用户" },
          { key: "debit_credit_type", title: "借贷类型" },
          { key: "business_type", title: "业务类型" },
          { key: "purpose_type", title: "用途类型" },
          { key: "amount_yuan", title: "金额(元)" },
          { key: "balance_yuan", title: "余额(元)" },
          { key: "counterparty_name", title: "对手" },
          { key: "counterparty_bank_name", title: "对手银行" },
          { key: "remark1", title: "备注1" },
          { key: "remark2", title: "备注2" },
          { key: "txn_no", title: "交易单号" },
        ],
        fileName,
        "微信明细"
      );
      downloadBlob(blob, `${fileName}.xlsx`);
      message.success("微信明细已导出");
    } catch (err) {
      message.error((err as Error).message || "导出失败");
    }
  };

  return (
    <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>微信流水分析</Title>
        <Space>
          <span>微信批次：</span>
          <Select
            style={{ minWidth: 320 }}
            value={batchId || undefined}
            onChange={(val) => setBatchId(val)}
            options={batches.map((b) => ({
              value: b.import_batch_id,
              label: `${batchLabel(b)} (${b.file_count} 文件 · ${b.imported_at})`,
            }))}
          />
        </Space>
      </div>
      <Paragraph style={{ color: "#5b6477" }}>
        支持按借贷类型自定义区分收支方向，默认「入」为收入、「出」为支出；金额由分自动换算为元展示。
      </Paragraph>

      <Form
        layout="vertical"
        form={filter}
        initialValues={{ income_types: ["入"], expense_types: ["出"] }}
      >
        <Form.Item
          label="快速筛选"
          name="quick_query"
          tooltip="多个关键词用空格隔开，会匹配用户、对手、收支类型、业务类型、用途、备注、银行卡等字段"
        >
          <Input.Search
            allowClear
            size="large"
            placeholder="例如：孙丽 转入 郑凯/孙俪 转出"
            enterButton="快速筛选"
            loading={loading}
            onSearch={() => void runQuery()}
          />
        </Form.Item>
        <Space>
          <Button type="primary" loading={loading} onClick={() => void runQuery()}>查询</Button>
          <Button icon={advancedOpen ? <UpOutlined /> : <DownOutlined />} onClick={() => setAdvancedOpen((open) => !open)}>
            更多筛选
          </Button>
          <Button onClick={() => filter.resetFields()}>重置</Button>
        </Space>
        {advancedOpen ? (
          <div className="analysis-advanced-filter">
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item label="用户侧账号名称" name="user_name">
                  <Select allowClear showSearch placeholder="全部" options={(filterOptions.user_name || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="借贷类型" name="debit_credit_type">
                  <Select allowClear showSearch placeholder="全部" options={(filterOptions.debit_credit_type || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="对手侧账户名称" name="counterparty_name">
                  <Select allowClear showSearch placeholder="全部" options={(filterOptions.counterparty_name || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="交易业务类型" name="business_type">
                  <Select allowClear showSearch placeholder="全部" options={(filterOptions.business_type || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="交易用途类型" name="purpose_type">
                  <Select allowClear showSearch placeholder="全部" options={(filterOptions.purpose_type || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="备注关键词" name="remark">
                  <Input placeholder="匹配备注1/备注2" allowClear />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item label="金额下限(元)" name="amount_min">
                  <InputNumber style={{ width: "100%" }} min={0} />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item label="金额上限(元)" name="amount_max">
                  <InputNumber style={{ width: "100%" }} min={0} />
                </Form.Item>
              </Col>
              <AnalysisDateTimeFilterFields dateCol={{ xs: 24, md: 6 }} timeCol={{ xs: 24, md: 6 }} />
              <Col xs={24} md={12}>
                <Form.Item label="收入借贷类型（自定义）" name="income_types" tooltip="这些借贷类型值将计入收入统计">
                  <Select mode="tags" placeholder="默认：入" options={[{ value: "入", label: "入" }]} />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="支出借贷类型（自定义）" name="expense_types" tooltip="这些借贷类型值将计入支出统计">
                  <Select mode="tags" placeholder="默认：出" options={[{ value: "出", label: "出" }]} />
                </Form.Item>
              </Col>
            </Row>
          </div>
        ) : null}
      </Form>

      {records && (
        <div style={{ marginTop: 20 }}>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <div className="metric-card analysis-kpi-tile"><div className="metric-title">收入合计(元)</div><div className="metric-value">{formatAmount(records.summary.in_total)}</div></div>
            </Col>
            <Col xs={24} md={8}>
              <div className="metric-card analysis-kpi-tile analysis-kpi-tile-alt"><div className="metric-title">支出合计(元)</div><div className="metric-value">{formatAmount(records.summary.out_total)}</div></div>
            </Col>
            <Col xs={24} md={8}>
              <div className="metric-card analysis-kpi-tile analysis-kpi-tile-warm"><div className="metric-title">净流入(元)</div><div className="metric-value">{formatAmount(records.summary.net_total)}</div></div>
            </Col>
          </Row>
          <Row gutter={16} style={{ marginTop: 16 }}>
            {directionOption && (
              <Col xs={24} md={8}>
                <Card size="small" title="收支占比">
                  <ReactECharts option={directionOption} style={{ height: 280 }} />
                </Card>
              </Col>
            )}
            {counterpartyOption && (
              <Col xs={24} md={8}>
                <Card size="small" title="交易对手 Top">
                  <ReactECharts option={counterpartyOption} style={{ height: 280 }} />
                </Card>
              </Col>
            )}
            {purposeOption && (
              <Col xs={24} md={8}>
                <Card size="small" title="用途类型分布">
                  <ReactECharts option={purposeOption} style={{ height: 280 }} />
                </Card>
              </Col>
            )}
          </Row>
          <div className="app-card analysis-table-card" style={{ marginTop: 16 }}>
            <div className="bank-section-head analysis-table-toolbar">
              <Title level={5} style={{ margin: 0 }}>微信明细</Title>
              <Space wrap>
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索用户、对手、类型、备注"
                  value={tableKeyword}
                  onChange={(event) => setTableKeyword(event.target.value)}
                  style={{ width: 260 }}
                />
                <Button icon={<DownloadOutlined />} disabled={!filteredRecords.length} onClick={() => void exportRecords()}>
                  导出Excel
                </Button>
              </Space>
            </div>
            <Table
              className="analysis-data-table"
              size="middle"
              rowKey={(row) => `${row.txn_no}-${row.txn_time}`}
              loading={loading}
              columns={recordColumns}
              dataSource={filteredRecords}
              scroll={{ x: 1400 }}
              pagination={{ pageSize: 20, showSizeChanger: true }}
            />
          </div>
        </div>
      )}
    </Card>
  );
}

export default WechatAnalysisPage;
