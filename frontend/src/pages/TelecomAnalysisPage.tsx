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
import { api, BatchInfo, batchLabel, TelecomAnalysisFilter, TelecomAnalysisResponse } from "../api";
import { chartPair, chartPalette } from "../theme";
import { AnalysisDateTimeFilterFields, AnalysisDateTimeFormFields, serializeAnalysisDateTimeFilters } from "../components/AnalysisDateTimeFilters";

type TelecomFilterForm = TelecomAnalysisFilter & AnalysisDateTimeFormFields;

const { Title, Paragraph } = Typography;

const DIRECTION_LABELS: Record<string, string> = {
  outbound: "主叫",
  inbound: "被叫",
  sms: "短信",
  unknown: "其他",
};

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

function formatDuration(seconds: number) {
  const sec = Number(seconds || 0);
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  const rest = sec % 60;
  return rest ? `${min} 分 ${rest} 秒` : `${min} 分`;
}

function TelecomAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<TelecomFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<TelecomAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.listBatches("telecom");
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
    void api.telecomAnalysisFilterOptions(batchId).then(setFilterOptions).catch(() => setFilterOptions({}));
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runQuery = async () => {
    if (!batchId) return;
    setLoading(true);
    try {
      const values = await filter.validateFields();
      const data = await api.telecomAnalysisRecords(batchId, serializeAnalysisDateTimeFilters(values));
      setRecords(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const directionOption = useMemo(() => {
    if (!records) return null;
    const counts = records.summary.direction_counts || {};
    const data = Object.entries(counts)
      .filter(([, value]) => Number(value) > 0)
      .map(([key, value]) => ({ name: DIRECTION_LABELS[key] || key, value }));
    if (!data.length) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [{ type: "pie", radius: ["45%", "70%"], data }],
    };
  }, [records]);

  const peerOption = useMemo(() => {
    const top = records?.summary.peer_ranking || [];
    if (!top.length) return null;
    const slice = top.slice(0, 10);
    return {
      color: chartPalette,
      tooltip: { trigger: "axis" },
      grid: { top: 12, left: 12, right: 36, bottom: 28, containLabel: true },
      xAxis: { type: "value" },
      yAxis: {
        type: "category",
        data: slice.map((item) => item.peer_phone).reverse(),
        axisLabel: { width: 120, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          data: slice.map((item) => item.call_count).reverse(),
          itemStyle: { color: chartPair.primary, borderRadius: [0, 6, 6, 0] },
        },
      ],
    };
  }, [records]);

  const hourlyOption = useMemo(() => {
    const hourly = records?.summary.hourly_distribution || [];
    if (!hourly.length) return null;
    return {
      color: [chartPair.secondary],
      tooltip: { trigger: "axis" },
      grid: { top: 12, left: 12, right: 12, bottom: 28, containLabel: true },
      xAxis: {
        type: "category",
        data: hourly.map((item) => `${item.hour}时`),
      },
      yAxis: { type: "value" },
      series: [{ type: "bar", data: hourly.map((item) => item.count), itemStyle: { borderRadius: [4, 4, 0, 0] } }],
    };
  }, [records]);

  const dailyOption = useMemo(() => {
    const daily = records?.summary.daily_distribution || [];
    if (!daily.length) return null;
    return {
      color: [chartPair.primary],
      tooltip: { trigger: "axis" },
      grid: { top: 12, left: 12, right: 12, bottom: 28, containLabel: true },
      xAxis: { type: "category", data: daily.map((item) => item.date) },
      yAxis: { type: "value" },
      series: [{ type: "line", smooth: true, data: daily.map((item) => item.count) }],
    };
  }, [records]);

  const peerColumns = useMemo(
    () => [
      { title: "本机号码", dataIndex: "local_phone", width: 130, ellipsis: true },
      { title: "对方号码", dataIndex: "peer_phone", width: 130, ellipsis: true },
      { title: "通话次数", dataIndex: "call_count", width: 90 },
      {
        title: "累计时长",
        dataIndex: "total_duration_sec",
        width: 110,
        render: (v: number) => formatDuration(v),
      },
      { title: "主叫", dataIndex: "outbound_count", width: 70 },
      { title: "被叫", dataIndex: "inbound_count", width: 70 },
      { title: "首次通话", dataIndex: "first_call_time", width: 170, ellipsis: true },
      { title: "末次通话", dataIndex: "last_call_time", width: 170, ellipsis: true },
    ],
    []
  );

  const recordColumns = useMemo(
    () => [
      { title: "通话时间", dataIndex: "call_time", width: 170, ellipsis: true },
      { title: "本机号码", dataIndex: "local_phone_display", width: 130, ellipsis: true },
      { title: "对方号码", dataIndex: "peer_phone_display", width: 130, ellipsis: true },
      {
        title: "方向",
        dataIndex: "direction",
        width: 80,
        render: (v: string) => {
          const color = v === "outbound" ? "blue" : v === "inbound" ? "green" : "default";
          return <Tag color={color}>{DIRECTION_LABELS[v] || v || "-"}</Tag>;
        },
      },
      { title: "通话类型", dataIndex: "call_type", width: 120, ellipsis: true },
      { title: "话单类型", dataIndex: "bill_type", width: 90, ellipsis: true },
      {
        title: "时长",
        dataIndex: "duration_sec",
        width: 90,
        render: (v: number) => formatDuration(v),
      },
      { title: "本机运营商", dataIndex: "local_carrier", width: 100, ellipsis: true },
      { title: "对方运营商", dataIndex: "peer_carrier", width: 100, ellipsis: true },
      { title: "对方归属地", dataIndex: "peer_location", width: 90, ellipsis: true },
      { title: "本机所在地", dataIndex: "local_location", width: 90, ellipsis: true },
    ],
    []
  );

  return (
    <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>通讯话单分析</Title>
        <Space>
          <span>话单批次：</span>
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
        支持按本机/对方号码、时间、通话类型筛选，统计通联频次、累计时长与时段分布。
      </Paragraph>

      <Form layout="vertical" form={filter}>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item label="本机号码" name="local_phone">
              <Input placeholder="支持模糊匹配" allowClear />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="对方号码" name="peer_phone">
              <Input placeholder="支持模糊匹配" allowClear />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="通话类型" name="call_type">
              <Select allowClear showSearch placeholder="全部" options={(filterOptions.call_type || []).map((v) => ({ value: v, label: v }))} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="话单类型" name="bill_type">
              <Select allowClear showSearch placeholder="全部" options={(filterOptions.bill_type || []).map((v) => ({ value: v, label: v }))} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="方向" name="direction">
              <Select
                allowClear
                placeholder="全部"
                options={[
                  { value: "outbound", label: "主叫" },
                  { value: "inbound", label: "被叫" },
                  { value: "sms", label: "短信" },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="对方归属地" name="peer_location">
              <Select allowClear showSearch placeholder="全部" options={(filterOptions.peer_location || []).map((v) => ({ value: v, label: v }))} />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item label="时长下限(秒)" name="duration_min">
              <InputNumber style={{ width: "100%" }} min={0} />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item label="时长上限(秒)" name="duration_max">
              <InputNumber style={{ width: "100%" }} min={0} />
            </Form.Item>
          </Col>
          <AnalysisDateTimeFilterFields dateCol={{ xs: 24, md: 6 }} timeCol={{ xs: 24, md: 6 }} />
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
              <Card size="small" title="话单条数">
                <div style={{ fontSize: 22, fontWeight: 600 }}>{records.summary.record_count}</div>
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small" title="累计时长">
                <div style={{ fontSize: 22, fontWeight: 600, color: chartPair.primary }}>
                  {formatDuration(records.summary.total_duration_sec)}
                </div>
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small" title="通联对象数">
                <div style={{ fontSize: 22, fontWeight: 600 }}>
                  {records.summary.peer_ranking.length}
                </div>
              </Card>
            </Col>
          </Row>
          <Row gutter={16} style={{ marginTop: 16 }}>
            {directionOption && (
              <Col xs={24} md={8}>
                <Card size="small" title="主被叫占比">
                  <ReactECharts option={directionOption} style={{ height: 280 }} />
                </Card>
              </Col>
            )}
            {peerOption && (
              <Col xs={24} md={8}>
                <Card size="small" title="通联频次 Top 10">
                  <ReactECharts option={peerOption} style={{ height: 280 }} />
                </Card>
              </Col>
            )}
            {hourlyOption && (
              <Col xs={24} md={8}>
                <Card size="small" title="按小时分布">
                  <ReactECharts option={hourlyOption} style={{ height: 280 }} />
                </Card>
              </Col>
            )}
          </Row>
          {dailyOption && (
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col xs={24}>
                <Card size="small" title="按日期分布">
                  <ReactECharts option={dailyOption} style={{ height: 280 }} />
                </Card>
              </Col>
            </Row>
          )}
          <Table
            style={{ marginTop: 16 }}
            size="small"
            rowKey={(row) => `${row.local_phone}-${row.peer_phone}-${row.first_call_time}`}
            loading={loading}
            columns={peerColumns}
            dataSource={records.summary.peer_ranking}
            scroll={{ x: 900 }}
            pagination={{ pageSize: 10, showSizeChanger: true }}
            title={() => "通联排行"}
          />
          <Table
            style={{ marginTop: 16 }}
            size="small"
            rowKey={(row) => `${row.call_time}-${row.local_phone_display}-${row.peer_phone_display}`}
            loading={loading}
            columns={recordColumns}
            dataSource={records.records}
            scroll={{ x: 1300 }}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            title={() => "话单明细"}
          />
        </div>
      )}
    </Card>
  );
}

export default TelecomAnalysisPage;
