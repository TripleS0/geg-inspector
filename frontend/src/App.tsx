import { useEffect, useMemo, useState } from "react";
import { Button, Layout, Menu, Select, Tag, Tooltip, Typography } from "antd";
import {
  AlertOutlined,
  AppstoreOutlined,
  BankOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileProtectOutlined,
  FundProjectionScreenOutlined,
  HomeOutlined,
  IdcardOutlined,
  LineChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PartitionOutlined,
  PhoneOutlined,
  ProfileOutlined,
  ProjectOutlined,
  SafetyOutlined,
  SettingOutlined,
  WechatOutlined,
} from "@ant-design/icons";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ItemType } from "antd/es/menu/interface";
import BankOcrProofreadPage from "./pages/BankOcrProofreadPage";
import CaseManagePage from "./pages/CaseManagePage";
import PersonLinkingPage from "./pages/PersonLinkingPage";
import FusionAnalysisHubPage from "./pages/FusionAnalysisHubPage";
import GraphExplorePage from "./pages/GraphExplorePage";
import DataDashboardPage from "./pages/DataDashboardPage";
import DataManagePage from "./pages/DataManagePage";
import HomePage from "./pages/HomePage";
import ImportPage from "./pages/ImportPage";
import BatchesPage from "./pages/BatchesPage";
import TablesPage from "./pages/TablesPage";
import BankAnalysisPage from "./pages/BankAnalysisPage";
import BankTemplatesPage from "./pages/BankTemplatesPage";
import CommercialAnalysisPage from "./pages/CommercialAnalysisPage";
import CommercialRiskPage from "./pages/CommercialRiskPage";
import DesensitizationPage from "./pages/DesensitizationPage";
import QichachaIcPage from "./pages/QichachaIcPage";
import WechatAnalysisPage from "./pages/WechatAnalysisPage";
import TelecomAnalysisPage from "./pages/TelecomAnalysisPage";
import {
  api,
  CaseInfo,
  CASE_CHANGED_EVENT,
  emitCaseChanged,
  HealthInfo,
  persistSelectedCaseId,
  resolveSelectedCaseId,
} from "./api";

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const PAGE_META: Record<string, { title: string; desc: string }> = {
  home: { title: "首页", desc: "案件数据、融合研判与专题分析的统一入口" },
  import: { title: "数据管理", desc: "导入、批次、原始表和数据治理工具" },
  "bank-ocr": { title: "数据管理 · 银行 OCR", desc: "对照原图校对 OCR 识别结果并录入" },
  batches: { title: "数据管理 · 批次", desc: "检查历史导入批次并绑定案件分析范围" },
  cases: { title: "数据管理 · 案件", desc: "创建案件、绑定数据批次并维护分析作用域" },
  "person-linking": { title: "专题分析 · 人物关系", desc: "将姓名、手机号、微信、银行卡等标识归并到同一人物" },
  "fusion-cockpit": { title: "研判中心 · 融合分析驾驶舱", desc: "综合研判 · 单人全景、双人关系与标识符自由检索" },
  "fusion-events": { title: "研判中心 · 事件管理", desc: "按已启用模型扫描案件数据，展示大额转账、围标等触发事件" },
  "fusion-models": { title: "研判中心 · 模型管理", desc: "配置银行流水、微信转账、商务网与围串标风险模型的启用与参数" },
  "data-dashboard": { title: "数据中心 · 数据看板", desc: "全方面数据概览、趋势图表与关联人物排名" },
  "data-manage": { title: "数据中心 · 数据管理", desc: "数据记录、批次与案件的查询与删除" },
  tables: { title: "数据管理 · 数据表", desc: "预览入库明细并核对原始数据" },
  desensitization: { title: "数据管理 · 数据脱敏", desc: "对文件进行批量脱敏处理并导出结果" },
  bank: { title: "专题分析 · 资金往来", desc: "识别大额、特殊金额、特殊时间等资金线索" },
  "bank-templates": { title: "数据管理 · 银行模板", desc: "维护银行流水字段映射与收支规则" },
  "wechat-analysis": { title: "专题分析 · 微信流水", desc: "分析微信转账流水与交易对手关系" },
  "telecom-analysis": { title: "专题分析 · 通讯记录", desc: "分析通联频次、时长、时段与号码关系" },
  "commercial-analysis": { title: "专题分析 · 商务数据", desc: "统计询价、中标与供应商资金关联" },
  risk: { title: "专题分析 · 商务风险", desc: "识别围标、串标、陪标等风险事件" },
  qichacha: { title: "数据管理 · 工商信息", desc: "补充企业工商主体与关联信息" },
};

const SIDER_STORAGE_KEY = "datafusionx.siderCollapsed";

