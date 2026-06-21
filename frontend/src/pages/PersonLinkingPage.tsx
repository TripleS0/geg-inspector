import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Card, Select, Space, Typography, message } from "antd";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  CASE_CHANGED_EVENT,
  CASE_STORAGE_KEY,
  emitCaseChanged,
  persistSelectedCaseId,
} from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT } from "../components/WorkflowGuide";
import PersonLinkingPanel from "../components/fusion/PersonLinkingPanel";

const { Title, Paragraph } = Typography;

function PersonLinkingPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [cases, setCases] = useState<Array<{ case_id: number; case_name: string; batch_count: number }>>([]);
  const [caseId, setCaseId] = useState<number | null>(null);
  const [stats, setStats] = useState({ personCount: 0, linkedCount: 0, pendingCount: 0 });

  const refreshCases = useCallback(async () => {
    const data = await api.listCases();
    setCases(data.items.map((c) => ({ case_id: c.case_id, case_name: c.case_name, batch_count: c.batch_count })));
    const param = searchParams.get("case");
    const stored = localStorage.getItem(CASE_STORAGE_KEY);
    const preferred = param ? Number(param) : stored ? Number(stored) : null;
    const next =
      preferred && data.items.some((c) => c.case_id === preferred)
        ? preferred
        : data.items[0]?.case_id ?? null;
    setCaseId(next);
  }, [searchParams]);

  useEffect(() => {
    void refreshCases().catch((err) => message.error((err as Error).message));
  }, [refreshCases]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId;
      if (nextCaseId && nextCaseId !== caseId) {
        setCaseId(nextCaseId);
        setSearchParams({ case: String(nextCaseId) });
      }
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, [caseId, setSearchParams]);

  useEffect(() => {
    if (!caseId) return;
    localStorage.setItem(CASE_STORAGE_KEY, String(caseId));
    setSearchParams({ case: String(caseId) });
  }, [caseId, setSearchParams]);

  const selectedCase = cases.find((item) => item.case_id === caseId) ?? null;
  const guideSteps = buildWorkflowSteps({
    ...DEFAULT_WORKFLOW_SNAPSHOT,
    caseCount: cases.length,
    batchCount: selectedCase?.batch_count ?? 0,
    boundBatchCount: selectedCase?.batch_count ?? 0,
    personCount: stats.personCount,
    linkedIdentifierCount: stats.linkedCount,
    pendingCandidateCount: stats.pendingCount,
    selectedCaseId: caseId,
  });

  return (
    <div className="link-page">
      <WorkflowGuide steps={guideSteps} currentKey="person-linking" compact />
      <Card className="app-card" bordered={false} style={{ marginBottom: 16 }}>
        <Space wrap align="center" style={{ width: "100%", justifyContent: "space-between" }}>
          <div>
            <Title level={4} style={{ margin: 0 }}>选择案件</Title>
            <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
              人物关联基于当前案件已绑定的批次数据。
            </Paragraph>
          </div>
          <Space wrap>
            <Select
              className="link-case-select"
              placeholder="选择案件"
              style={{ minWidth: 220 }}
              value={caseId ?? undefined}
              onChange={(value) => {
                setCaseId(value);
                persistSelectedCaseId(value);
                emitCaseChanged(value);
              }}
              options={cases.map((c) => ({ value: c.case_id, label: c.case_name }))}
            />
            <Button
              type="primary"
              ghost
              onClick={() => navigate(`/fusion-cockpit?case=${caseId || ""}&view=analysis&tab=open`)}
              disabled={!caseId}
            >
              融合驾驶舱
            </Button>
          </Space>
        </Space>
      </Card>
      {caseId ? (
        <PersonLinkingPanel
          caseId={caseId}
          onStatsChange={setStats}
          onEnterCockpit={() => navigate(`/fusion-cockpit?case=${caseId}&view=analysis&tab=open`)}
        />
      ) : null}
    </div>
  );
}

export default PersonLinkingPage;
