import { useCallback, useEffect, useMemo, useState } from "react";
import { dataManageTablesPath } from "../../pages/DataManageLayout";
import {
  Button,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import ReactECharts from "echarts-for-react";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import { useNavigate } from "react-router-dom";
import {
  api,
  FusionRecord,
  GraphSelectionDetailRequest,
  RecordDetailResponse,
} from "../../api";
import { formatFusionAmount, graphRecordTypeLabel } from "../../utils/graphRecordUtils";
import {
  bilateralFlowSlotCount,
  buildBilateralFlowChartOption,
  buildBilateralFlowItems,
  parsePartiesFromTitle,
} from "../../utils/bilateralFlowChart";
import { chartPalette } from "../../theme";
import "dayjs/locale/zh-cn";

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const RECORD_TYPE_COLORS: Record<string, string> = {
  bank_txn: "#e85d45",
  wechat: "#52c41a",
  telecom: "#1890ff",
  enterprise: "#722ed1",
  commercial: "#fa8c16",
};

const RECORD_TYPE_LABELS: Record<string, string> = {
  bank_txn: "银行流水",
  wechat: "微信转账",
  telecom: "通讯话单",
  enterprise: "工商主体",
  commercial: "商务网",
};

export interface GraphRecordDrawerExtras {
  identifiers?: Array<{ identifier_type: string; identifier_value: string; display_label: string }>;
  selection?: GraphSelectionDetailRequest;
  detailKind?: "node" | "edge";
  relationType?: string;
  partyA?: string;
  partyB?: string;
}

function filterRecordsByRange(records: FusionRecord[], range: [string, string] | null) {
  if (!range) return records;
  const [from, to] = range;
  return records.filter((rec) => {
    if (!rec.time) return false;
    const day = rec.time.slice(0, 10);
    return day >= from && day <= to;
  });
}

function buildActivityTimeline(records: FusionRecord[]) {
  const timeline: Record<string, Record<string, number>> = {};
  records.forEach((rec) => {
    const day = rec.time?.slice(0, 10);
    if (!day) return;
    if (!timeline[day]) timeline[day] = {};
    timeline[day][rec.record_type] = (timeline[day][rec.record_type] || 0) + 1;
  });
  const days = Object.keys(timeline).sort();
  const types = ["bank_txn", "wechat", "telecom", "enterprise", "commercial"];
  return {
    days,
    series: types.map((type) => ({
      name: type,
      data: days.map((day) => timeline[day][type] || 0),
    })),
  };
}

function buildFundPie(records: FusionRecord[]) {
  const fund = { bank_in: 0, bank_out: 0, wechat_in: 0, wechat_out: 0 };
  records.forEach((rec) => {
    if (rec.record_type === "bank_txn" && rec.amount != null) {
      if (rec.direction?.includes("收")) fund.bank_in += rec.amount;
      else if (rec.direction?.includes("支")) fund.bank_out += rec.amount;
      else fund.bank_out += Math.abs(rec.amount);
    }
    if (rec.record_type === "wechat" && rec.amount != null) {
      if (rec.direction === "入") fund.wechat_in += rec.amount;
      else if (rec.direction === "出") fund.wechat_out += rec.amount;
      else fund.wechat_out += Math.abs(rec.amount);
    }
  });
  return [
    { name: "银行收入", value: Math.round(fund.bank_in * 100) / 100 },
    { name: "银行支出", value: Math.round(fund.bank_out * 100) / 100 },
    { name: "微信收入", value: Math.round(fund.wechat_in * 100) / 100 },
    { name: "微信支出", value: Math.round(fund.wechat_out * 100) / 100 },
  ].filter((item) => item.value > 0);
}

function buildTelecomHourly(records: FusionRecord[]) {
  const counts = Array.from({ length: 24 }, (_, hour) => ({ hour, count: 0 }));
  records
    .filter((rec) => rec.record_type === "telecom")
    .forEach((rec) => {
      const match = rec.time?.match(/(?:T|\s)(\d{1,2}):/);
      const hour = match ? Number(match[1]) : Number.NaN;
      if (Number.isInteger(hour) && hour >= 0 && hour <= 23) counts[hour].count += 1;
    });
  return counts;
}

function buildEdgeChannelSummary(records: FusionRecord[]) {
  const summary = { bank_amount: 0, wechat_amount: 0, telecom_count: 0 };
  records.forEach((rec) => {
    if (rec.record_type === "bank_txn") summary.bank_amount += Math.abs(rec.amount || 0);
    if (rec.record_type === "wechat") summary.wechat_amount += Math.abs(rec.amount || 0);
    if (rec.record_type === "telecom") summary.telecom_count += 1;
  });
  return summary;
}

type EdgeStatItem = {
  key: string;
  title: string;
  value: number;
  prefix?: string;
  suffix?: string;
  precision?: number;
};

function edgeStatsForRelation(relationType: string | undefined, summary: ReturnType<typeof buildEdgeChannelSummary>): EdgeStatItem[] {
  const all: EdgeStatItem[] = [
    { key: "bank_txn", title: "银行往来", value: summary.bank_amount, prefix: "¥", precision: 2 },
    { key: "wechat", title: "微信往来", value: summary.wechat_amount, prefix: "¥", precision: 2 },
    { key: "telecom", title: "通讯次数", value: summary.telecom_count, suffix: "次" },
  ];
  if (relationType) {
    return all.filter((item) => item.key === relationType);
  }
  return all.filter((item) => {
    if (item.key === "telecom") return summary.telecom_count > 0;
    if (item.key === "bank_txn") return summary.bank_amount > 0;
    if (item.key === "wechat") return summary.wechat_amount > 0;
    return false;
  });
}

export function useFusionRecordDrawers(caseId: number | null) {
  const navigate = useNavigate();
  const [listOpen, setListOpen] = useState(false);
  const [listTitle, setListTitle] = useState("");
  const [listMeta, setListMeta] = useState<Record<string, string>>({});
  const [listRecords, setListRecords] = useState<FusionRecord[]>([]);
  const [detailKind, setDetailKind] = useState<"node" | "edge">("node");
  const [relationType, setRelationType] = useState<string | undefined>();
  const [partyA, setPartyA] = useState("");
  const [partyB, setPartyB] = useState("");
  const [activeTab, setActiveTab] = useState("records");
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRecord, setDetailRecord] = useState<FusionRecord | null>(null);
  const [rawDetail, setRawDetail] = useState<RecordDetailResponse | null>(null);
  const [rawLoading, setRawLoading] = useState(false);

  const openRecords = useCallback(
    (
      title: string,
      records: FusionRecord[],
      meta: Record<string, string> = {},
      extras: GraphRecordDrawerExtras = {}
    ) => {
      setListTitle(title);
      setListMeta(meta);
      setListRecords(records);
      setDetailKind(extras.detailKind || "node");
      setRelationType(extras.relationType);
      const parsed = parsePartiesFromTitle(title);
      setPartyA(extras.partyA || parsed?.partyA || "");
      setPartyB(extras.partyB || parsed?.partyB || "");
      setActiveTab("records");
      setDateRange(null);
      setListOpen(true);
    },
    []
  );

  const openDetail = useCallback((record: FusionRecord) => {
    setDetailRecord(record);
    setRawDetail(null);
    setDetailOpen(true);
  }, []);

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

  const gotoRawTable = useCallback(() => {
    if (!rawDetail) return;
    const pk = rawDetail.pk as { raw_id?: number };
    if (rawDetail.layer === "raw" && pk.raw_id) {
      navigate(dataManageTablesPath({ table: rawDetail.table, highlight: pk.raw_id }));
    } else {
      navigate(dataManageTablesPath({ table: rawDetail.table }));
    }
  }, [navigate, rawDetail]);

  const filteredRecords = useMemo(
    () => filterRecordsByRange(listRecords, dateRange),
    [dateRange, listRecords]
  );

  const chartBase = useMemo(
    () => ({
      textStyle: { fontFamily: "inherit" },
      grid: { left: 48, right: 20, top: 48, bottom: 32 },
    }),
    []
  );

  const activityTimelineOption = useMemo(() => {
    const chart = buildActivityTimeline(filteredRecords);
    if (!chart.days.length) return null;
    return {
      ...chartBase,
      color: chartPalette,
      tooltip: { trigger: "axis" },
      legend: { top: 8, icon: "roundRect" },
      xAxis: { type: "category", data: chart.days },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { type: "dashed", color: "#f0f0f0" } } },
      series: chart.series.map((s) => ({
        name: RECORD_TYPE_LABELS[s.name] || s.name,
        type: "bar",
        stack: "total",
        barMaxWidth: 28,
        data: s.data,
      })),
    };
  }, [chartBase, filteredRecords]);

  const fundPieOption = useMemo(() => {
    const data = buildFundPie(filteredRecords);
    if (!data.length) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "item", formatter: "{b}: ¥{c} ({d}%)" },
      legend: { bottom: 0, icon: "circle" },
      series: [
        {
          type: "pie",
          radius: ["42%", "68%"],
          center: ["50%", "46%"],
          data,
        },
      ],
    };
  }, [filteredRecords]);

  const telecomHourOption = useMemo(() => {
    const counts = buildTelecomHourly(filteredRecords);
    if (!counts.some((item) => item.count > 0)) return null;
    return {
      ...chartBase,
      color: ["#1890ff"],
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: counts.map((d) => `${d.hour}时`) },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { type: "dashed", color: "#f0f0f0" } } },
      series: [{ type: "bar", data: counts.map((d) => d.count), barMaxWidth: 28 }],
    };
  }, [chartBase, filteredRecords]);

  const edgeSummary = useMemo(() => buildEdgeChannelSummary(filteredRecords), [filteredRecords]);
  const edgeStatsItems = useMemo(
    () => (detailKind === "edge" ? edgeStatsForRelation(relationType, edgeSummary) : []),
    [detailKind, edgeSummary, relationType]
  );

  const bilateralFlowOption = useMemo(() => {
    if (detailKind !== "edge" || !partyA || !partyB) return null;
    const items = buildBilateralFlowItems(filteredRecords, partyA, partyB);
    return buildBilateralFlowChartOption(items, partyA, partyB);
  }, [detailKind, filteredRecords, partyA, partyB]);

  const bilateralFlowHeight = useMemo(() => {
    if (detailKind !== "edge" || !partyA || !partyB) return 360;
    const items = buildBilateralFlowItems(filteredRecords, partyA, partyB);
    const slotCount = bilateralFlowSlotCount(items);
    if (!slotCount) return 360;
    return Math.min(780, Math.max(380, slotCount * 58 + 140));
  }, [detailKind, filteredRecords, partyA, partyB]);

  const recordColumns = useMemo(
    () => [
      {
        title: "类型",
        dataIndex: "record_type",
        width: 96,
        render: (v: string) => (
          <Tag color={RECORD_TYPE_COLORS[v] || "default"}>{graphRecordTypeLabel(v)}</Tag>
        ),
      },
      { title: "时间", dataIndex: "time", width: 158, render: (v: string | null) => v || "—" },
      { title: "摘要", dataIndex: "summary", ellipsis: true },
      { title: "对手/关联", dataIndex: "counterparty", ellipsis: true, width: 140 },
      {
        title: "金额/时长",
        dataIndex: "amount",
        width: 110,
        render: (v: number | null, row: FusionRecord) =>
          row.record_type === "telecom" ? `${v ?? 0} 秒` : formatFusionAmount(v),
      },
    ],
    []
  );

  const statsContent = (
    <div className="graph-drawer-stats">
      <Space wrap style={{ marginBottom: 16 }}>
        <Text type="secondary">统计时间段</Text>
        <RangePicker
          locale={zhCN}
          allowClear
          onChange={(values) => {
            if (!values?.[0] || !values[1]) {
              setDateRange(null);
              return;
            }
            setDateRange([values[0].format("YYYY-MM-DD"), values[1].format("YYYY-MM-DD")]);
          }}
        />
        <Text type="secondary">共 {filteredRecords.length} 条记录</Text>
      </Space>

      {edgeStatsItems.length > 0 ? (
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {edgeStatsItems.map((item) => (
            <Col key={item.key} span={edgeStatsItems.length === 1 ? 24 : 8}>
              <Statistic
                title={item.title}
                value={item.value}
                precision={item.precision}
                prefix={item.prefix}
                suffix={item.suffix}
              />
            </Col>
          ))}
        </Row>
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          {detailKind === "edge" ? (
            bilateralFlowOption ? (
              <>
                <Title level={5}>双方往来</Title>
                <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
                  左侧 {partyA} · 右侧 {partyB} · 箭头表示方向，线宽反映金额或通话时长，空白时段已压缩
                </Text>
                <ReactECharts
                  className="graph-bilateral-chart"
                  option={bilateralFlowOption}
                  style={{ height: bilateralFlowHeight }}
                  notMerge
                  lazyUpdate
                />
              </>
            ) : (
              <Text type="secondary">当前时间段内暂无双方往来记录</Text>
            )
          ) : activityTimelineOption ? (
            <>
              <Title level={5}>活动分布（银行 / 微信转账 / 通讯）</Title>
              <ReactECharts option={activityTimelineOption} style={{ height: 320 }} notMerge lazyUpdate />
            </>
          ) : (
            <Text type="secondary">当前时间段内暂无活动记录</Text>
          )}
        </Col>
        {detailKind === "node" && fundPieOption ? (
          <Col xs={24} lg={10}>
            <Title level={5}>资金方向</Title>
            <ReactECharts option={fundPieOption} style={{ height: 320 }} notMerge lazyUpdate />
          </Col>
        ) : null}
        {detailKind === "node" && telecomHourOption ? (
          <Col xs={24}>
            <Title level={5}>通讯时段分布</Title>
            <ReactECharts option={telecomHourOption} style={{ height: 280 }} notMerge lazyUpdate />
          </Col>
        ) : null}
      </Row>
    </div>
  );

  const drawers = (
    <>
      <Drawer
        title={listTitle || "详情数据"}
        width={760}
        placement="right"
        open={listOpen}
        onClose={() => setListOpen(false)}
      >
        {Object.keys(listMeta).length > 0 && (
          <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
            {Object.entries(listMeta).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {v}
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: "records",
              label: "明细数据",
              children: (
                <Table
                  rowKey={(_, idx) => `graph-record-${idx}`}
                  size="small"
                  columns={recordColumns}
                  dataSource={filteredRecords}
                  onRow={(row) => ({ onClick: () => openDetail(row), className: "cockpit-record-row" })}
                  pagination={{ pageSize: 8, showTotal: (t) => `共 ${t} 条` }}
                  locale={{ emptyText: "暂无可展示的明细记录" }}
                />
              ),
            },
            {
              key: "stats",
              label: "图表统计",
              children: statsContent,
            },
          ]}
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
                  {graphRecordTypeLabel(detailRecord.record_type)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="标题">{detailRecord.title}</Descriptions.Item>
              <Descriptions.Item label="时间">{detailRecord.time || "—"}</Descriptions.Item>
              <Descriptions.Item label="金额/时长">
                {detailRecord.record_type === "telecom"
                  ? `${detailRecord.amount ?? 0} 秒`
                  : formatFusionAmount(detailRecord.amount)}
              </Descriptions.Item>
              <Descriptions.Item label="对手/关联">{detailRecord.counterparty || "—"}</Descriptions.Item>
              <Descriptions.Item label="摘要">{detailRecord.summary || "—"}</Descriptions.Item>
            </Descriptions>
            {rawDetail && (
              <>
                <Title level={5} style={{ marginTop: 16 }}>
                  原始字段
                </Title>
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
    </>
  );

  return { openRecords, drawers };
}
