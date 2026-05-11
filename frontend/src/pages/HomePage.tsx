import { Col, Row, Typography } from "antd";
import {
  AppstoreOutlined,
  BankOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  FileProtectOutlined,
  IdcardOutlined,
  LineChartOutlined,
  ProfileOutlined,
  SafetyOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { HealthInfo } from "../api";

const { Paragraph, Title } = Typography;

interface HomePageProps {
  health: HealthInfo | null;
}

const QUICK_ENTRIES: Array<{ to: string; title: string; desc: string; icon: ReactNode }> = [
  { to: "/qichacha-ic", title: "工商信息录入", desc: "按名称查询企查查工商信息，支持名单导入与导出 Excel", icon: <IdcardOutlined /> },
  { to: "/import", title: "数据导入", desc: "选择银行流水、商务网招投标、工商企业信息文件", icon: <CloudUploadOutlined /> },
  { to: "/batches", title: "批次管理", desc: "查看历史导入批次，挑选需要分析的数据集", icon: <AppstoreOutlined /> },
  { to: "/tables", title: "数据表浏览", desc: "预览已入库表格，按需删行或删表", icon: <DatabaseOutlined /> },
  { to: "/bank-templates", title: "银行模板录入", desc: "录入开户信息与流水明细模板，拖拽映射字段并配置收支规则", icon: <ProfileOutlined /> },
  { to: "/desensitization", title: "数据脱敏", desc: "支持 txt、xlsx、xls 文件批量脱敏并导出结果", icon: <FileProtectOutlined /> },
  { to: "/bank", title: "银行流水分析", desc: "大额进出、特殊金额、特殊时间等固定模块", icon: <BankOutlined /> },
  { to: "/commercial-analysis", title: "商务网分析", desc: "查询商务网数据，统计中标资金关联并导出 Word 报告", icon: <LineChartOutlined /> },
  { to: "/risk", title: "商务网风险", desc: "围标、串标、陪标等规则自动识别", icon: <SafetyOutlined /> },
];

function HomePage({ health }: HomePageProps) {
  return (
    <div>
      <div className="app-card home-hero">
        <div className="home-kicker">广东电力开发有限公司</div>
        <Title level={3} style={{ marginBottom: 8 }}>欢迎使用智能数据分析平台</Title>
        <Paragraph style={{ marginBottom: 0 }}>
          面向本地数据治理与风险分析场景，支持离线导入、批次管理、表格浏览与专题分析。
        </Paragraph>
        {health && (
          <div className="home-meta">
            <span>数据库：{health.db_path}</span>
            <span>导出目录：{health.exports_dir}</span>
          </div>
        )}
      </div>
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {QUICK_ENTRIES.map((entry) => (
          <Col xs={24} sm={12} md={8} key={entry.to}>
            <Link to={entry.to}>
              <div className="app-card quick-card">
                <div className="quick-card-header">
                  <span className="quick-icon">{entry.icon}</span>
                  <Title level={4} style={{ margin: 0 }}>{entry.title}</Title>
                </div>
                <Paragraph style={{ marginBottom: 0, color: "#7c6d67" }}>{entry.desc}</Paragraph>
              </div>
            </Link>
          </Col>
        ))}
      </Row>
    </div>
  );
}

export default HomePage;
