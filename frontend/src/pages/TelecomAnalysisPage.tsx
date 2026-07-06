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
import { DownloadOutlined, DownOutlined, UpOutlined } from "@ant-design/icons";
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

function formatDuration(seconds: number) {
  const sec = Number(seconds || 0);
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  const rest = sec % 60;
  return rest ? `${min} 分 ${rest} 秒` : `${min} 分`;
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

function TelecomAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<TelecomFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<TelecomAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

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

  const exportPeerRanking = async () => {
    if (!records?.summary.peer_ranking.length) {
      message.warning("当前没有可导出的通联排行");
      return;
    }
    try {
      const currentBatch = batches.find((item) => item.import_batch_id === batchId);
      const fileName = `${batchLabel(currentBatch || { import_batch_id: batchId })}_通联排行`;
      const blob = await api.exportRowsToExcel(
        records.summary.peer_ranking as unknown as Record<string, unknown>[],
        [
          { key: "local_phone", title: "本机号码" },
          { key: "peer_phone", title: "对方号码" },
          { key: "call_count", title: "通话次数" },
          { key: "total_duration_sec", title: "累计时长(秒)" },
          { key: "outbound_count", title: "主叫" },
          { key: "inbound_count", title: "被叫" },
          { key: "first_call_time", title: "首次通话" },
          { key: "last_call_time", title: "末次通话" },
        ],
        fileName,
        "通联排行"
      );
      downloadBlob(blob, `${fileName}.xlsx`);
      message.success("通联排行已导出");
    } catch (err) {
      message.error((err as Error).message || "导出失败");
    }
  };

  const exportRecords = async () => {
    if (!records?.records.length) {
      message.warning("当前没有可导出的话单明细");
      return;
    }
    try {
      const currentBatch = batches.find((item) => item.import_batch_id === batchId);
      const fileName = `${batchLabel(currentBatch || { import_batch_id: batchId })}_话单明细`;
      const blob = await api.exportRowsToExcel(
        records.records as unknown as Record<string, unknown>[],
        [
          { key: "call_time", title: "通话时间" },
          { key: "local_phone_display", title: "本机号码" },
          { key: "peer_phone_display", title: "对方号码" },
          { key: "direction", title: "方向" },
          { key: "call_type", title: "通话类型" },
          { key: "bill_type", title: "话单类型" },
          { key: "duration_sec", title: "时长(秒)" },
          { key: "local_carrier", title: "本机运营商" },
          { key: "peer_carrier", title: "对方运营商" },
          { key: "peer_location", title: "对方归属地" },
          { key: "local_location", title: "本机所在地" },
        ],
        fileName,
        "话单明细"
      );
      downloadBlob(blob, `${fileName}.xlsx`);
      message.success("话单明细已导出");
    } catch (err) {
      message.error((err as Error).message || "导出失败");
    }
  };

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
        <Form.Item
          label="快速筛选"
          name="quick_query"
          tooltip="多个关键词用空格隔开，会匹配本机/对方号码、主叫被叫、运营商、归属地、通话类型等字段"
        >
          <Input.Search
            allowClear
            size="large"
            placeholder="例如：13800138000 主叫 北京"
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
          </div>
        ) : null}
      </Form>

      {records && (
        <div style={{ marginTop: 20 }}>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <div className="metric-card"><div className="metric-title">话单条数</div><div className="metric-value">{records.summary.record_count}</div></div>
            </Col>
            <Col xs={24} md={8}>
              <div className="metric-card"><div className="metric-title">累计时长</div><div className="metric-value metric-primary">{formatDuration(records.summary.total_duration_sec)}</div></div>
            </Col>
            <Col xs={24} md={8}>
              <div className="metric-card"><div className="metric-title">通联对象数</div><div className="metric-value">{records.summary.peer_ranking.length}</div></div>
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
          <div className="app-card" style={{ marginTop: 16 }}>
            <div className="bank-section-head">
              <Title level={5} style={{ margin: 0 }}>通联排行</Title>
              <Button icon={<DownloadOutlined />} disabled={!records.summary.peer_ranking.length} onClick={() => void exportPeerRanking()}>
                导出Excel
              </Button>
            </div>
            <Table
              size="small"
              rowKey={(row) => `${row.local_phone}-${row.peer_phone}-${row.first_call_time}`}
              loading={loading}
              columns={peerColumns}
              dataSource={records.summary.peer_ranking}
              scroll={{ x: 900 }}
              pagination={{ pageSize: 10, showSizeChanger: true }}
            />
          </div>
          <div className="app-card" style={{ marginTop: 16 }}>
            <div className="bank-section-head">
              <Title level={5} style={{ margin: 0 }}>话单明细</Title>
              <Button icon={<DownloadOutlined />} disabled={!records.records.length} onClick={() => void exportRecords()}>
                导出Excel
              </Button>
            </div>
            <Table
              size="small"
              rowKey={(row) => `${row.call_time}-${row.local_phone_display}-${row.peer_phone_display}`}
              loading={loading}
              columns={recordColumns}
              dataSource={records.records}
              scroll={{ x: 1300 }}
              pagination={{ pageSize: 20, showSizeChanger: true }}
            />
          </div>
        </div>
      )}
    </Card>
  );
}

export default TelecomAnalysisPage;