function GraphExploreRedirect() {
  const location = useLocation();
  return <Navigate to={`/fusion-cockpit/graph${location.search}`} replace />;
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
    if (path.startsWith("/cases")) return "cases";
    if (path.startsWith("/import")) return "import";
    if (path.startsWith("/batches")) return "batches";
    if (path.startsWith("/tables")) return "tables";
    if (path.startsWith("/desensitization")) return "desensitization";
    if (path.startsWith("/bank-ocr")) return "bank-ocr";
    if (path.startsWith("/bank-templates")) return "bank-templates";
    if (path.startsWith("/bank")) return "bank";
    if (path.startsWith("/commercial-analysis")) return "commercial-analysis";
    if (path.startsWith("/risk")) return "risk";
    if (path.startsWith("/wechat-analysis")) return "wechat-analysis";
    if (path.startsWith("/telecom-analysis")) return "telecom-analysis";
    if (path.startsWith("/qichacha-ic")) return "qichacha";
    return "home";
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
  const pageMeta = useMemo(() => {
    if (location.pathname.startsWith("/fusion-cockpit/graph")) {
      return {
        title: "研判中心 · 融合分析驾驶舱",
        desc: "综合关联 · 多层扩张、路径发现与关系过滤",
      };
    }
    return PAGE_META[selectedKey] ?? PAGE_META.home;
  }, [location.pathname, selectedKey]);

  const menuItems: ItemType[] = [
    { type: "group", label: "入口", children: [
      { key: "home", icon: <HomeOutlined />, label: "首页" },
      { key: "import", icon: <CloudUploadOutlined />, label: "数据导入" },
    ] },
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
    { type: "group", label: "更多", children: [
      { key: "cases", icon: <ProjectOutlined />, label: "案件管理" },
      { key: "batches", icon: <AppstoreOutlined />, label: "批次管理" },
      { key: "tables", icon: <DatabaseOutlined />, label: "数据表浏览" },
      { key: "risk", icon: <SafetyOutlined />, label: "商务风险" },
      { key: "desensitization", icon: <FileProtectOutlined />, label: "数据脱敏" },
      { key: "qichacha", icon: <IdcardOutlined />, label: "工商信息录入" },
      { key: "bank-templates", icon: <ProfileOutlined />, label: "银行模板录入" },
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
              home: "/",
              import: "/import",
              batches: "/batches",
              tables: "/tables",
              desensitization: "/desensitization",
              bank: "/bank",
              "bank-templates": "/bank-templates",
              "commercial-analysis": "/commercial-analysis",
              risk: "/risk",
              "wechat-analysis": "/wechat-analysis",
              "telecom-analysis": "/telecom-analysis",
              qichacha: "/qichacha-ic",
              cases: "/cases",
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
          <div className="header-title">
            <span className="header-icon"><FundProjectionScreenOutlined /></span>
            <div>
              <div className="header-name">{pageMeta.title}</div>
              <div className="header-desc">{pageMeta.desc}</div>
            </div>
          </div>
          <div className="header-context">
            <div className="case-selector-wrap">
              <Text className="context-label">当前案件</Text>
              <Select
                size="small"
                className="case-selector"
                placeholder={cases.length ? "未选择案件" : "暂无案件"}
                value={effectiveCaseId ?? undefined}
                disabled={!cases.length}
                options={cases.map((item) => ({ label: item.case_name, value: item.case_id }))}
                optionRender={(option) => {
                  const item = cases.find((caseItem) => caseItem.case_id === option.value);
                  return (
                    <div className="case-option">
                      <strong>{option.label}</strong>
                      {item && <span>#{item.case_id} · {item.status} · {item.batch_count} 个批次</span>}
                    </div>
                  );
                }}
                onChange={(value) => {
                  setSelectedCaseId(value);
                  persistSelectedCaseId(value);
                  emitCaseChanged(value);
                  if (location.pathname.startsWith("/fusion-cockpit/events") || location.pathname.startsWith("/fusion-cockpit/models")) {
                    const next = new URLSearchParams(location.search);
                    next.set("case", String(value));
                    navigate(`${location.pathname}?${next.toString()}`, { replace: true });
                  }
                }}
                dropdownMatchSelectWidth={280}
              />
            </div>
            {selectedCase ? (
              <Tooltip title={`案件编号 #${selectedCase.case_id} · ${selectedCase.status} · 更新于 ${selectedCase.updated_at}`}>
                <Tag color="volcano">{selectedCase.batch_count} 个批次</Tag>
              </Tooltip>
            ) : null}
            <Tooltip title={health?.db_path || error || "等待后端连接"}>
              <span className={`backend-dot ${health ? "online" : error ? "offline" : "pending"}`} />
            </Tooltip>
            {selectedKey === "home" || selectedKey === "import" ? (
              <Button type="primary" icon={<DashboardOutlined />} onClick={() => navigate("/import")}>导入数据</Button>
            ) : null}
          </div>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<HomePage health={health} />} />
            <Route path="/cases" element={<CaseManagePage />} />
            <Route path="/person-linking" element={<PersonLinkingPage />} />
            <Route path="/fusion-cockpit/events" element={<FusionAnalysisHubPage />} />
            <Route path="/fusion-cockpit/models" element={<FusionAnalysisHubPage />} />
            <Route path="/fusion-cockpit" element={<FusionAnalysisHubPage />} />
            <Route path="/fusion-cockpit/graph" element={<GraphExplorePage embedded />} />
            <Route path="/graph-explore" element={<GraphExploreRedirect />} />
            <Route path="/data-center/manage" element={<DataManagePage />} />
            <Route path="/data-center" element={<DataDashboardPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/bank-ocr/:jobId" element={<BankOcrProofreadPage />} />
            <Route path="/batches" element={<BatchesPage />} />
            <Route path="/tables" element={<TablesPage />} />
            <Route path="/desensitization" element={<DesensitizationPage />} />
            <Route path="/bank" element={<BankAnalysisPage />} />
            <Route path="/bank-templates" element={<BankTemplatesPage />} />
            <Route path="/wechat-analysis" element={<WechatAnalysisPage />} />
            <Route path="/telecom-analysis" element={<TelecomAnalysisPage />} />
            <Route path="/commercial-analysis" element={<CommercialAnalysisPage />} />
            <Route path="/risk" element={<CommercialRiskPage />} />
            <Route path="/qichacha-ic" element={<QichachaIcPage />} />
            <Route path="*" element={<div className="app-card">未找到该页面，<Link to="/">返回首页</Link></div>} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default App;
