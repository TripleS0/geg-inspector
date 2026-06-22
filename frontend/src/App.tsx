import { useEffect, useMemo, useState } from "react";
import { Button, Layout, Menu } from "antd";
import {
  AlertOutlined,
  BankOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PartitionOutlined,
  PhoneOutlined,
  SettingOutlined,
  WechatOutlined,
} from "@ant-design/icons";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ItemType } from "antd/es/menu/interface";
import BankOcrProofreadPage from "./pages/BankOcrProofreadPage";
import PersonLinkingPage from "./pages/PersonLinkingPage";
import FusionCaseActionPage from "./pages/FusionCaseActionPage";
import FusionSectionPage from "./pages/FusionSectionPage";
import GraphExplorePage from "./pages/GraphExplorePage";
import GlobalCaseBar from "./components/layout/GlobalCaseBar";
import DataDashboardPage from "./pages/DataDashboardPage";
import DataManagePage from "./pages/DataManagePage";
import DataManageLayout from "./pages/DataManageLayout";
import TablesPage from "./pages/TablesPage";
import BankAnalysisPage from "./pages/BankAnalysisPage";
import BankTemplatesPage from "./pages/BankTemplatesPage";
import CommercialAnalysisPage from "./pages/CommercialAnalysisPage";
import DesensitizationPage from "./pages/DesensitizationPage";
import QichachaIcPage from "./pages/QichachaIcPage";
import WechatAnalysisPage from "./pages/WechatAnalysisPage";
import TelecomAnalysisPage from "./pages/TelecomAnalysisPage";
import {
  api,
  CaseInfo,
  CASE_CHANGED_EVENT,
  HealthInfo,
  persistSelectedCaseId,
  resolveSelectedCaseId,
} from "./api";

const { Header, Sider, Content } = Layout;

const SIDER_STORAGE_KEY = "datafusionx.siderCollapsed";

function GraphExploreRedirect() {
  const location = useLocation();
  return <Navigate to={`/fusion-cockpit${location.search}`} replace />;
}

function LegacyDataManageRedirect({ suffix }: { suffix: string }) {
  const location = useLocation();
  return <Navigate to={`/data-center/manage${suffix}${location.search}`} replace />;
}

