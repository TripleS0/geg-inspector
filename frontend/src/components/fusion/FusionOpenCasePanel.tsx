import { Button, Empty, Space, Table, Tag, Typography, message } from "antd";
import { FolderOpenOutlined } from "@ant-design/icons";
import { api, CaseInfo } from "../../api";

const { Paragraph, Title } = Typography;

interface FusionOpenCasePanelProps {
  cases: CaseInfo[];
  loading: boolean;
  currentCaseId: number | null;
  onOpen: (caseId: number) => void;
  onRefresh: () => void;
  onSwitchToNew: () => void;
}

function FusionOpenCasePanel({ cases, loading, currentCaseId, onOpen, onRefresh, onSwitchToNew }: FusionOpenCasePanelProps) {
  return (
    <div className="fusion-hub-panel fusion-open-panel app-card">
      <div className="fusion-panel-head">
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>打开案件</Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            选择已有案件，进入融合分析驾驶舱。
          </Paragraph>
        </div>
        <Button onClick={onRefresh}>刷新列表</Button>
      </div>

      <Table
        rowKey="case_id"
        loading={loading}
        size="middle"
        dataSource={cases}
        pagination={{ pageSize: 8, showTotal: (total) => `共 ${total} 个案件` }}
        locale={{
          emptyText: (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无案件，请先新建案件">
              <Button type="primary" onClick={onSwitchToNew}>前往新建案件</Button>
            </Empty>
          ),
        }}
        columns={[
          { title: "案件名称", dataIndex: "case_name", ellipsis: true },
          { title: "编号", dataIndex: "case_id", width: 88, render: (v: number) => `#${v}` },
          {
            title: "状态",
            dataIndex: "status",
            width: 96,
            render: (v: string) => <Tag color={v === "active" ? "green" : "default"}>{v}</Tag>,
          },
          {
            title: "批次",
            dataIndex: "batch_count",
            width: 88,
            render: (v: number) => `${v} 个`,
          },
          {
            title: "更新时间",
            dataIndex: "updated_at",
            width: 168,
            render: (v: string) => (v ? v.replace("T", " ").slice(0, 16) : "—"),
          },
          {
            title: "操作",
            key: "actions",
            width: 120,
            render: (_: unknown, row: CaseInfo) => (
              <Button
                type="primary"
                icon={<FolderOpenOutlined />}
                onClick={() => {
                  onOpen(row.case_id);
                  message.success(`已打开案件：${row.case_name}`);
                }}
              >
                {row.case_id === currentCaseId ? "继续分析" : "打开"}
              </Button>
            ),
          },
        ]}
      />
    </div>
  );
}

export default FusionOpenCasePanel;
