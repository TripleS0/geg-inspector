import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Col, Empty, Row, Skeleton, Space, Tag, Typography, message } from "antd";
import {
  AppstoreOutlined,
  BankOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  PartitionOutlined,
  PhoneOutlined,
  ProjectOutlined,
  WechatOutlined,
} from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { api, BatchInfo, batchLabel, CaseInfo, CASE_CHANGED_EVENT, CASE_STORAGE_KEY, HealthInfo, PersonInfo } from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT, getNextWorkflowStep } from "../components/WorkflowGuide";

const { Paragraph, Text, Title } = Typography;

interface HomePageProps {
  health: HealthInfo | null;
}

const SOURCE_LABELS: Record<string, string> = {
  bank: "银行",
  commercial: "商务网",
  enterprise: "工商",
  wechat: "微信",
  telecom: "通讯",
};

const ANALYSIS_ENTRIES: Array<{ to: string; title: string; desc: string; icon: ReactNode; featured?: boolean }> = [
  { to: "/fusion-cockpit", title: "融合分析驾驶舱", desc: "综合研判与关系图谱探索，单人全景、双人关系与多层关联分析", icon: <PartitionOutlined />, featured: true },
  { to: "/bank", title: "资金往来分析", desc: "大额、特殊金额、特殊时间资金线索", icon: <BankOutlined /> },
  { to: "/wechat-analysis", title: "微信流水分析", desc: "分析微信转账流水与交易对手关系", icon: <WechatOutlined /> },
  { to: "/telecom-analysis", title: "通讯记录分析", desc: "通联频次、时长、时段与号码关系", icon: <PhoneOutlined /> },
  { to: "/commercial-analysis", title: "商务数据分析", desc: "询价、中标、供应商与资金关联", icon: <LineChartOutlined /> },
];

function formatTime(value?: string) {
  if (!value) return "-";
  return value.replace("T", " ").slice(0, 16);
}

