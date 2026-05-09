import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Card, Popconfirm, Segmented, Space, Table, Tag, Typography, message } from "antd";
import { useNavigate } from "react-router-dom";
import { api, BatchInfo, pollTask } from "../api";

const { Title, Paragraph } = Typography;

type Source = "all" | "bank" | "commercial" | "enterprise";

const SOURCE_LABELS: Record<Source, string> = {
  all: "全部",
  bank: "银行",
  commercial: "商务网",
  enterprise: "工商",
};

const SOURCE_TAG_LABELS: Record<string, string> = {
  bank: "银行流水",
  commercial: "商务网",
  enterprise: "工商信息",
};

function BatchesPage() {
  const [filter, setFilter] = useState<Source>("all");
  const [items, setItems] = useState<BatchInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listBatches(filter === "all" ? undefined : filter);
      setItems(data.items);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const exportRow = async (row: BatchInfo) => {
    if (row.source_type !== "bank" && row.source_type !== "commercial") {
      message.info("当前类型暂不支持一键导出");
      return;
    }
    try {
      message.loading({ content: "正在生成电子表格…", key: "export-task" });
      const { task_id } = await api.exportBatch(row.source_type, row.import_batch_id);
      const status = await pollTask(task_id);
      message.success({ content: `导出完成：${(status.result as { output_path?: string }).output_path}`, key: "export-task", duration: 5 });
    } catch (err) {
      message.error({ content: (err as Error).message, key: "export-task" });
    }
  };

  const deleteRow = async (row: BatchInfo) => {
    try {
      await api.deleteBatch(row.import_batch_id);
      message.success("已删除该批次及相关数据");
      void fetchData();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: "批次编号",
        dataIndex: "import_batch_id",
        render: (val: string) => <code>{val}</code>,
      },
      {
        title: "来源",
        dataIndex: "source_type",
        width: 120,
        render: (val: string) => (
          <Tag
            color={
              val === "bank" ? "blue" : val === "commercial" ? "purple" : val === "enterprise" ? "green" : "default"
            }
          >
            {SOURCE_TAG_LABELS[val] || val}
          </Tag>
        ),
      },
      { title: "条数", dataIndex: "file_count", width: 88 },
      { title: "最近导入时间", dataIndex: "imported_at", width: 200 },
      {
        title: "操作",
        key: "actions",
        width: 400,
        render: (_: unknown, row: BatchInfo) => (
          <Space wrap>
            {row.source_type === "bank" && (
              <Button size="small" type="primary" onClick={() => navigate(`/bank?batch=${encodeURIComponent(row.import_batch_id)}`)}>
                银行分析
              </Button>
            )}
            {row.source_type === "commercial" && (
              <Button size="small" type="primary" onClick={() => navigate(`/risk?batch=${encodeURIComponent(row.import_batch_id)}`)}>
                风险分析
              </Button>
            )}
            {row.source_type === "enterprise" && (
              <Button
                size="small"
                type="primary"
                onClick={() => navigate(`/risk?enterpriseBatch=${encodeURIComponent(row.import_batch_id)}`)}
              >
                关联风险
              </Button>
            )}
            <Button size="small" onClick={() => void exportRow(row)}>
              导出电子表格
            </Button>
            <Popconfirm
              title="确定删除该批次？"
              description="将删除本批 raw/std 与元数据；商务网还会清除匹配与风险结果；工商会清除主体及依赖的匹配行。不可恢复。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => void deleteRow(row)}
            >
              <Button size="small" danger>
                删除批次
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [navigate, fetchData]
  );

  return (
    <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>批次管理</Title>
        <Space>
          <Segmented
            options={(Object.keys(SOURCE_LABELS) as Source[]).map((key) => ({ value: key, label: SOURCE_LABELS[key] }))}
            value={filter}
            onChange={(val) => setFilter(val as Source)}
          />
          <Button onClick={fetchData}>刷新</Button>
        </Space>
      </div>
      <Paragraph style={{ color: "#5b6477" }}>
        「全部」包含银行、商务网与工商（企查查/工商库）批次，按导入时间混合排序。删除批次会移除该批在库中的业务数据与元数据，请谨慎操作。
      </Paragraph>
      <Table
        rowKey="import_batch_id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{ pageSize: 10 }}
        size="small"
      />
    </Card>
  );
}

export default BatchesPage;
