import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Space,
  Typography,
  Progress,
  message,
} from "antd";
import { Link, useNavigate } from "react-router-dom";
import { api, CASE_CHANGED_EVENT, CASE_STORAGE_KEY, CaseInfo, pollTask } from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT } from "../components/WorkflowGuide";
import { useDataImportForm } from "../components/data-import/DataImportForm";
import { buildReadableLogs } from "../components/data-import/importHelpers";

const { Title, Paragraph } = Typography;

function ImportPage() {
  const navigate = useNavigate();
  const importForm = useDataImportForm({ allowOcr: true });
  const [progress, setProgress] = useState<{ percent: number; message: string }>({ percent: 0, message: "" });
  const [running, setRunning] = useState(false);
  const [resultLogs, setResultLogs] = useState<string[]>([]);
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [batchCount, setBatchCount] = useState(0);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(() => Number(localStorage.getItem(CASE_STORAGE_KEY)) || null);

  useEffect(() => {
    let active = true;
    const refreshGuide = async () => {
      try {
        const [caseData, batchData] = await Promise.all([api.listCases(), api.listBatches()]);
        if (!active) return;
        setCases(caseData.items);
        setBatchCount(batchData.items.length);
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

  const onSubmitExcel = async () => {
    if (running) return;
    try {
      const { values, files } = await importForm.getPayload();
      setRunning(true);
      setResultLogs([]);
      setProgress({ percent: 5, message: "上传文件中…" });
      const { task_id } = await api.uploadFiles(
        values.source_type,
        files,
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
      const { values, files } = await importForm.getPayload();
      if (files.length === 0) {
        message.warning("请先选择至少一个图片或 PDF 文件");
        return;
      }
      setRunning(true);
      setResultLogs([]);
      setProgress({ percent: 5, message: "上传并识别中…" });
      const { task_id } = await api.uploadBankOcr(
        files,
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

  const onSubmit = () => {
    if (importForm.isOcrMode) {
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
          支持本地表格文件批量导入；银行流水另支持图片/PDF 离线 OCR 识别后校对录入。商务网请将多个发电厂/采购单位文件在同一批次中多选导入，系统会按批次整合后统一分析。
        </Paragraph>
        {importForm.formElement}
        <Space>
          <Button type="primary" loading={running} onClick={onSubmit}>
            {importForm.isOcrMode ? "开始 OCR 识别" : "开始导入"}
          </Button>
          <Button
            onClick={() => {
              importForm.reset();
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
