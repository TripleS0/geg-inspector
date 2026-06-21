import { Button, Empty, Popconfirm, Space, Table, Tag, Typography, message } from "antd";
import { DeleteOutlined } from "@ant-design/icons";
import { api, CaseInfo } from "../../api";

const { Paragraph, Text, Title } = Typography;

interface FusionManageCasePanelProps {
  cases: CaseInfo[];
  loading: boolean;
  currentCaseId: number | null;
  onRefresh: () => void;
  onDeleted: (deletedCaseId: number) => void;
}

function FusionManageCasePanel({
  cases,
  loading,
  currentCaseId,
  onRefresh,
  onDeleted,
}: FusionManageCasePanelProps) {
  const deleteCase = async (caseId: number, caseName: string) => {
    try {
      await api.deleteCase(caseId);
      message.success(`已删除案件：${caseName}`);
      onDeleted(caseId);
      onRefresh();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  return (
    <div className="fusion-hub-panel fusion-manage-panel app-card">
      <div className="fusion-panel-head">
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>管理案件</Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            查看全部案件，删除不再需要的分析案件。删除后关联的人物归并与模型配置一并清除，不可恢复。
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
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无案件" />,
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
              <Space>
                {row.case_id === currentCaseId ? <Tag color="volcano">当前</Tag> : null}
                <Popconfirm
                  title="确认删除该案件？"
                  description={`将永久删除「${row.case_name}」及其人物关联、模型配置，此操作不可恢复。`}
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => void deleteCase(row.case_id, row.case_name)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      {currentCaseId ? (
        <Text type="secondary" className="fusion-manage-hint">
          当前选中案件 #{currentCaseId}。删除当前案件后，顶部案件选择将自动切换。
        </Text>
      ) : null}
    </div>
  );
}

export default FusionManageCasePanel;
