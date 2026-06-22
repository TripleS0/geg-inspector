import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { SearchOutlined, UnorderedListOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { api, FusionEventItem } from "../../api";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

const SOURCE_LABELS: Record<string, string> = {
  bank: "银行流水",
  wechat: "微信转账",
  commercial: "商务网",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  大额转账: "red",
  特殊日子转账: "orange",
  围标: "volcano",
  串标: "magenta",
  陪标: "gold",
  特殊金额: "cyan",
  大额中标: "purple",
  重复中标: "geekblue",
};

interface FusionEventManagePanelProps {
  caseId: number;
  caseName?: string;
}

function FusionEventManagePanel({ caseId, caseName }: FusionEventManagePanelProps) {
  const [loading, setLoading] = useState(false);
  const [events, setEvents] = useState<FusionEventItem[]>([]);
  const [summary, setSummary] = useState<{ enabled_model_count: number; event_count: number; by_event_type: Record<string, number> } | null>(null);
  const [keyword, setKeyword] = useState("");
  const [eventType, setEventType] = useState<string | undefined>(undefined);
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [availableEventTypes, setAvailableEventTypes] = useState<string[]>([]);

  const runScan = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.scanFusionEvents(caseId, {
        start_date: dateRange?.[0]?.format("YYYY-MM-DD") ?? "",
        end_date: dateRange?.[1]?.format("YYYY-MM-DD") ?? "",
        keyword: keyword.trim(),
        event_type: eventType ?? "",
      });
      setEvents(data.items);
      setSummary(data.summary);
      setAvailableEventTypes(data.available_event_types ?? []);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId, dateRange, keyword, eventType]);

  useEffect(() => {
    void runScan();
  }, [runScan]);

  const columns = useMemo(
    () => [
      {
        title: "事件编号",
        dataIndex: "event_id",
        width: 96,
        render: (id: string) => <Text code>{id}</Text>,
      },
      {
        title: "事件类型",
        dataIndex: "event_type",
        width: 120,
        render: (type: string) => <Tag color={EVENT_TYPE_COLORS[type] || "default"}>{type}</Tag>,
      },
      {
        title: "关联人员",
        dataIndex: "related_person",
        width: 140,
        ellipsis: true,
      },
      {
        title: "日期",
        dataIndex: "date",
        width: 110,
        render: (date: string) => date || "—",
      },
      {
        title: "描述",
        dataIndex: "description",
        ellipsis: true,
      },
      {
        title: "来源",
        dataIndex: "source",
        width: 100,
        render: (source: string) => SOURCE_LABELS[source] || source,
      },
    ],
    []
  );

  const typeStats = summary?.by_event_type ?? {};

  return (
    <div className="fusion-event-manage">
      <Card className="app-card fusion-hub-panel" bordered={false}>
        <div className="fusion-panel-head">
          <div>
            <Title level={4} style={{ margin: 0 }}>
              <UnorderedListOutlined style={{ marginRight: 8, color: "#9a3412" }} />
              事件管理
            </Title>
            <Paragraph type="secondary" style={{ margin: "6px 0 0" }}>
              根据案件绑定的数据与已启用模型自动扫描，展示大额转账、围标、特殊日子转账等触发事件。
              {caseName ? ` 当前案件：${caseName}` : ""}
            </Paragraph>
          </div>
        </div>

        <div className="fusion-event-filters">
          <Space wrap size="middle">
            <span className="fusion-event-filter-label">日期范围</span>
            <RangePicker
              value={dateRange}
              onChange={(vals) => setDateRange(vals)}
              allowEmpty={[true, true]}
              placeholder={["起始日期", "截止日期"]}
            />
            <span className="fusion-event-filter-label">事件类型</span>
            <Select
              className="fusion-event-type-select"
              placeholder="全部类型"
              allowClear
              value={eventType}
              onChange={(value) => setEventType(value)}
              options={availableEventTypes.map((type) => ({
                value: type,
                label: type,
              }))}
              style={{ minWidth: 140 }}
            />
            <span className="fusion-event-filter-label">模糊搜索</span>
            <Input
              className="fusion-event-search"
              placeholder="搜索事件类型、人员、描述…"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onPressEnter={() => void runScan()}
              allowClear
            />
            <Button onClick={() => void runScan()} loading={loading}>
              筛选
            </Button>
          </Space>
        </div>

        {summary && (
          <Row gutter={16} className="fusion-event-stats">
            <Col xs={12} sm={6}>
              <Statistic title="触发事件" value={summary.event_count} />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic title="已启用模型" value={summary.enabled_model_count} />
            </Col>
            <Col xs={24} sm={12}>
              <div className="fusion-event-type-tags">
                <Text type="secondary" style={{ marginRight: 8 }}>类型分布</Text>
                {Object.entries(typeStats).map(([type, count]) => (
                  <Tag
                    key={type}
                    color={EVENT_TYPE_COLORS[type] || "default"}
                    className={eventType === type ? "fusion-event-type-tag-active" : "fusion-event-type-tag"}
                    style={{ cursor: "pointer" }}
                    onClick={() => setEventType(eventType === type ? undefined : type)}
                  >
                    {type} {count}
                  </Tag>
                ))}
              </div>
            </Col>
          </Row>
        )}

        {loading && events.length === 0 ? (
          <div className="fusion-panel-loading">
            <Spin tip="正在扫描案件数据并匹配模型…" />
          </div>
        ) : events.length === 0 ? (
          <Empty
            description="暂无触发事件。请确认案件已绑定数据批次，并在模型管理中启用相应模型。"
            style={{ padding: "48px 0" }}
          />
        ) : (
          <Table
            className="fusion-event-table"
            rowKey={(row) => `${row.event_id}-${row.model_key}-${row.description}`}
            columns={columns}
            dataSource={events}
            loading={loading}
            pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (t) => `共 ${t} 条事件` }}
            size="middle"
          />
        )}
      </Card>
    </div>
  );
}

export default FusionEventManagePanel;
