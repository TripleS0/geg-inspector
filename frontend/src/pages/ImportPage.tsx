import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Progress,
  Radio,
  Space,
  Typography,
  Upload,
  message,
} from "antd";
import { InboxOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd";
import { api, pollTask } from "../api";

const { Dragger } = Upload;
const { Title, Paragraph } = Typography;

type SourceType = "bank" | "commercial" | "enterprise";

const SOURCE_LABELS: Record<SourceType, string> = {
  bank: "银行流水",
  commercial: "商务网招投标",
  enterprise: "工商/企业基础信息",
};

function buildReadableLogs(result: Record<string, unknown>): string[] {
  const sourceType = String(result.source_type || "");
  const importBatchId = String(result.import_batch_id || "");
  const filesTotal = Number(result.files_total || 0);
  const failedFiles = Number(result.failed_files || 0);
  const rowsTotal = Number(result.rows_total || 0);
  const sheetsTotal = Number(result.sheets_total || 0);
  const newTemplates = Number(result.new_templates || 0);
  const standardizedRows = Number(result.standardized_rows || 0);

  const sourceLabel = SOURCE_LABELS[sourceType as SourceType] || sourceType || "未知来源";
  const logs: string[] = [];
  logs.push(`来源类型：${sourceLabel}`);
  if (importBatchId) {
    logs.push(`导入批次：${importBatchId}`);
  }
  logs.push(`已处理文件：${filesTotal} 个`);
  logs.push(`失败文件：${failedFiles} 个`);
  if (sheetsTotal > 0) {
    logs.push(`识别工作表：${sheetsTotal} 个`);
  }
  if (rowsTotal > 0) {
    logs.push(`入库总行数：${rowsTotal} 行`);
  }
  if (newTemplates > 0) {
    logs.push(`新增模板：${newTemplates} 个`);
  }
  if (standardizedRows > 0) {
    logs.push(`标准化写入：${standardizedRows} 行`);
  }
  if (failedFiles === 0) {
    logs.push("处理状态：全部成功");
  } else {
    logs.push("处理状态：部分文件失败，请检查文件格式和日志");
  }
  return logs;
}

function ImportPage() {
  const [form] = Form.useForm<{ source_type: SourceType; bank_name: string }>();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [progress, setProgress] = useState<{ percent: number; message: string }>({ percent: 0, message: "" });
  const [running, setRunning] = useState(false);
  const [resultLogs, setResultLogs] = useState<string[]>([]);

  const onSubmit = async () => {
    if (running) return;
    try {
      const values = await form.validateFields();
      if (files.length === 0) {
        message.warning("请先选择至少一个表格文件（.xlsx 或 .xls）");
        return;
      }
      setRunning(true);
      setResultLogs([]);
      setProgress({ percent: 5, message: "上传文件中…" });
      const realFiles = files
        .map((item) => (item.originFileObj as File | undefined))
        .filter((file): file is File => Boolean(file));
      const { task_id } = await api.uploadFiles(values.source_type, realFiles, values.bank_name || "默认来源");
      const status = await pollTask(task_id, (t) =>
        setProgress({ percent: Math.max(t.progress, 10), message: t.message })
      );
      setProgress({ percent: 100, message: status.message });
      setResultLogs(buildReadableLogs(status.result || {}));
      message.success("导入完成，可在批次管理或数据表浏览中查看");
    } catch (err) {
      message.error((err as Error).message || "导入失败");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <Card className="app-card" bordered={false}>
        <Title level={4}>数据导入</Title>
        <Paragraph style={{ color: "#5b6477", marginBottom: 16 }}>
          支持本地表格文件（.xlsx / .xls）批量导入；导入完成后会写入本地数据库，下次启动即可直接查询。
        </Paragraph>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ source_type: "bank", bank_name: "默认来源" }}
        >
          <Form.Item label="数据来源" name="source_type" rules={[{ required: true }]}>
            <Radio.Group>
              {(Object.keys(SOURCE_LABELS) as SourceType[]).map((key) => (
                <Radio.Button value={key} key={key}>
                  {SOURCE_LABELS[key]}
                </Radio.Button>
              ))}
            </Radio.Group>
          </Form.Item>
          <Form.Item
            label="来源标识 / 银行名称"
            name="bank_name"
            tooltip="银行流水建议填写银行简称；商务网/工商可使用默认值"
          >
            <Input placeholder="如：工商银行 / 商务网 / 企查查" />
          </Form.Item>
          <Form.Item label="选择表格文件">
            <Dragger
              className="import-upload-dragger"
              multiple
              beforeUpload={() => false}
              fileList={files}
              accept=".xlsx,.xls"
              onChange={(info) => setFiles(info.fileList)}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">点击或拖拽表格文件到此区域</p>
              <p className="ant-upload-hint">支持多选；支持扩展名 .xlsx、.xls；数据仅写入本地数据库，不会上传到外网</p>
            </Dragger>
          </Form.Item>
        </Form>
        <Space>
          <Button type="primary" loading={running} onClick={onSubmit}>开始导入</Button>
          <Button onClick={() => { setFiles([]); setResultLogs([]); setProgress({ percent: 0, message: "" }); }}>
            清空
          </Button>
        </Space>
        {progress.percent > 0 && (
          <div style={{ marginTop: 16 }}>
            <Progress
              percent={progress.percent}
              status={running ? "active" : "success"}
              strokeColor={{ "0%": "#ffb366", "100%": "#d94832" }}
            />
            <div style={{ color: "#5b6477", marginTop: 4 }}>{progress.message}</div>
          </div>
        )}
        {resultLogs.length > 0 && (
          <Alert
            type="success"
            style={{ marginTop: 16 }}
            message="导入结果"
            description={
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {resultLogs.map((line) => (
                  <li key={line} style={{ marginBottom: 4 }}>{line}</li>
                ))}
              </ul>
            }
            showIcon
          />
        )}
      </Card>
    </div>
  );
}

export default ImportPage;
