import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Avatar,
  Card,
  Col,
  Empty,
  Row,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from "antd";
import {
  AppstoreOutlined,
  DatabaseOutlined,
  ProjectOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import {
  api,
  CASE_CHANGED_EVENT,
  CASE_STORAGE_KEY,
  DataCenterDashboardResponse,
} from "../api";
import { chartPalette } from "../theme";

const { Paragraph, Text } = Typography;

function DataDashboardPage() {
  const [dashboard, setDashboard] = useState<DataCenterDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(
    () => Number(localStorage.getItem(CASE_STORAGE_KEY)) || null
  );

  const fetchDashboard = useCallback(async (caseId?: number | null) => {
    setLoading(true);
    try {
      const data = await api.getDataCenterDashboard(caseId ?? undefined);
      setDashboard(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchDashboard(selectedCaseId);
  }, [fetchDashboard, selectedCaseId]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId ?? null;
      setSelectedCaseId(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, []);

  const timelineOption = useMemo(() => {
    if (!dashboard?.timeline.months.length) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "axis" as const },
      legend: { bottom: 0, type: "scroll" as const },
      grid: { left: 48, right: 24, top: 36, bottom: 48 },
      xAxis: {
        type: "category" as const,
        data: dashboard.timeline.months,
        axisLabel: { rotate: dashboard.timeline.months.length > 8 ? 30 : 0 },
      },
      yAxis: { type: "value" as const, name: "数据条数" },
      series: dashboard.timeline.series.map((item) => ({
        name: item.label,
        type: "line" as const,
        smooth: true,
        data: item.data,
      })),
    };
  }, [dashboard]);

  const sourcePieOption = useMemo(() => {
    if (!dashboard?.source_distribution.length) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "item" as const },
      legend: { bottom: 0, type: "scroll" as const },
      series: [
        {
          type: "pie" as const,
          radius: ["38%", "68%"],
          center: ["50%", "44%"],
          data: dashboard.source_distribution.map((item) => ({
            name: item.label,
            value: item.count,
          })),
          label: { formatter: "{b}\n{d}%" },
        },
      ],
    };
  }, [dashboard]);

  const batchBarOption = useMemo(() => {
    if (!dashboard?.batch_ranking.length) return null;
    const names = dashboard.batch_ranking.map((item) => item.batch_name);
    return {
      color: [chartPalette[0]],
      tooltip: { trigger: "axis" as const },
      grid: { left: 48, right: 24, top: 24, bottom: 64 },
      xAxis: {
        type: "category" as const,
        data: names,
        axisLabel: { rotate: 28, interval: 0 },
      },
      yAxis: { type: "value" as const, name: "记录数" },
      series: [
        {
          type: "bar" as const,
          data: dashboard.batch_ranking.map((item) => item.count),
          barMaxWidth: 36,
        },
      ],
    };
  }, [dashboard]);

  const eventBarOption = useMemo(() => {
    if (!dashboard?.event_distribution.length) return null;
    return {
      color: [chartPalette[3]],
      tooltip: { trigger: "axis" as const },
      grid: { left: 48, right: 24, top: 24, bottom: 64 },
      xAxis: {
        type: "category" as const,
        data: dashboard.event_distribution.map((item) => item.event_type),
        axisLabel: { rotate: 24, interval: 0 },
      },
      yAxis: { type: "value" as const, name: "事件数" },
      series: [
        {
          type: "bar" as const,
          data: dashboard.event_distribution.map((item) => item.count),
          barMaxWidth: 36,
        },
      ],
    };
  }, [dashboard]);

  const overview = dashboard?.overview;

  return (
    <div className="data-dashboard-page">
      <Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {selectedCaseId
          ? "以下图表基于当前选中案件关联批次的数据统计；可在顶部切换案件。"
          : "当前展示全库数据概览；选择案件后可查看案件范围内的统计。"}
      </Paragraph>

      <Row gutter={[16, 16]} className="dashboard-stat-row">
        {[
          { title: "数据总量", value: overview?.record_count ?? 0, icon: <DatabaseOutlined /> },
          { title: "导入批次", value: overview?.batch_count ?? 0, icon: <AppstoreOutlined /> },
          { title: "案件数量", value: overview?.case_count ?? 0, icon: <ProjectOutlined /> },
          { title: "关联人物", value: overview?.person_count ?? 0, icon: <TeamOutlined /> },
        ].map((item) => (
          <Col xs={12} md={6} key={item.title}>
            <Card className="app-card dashboard-stat-card" bordered={false}>
              {loading ? (
                <Skeleton active paragraph={false} />
              ) : (
                <Space align="start">
                  <span className="dashboard-stat-icon">{item.icon}</span>
                  <Statistic title={item.title} value={item.value} />
                </Space>
              )}
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card className="app-card" bordered={false} title="时间轴数据量趋势">
            <Paragraph type="secondary" className="chart-caption">
              折线图展示时间轴上各类型数据条数
            </Paragraph>
            {loading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : timelineOption ? (
              <ReactECharts option={timelineOption} style={{ height: 340 }} />
            ) : (
              <Empty description="暂无时间序列数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card className="app-card" bordered={false} title="异常事件关联人物排名">
            {loading ? (
              <Skeleton active avatar paragraph={{ rows: 4 }} />
            ) : dashboard?.person_ranking.length ? (
              <div className="person-ranking-list">
                {dashboard.person_ranking.map((item, index) => (
                  <div className="person-ranking-item" key={`${item.person_name}-${index}`}>
                    <Space>
                      <Text type="secondary">{index + 1}.</Text>
                      <Avatar icon={<UserOutlined />} size={40} />
                      <div>
                        <Text strong>{item.person_name}</Text>
                        <div>
                          <Tag color="volcano">转账 {item.transfer_count} 次</Tag>
                          <Tag color="blue">通话 {item.call_count} 次</Tag>
                        </div>
                      </div>
                    </Space>
                  </div>
                ))}
              </div>
            ) : (
              <Empty description="暂无人物排名数据" />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card className="app-card" bordered={false} title="数据来源分布">
            {loading ? (
              <Skeleton active paragraph={{ rows: 6 }} />
            ) : sourcePieOption ? (
              <ReactECharts option={sourcePieOption} style={{ height: 300 }} />
            ) : (
              <Empty description="暂无来源分布数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card className="app-card" bordered={false} title="批次数据量排名">
            {loading ? (
              <Skeleton active paragraph={{ rows: 6 }} />
            ) : batchBarOption ? (
              <ReactECharts option={batchBarOption} style={{ height: 300 }} />
            ) : (
              <Empty description="暂无批次排名数据" />
            )}
          </Card>
        </Col>
      </Row>

      {selectedCaseId && dashboard?.event_distribution.length ? (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card className="app-card" bordered={false} title="融合事件类型分布">
              {loading ? (
                <Skeleton active paragraph={{ rows: 6 }} />
              ) : eventBarOption ? (
                <ReactECharts option={eventBarOption} style={{ height: 280 }} />
              ) : (
                <Empty description="暂无事件数据" />
              )}
            </Card>
          </Col>
        </Row>
      ) : null}
    </div>
  );
}

export default DataDashboardPage;
