import { useEffect, useState } from "react";
import { Layout, Menu, Tag } from "antd";
import {
  AppstoreOutlined,
  BankOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  FileProtectOutlined,
  FundProjectionScreenOutlined,
  HomeOutlined,
  IdcardOutlined,
  LineChartOutlined,
  ProfileOutlined,
  SafetyOutlined,
} from "@ant-design/icons";
import { Link, Route, Routes, useLocation, useNavigate } from "react-router-dom";
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
import { api, HealthInfo } from "./api";

const { Header, Sider, Content } = Layout;

function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [error, setError] = useState<string>("");
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

  const selectedKey = (() => {
    const path = location.pathname;
    if (path.startsWith("/import")) return "import";
    if (path.startsWith("/batches")) return "batches";
    if (path.startsWith("/tables")) return "tables";
    if (path.startsWith("/desensitization")) return "desensitization";
    if (path.startsWith("/bank-templates")) return "bank-templates";
    if (path.startsWith("/bank")) return "bank";
    if (path.startsWith("/commercial-analysis")) return "commercial-analysis";
    if (path.startsWith("/risk")) return "risk";
    if (path.startsWith("/qichacha-ic")) return "qichacha";
    return "home";
  })();

  return (
    <Layout className="app-shell">
      <Sider width={248} className="app-sider">
        <div className="brand">
          <div className="brand-compact">
            <img className="brand-mark" src="/logo.png" alt="智能数据分析平台" />
            <span>智能数据分析平台</span>
          </div>
        </div>
        <Menu
          theme="light"
          mode="inline"
          className="side-menu"
          selectedKeys={[selectedKey]}
          onClick={({ key }) => {
            switch (key) {
              case "home":
                navigate("/");
                break;
              case "import":
                navigate("/import");
                break;
              case "batches":
                navigate("/batches");
                break;
              case "tables":
                navigate("/tables");
                break;
              case "desensitization":
                navigate("/desensitization");
                break;
              case "bank":
                navigate("/bank");
                break;
              case "bank-templates":
                navigate("/bank-templates");
                break;
              case "commercial-analysis":
                navigate("/commercial-analysis");
                break;
              case "risk":
                navigate("/risk");
                break;
              case "qichacha":
                navigate("/qichacha-ic");
                break;
              default:
                break;
            }
          }}
          items={[
            { key: "home", icon: <HomeOutlined />, label: "首页" },
            { key: "import", icon: <CloudUploadOutlined />, label: "数据导入" },
            { key: "batches", icon: <AppstoreOutlined />, label: "批次管理" },
            { key: "tables", icon: <DatabaseOutlined />, label: "数据表浏览" },
            { key: "desensitization", icon: <FileProtectOutlined />, label: "数据脱敏" },
            { key: "bank", icon: <BankOutlined />, label: "银行流水分析" },
            { key: "bank-templates", icon: <ProfileOutlined />, label: "银行模板录入" },
            { key: "commercial-analysis", icon: <LineChartOutlined />, label: "商务网分析" },
            { key: "risk", icon: <SafetyOutlined />, label: "商务网风险" },
            { key: "qichacha", icon: <IdcardOutlined />, label: "工商信息录入" },
          ]}
        />
      </Sider>
      <Layout className="main-layout">
        <Header className="app-header">
          <div className="header-title">
            <span className="header-icon"><FundProjectionScreenOutlined /></span>
            <div>
              <div className="header-name">智能数据分析平台</div>
              <div className="header-desc">离线运行 · 本地数据分析</div>
            </div>
          </div>
          <div className="health-pill">
            {health ? (
              <>
                <Tag color="green">后端在线</Tag>
                <span>v{health.version}</span>
                <span className="health-db">数据库：{health.db_path}</span>
              </>
            ) : (
              <Tag color={error ? "red" : "orange"}>{error || "等待后端…"}</Tag>
            )}
          </div>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<HomePage health={health} />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/batches" element={<BatchesPage />} />
            <Route path="/tables" element={<TablesPage />} />
            <Route path="/desensitization" element={<DesensitizationPage />} />
            <Route path="/bank" element={<BankAnalysisPage />} />
            <Route path="/bank-templates" element={<BankTemplatesPage />} />
            <Route path="/commercial-analysis" element={<CommercialAnalysisPage />} />
            <Route path="/risk" element={<CommercialRiskPage />} />
            <Route path="/qichacha-ic" element={<QichachaIcPage />} />
            <Route
              path="*"
              element={<div className="app-card">未找到该页面，<Link to="/">返回首页</Link></div>}
            />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default App;
