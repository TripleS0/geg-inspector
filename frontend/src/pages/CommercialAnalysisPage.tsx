import { useEffect, useMemo, useState } from "react";
import { Button, Card, Col, Form, Input, InputNumber, Row, Select, Space, Switch, Table, Tag, Typography, message } from "antd";
import { DownloadOutlined, DownOutlined, UpOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  BatchInfo,
  batchLabel,
  CommercialAnalysisFilter,
  CommercialAnalysisRecord,
  CommercialAnalysisResponse,
  pollTask,
} from "../api";
import { chartPair, chartPalette } from "../theme";

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

function CommercialAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<CommercialAnalysisFilter>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<CommercialAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

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
    void api.commercialAnalysisFilterOptions(batchId).then(setFilterOptions).catch(() => setFilterOptions({}));
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runQuery = async () => {
    if (!batchId) return;
    setLoading(true);
    try {
      const values = await filter.validateFields();
      const data = await api.commercialAnalysisRecords(batchId, values || {});
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

  const companyAmountOption = useMemo(() => {
    const top = records?.summary.top_company_amounts || [];
    if (!top.length) return null;
    return {
      color: [chartPair.primary],
      tooltip: { trigger: "axis" },
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
      yAxis: { type: "category", data: top.map(([name]) => name).reverse(), axisLabel: { width: 120, overflow: "truncate" } },
      series: [{ type: "bar", data: top.map(([, val]) => val).reverse(), itemStyle: { borderRadius: [0, 6, 6, 0] } }],
    };
  }, [records]);

  const purchaserAmountOption = useMemo(() => {
    const top = records?.summary.top_purchaser_amounts || [];
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
      { title: "询价单号", dataIndex: "inquiry_no", width: 140, ellipsis: true },
      { title: "采购单位", dataIndex: "purchaser", width: 180, ellipsis: true },
      { title: "企业", dataIndex: "company_name", width: 190, ellipsis: true },
      {
        title: "是否中标",
        dataIndex: "is_winner",
        width: 90,
        render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "中标" : "未中标"}</Tag>,
      },
      { title: "中标供应商", dataIndex: "winner", width: 190, ellipsis: true },
      { title: "中标金额", dataIndex: "win_amount", width: 120, render: formatAmount },
      { title: "物资/项目", dataIndex: "item_name", width: 240, ellipsis: true },
      { title: "数据来源", dataIndex: "source", width: 220, ellipsis: true },
    ],
    []
  );

  const companyColumns = useMemo(
    () => [
      { title: "企业", dataIndex: "company_name", ellipsis: true },
      { title: "参标次数", dataIndex: "participation_count", width: 90 },
      { title: "中标次数", dataIndex: "win_count", width: 90 },
      { title: "中标金额", dataIndex: "win_amount", width: 130, render: formatAmount },
      { title: "风险等级", dataIndex: "risk_level", width: 90, render: (v: string) => v || "-" },
      { title: "风险分", dataIndex: "risk_score", width: 90 },
    ],
    []
  );

  const fundColumns = useMemo(
    () => [
      { title: "企业", dataIndex: "company_name", width: 190, ellipsis: true },
      { title: "采购单位", dataIndex: "purchaser", width: 190, ellipsis: true },
      { title: "询价单号", dataIndex: "inquiry_no", width: 140, ellipsis: true },
      { title: "中标金额", dataIndex: "win_amount", width: 130, render: formatAmount },
      { title: "风险等级", dataIndex: "risk_level", width: 90, render: (v: string) => v || "-" },
      { title: "风险分", dataIndex: "risk_score", width: 90 },
      { title: "数据来源", dataIndex: "source", width: 220, ellipsis: true },
    ],
    []
  );

  const exportRows = async (
    rows: Record<string, unknown>[],
    columns: Array<{ key: string; title: string }>,
    suffix: string,
  ) => {
    if (!rows.length) {
      message.warning(`当前没有可导出的${suffix}`);
      return;
    }
    try {
      const currentBatch = batches.find((item) => item.import_batch_id === batchId);
      const fileName = `${batchLabel(currentBatch || { import_batch_id: batchId })}_${suffix}`;
      const blob = await api.exportRowsToExcel(rows, columns, fileName, suffix);
      downloadBlob(blob, `${fileName}.xlsx`);
      message.success(`${suffix}已导出`);
    } catch (err) {
      message.error((err as Error).message || "导出失败");
    }
  };

  return (
    <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>商务网分析</Title>
        <Space>
          <span>商务网批次：</span>
          <Select
            style={{ minWidth: 320 }}
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
      <Paragraph style={{ color: "#5b6477" }}>
        用于商务网数据的查询、统计和中标资金关联展示；风险规则判断仍保留在「商务网风险」页面。
      </Paragraph>

      <Form layout="vertical" form={filter} initialValues={{ only_winners: false }}>
        <Form.Item
          name="quick_query"
          label="快速筛选"
          tooltip="多个关键词用空格隔开，会匹配企业、采购单位、询价单号、中标供应商、物资/项目、数据来源等字段"
        >
          <Input.Search
            allowClear
            size="large"
            placeholder="例如：华南机电 供电公司 中标"
            enterButton="快速筛选"
            loading={loading}
            onSearch={() => void runQuery()}
          />
        </Form.Item>
        <Space>
          <Button type="primary" loading={loading} onClick={() => void runQuery()}>查询并生成统计</Button>
          <Button icon={advancedOpen ? <UpOutlined /> : <DownOutlined />} onClick={() => setAdvancedOpen((open) => !open)}>
            更多筛选
          </Button>
          <Button onClick={() => filter.resetFields()}>重置</Button>
        </Space>
        {advancedOpen ? (
          <div className="analysis-advanced-filter">
            <Row gutter={12}>
              <Col span={6}>
                <Form.Item name="company_name" label="企业">
                  <Select allowClear showSearch options={(filterOptions.company_name || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="purchaser" label="采购单位">
                  <Select allowClear showSearch options={(filterOptions.purchaser || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="inquiry_no" label="询价单号">
                  <Select allowClear showSearch options={(filterOptions.inquiry_no || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="winner" label="中标供应商">
                  <Select allowClear showSearch options={(filterOptions.winner || []).map((v) => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="amount_min" label="中标金额下限">
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="amount_max" label="中标金额上限">
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="only_winners" label="仅看中标企业" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
          </div>
        ) : null}
      </Form>

      {records && (
        <>
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={6}>
              <div className="metric-card"><div className="metric-title">询价单数量</div><div className="metric-value">{records.summary.inquiry_count}</div></div>
            </Col>
            <Col span={6}>
              <div className="metric-card"><div className="metric-title">参与企业数</div><div className="metric-value">{records.summary.company_count}</div></div>
            </Col>
            <Col span={6}>
              <div className="metric-card"><div className="metric-title">中标企业数</div><div className="metric-value">{records.summary.winner_company_count}</div></div>
            </Col>
            <Col span={6}>
              <div className="metric-card"><div className="metric-title">中标金额合计</div><div className="metric-value metric-primary">{formatAmount(records.summary.total_win_amount)}</div></div>
            </Col>
          </Row>

          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={14}>
              <div className="app-card">
                <Title level={5}>企业中标金额 Top 10</Title>
                {companyAmountOption ? <ReactECharts option={companyAmountOption} style={{ height: 260 }} /> : <Paragraph>暂无数据</Paragraph>}
              </div>
            </Col>
            <Col span={10}>
              <div className="app-card">
                <Title level={5}>采购单位关联中标金额</Title>
                {purchaserAmountOption ? <ReactECharts option={purchaserAmountOption} style={{ height: 260 }} /> : <Paragraph>暂无数据</Paragraph>}
              </div>
            </Col>
          </Row>

          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={12}>
              <div className="app-card">
                <div className="bank-section-head">
                  <Title level={5} style={{ margin: 0 }}>企业中标统计</Title>
                  <Button
                    icon={<DownloadOutlined />}
                    disabled={!records.summary.company_summary.length}
                    onClick={() => void exportRows(
                      records.summary.company_summary as Record<string, unknown>[],
                      [
                        { key: "company_name", title: "企业" },
                        { key: "participation_count", title: "参标次数" },
                        { key: "win_count", title: "中标次数" },
                        { key: "win_amount", title: "中标金额" },
                        { key: "risk_level", title: "风险等级" },
                        { key: "risk_score", title: "风险分" },
                      ],
                      "企业中标统计"
                    )}
                  >
                    导出Excel
                  </Button>
                </div>
                <Table
                  rowKey={(r) => String(r.company_norm || r.company_name)}
                  size="small"
                  loading={loading}
                  scroll={{ x: "max-content" }}
                  columns={companyColumns}
                  dataSource={records.summary.company_summary}
                  pagination={{ pageSize: 20 }}
                />
              </div>
            </Col>
            <Col span={12}>
              <div className="app-card">
                <div className="bank-section-head">
                  <Title level={5} style={{ margin: 0 }}>中标资金关联</Title>
                  <Button
                    icon={<DownloadOutlined />}
                    disabled={!records.summary.fund_links.length}
                    onClick={() => void exportRows(
                      records.summary.fund_links as Record<string, unknown>[],
                      [
                        { key: "company_name", title: "企业" },
                        { key: "purchaser", title: "采购单位" },
                        { key: "inquiry_no", title: "询价单号" },
                        { key: "winner", title: "中标供应商" },
                        { key: "win_amount", title: "中标金额" },
                        { key: "risk_level", title: "风险等级" },
                        { key: "risk_score", title: "风险分" },
                        { key: "source", title: "数据来源" },
                      ],
                      "中标资金关联"
                    )}
                  >
                    导出Excel
                  </Button>
                </div>
                <Table
                  rowKey={(r, idx) => `${r.company_name}-${r.inquiry_no}-${idx}`}
                  size="small"
                  loading={loading}
                  scroll={{ x: "max-content" }}
                  columns={fundColumns}
                  dataSource={records.summary.fund_links}
                  pagination={{ pageSize: 20 }}
                />
              </div>
            </Col>
          </Row>

          <div className="app-card" style={{ marginTop: 16 }}>
            <div className="bank-section-head">
              <Title level={5} style={{ margin: 0 }}>查询明细（前 500 行）</Title>
              <Button
                icon={<DownloadOutlined />}
                disabled={!records.records.length}
                onClick={() => void exportRows(
                  records.records as unknown as Record<string, unknown>[],
                  [
                    { key: "inquiry_no", title: "询价单号" },
                    { key: "purchaser", title: "采购单位" },
                    { key: "company_name", title: "企业" },
                    { key: "is_winner", title: "是否中标" },
                    { key: "winner", title: "中标供应商" },
                    { key: "win_amount", title: "中标金额" },
                    { key: "item_name", title: "物资/项目" },
                    { key: "source", title: "数据来源" },
                  ],
                  "商务网查询明细"
                )}
              >
                导出Excel
              </Button>
            </div>
            <Table<CommercialAnalysisRecord>
              rowKey={(r, idx) => `${r.inquiry_no}-${r.company_name}-${idx}`}
              size="small"
              loading={loading}
              scroll={{ x: "max-content" }}
              columns={recordColumns}
              dataSource={records.records.slice(0, 500)}
              pagination={{ pageSize: 30 }}
            />
          </div>
        </>
      )}
    </Card>
  );
}

export default CommercialAnalysisPage;
