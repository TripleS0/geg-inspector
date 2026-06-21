import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Segmented, message } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useLocation, useSearchParams } from "react-router-dom";
import {
  api,
  CaseInfo,
  CASE_CHANGED_EVENT,
  emitCaseChanged,
  persistSelectedCaseId,
  resolveSelectedCaseId,
} from "../api";
import FusionCockpitPage from "./FusionCockpitPage";
import FusionExportCasePanel from "../components/fusion/FusionExportCasePanel";
import FusionNewCaseFlow from "../components/fusion/FusionNewCaseFlow";
import FusionManageCasePanel from "../components/fusion/FusionManageCasePanel";
import FusionOpenCasePanel from "../components/fusion/FusionOpenCasePanel";
import FusionEventManagePanel from "../components/fusion/FusionEventManagePanel";
import FusionModelManagePanel from "../components/fusion/FusionModelManagePanel";

type HubTab = "new" | "open" | "export" | "manage";
type HubSection = "cockpit" | "events" | "models";

function parseTab(value: string | null): HubTab {
  if (value === "open" || value === "export" || value === "manage") return value;
  return "new";
}

function parseSection(pathname: string): HubSection {
  if (pathname.includes("/events")) return "events";
  if (pathname.includes("/models")) return "models";
  return "cockpit";
}

function FusionAnalysisHubPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [loadingCases, setLoadingCases] = useState(false);

  const section = parseSection(location.pathname);
  const tab = parseTab(searchParams.get("tab"));
  const view = searchParams.get("view");
  const caseParam = searchParams.get("case");
  const resolvedFromStorage = resolveSelectedCaseId(cases, null);
  const caseId = caseParam ? Number(caseParam) : resolvedFromStorage;
  const hasValidCase = caseId !== null && !Number.isNaN(caseId);
  const currentCase = cases.find((item) => item.case_id === caseId) ?? null;
  const showAnalysis =
    section === "cockpit" && hasValidCase && (view === "analysis" || (!view && !searchParams.get("tab")));

  const refreshCases = useCallback(async (preferredId?: number | null) => {
    setLoadingCases(true);
    try {
      const data = await api.listCases();
      setCases(data.items);
      const resolved = resolveSelectedCaseId(data.items, preferredId ?? caseId);
      if (resolved && (showAnalysis || section !== "cockpit")) {
        persistSelectedCaseId(resolved);
        emitCaseChanged(resolved);
      }
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoadingCases(false);
    }
  }, [caseId, showAnalysis, section]);

  useEffect(() => {
    void refreshCases();
  }, [refreshCases]);

  useEffect(() => {
    const onCaseChanged = () => {
      void refreshCases();
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, [refreshCases]);

  useEffect(() => {
    if (section === "cockpit") return;
    if (hasValidCase) return;
    if (!cases.length) return;
    const resolved = resolveSelectedCaseId(cases, null);
    if (!resolved) return;
    const next = new URLSearchParams(searchParams);
    next.set("case", String(resolved));
    setSearchParams(next, { replace: true });
  }, [cases, hasValidCase, searchParams, section, setSearchParams]);

  const setTab = (nextTab: HubTab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    next.delete("view");
    if (nextTab !== "open") {
      next.delete("case");
    } else if (caseId) {
      next.set("case", String(caseId));
    }
    setSearchParams(next, { replace: true });
  };

  const openAnalysis = (nextCaseId: number) => {
    persistSelectedCaseId(nextCaseId);
    emitCaseChanged(nextCaseId);
    const next = new URLSearchParams();
    next.set("tab", "open");
    next.set("case", String(nextCaseId));
    next.set("view", "analysis");
    setSearchParams(next, { replace: true });
    void refreshCases(nextCaseId);
  };

  const backToOpenList = () => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", "open");
    next.delete("view");
    if (caseId) next.set("case", String(caseId));
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    if (section !== "cockpit" || !hasValidCase || view === "analysis") return;
    if (!searchParams.get("tab") && caseId) {
      const next = new URLSearchParams(searchParams);
      next.set("view", "analysis");
      next.set("tab", "open");
      setSearchParams(next, { replace: true });
    }
  }, [caseId, hasValidCase, searchParams, section, setSearchParams, view]);

  useEffect(() => {
    if (section !== "cockpit" || searchParams.get("tab") || showAnalysis) return;
    const next = new URLSearchParams(searchParams);
    next.set("tab", cases.length ? "open" : "new");
    setSearchParams(next, { replace: true });
  }, [cases.length, searchParams, section, setSearchParams, showAnalysis]);

  const sectionHint = useMemo(() => {
    if (section === "events") return "事件管理需先选择案件，系统将根据已启用模型扫描案件数据。";
    if (section === "models") return "模型管理按案件保存启用状态与参数，不同案件可独立配置。";
    return null;
  }, [section]);

  const handleCaseDeleted = (deletedCaseId: number) => {
    const remaining = cases.filter((item) => item.case_id !== deletedCaseId);
    const nextId = resolveSelectedCaseId(remaining, null);
    persistSelectedCaseId(nextId);
    emitCaseChanged(nextId);
    if (caseId === deletedCaseId) {
      const next = new URLSearchParams(searchParams);
      next.delete("case");
      next.delete("view");
      next.set("tab", "manage");
      setSearchParams(next, { replace: true });
    }
  };

  const renderSection = () => {
    if (section === "events") {
      if (!hasValidCase) {
        return (
          <Alert
            type="info"
            showIcon
            message="请先选择或打开案件"
            description="在顶部「当前案件」下拉框中选择案件，或前往「打开案件」标签页。"
          />
        );
      }
      return <FusionEventManagePanel caseId={caseId!} caseName={currentCase?.case_name} />;
    }
    if (section === "models") {
      if (!hasValidCase) {
        return (
          <Alert
            type="info"
            showIcon
            message="请先选择或打开案件"
            description="模型配置按案件保存，请先在顶部选择当前案件。"
          />
        );
      }
      return <FusionModelManagePanel caseId={caseId!} caseName={currentCase?.case_name} />;
    }
    if (showAnalysis) {
      return <FusionCockpitPage embeddedInHub caseIdOverride={caseId} onBackToOpenList={backToOpenList} />;
    }
    if (tab === "new") {
      return <FusionNewCaseFlow onComplete={openAnalysis} />;
    }
    if (tab === "open") {
      return (
        <FusionOpenCasePanel
          cases={cases}
          loading={loadingCases}
          currentCaseId={hasValidCase ? caseId : null}
          onOpen={openAnalysis}
          onRefresh={() => void refreshCases()}
          onSwitchToNew={() => setTab("new")}
        />
      );
    }
    if (tab === "manage") {
      return (
        <FusionManageCasePanel
          cases={cases}
          loading={loadingCases}
          currentCaseId={hasValidCase ? caseId : null}
          onRefresh={() => void refreshCases()}
          onDeleted={handleCaseDeleted}
        />
      );
    }
    return <FusionExportCasePanel />;
  };

  return (
    <div className="fusion-analysis-hub">
      {section === "cockpit" ? (
        <div className="fusion-hub-toolbar app-card">
          <div className="fusion-hub-toolbar-row">
            {showAnalysis && tab === "open" ? (
              <Button icon={<ArrowLeftOutlined />} onClick={backToOpenList}>
                返回打开案件
              </Button>
            ) : null}
            <Segmented
              className="fusion-hub-tabs"
              value={tab}
              onChange={(value) => setTab(value as HubTab)}
              options={[
                { label: "新建案件", value: "new" },
                { label: "打开案件", value: "open" },
                { label: "管理案件", value: "manage" },
                { label: "导出案件", value: "export" },
              ]}
            />
          </div>
        </div>
      ) : sectionHint ? (
        <div className="fusion-hub-toolbar app-card fusion-hub-section-hint">
          {sectionHint}
        </div>
      ) : null}

      {renderSection()}
    </div>
  );
}

export default FusionAnalysisHubPage;