function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [error, setError] = useState<string>("");
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [siderCollapsed, setSiderCollapsed] = useState(
    () => localStorage.getItem(SIDER_STORAGE_KEY) === "1"
  );
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const data = await api.health();
        if (active) setHealth(data);
      } catch (err) {
        if (active) setError((err as Error).message);
      }
    };
    void refresh();
    const id = window.setInterval(refresh, 15_000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const applyCaseSelection = (items: CaseInfo[], preferredId?: number | null) => {
    const nextId = resolveSelectedCaseId(items, preferredId);
    setSelectedCaseId(nextId);
    persistSelectedCaseId(nextId);
    return nextId;
  };

  useEffect(() => {
    let active = true;
    const refreshCases = async (preferredId?: number | null) => {
      try {
        const data = await api.listCases();
        if (!active) return;
        setCases(data.items);
        applyCaseSelection(data.items, preferredId);
      } catch {
        if (active) {
          setCases([]);
          setSelectedCaseId(null);
        }
      }
    };
    void refreshCases();
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number | null }>).detail?.caseId ?? null;
      void refreshCases(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => {
      active = false;
      window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    };
  }, []);

  const selectedKey = (() => {
    const path = location.pathname;
    if (path.startsWith("/fusion-cockpit/events")) return "fusion-events";
    if (path.startsWith("/fusion-cockpit/models")) return "fusion-models";
    if (path.startsWith("/fusion-cockpit")) return "fusion-cockpit";
    if (path.startsWith("/data-center/manage")) return "data-manage";
    if (path.startsWith("/data-center")) return "data-dashboard";
    if (path.startsWith("/person-linking")) return "person-linking";
    if (path.startsWith("/tables")) return "data-manage";
    if (path.startsWith("/desensitization")) return "data-manage";
    if (path.startsWith("/bank-ocr")) return "bank-ocr";
    if (path.startsWith("/bank-templates")) return "data-manage";
    if (path.startsWith("/bank")) return "bank";
    if (path.startsWith("/commercial-analysis")) return "commercial-analysis";
    if (path.startsWith("/wechat-analysis")) return "wechat-analysis";
    if (path.startsWith("/telecom-analysis")) return "telecom-analysis";
    if (path.startsWith("/qichacha-ic")) return "data-manage";
    return "fusion-cockpit";
  })();

  const effectiveCaseId = useMemo(
    () => resolveSelectedCaseId(cases, selectedCaseId),
    [cases, selectedCaseId]
  );
  const selectedCase = useMemo(
    () => cases.find((item) => item.case_id === effectiveCaseId) ?? null,
    [cases, effectiveCaseId]
  );

  const toggleSider = (collapsed: boolean) => {
    setSiderCollapsed(collapsed);
    localStorage.setItem(SIDER_STORAGE_KEY, collapsed ? "1" : "0");
  };

  const menuItems: ItemType[] = [
    { type: "group", label: "研判中心", children: [
      { key: "fusion-cockpit", icon: <PartitionOutlined />, label: "融合分析驾驶舱" },
      { key: "fusion-events", icon: <AlertOutlined />, label: "事件管理" },
      { key: "fusion-models", icon: <SettingOutlined />, label: "模型管理" },
    ] },
    { type: "group", label: "专题分析", children: [
      { key: "bank", icon: <BankOutlined />, label: "资金往来分析" },
      { key: "wechat-analysis", icon: <WechatOutlined />, label: "微信流水分析" },
      { key: "telecom-analysis", icon: <PhoneOutlined />, label: "通讯记录分析" },
      { key: "commercial-analysis", icon: <LineChartOutlined />, label: "商务数据分析" },
    ] },
    { type: "group", label: "数据中心", children: [
      { key: "data-dashboard", icon: <DashboardOutlined />, label: "数据看板" },
      { key: "data-manage", icon: <DatabaseOutlined />, label: "数据管理" },
    ] },
  ];

  return (
    <Layout className="app-shell">
      <Sider
        width={258}
        collapsedWidth={72}
        collapsible
        collapsed={siderCollapsed}
        onCollapse={toggleSider}
        trigger={null}
        className={`app-sider${siderCollapsed ? " app-sider-collapsed" : ""}`}
      >
        <div className="brand">
          <div className="brand-compact">
            <img className="brand-mark" src="/logo.png" alt="智能数据分析平台" />
            {!siderCollapsed && <span>智能数据分析平台</span>}
          </div>
        </div>
        <Menu
          theme="light"
          mode="inline"
          inlineCollapsed={siderCollapsed}
          className="side-menu"
          selectedKeys={[selectedKey]}
          onClick={({ key }) => {
            const routes: Record<string, string> = {
              bank: "/bank",
              "commercial-analysis": "/commercial-analysis",
              "wechat-analysis": "/wechat-analysis",
              "telecom-analysis": "/telecom-analysis",
              "person-linking": "/person-linking",
              "fusion-cockpit": "/fusion-cockpit",
              "fusion-events": "/fusion-cockpit/events",
              "fusion-models": "/fusion-cockpit/models",
              "data-dashboard": "/data-center",
              "data-manage": "/data-center/manage",
            };
            if (routes[String(key)]) navigate(routes[String(key)]);
          }}
          items={menuItems}
        />
        <div className="sider-footer">
          <Button
            type="text"
            className="sider-toggle"
            icon={siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => toggleSider(!siderCollapsed)}
            aria-label={siderCollapsed ? "展开导航栏" : "收起导航栏"}
          />
        </div>
      </Sider>
      <Layout className="main-layout">
        <Header className="app-header">
          <GlobalCaseBar
            cases={cases}
            effectiveCaseId={effectiveCaseId}
            selectedCase={selectedCase}
            health={health}
            error={error}
            onCaseChange={setSelectedCaseId}
          />
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Navigate to="/fusion-cockpit" replace />} />
            <Route path="/cases" element={<Navigate to="/fusion-cockpit/open" replace />} />
            <Route path="/import" element={<Navigate to="/fusion-cockpit/new" replace />} />
            <Route path="/batches" element={<Navigate to="/data-center/manage" replace />} />
            <Route path="/risk" element={<Navigate to="/commercial-analysis" replace />} />
            <Route path="/person-linking" element={<PersonLinkingPage />} />
            <Route path="/fusion-cockpit/events" element={<FusionSectionPage section="events" />} />
            <Route path="/fusion-cockpit/models" element={<FusionSectionPage section="models" />} />
            <Route path="/fusion-cockpit/new" element={<FusionCaseActionPage action="new" />} />
            <Route path="/fusion-cockpit/open" element={<FusionCaseActionPage action="open" />} />
            <Route path="/fusion-cockpit/export" element={<FusionCaseActionPage action="export" />} />
            <Route path="/fusion-cockpit" element={<GraphExplorePage cockpitMode />} />
            <Route path="/fusion-cockpit/graph" element={<Navigate to="/fusion-cockpit" replace />} />
            <Route path="/graph-explore" element={<GraphExploreRedirect />} />
            <Route path="/data-center/manage" element={<DataManageLayout />}>
              <Route index element={<DataManagePage />} />
              <Route path="tables" element={<TablesPage />} />
              <Route path="desensitization" element={<DesensitizationPage />} />
              <Route path="qichacha-ic" element={<QichachaIcPage />} />
              <Route path="bank-templates" element={<BankTemplatesPage />} />
            </Route>
            <Route path="/data-center" element={<DataDashboardPage />} />
            <Route path="/bank-ocr/:jobId" element={<BankOcrProofreadPage />} />
            <Route path="/tables" element={<LegacyDataManageRedirect suffix="/tables" />} />
            <Route path="/desensitization" element={<LegacyDataManageRedirect suffix="/desensitization" />} />
            <Route path="/bank" element={<BankAnalysisPage />} />
            <Route path="/bank-templates" element={<LegacyDataManageRedirect suffix="/bank-templates" />} />
            <Route path="/wechat-analysis" element={<WechatAnalysisPage />} />
            <Route path="/telecom-analysis" element={<TelecomAnalysisPage />} />
            <Route path="/commercial-analysis" element={<CommercialAnalysisPage />} />
            <Route path="/qichacha-ic" element={<LegacyDataManageRedirect suffix="/qichacha-ic" />} />
            <Route path="*" element={<div className="app-card">未找到该页面，<Link to="/fusion-cockpit">返回驾驶舱</Link></div>} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default App;
