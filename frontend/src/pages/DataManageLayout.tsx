import { Tabs, Typography } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

const { Title } = Typography;

export const DATA_MANAGE_SECTIONS = [
  { key: "records", label: "数据记录", path: "/data-center/manage" },
  { key: "tables", label: "数据表浏览", path: "/data-center/manage/tables" },
  { key: "desensitization", label: "数据脱敏", path: "/data-center/manage/desensitization" },
  { key: "qichacha", label: "工商信息录入", path: "/data-center/manage/qichacha-ic" },
  { key: "bank-templates", label: "银行模板管理", path: "/data-center/manage/bank-templates" },
] as const;

export function dataManageTablesPath(params?: { table?: string; highlight?: number | string }) {
  const search = new URLSearchParams();
  if (params?.table) search.set("table", params.table);
  if (params?.highlight != null) search.set("highlight", String(params.highlight));
  const qs = search.toString();
  return `/data-center/manage/tables${qs ? `?${qs}` : ""}`;
}

function resolveSectionKey(pathname: string): string {
  if (pathname.includes("/tables")) return "tables";
  if (pathname.includes("/desensitization")) return "desensitization";
  if (pathname.includes("/qichacha-ic")) return "qichacha";
  if (pathname.includes("/bank-templates")) return "bank-templates";
  return "records";
}

function DataManageLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeKey = resolveSectionKey(location.pathname);

  return (
    <div className="app-card data-manage-layout">
      <Title level={4} style={{ marginTop: 0, marginBottom: 12 }}>
        数据管理
      </Title>
      <Tabs
        activeKey={activeKey}
        onChange={(key) => {
          const section = DATA_MANAGE_SECTIONS.find((item) => item.key === key);
          if (section) navigate(section.path);
        }}
        items={DATA_MANAGE_SECTIONS.map((item) => ({ key: item.key, label: item.label }))}
        style={{ marginBottom: 16 }}
      />
      <Outlet />
    </div>
  );
}

export default DataManageLayout;
