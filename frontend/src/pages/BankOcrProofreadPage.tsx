import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Pagination,
  Space,
  Switch,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  pollTask,
  type BankOcrJob,
  type BankOcrRow,
} from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT } from "../components/WorkflowGuide";

const { Title, Paragraph, Text } = Typography;
const LOW_CONFIDENCE = 0.75;

function BankOcrProofreadPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<BankOcrJob | null>(null);
  const [rows, setRows] = useState<BankOcrRow[]>([]);
  const [header, setHeader] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [showAllPages, setShowAllPages] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [selectedRowIndex, setSelectedRowIndex] = useState<number | null>(null);

  const refreshJob = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const data = await api.getBankOcrJob(jobId);
      setJob(data);
      setRows(data.rows || []);
      setHeader(data.header || {});
      if (data.pages?.length) {
        setCurrentPage((prev) => Math.min(prev, data.pages.length) || 1);
      }
    } catch (err) {
      message.error((err as Error).message || "加载 OCR 任务失败");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void refreshJob();
  }, [refreshJob]);

  const visibleRows = useMemo(() => {
    if (showAllPages) return rows;
    return rows.filter((row) => row.page_index === currentPage);
  }, [rows, showAllPages, currentPage]);

  const tableColumns = job?.table_columns || [];

  const updateCell = (rowIndex: number, column: string, value: string) => {
    setRows((prev) =>
      prev.map((row) =>
        row.row_index === rowIndex
          ? {
              ...row,
              cells: { ...row.cells, [column]: value },
              is_edited: true,
            }
          : row
      )
    );
  };

  const addRow = () => {
    const pageIndex = showAllPages ? currentPage : currentPage;
    const nextIndex = rows.length ? Math.max(...rows.map((row) => row.row_index)) + 1 : 0;
    const emptyCells = Object.fromEntries(tableColumns.map((column) => [column, ""]));
    setRows((prev) => [
      ...prev,
      {
        page_index: pageIndex,
        row_index: nextIndex,
        cells: emptyCells,
        confidence: Object.fromEntries(tableColumns.map((column) => [column, 1])),
        is_edited: true,
      },
    ]);
  };

  const removeRow = (rowIndex: number) => {
    setRows((prev) => prev.filter((row) => row.row_index !== rowIndex));
  };

  const columns: ColumnsType<BankOcrRow> = [
    {
      title: "页",
      dataIndex: "page_index",
      width: 56,
      fixed: "left",
    },
    ...tableColumns.map((column) => ({
      title: column,
      dataIndex: column,
      width: column.includes("摘要") ? 220 : 140,
      render: (_: unknown, record: BankOcrRow) => {
        const value = record.cells?.[column] || "";
        const confidence = record.confidence?.[column] ?? 1;
        const low = confidence < LOW_CONFIDENCE && !record.is_edited;
        return (
          <Input
            size="small"
            value={value}
            status={low ? "warning" : undefined}
            style={low ? { background: "#fffbe6" } : undefined}
            onChange={(event) => updateCell(record.row_index, column, event.target.value)}
          />
        );
      },
    })),
    {
      title: "操作",
      key: "actions",
      width: 72,
      fixed: "right",
      render: (_: unknown, record: BankOcrRow) => (
        <Button type="link" danger size="small" onClick={() => removeRow(record.row_index)}>
          删除
        </Button>
      ),
    },
  ];

  const onSaveDraft = async () => {
    if (!jobId) return;
    setSaving(true);
    try {
      const data = await api.saveBankOcrRows(jobId, rows);
      await api.saveBankOcrHeader(jobId, header);
      setJob(data);
      setRows(data.rows || []);
      setHeader(data.header || {});
      message.success("草稿已保存");
    } catch (err) {
      message.error((err as Error).message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const onCommit = async () => {
    if (!jobId) return;
    setCommitting(true);
    try {
      await api.saveBankOcrRows(jobId, rows);
      await api.saveBankOcrHeader(jobId, header);
      const { task_id } = await api.commitBankOcrJob(jobId);
      const status = await pollTask(task_id);
      message.success("原始表已录入；请配置银行模板映射后在批次管理中标准化");
      const importBatchId = String(status.result?.import_batch_id || "");
      navigate(importBatchId ? `/data-center/manage?highlight=${encodeURIComponent(importBatchId)}` : "/data-center/manage");
    } catch (err) {
      message.error((err as Error).message || "录入失败");
    } finally {
      setCommitting(false);
    }
  };

  const onDiscard = async () => {
    if (!jobId) return;
    try {
      await api.deleteBankOcrJob(jobId);
      message.success("已放弃该 OCR 草稿");
      navigate("/fusion-cockpit/new");
    } catch (err) {
      message.error((err as Error).message || "删除失败");
    }
  };

  const guideSteps = buildWorkflowSteps({
    ...DEFAULT_WORKFLOW_SNAPSHOT,
    batchCount: 1,
  });

  if (!jobId) {
    return <div className="app-card">缺少 OCR 任务编号，<Link to="/fusion-cockpit/new">返回新建案件</Link></div>;
  }

  return (
    <div>
      <WorkflowGuide steps={guideSteps} currentKey="import" compact />
      <Card className="app-card" bordered={false} loading={loading}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div>
            <Title level={4}>银行流水 OCR 校对</Title>
            <Paragraph style={{ color: "#5b6477", marginBottom: 0 }}>
              左侧对照原图，右侧修正识别结果。列名保持 OCR 原始表头（如存入金额、检出金额），不会自动合并为标准字段。
              确认无误后录入原始表，再到
              <Link to="/data-center/manage/bank-templates"> 银行模板录入 </Link>
              配置映射，并在批次管理中执行标准化。
            </Paragraph>
          </div>

          {job?.status === "committed" && (
            <Alert type="success" showIcon message="该任务已完成录入，如需修改请重新导入。" />
          )}
          {job?.error_message ? <Alert type="error" showIcon message={job.error_message} /> : null}

          <Form layout="inline">
            {(job?.header_fields || []).map((field) => (
              <Form.Item key={field} label={field}>
                <Input
                  value={header[field] || ""}
                  onChange={(event) => setHeader((prev) => ({ ...prev, [field]: event.target.value }))}
                  style={{ width: 220 }}
                />
              </Form.Item>
            ))}
          </Form>

          <div className="bank-ocr-proofread-layout">
            <div className="bank-ocr-proofread-image-panel">
              <Space wrap style={{ marginBottom: 12 }}>
                <Text>缩放</Text>
                <InputNumber min={0.5} max={2.5} step={0.1} value={zoom} onChange={(value) => setZoom(Number(value) || 1)} />
                {job?.page_count ? (
                  <Pagination
                    simple
                    current={currentPage}
                    total={job.page_count}
                    pageSize={1}
                    onChange={(page) => setCurrentPage(page)}
                  />
                ) : null}
              </Space>
              <div className="bank-ocr-proofread-image-wrap">
                <img
                  className="bank-ocr-proofread-image"
                  src={api.bankOcrPageImageUrl(jobId, currentPage)}
                  alt={`第 ${currentPage} 页`}
                  style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }}
                />
              </div>
            </div>

            <div className="bank-ocr-proofread-table-panel">
              <Space wrap style={{ marginBottom: 12 }}>
                <Switch checked={showAllPages} onChange={setShowAllPages} checkedChildren="全部页" unCheckedChildren="当前页" />
                <Button onClick={addRow}>新增行</Button>
                <Text type="secondary">共 {visibleRows.length} 行</Text>
              </Space>
              <Table
                size="small"
                rowKey="row_index"
                columns={columns}
                dataSource={visibleRows}
                scroll={{ x: 1200, y: 520 }}
                pagination={false}
                onRow={(record) => ({
                  onClick: () => setSelectedRowIndex(record.row_index),
                  className: selectedRowIndex === record.row_index ? "bank-ocr-row-selected" : "",
                })}
              />
            </div>
          </div>

          <Space wrap>
            <Button onClick={() => void onSaveDraft()} loading={saving} disabled={job?.status === "committed"}>
              保存草稿
            </Button>
            <Button type="primary" onClick={() => void onCommit()} loading={committing} disabled={job?.status === "committed"}>
              确认录入原始表
            </Button>
            <Link to="/data-center/manage/bank-templates">银行模板录入</Link>
            <Button danger onClick={() => void onDiscard()} disabled={job?.status === "committed"}>
              放弃
            </Button>
            <Link to="/fusion-cockpit/new">返回新建案件</Link>
          </Space>
        </Space>
      </Card>
    </div>
  );
}

export default BankOcrProofreadPage;
