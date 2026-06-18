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
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import { api, BatchInfo, batchLabel, WechatAnalysisFilter, WechatAnalysisResponse } from "../api";
import { chartPair, chartPalette } from "../theme";
import { AnalysisDateTimeFilterFields, AnalysisDateTimeFormFields, serializeAnalysisDateTimeFilters } from "../components/AnalysisDateTimeFilters";

type WechatFilterForm = WechatAnalysisFilter & AnalysisDateTimeFormFields;

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

function WechatAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<WechatFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<WechatAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);

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
      { title: "交易时间", dataIndex: "txn_time", width: 170, ellipsis: true },
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
      { title: "金额(元)", dataIndex: "amount_yuan", width: 110, render: formatAmount },
      { title: "余额(元)", dataIndex: "balance_yuan", width: 110, render: formatAmount },
      { title: "对手", dataIndex: "counterparty_name", width: 140, ellipsis: true },
      { title: "对手银行", dataIndex: "counterparty_bank_name", width: 120, ellipsis: true },
      { title: "备注1", dataIndex: "remark1", width: 120, ellipsis: true },
      { title: "备注2", dataIndex: "remark2", width: 120, ellipsis: true },
      { title: "交易单号", dataIndex: "txn_no", width: 180, ellipsis: true },
    ],
    [records]
  );

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
        <Space>
          <Button type="primary" loading={loading} onClick={() => void runQuery()}>查询</Button>
          <Button onClick={() => filter.resetFields()}>重置</Button>
        </Space>
      </Form>

      {records && (
        <div style={{ marginTop: 20 }}>
          {renderDescription(records.description)}
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col xs={24} md={8}>
              <Card size="small" title="收入合计(元)">
                <div style={{ fontSize: 22, fontWeight: 600, color: chartPair.primary }}>
                  {formatAmount(records.summary.in_total)}
                </div>
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small" title="支出合计(元)">
                <div style={{ fontSize: 22, fontWeight: 600, color: chartPair.secondary }}>
                  {formatAmount(records.summary.out_total)}
                </div>
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small" title="净流入(元)">
                <div style={{ fontSize: 22, fontWeight: 600 }}>
                  {formatAmount(records.summary.net_total)}
                </div>
              </Card>
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
          <Table
            style={{ marginTop: 16 }}
            size="small"
            rowKey={(row) => `${row.txn_no}-${row.txn_time}`}
            loading={loading}
            columns={recordColumns}
            dataSource={records.records}
            scroll={{ x: 1400 }}
            pagination={{ pageSize: 20, showSizeChanger: true }}
          />
        </div>
      )}
    </Card>
  );
}

export default WechatAnalysisPage;
