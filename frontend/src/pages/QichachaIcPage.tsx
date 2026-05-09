import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Input,
  InputNumber,
  Space,
  Table,
  Tabs,
  Typography,
  Upload,
  message,
} from "antd";
import { InboxOutlined, IdcardOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { UploadFile } from "antd";
import { useNavigate } from "react-router-dom";
import {
  api,
  exportQichachaExcelFromRows,
  queryQichachaBasicDetails,
  type QichachaLogItem,
} from "../api";

const { TextArea } = Input;
const { Dragger } = Upload;
const { Paragraph, Title } = Typography;

const LOG_COLUMNS: ColumnsType<QichachaLogItem> = [
  { title: "时间", dataIndex: "created_at", key: "created_at", width: 170 },
  { title: "查询词", dataIndex: "query_keyword", key: "query_keyword", ellipsis: true },
  { title: "来源", dataIndex: "input_source", key: "input_source", width: 88 },
  { title: "接口状态", dataIndex: "api_status", key: "api_status", width: 96 },
  { title: "匹配名称", dataIndex: "matched_name", key: "matched_name", ellipsis: true },
  { title: "统一社会信用代码", dataIndex: "credit_code", key: "credit_code", width: 160, ellipsis: true },
  { title: "订单号", dataIndex: "order_number", key: "order_number", width: 200, ellipsis: true },
  { title: "耗时(ms)", dataIndex: "duration_ms", key: "duration_ms", width: 96 },
  { title: "错误", dataIndex: "error_detail", key: "error_detail", ellipsis: true },
];

const PREVIEW_COL_PRIORITY = [
  "query_keyword",
  "Name",
  "CreditCode",
  "qcc_Status",
  "qcc_Message",
  "qcc_OrderNumber",
  "error_message",
];

function buildPreviewColumns(rows: Record<string, unknown>[]): ColumnsType<Record<string, unknown>> {
  if (!rows.length) return [];
  const keys = Object.keys(rows[0]);
  const rest = keys.filter((k) => !PREVIEW_COL_PRIORITY.includes(k)).sort();
  const ordered = [...PREVIEW_COL_PRIORITY.filter((k) => keys.includes(k)), ...rest];
  return ordered.map((k) => ({
    title: k,
    dataIndex: k,
    key: k,
    ellipsis: true,
    render: (v: unknown) => {
      if (v === null || v === undefined) return "";
      if (typeof v === "object") return JSON.stringify(v);
      return String(v);
    },
  }));
}

function QichachaIcPage() {
  const navigate = useNavigate();
  const [manualText, setManualText] = useState("");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [columnIndex, setColumnIndex] = useState(0);
  const [columnLetter, setColumnLetter] = useState("");
  const [skipHeader, setSkipHeader] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[]>([]);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<QichachaLogItem[]>([]);
  const [logLoading, setLogLoading] = useState(false);

  const previewColumns = useMemo(() => buildPreviewColumns(previewRows), [previewRows]);

  const loadLogs = useCallback(async () => {
    setLogLoading(true);
    try {
      const { items } = await api.qichachaQueryLogs(200, 0);
      setLogs(items);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLogLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  const onQuery = async () => {
    const f = fileList[0]?.originFileObj;
    if (!manualText.trim() && !f) {
      message.warning("请输入企业名称或上传名单文件");
      return;
    }
    setQueryLoading(true);
    try {
      const result = await queryQichachaBasicDetails({
        keywordsText: manualText.trim() || undefined,
        file: f ?? null,
        columnIndex,
        columnLetter: columnLetter.trim() || undefined,
        skipHeader,
      });
      setLastRunId(result.run_id);
      setPreviewRows(result.rows);
      message.success(`查询完成，共 ${result.count} 条`);
      await loadLogs();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setQueryLoading(false);
    }
  };

  const onExport = async () => {
    if (!previewRows.length) {
      message.warning("请先查询，预览无误后再导出");
      return;
    }
    setExportLoading(true);
    try {
      const { blob, runId } = await exportQichachaExcelFromRows(previewRows, lastRunId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `qichacha_${runId || Date.now()}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      message.success("已导出 Excel");
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setExportLoading(false);
    }
  };

  const onIngestProfile = async () => {
    if (!previewRows.length) {
      message.warning("请先查询，预览无误后再导入工商库");
      return;
    }
    setIngestLoading(true);
    try {
      const res = await api.ingestQichachaProfile(previewRows, lastRunId);
      message.success(
        `已写入工商库：批次 ${res.import_batch_id.slice(0, 8)}…，共 ${res.rows_total} 条`
      );
      navigate(`/risk?enterpriseBatch=${encodeURIComponent(res.import_batch_id)}`);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setIngestLoading(false);
    }
  };

  return (
    <div>
      <div className="app-card">
        <Title level={4} style={{ marginTop: 0 }}>
          <IdcardOutlined /> 工商信息录入（企查查）
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 16 }}>
          先点击「查询」调用企查查并写入本地日志，在下方预览核对后可「导入工商库」写入标准企业表，或「导出 Excel」。Excel 名单：每行一家企业；TXT：每行一名。密钥：环境变量{" "}
          <code>QICHACHA_APP_KEY</code> / <code>QICHACHA_SECRET_KEY</code> → <code>data/qichacha_config.json</code> 等（见此前说明）。
        </Paragraph>
        <Tabs
          items={[
            {
              key: "manual",
              label: "手动输入",
              children: (
                <TextArea
                  rows={10}
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  placeholder="每行一个企业名称，或用英文逗号 / 中文逗号分隔"
                />
              ),
            },
            {
              key: "file",
              label: "文件导入",
              children: (
                <div>
                  <Dragger
                    accept=".xlsx,.xls,.txt"
                    multiple={false}
                    beforeUpload={() => false}
                    fileList={fileList}
                    onChange={({ fileList: fl }) => setFileList(fl.slice(-1))}
                  >
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">点击或拖拽上传 .xlsx / .xls / .txt</p>
                    <p className="ant-upload-hint">Excel 每行一家公司；可指定列序号或列字母，可选跳过首行表头</p>
                  </Dragger>
                  <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
                    <span>列序号（0=A）</span>
                    <InputNumber min={0} value={columnIndex} onChange={(v) => setColumnIndex(Number(v) ?? 0)} />
                    <span>列字母（优先于序号）</span>
                    <Input
                      value={columnLetter}
                      onChange={(e) => setColumnLetter(e.target.value)}
                      placeholder="如 B"
                      style={{ width: 72 }}
                    />
                    <Checkbox checked={skipHeader} onChange={(e) => setSkipHeader(e.target.checked)}>
                      跳过首行（表头）
                    </Checkbox>
                  </div>
                </div>
              ),
            },
          ]}
        />
        <Space style={{ marginTop: 16 }} wrap>
          <Button type="primary" onClick={() => void onQuery()} loading={queryLoading}>
            查询
          </Button>
          <Button onClick={() => void onExport()} loading={exportLoading} disabled={!previewRows.length}>
            导出 Excel
          </Button>
          <Button
            type="default"
            onClick={() => void onIngestProfile()}
            loading={ingestLoading}
            disabled={!previewRows.length}
          >
            导入工商库
          </Button>
        </Space>
        {lastRunId && (
          <Paragraph style={{ marginTop: 12, marginBottom: 0 }} type="secondary">
            当前预览批次 run_id：{lastRunId}
          </Paragraph>
        )}
      </div>

      <Card title="查询结果预览" style={{ marginTop: 16 }}>
        <Table<Record<string, unknown>>
          size="small"
          rowKey={(_, i) => String(i)}
          columns={previewColumns}
          dataSource={previewRows}
          scroll={{ x: "max-content" }}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          locale={{ emptyText: "暂无数据，请先查询" }}
        />
      </Card>

      <Card
        title="查询日志"
        style={{ marginTop: 16 }}
        extra={
          <Button size="small" onClick={() => void loadLogs()}>
            刷新
          </Button>
        }
      >
        <Table<QichachaLogItem>
          size="small"
          loading={logLoading}
          rowKey="log_id"
          columns={LOG_COLUMNS}
          dataSource={logs}
          scroll={{ x: 1200 }}
          pagination={{ pageSize: 20, showSizeChanger: true }}
        />
      </Card>
    </div>
  );
}

export default QichachaIcPage;
