import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  List,
  Progress,
  Radio,
  Space,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import type { UploadFile } from "antd";
import { api, CASE_CHANGED_EVENT, CASE_STORAGE_KEY, CaseInfo, pollTask, type BankOcrJob, type BankOcrProfile } from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT } from "../components/WorkflowGuide";

const { Dragger } = Upload;
const { Title, Paragraph, Text } = Typography;

type SourceType = "bank" | "commercial" | "enterprise" | "wechat" | "telecom";

const SOURCE_LABELS: Record<SourceType, string> = {
  bank: "银行流水",
  commercial: "商务网招投标",
  enterprise: "工商/企业基础信息",
  wechat: "微信转账流水",
  telecom: "运营商话单",
};

function buildReadableLogs(result: Record<string, unknown>): string[] {
  const sourceType = String(result.source_type || "");
  const importBatchId = String(result.import_batch_id || "");
  const batchName = String(result.batch_name || "");
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
    logs.push(`导入批次：${batchName || importBatchId}`);
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
  const navigate = useNavigate();
  const [form] = Form.useForm<{ source_type: SourceType; bank_name: string; batch_name: string }>();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [ocrFiles, setOcrFiles] = useState<UploadFile[]>([]);
  const [bankImportMode, setBankImportMode] = useState<"excel" | "ocr">("excel");
  const [progress, setProgress] = useState<{ percent: number; message: string }>({ percent: 0, message: "" });
  const [running, setRunning] = useState(false);
  const [resultLogs, setResultLogs] = useState<string[]>([]);
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [batchCount, setBatchCount] = useState(0);
  const [ocrJobs, setOcrJobs] = useState<BankOcrJob[]>([]);
  const [ocrFormatHint, setOcrFormatHint] = useState("支持 PNG、JPEG、BMP、TIFF、WebP、GIF、SVG 及 PDF");
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(() => Number(localStorage.getItem(CASE_STORAGE_KEY)) || null);
  const sourceType = Form.useWatch("source_type", form) as SourceType | undefined;

  useEffect(() => {
    let active = true;
    const refreshGuide = async () => {
      try {
        const [caseData, batchData, ocrData, profileData] = await Promise.all([
          api.listCases(),
          api.listBatches(),
          api.listBankOcrJobs("ready"),
          api.listBankOcrProfiles().catch(() => ({ items: [] as BankOcrProfile[], format_hint: "" })),
        ]);
        if (!active) return;
        setCases(caseData.items);
        setBatchCount(batchData.items.length);
        setOcrJobs(ocrData.items);
        if (profileData.format_hint) {
          setOcrFormatHint(profileData.format_hint);
        }
        const stored = Number(localStorage.getItem(CASE_STORAGE_KEY)) || null;
        setSelectedCaseId(stored && caseData.items.some((item) => item.case_id === stored) ? stored : caseData.items[0]?.case_id ?? null);
      } catch {
        // 流程引导失败不影响导入主功能
      }
    };
    void refreshGuide();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId;
      if (nextCaseId) setSelectedCaseId(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, []);

  const selectedCase = cases.find((item) => item.case_id === selectedCaseId) ?? null;
  const guideSteps = buildWorkflowSteps({
    ...DEFAULT_WORKFLOW_SNAPSHOT,
    caseCount: cases.length,
    batchCount,
    boundBatchCount: selectedCase?.batch_count ?? 0,
    selectedCaseId,
  });

  useEffect(() => {
    const activeFiles = sourceType === "bank" && bankImportMode === "ocr" ? ocrFiles : files;
    if (activeFiles.length === 0) return;
    const current = String(form.getFieldValue("batch_name") || "").trim();
    if (current) return;
    const first = activeFiles[0].name.replace(/\.(xlsx|xls|jpg|jpeg|png|pdf)$/i, "");
    form.setFieldsValue({ batch_name: first });
  }, [files, ocrFiles, form, sourceType, bankImportMode]);

  const onSubmitExcel = async () => {
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
      const { task_id } = await api.uploadFiles(
        values.source_type,
        realFiles,
        values.bank_name || "默认来源",
        values.batch_name
      );
      const status = await pollTask(task_id, (t) =>
        setProgress({ percent: Math.max(t.progress, 10), message: t.message })
      );
      setProgress({ percent: 100, message: status.message });
      setResultLogs(buildReadableLogs({ ...(status.result || {}), batch_name: values.batch_name || "" }));
      setBatchCount((prev) => prev + 1);
      message.success("导入完成，可继续进入批次管理绑定案件");
    } catch (err) {
      message.error((err as Error).message || "导入失败");
    } finally {
      setRunning(false);
    }
  };

  const onSubmitOcr = async () => {
    if (running) return;
    try {
      const values = await form.validateFields();
      if (ocrFiles.length === 0) {
        message.warning("请先选择至少一个图片或 PDF 文件");
        return;
      }
      setRunning(true);
      setResultLogs([]);
      setProgress({ percent: 5, message: "上传并识别中…" });
      const realFiles = ocrFiles
        .map((item) => (item.originFileObj as File | undefined))
        .filter((file): file is File => Boolean(file));
      const { task_id } = await api.uploadBankOcr(
        realFiles,
        values.bank_name || "光大银行",
        values.batch_name,
        "ceb_txn_v1"
      );
      const status = await pollTask(task_id, (t) =>
        setProgress({ percent: Math.max(t.progress, 10), message: t.message })
      );
      setProgress({ percent: 100, message: status.message });
      const jobId = String(status.result?.job_id || "");
      message.success("OCR 识别完成，请进入校对页确认后录入");
      if (jobId) {
        navigate(`/bank-ocr/${jobId}`);
      }
    } catch (err) {
      message.error((err as Error).message || "OCR 识别失败");
    } finally {
      setRunning(false);
    }
  };

  const uploadSection =
    sourceType === "bank" ? (
      <Tabs
        activeKey={bankImportMode}
        onChange={(key) => setBankImportMode(key as "excel" | "ocr")}
        items={[
          {
            key: "excel",
            label: "Excel 导入",
            children: (
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
                  <p className="ant-upload-hint">支持 .xlsx、.xls；数据仅写入本地数据库</p>
                </Dragger>
              </Form.Item>
            ),
          },
          {
            key: "ocr",
            label: "图片/PDF 导入（OCR）",
            children: (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message={`离线 OCR 识别银行流水扫描件，识别后需人工校对再录入。${ocrFormatHint}`}
                />
                <Form.Item label="选择图片或 PDF">
                  <Dragger
                    className="import-upload-dragger"
                    multiple
                    beforeUpload={() => false}
                    fileList={ocrFiles}
                    accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp,.gif,.svg,.pdf"
                    onChange={(info) => setOcrFiles(info.fileList)}
                  >
                    <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                    <p className="ant-upload-text">点击或拖拽图片或 PDF 到此区域</p>
                    <p className="ant-upload-hint">{ocrFormatHint}；支持多页 PDF 合并为一个批次校对</p>
                  </Dragger>
                </Form.Item>
                {ocrJobs.length > 0 && (
                  <Card size="small" title="待校对任务" style={{ marginBottom: 16 }}>
                    <List
                      size="small"
                      dataSource={ocrJobs}
                      renderItem={(item) => (
                        <List.Item
                          actions={[
                            <Link key="review" to={`/bank-ocr/${item.job_id}`}>
                              去校对
                            </Link>,
                          ]}
                        >
                          <Space direction="vertical" size={0}>
                            <span>{item.batch_name || item.job_id.slice(0, 8)}</span>
                            <Text type="secondary">{item.bank_name} · {item.page_count} 页 · {item.rows?.length || 0} 行</Text>
                          </Space>
                          <Tag color="gold">待校对</Tag>
                        </List.Item>
                      )}
                    />
                  </Card>
                )}
              </>
            ),
          },
        ]}
      />
    ) : (
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
    );

  const onSubmit = () => {
    if (sourceType === "bank" && bankImportMode === "ocr") {
      void onSubmitOcr();
      return;
    }
    void onSubmitExcel();
  };

  return (
    <div>
      <WorkflowGuide steps={guideSteps} currentKey="import" compact />
      <Card className="app-card" bordered={false}>
        <Title level={4}>数据导入</Title>
        <Paragraph style={{ color: "#5b6477", marginBottom: 16 }}>
          支持本地表格文件批量导入；银行流水另支持图片/PDF 离线 OCR 识别后校对录入。
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
            label="批次名称"
            name="batch_name"
            tooltip="导入后可识别该批数据的名称；可在批次管理中修改"
            rules={[{ max: 120, message: "批次名称不能超过 120 个字符" }]}
          >
            <Input placeholder="如：张三建行流水 / 2024年商务网询价" />
          </Form.Item>
          <Form.Item
            label="来源标识 / 银行名称"
            name="bank_name"
            tooltip="银行流水建议填写银行简称；OCR 导入建议填写「光大银行」"
          >
            <Input placeholder="如：工商银行 / 光大银行 / 商务网 / 微信" />
          </Form.Item>
          {uploadSection}
        </Form>
        <Space>
          <Button type="primary" loading={running} onClick={onSubmit}>
            {sourceType === "bank" && bankImportMode === "ocr" ? "开始 OCR 识别" : "开始导入"}
          </Button>
          <Button
            onClick={() => {
              setFiles([]);
              setOcrFiles([]);
              setResultLogs([]);
              setProgress({ percent: 0, message: "" });
            }}
          >
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
              <Space direction="vertical" style={{ width: "100%" }}>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {resultLogs.map((line) => (
                    <li key={line} style={{ marginBottom: 4 }}>{line}</li>
                  ))}
                </ul>
                <Link to="/batches">
                  <Button type="primary">下一步：去批次管理绑定案件</Button>
                </Link>
              </Space>
            }
            showIcon
          />
        )}
      </Card>
    </div>
  );
}

export default ImportPage;
