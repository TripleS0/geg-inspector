import { useEffect, useMemo, useState } from "react";
import { Button, Card, Col, Form, InputNumber, Row, Select, Space, Table, Tabs, Tag, Typography, message } from "antd";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import { api, BankFilter, BankRecordsResponse, BatchInfo, batchLabel, ModuleParams } from "../api";
import { chartPair, chartPalette } from "../theme";
import { AnalysisDateTimeFilterFields, AnalysisDateTimeFormFields, serializeAnalysisDateTimeFilters } from "../components/AnalysisDateTimeFilters";

type BankFilterForm = BankFilter & AnalysisDateTimeFormFields;

const { Title, Paragraph } = Typography;

const MODULES: Array<{ id: string; name: string; desc: string }> = [
  { id: "large_inout", name: "大额进出", desc: "按阈值挑出大额收支记录" },
  { id: "large_flow", name: "大额资金流向", desc: "按交易对手统计大额流向排名" },
  { id: "special_amount", name: "特殊金额", desc: "敏感金额、整数金额、重复金额" },
  { id: "special_time", name: "特殊时间", desc: "深夜、凌晨、节假日交易" },
];

function renderDescription(text: string) {
  const paragraphs = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (paragraphs.length === 0) {
    return <Paragraph className="analysis-empty">暂无描述</Paragraph>;
  }

  return (
    <div className="analysis-description">
      {paragraphs.map((line, index) => (
        <Paragraph key={`${index}-${line}`} className="analysis-description-line">
          {line}
        </Paragraph>
      ))}
    </div>
  );
}

function BankAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<BankFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<BankRecordsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [moduleParams] = Form.useForm<ModuleParams>();
  const [moduleResult, setModuleResult] = useState<Record<string, unknown> | null>(null);
  const [moduleLoading, setModuleLoading] = useState(false);
  const [activeModule, setActiveModule] = useState<string>(MODULES[0].id);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.listBatches("bank");
        setBatches(data.items);
        const param = searchParams.get("batch") || "";
        const next = param || data.items[0]?.import_batch_id || "";
        setBatchId(next);
      } catch (err) {
        message.error((err as Error).message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!batchId) return;
    setSearchParams({ batch: batchId });
    void api.bankFilterOptions(batchId).then(setFilterOptions).catch(() => setFilterOptions({}));
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runQuery = async () => {
    if (!batchId) return;
    setLoading(true);
    try {
      const values = await filter.validateFields();
      const data = await api.bankRecords(batchId, serializeAnalysisDateTimeFilters(values));
      setRecords(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const runModule = async (moduleId: string) => {
    if (!batchId) return;
    setActiveModule(moduleId);
    setModuleLoading(true);
    try {
      const params = await moduleParams.validateFields().catch(() => ({}));
      const data = await api.bankModule(batchId, moduleId, params as ModuleParams);
      setModuleResult(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setModuleLoading(false);
    }
  };

  const directionOption = useMemo(() => {
    if (!records) return null;
    const summary = records.summary as Record<string, number>;
    const inTotal = Number(summary.in_total || 0);
    const outTotal = Number(summary.out_total || 0);
    return {
      color: [chartPair.primary, chartPair.secondary],
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          data: [
            { name: "收入", value: inTotal },
            { name: "支出", value: outTotal },
          ],
        },
      ],
    };
  }, [records]);

  const topCounterpartyOption = useMemo(() => {
    if (!records) return null;
    const top = (records.summary?.top_counterparties as Array<[string, number]>) || [];
    if (top.length === 0) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "axis" },
      grid: { top: 12, left: 12, right: 36, bottom: 28, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: {
          hideOverlap: true,
          formatter: (v: number) => {
            if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}亿`;
            if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
            return String(v);
          },
        },
      },
      yAxis: { type: "category", data: top.map(([name]) => name).reverse(), axisLabel: { width: 100, overflow: "truncate" } },
      series: [
        {
          type: "bar",
          data: top.map(([, val]) => val).reverse(),
          itemStyle: {
            color: chartPair.primary,
            borderRadius: [0, 6, 6, 0],
          },
        },
      ],
    };
  }, [records]);

  const recordColumns = useMemo(() => {
    const keys = [
      ["txn_time", "时间"],
      ["bank_type", "银行"],
      ["person_name", "姓名"],
      ["acct_no", "账号/卡号"],
      ["txn_direction", "方向"],
      ["amount", "金额"],
      ["balance", "余额"],
      ["counterparty_name", "对手"],
      ["counterparty_account", "对手账号"],
      ["txn_desc", "摘要"],
      ["remark", "备注"],
    ];
    return keys.map(([dataIndex, title]) => ({
      title,
      dataIndex,
      key: dataIndex,
      ellipsis: true,
    }));
  }, []);

  const moduleHits = (moduleResult?.hit_records as Array<Record<string, string>>) || [];

  return (
    <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>银行流水分析</Title>
        <Space>
          <span>批次：</span>
          <Select
            style={{ minWidth: 320 }}
            value={batchId}
            onChange={(val) => setBatchId(val)}
            options={batches.map((b) => ({
              value: b.import_batch_id,
              label: `${batchLabel(b)} (${b.file_count} 文件 · ${b.imported_at})`,
            }))}
          />
        </Space>
      </div>
      <Tabs
        defaultActiveKey="custom"
        items={[
          {
            key: "custom",
            label: "自定义筛选",
            children: (
              <div>
                <Form layout="vertical" form={filter}>
                  <Row gutter={12}>
                    <Col span={6}>
                      <Form.Item name="bank_type" label="银行">
                        <Select allowClear options={(filterOptions.bank_type || []).map((v) => ({ value: v, label: v }))} />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item name="person_name" label="姓名">
                        <Select allowClear showSearch options={(filterOptions.person_name || []).map((v) => ({ value: v, label: v }))} />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item name="acct_no" label="卡号">
                        <Select allowClear showSearch options={(filterOptions.acct_no || []).map((v) => ({ value: v, label: v }))} />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item name="counterparty_name" label="对手姓名">
                        <Select allowClear showSearch options={(filterOptions.counterparty_name || []).map((v) => ({ value: v, label: v }))} />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item name="amount_min" label="金额下限">
                        <InputNumber style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item name="amount_max" label="金额上限">
                        <InputNumber style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <AnalysisDateTimeFilterFields dateCol={{ span: 6 }} timeCol={{ span: 6 }} />
                  </Row>
                  <Space>
                    <Button type="primary" loading={loading} onClick={runQuery}>查询并生成描述</Button>
                    <Button onClick={() => filter.resetFields()}>重置</Button>
                  </Space>
                </Form>
                {records && (
                  <>
                    <Row gutter={16} style={{ marginTop: 16 }}>
                      <Col span={6}>
                        <div className="kpi-tile"><div className="label">交易笔数</div><div className="value">{Number(records.summary.txn_count || 0)}</div></div>
                      </Col>
                      <Col span={6}>
                        <div className="kpi-tile"><div className="label">收入总额</div><div className="value">{Number(records.summary.in_total || 0).toFixed(2)}</div></div>
                      </Col>
                      <Col span={6}>
                        <div className="kpi-tile"><div className="label">支出总额</div><div className="value">{Number(records.summary.out_total || 0).toFixed(2)}</div></div>
                      </Col>
                      <Col span={6}>
                        <div className="kpi-tile"><div className="label">净额</div><div className="value">{Number(records.summary.net_amount || 0).toFixed(2)}</div></div>
                      </Col>
                    </Row>
                    <Row gutter={16} style={{ marginTop: 16 }}>
                      <Col span={10}>
                        <div className="app-card">
                          <Title level={5}>收支分布</Title>
                          {directionOption && <ReactECharts option={directionOption} style={{ height: 240 }} />}
                        </div>
                      </Col>
                      <Col span={14}>
                        <div className="app-card">
                          <Title level={5}>交易对手排名（按总流量）</Title>
                          {topCounterpartyOption ? (
                            <ReactECharts option={topCounterpartyOption} style={{ height: 240 }} />
                          ) : (
                            <Paragraph style={{ color: "#5b6477", margin: 0 }}>暂无数据</Paragraph>
                          )}
                        </div>
                      </Col>
                    </Row>
                    <div className="app-card" style={{ marginTop: 16 }}>
                      <Title level={5}>分析描述</Title>
                      {renderDescription(records.description)}
                    </div>
                    <div className="app-card" style={{ marginTop: 16 }}>
                      <Title level={5}>命中记录（前 200 行）</Title>
                      <Table
                        rowKey={(r) => `${r.txn_time}-${r.acct_no}-${r.amount}-${r.counterparty_account}`}
                        size="small"
                        scroll={{ x: "max-content" }}
                        columns={recordColumns}
                        dataSource={records.records.slice(0, 200)}
                        pagination={{ pageSize: 30 }}
                      />
                    </div>
                  </>
                )}
              </div>
            ),
          },
          {
            key: "module",
            label: "固定分析模块",
            children: (
              <div>
                <Form
                  layout="inline"
                  form={moduleParams}
                  initialValues={{ large_amount_threshold: 100000, top_n: 15, repeat_amount_min_count: 3 }}
                >
                  <Form.Item name="large_amount_threshold" label="大额阈值">
                    <InputNumber min={0} step={10000} />
                  </Form.Item>
                  <Form.Item name="top_n" label="排名数量">
                    <InputNumber min={1} max={500} />
                  </Form.Item>
                  <Form.Item name="repeat_amount_min_count" label="重复金额下限">
                    <InputNumber min={2} max={50} />
                  </Form.Item>
                </Form>
                <Space style={{ marginTop: 12 }}>
                  {MODULES.map((m) => (
                    <Button
                      key={m.id}
                      type={activeModule === m.id ? "primary" : "default"}
                      loading={moduleLoading && activeModule === m.id}
                      onClick={() => runModule(m.id)}
                    >
                      {m.name}
                    </Button>
                  ))}
                </Space>
                {moduleResult && (
                  <>
                    <div className="app-card" style={{ marginTop: 16 }}>
                      <Title level={5}>
                        {MODULES.find((m) => m.id === activeModule)?.name}
                        <Tag style={{ marginLeft: 8 }}>{moduleHits.length} 条命中</Tag>
                      </Title>
                      {renderDescription(String(moduleResult.description || ""))}
                    </div>
                    <div className="app-card" style={{ marginTop: 16 }}>
                      <Title level={5}>命中明细（前 200 行）</Title>
                      <Table
                        size="small"
                        rowKey={(r, idx) => `${idx}`}
                        scroll={{ x: "max-content" }}
                        columns={recordColumns}
                        dataSource={moduleHits.slice(0, 200)}
                        pagination={{ pageSize: 30 }}
                      />
                    </div>
                  </>
                )}
              </div>
            ),
          },
        ]}
      />
    </Card>
  );
}

export default BankAnalysisPage;
