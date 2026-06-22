import { Button, Segmented, Select, Tag, Tooltip, Typography } from "antd";
import {
  ExportOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
} from "@ant-design/icons";
import { useLocation, useNavigate } from "react-router-dom";
import { CaseInfo, HealthInfo, emitCaseChanged, persistSelectedCaseId } from "../../api";

const { Text } = Typography;

type CaseAction = "new" | "open" | "export";

interface GlobalCaseBarProps {
  cases: CaseInfo[];
  effectiveCaseId: number | null;
  selectedCase: CaseInfo | null;
  health: HealthInfo | null;
  error: string;
  onCaseChange: (caseId: number) => void;
}

function resolveCaseAction(pathname: string): CaseAction | null {
  if (pathname.startsWith("/fusion-cockpit/new")) return "new";
  if (pathname.startsWith("/fusion-cockpit/open")) return "open";
  if (pathname.startsWith("/fusion-cockpit/export")) return "export";
  return null;
}

function GlobalCaseBar({
  cases,
  effectiveCaseId,
  selectedCase,
  health,
  error,
  onCaseChange,
}: GlobalCaseBarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const activeAction = resolveCaseAction(location.pathname);

  const goAction = (action: CaseAction) => {
    navigate(`/fusion-cockpit/${action}`);
  };

  return (
    <div className="global-case-bar">
      <Segmented
        className="global-case-actions"
        value={activeAction ?? undefined}
        onChange={(value) => goAction(value as CaseAction)}
        options={[
          { label: "新建案件", value: "new", icon: <FolderAddOutlined /> },
          { label: "打开案件", value: "open", icon: <FolderOpenOutlined /> },
          { label: "导出案件", value: "export", icon: <ExportOutlined /> },
        ]}
      />

      <div className="global-case-bar-right">
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
                {item && (
                  <span>
                    #{item.case_id} · {item.status} · {item.batch_count} 个批次
                  </span>
                )}
              </div>
            );
          }}
          onChange={(value) => {
            persistSelectedCaseId(value);
            emitCaseChanged(value);
            onCaseChange(value);
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

      {activeAction ? (
        <Button type="link" className="global-case-back" onClick={() => navigate("/fusion-cockpit")}>
          返回驾驶舱
        </Button>
      ) : null}
      </div>
    </div>
  );
}

export default GlobalCaseBar;