function HomePage({ health }: HomePageProps) {
  const navigate = useNavigate();
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [pendingCandidateCount, setPendingCandidateCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const refreshWorkspace = useCallback(async (caseId?: number) => {
    setLoading(true);
    try {
      const [caseData, batchData] = await Promise.all([api.listCases(), api.listBatches()]);
      setCases(caseData.items);
      setBatches(batchData.items);
      const stored = localStorage.getItem(CASE_STORAGE_KEY);
      const storedId = stored ? Number(stored) : null;
      const selected = caseData.items.find((item) => item.case_id === (caseId ?? storedId)) ?? caseData.items[0] ?? null;
      if (selected) {
        const [personData, candidateData] = await Promise.all([
          api.listCasePersons(selected.case_id),
          api.listCaseCandidates(selected.case_id, "pending"),
        ]);
        setPersons(personData.items);
        setPendingCandidateCount(candidateData.items.length);
      } else {
        setPersons([]);
        setPendingCandidateCount(0);
      }
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshWorkspace();
    const onCaseChanged = (event: Event) => {
      const caseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId;
      void refreshWorkspace(caseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, [refreshWorkspace]);

  const selectedCase = useMemo(() => {
    const stored = localStorage.getItem(CASE_STORAGE_KEY);
    const storedId = stored ? Number(stored) : null;
    return cases.find((item) => item.case_id === storedId) ?? cases[0] ?? null;
  }, [cases]);

  const sourceTypes = useMemo(() => Array.from(new Set(batches.map((item) => item.source_type))), [batches]);
  const selectedCaseBoundBatchCount = selectedCase?.batch_count ?? 0;
  const linkedIdentifierCount = persons.reduce((sum, item) => sum + item.links.length, 0);
  const workflowSnapshot = {
    ...DEFAULT_WORKFLOW_SNAPSHOT,
    caseCount: cases.length,
    batchCount: batches.length,
    boundBatchCount: selectedCaseBoundBatchCount,
    personCount: persons.length,
    linkedIdentifierCount,
    pendingCandidateCount,
    selectedCaseId: selectedCase?.case_id ?? null,
  };
  const workflowSteps = buildWorkflowSteps(workflowSnapshot);
  const nextStep = getNextWorkflowStep(workflowSteps);

  return (
    <div className="workspace-page">
      <div className="app-card home-hero workspace-hero">
        <div className="workspace-hero-main">
          <div className="home-kicker">案件驱动的多源数据融合分析工作台</div>
          <Title level={3} style={{ marginBottom: 8 }}>从导入数据到融合研判，一站式完成案件分析</Title>
          <Paragraph style={{ marginBottom: 0 }}>
            当前进展来自真实案件、批次和人物关联数据；系统会自动推荐下一步，不再依赖固定写死的流程状态。
          </Paragraph>
          <Space wrap className="workspace-actions">
            <Button type="primary" size="large" icon={<PartitionOutlined />} onClick={() => navigate(selectedCase ? `/fusion-cockpit?case=${selectedCase.case_id}` : "/fusion-cockpit")}>融合分析驾驶舱</Button>
            {nextStep ? (
              <Button type="link" size="large" icon={nextStep.icon} onClick={() => navigate(nextStep.to)} disabled={nextStep.disabled}>
                下一步：{nextStep.title}
              </Button>
            ) : null}
          </Space>
        </div>
        <div className="next-step-panel">
          <Text className="context-label">系统建议</Text>
          <Title level={4} style={{ margin: "8px 0" }}>{nextStep?.title ?? "融合分析"}</Title>
          <Paragraph style={{ marginBottom: 0, color: "#7c6d67" }}>{nextStep?.desc ?? "当前主流程已完成，可进入驾驶舱持续研判。"}</Paragraph>
          {pendingCandidateCount > 0 && <Tag color="orange" style={{ marginTop: 12 }}>待处理候选 {pendingCandidateCount} 个</Tag>}
        </div>
      </div>

      <Row gutter={[16, 16]} className="metric-row">
        <Col xs={24} sm={12} lg={6}><div className="metric-card"><span className="metric-icon"><ProjectOutlined /></span><Text>案件</Text><Title level={3}>{loading ? "-" : cases.length}</Title></div></Col>
        <Col xs={24} sm={12} lg={6}><div className="metric-card"><span className="metric-icon"><AppstoreOutlined /></span><Text>导入批次</Text><Title level={3}>{loading ? "-" : batches.length}</Title></div></Col>
        <Col xs={24} sm={12} lg={6}><div className="metric-card"><span className="metric-icon"><DatabaseOutlined /></span><Text>当前案件批次</Text><Title level={3}>{loading ? "-" : selectedCaseBoundBatchCount}</Title></div></Col>
        <Col xs={24} sm={12} lg={6}><div className="metric-card"><span className="metric-icon"><CheckCircleOutlined /></span><Text>人物 / 标识</Text><Title level={3}>{loading ? "-" : `${persons.length}/${linkedIdentifierCount}`}</Title></div></Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <div className="app-card">
            <div className="section-heading">
              <div><Title level={4}>主流程引导</Title><Paragraph>进度基于真实数据计算，可从任一步直接跳转到后续步骤。</Paragraph></div>
            </div>
            {loading ? <Skeleton active paragraph={{ rows: 5 }} /> : <WorkflowGuide steps={workflowSteps} />}
          </div>
        </Col>
        <Col xs={24} lg={10}>
          <div className="app-card recent-card">
            <div className="section-heading">
              <div><Title level={4}>最近工作</Title><Paragraph>快速回到当前案件与最近导入批次。</Paragraph></div>
              <Button onClick={() => navigate("/cases")}>案件管理</Button>
            </div>
            {loading ? <Skeleton active paragraph={{ rows: 4 }} /> : (
              <>
                {selectedCase ? (
                  <div className="current-case-card">
                    <Text className="context-label">当前案件</Text>
                    <Title level={5}>{selectedCase.case_name}</Title>
                    <Space wrap><Tag color="volcano">{selectedCase.status}</Tag><Tag>{selectedCase.batch_count} 个批次</Tag><Text>{formatTime(selectedCase.updated_at)}</Text></Space>
                  </div>
                ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无案件"><Button type="primary" onClick={() => navigate("/cases")}>新建案件</Button></Empty>}
                <div className="recent-list">
                  {batches.slice(0, 4).map((batch) => (
                    <div className="recent-item" key={batch.import_batch_id}>
                      <div><Text strong>{SOURCE_LABELS[batch.source_type] ?? batch.source_type}</Text><Paragraph>{batchLabel(batch)}</Paragraph></div>
                      <Tag>{batch.file_count} 文件</Tag>
                    </div>
                  ))}
                </div>
                <div className="source-summary">可用数据源：{sourceTypes.length ? sourceTypes.map((item) => SOURCE_LABELS[item] ?? item).join("、") : "暂无"}</div>
              </>
            )}
          </div>
        </Col>
      </Row>

      <div className="app-card" style={{ marginTop: 16 }}>
        <div className="section-heading">
          <div><Title level={4}>融合分析驾驶舱</Title><Paragraph>综合研判与关系图谱统一入口，从驾驶舱内进入图谱探索。</Paragraph></div>
        </div>
        <Row gutter={[16, 16]}>
          {ANALYSIS_ENTRIES.filter((entry) => entry.featured).map((entry) => (
            <Col xs={24} md={12} key={entry.to}>
              <Link to={entry.to}>
                <div className="quick-card compact-analysis-card featured-analysis-card">
                  <span className="quick-icon">{entry.icon}</span>
                  <div><Title level={5}>{entry.title}</Title><Paragraph>{entry.desc}</Paragraph></div>
                </div>
              </Link>
            </Col>
          ))}
        </Row>
      </div>

      <div className="app-card" style={{ marginTop: 16 }}>
        <div className="section-heading">
          <div><Title level={4}>专题分析</Title><Paragraph>资金往来、微信流水、通讯记录与商务数据分析入口。</Paragraph></div>
        </div>
        <Row gutter={[16, 16]}>
          {ANALYSIS_ENTRIES.filter((entry) => !entry.featured).map((entry) => (
            <Col xs={24} sm={12} xl={6} key={entry.to}>
              <Link to={entry.to}>
                <div className="quick-card compact-analysis-card">
                  <span className="quick-icon">{entry.icon}</span>
                  <div><Title level={5}>{entry.title}</Title><Paragraph>{entry.desc}</Paragraph></div>
                </div>
              </Link>
            </Col>
          ))}
        </Row>
      </div>

      {health && (
        <div className="system-footnote">
          <span>本地数据库已连接</span>
          <span>导出目录：{health.exports_dir}</span>
        </div>
      )}
    </div>
  );
}

export default HomePage;
