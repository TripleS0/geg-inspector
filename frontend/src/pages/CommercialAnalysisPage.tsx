import { useEffect, useMemo, useState } from "react";
import { Button, Card, Col, Form, InputNumber, Row, Select, Space, Switch, Table, Tag, Typography, message } from "antd";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  BatchInfo,
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

function renderDescription(text: string) {
  const lines = text.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return <Paragraph className="analysis-empty">暂无描述</Paragraph>;
  return (
    <div className="analysis-description">
      {lines.map((line, index) => (
        <Paragraph key={`${index}-${line}`} className="analysis-description-line">
          {line}
        </Paragraph>
      ))}
    </div>
  );
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
              label: `${b.import_batch_id.slice(0, 8)}… (${b.file_count} 文件 · ${b.imported_at})`,
            }))}
          />
          <Button loading={exporting} onClick={() => void exportReport()}>导出统计 Word</Button>
        </Space>
      </div>
      <Paragraph style={{ color: "#5b6477" }}>
        用于商务网数据的查询、统计和中标资金关联展示；风险规则判断仍保留在「商务网风险」页面。
      </Paragraph>

      <Form layout="vertical" form={filter} initialValues={{ only_winners: false }}>
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
        <Space>
          <Button type="primary" loading={loading} onClick={() => void runQuery()}>查询并生成统计</Button>
          <Button onClick={() => filter.resetFields()}>重置</Button>
        </Space>
      </Form>

      {records && (
        <>
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={6}>
              <div className="kpi-tile"><div className="label">询价单数量</div><div className="value">{records.summary.inquiry_count}</div></div>
            </Col>
            <Col span={6}>
              <div className="kpi-tile"><div className="label">参与企业数</div><div className="value">{records.summary.company_count}</div></div>
            </Col>
            <Col span={6}>
              <div className="kpi-tile"><div className="label">中标企业数</div><div className="value">{records.summary.winner_company_count}</div></div>
            </Col>
            <Col span={6}>
              <div className="kpi-tile"><div className="label">中标金额合计</div><div className="value">{formatAmount(records.summary.total_win_amount)}</div></div>
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

          <div className="app-card" style={{ marginTop: 16 }}>
            <Title level={5}>统计描述</Title>
            {renderDescription(records.description)}
          </div>

          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={12}>
              <div className="app-card">
                <Title level={5}>企业中标统计</Title>
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
                <Title level={5}>中标资金关联</Title>
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
            <Title level={5}>查询明细（前 500 行）</Title>
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
