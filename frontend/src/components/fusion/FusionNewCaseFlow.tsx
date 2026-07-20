import { useMemo, useRef, useState } from "react";
import {
  Button,
  Checkbox,
  Input,
  List,
  Progress,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, LeftOutlined, RightOutlined } from "@ant-design/icons";
import { api, emitCaseChanged, persistSelectedCaseId, pollTask } from "../../api";
import PersonLinkingPanel from "./PersonLinkingPanel";
import { SOURCE_LABELS, SourceType } from "../data-import/constants";
import { useDataImportForm } from "../data-import/DataImportForm";

const { Paragraph, Text, Title } = Typography;

interface FusionNewCaseFlowProps {
  onComplete: (caseId: number) => void;
}

type FlowStep = 1 | 2 | 3;
type FlowPhase = "draft" | "importing" | "linking";

function FusionNewCaseFlow({ onComplete }: FusionNewCaseFlowProps) {
  const [step, setStep] = useState<FlowStep>(1);
  const [caseName, setCaseName] = useState("");
  const [phase, setPhase] = useState<FlowPhase>("draft");
  const [linkingCaseId, setLinkingCaseId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ percent: 0, message: "" });
  const importForm = useDataImportForm({ allowOcr: false, compact: false, hideUploadList: true });
  const queueRef = useRef<HTMLDivElement>(null);
  const dragOriginRef = useRef<{ x: number; y: number } | null>(null);
  const dragBaseSelectionRef = useRef<string[]>([]);
  const [selectionBox, setSelectionBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

  const queuedFiles = useMemo(
    () => importForm.selectedExcelPayloads.flatMap((payload) =>
      payload.files.map((file) => ({
        file,
        sourceType: payload.values.source_type,
      }))
    ),
    [importForm.selectedExcelPayloads]
  );

  const updateDragSelection = (clientX: number, clientY: number) => {
    const root = queueRef.current;
    const origin = dragOriginRef.current;
    if (!root || !origin) return;
    const rootRect = root.getBoundingClientRect();
    const left = Math.min(origin.x, clientX);
    const right = Math.max(origin.x, clientX);
    const top = Math.min(origin.y, clientY);
    const bottom = Math.max(origin.y, clientY);
    setSelectionBox({ left: left - rootRect.left, top: top - rootRect.top, width: right - left, height: bottom - top });
    const hitNames = Array.from(root.querySelectorAll<HTMLElement>("[data-bank-file-name]"))
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return left <= rect.right && right >= rect.left && top <= rect.bottom && bottom >= rect.top;
      })
      .map((element) => element.dataset.bankFileName || "")
      .filter(Boolean);
    importForm.replaceBankFileSelection([...dragBaseSelectionRef.current, ...hitNames]);
  };

  const startQueueSelection = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("button, input, a, .ant-select, .ant-checkbox-wrapper")) return;
    if (!target.closest("[data-bank-file-name], .ant-list-items")) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragOriginRef.current = { x: event.clientX, y: event.clientY };
    dragBaseSelectionRef.current = event.ctrlKey || event.metaKey ? importForm.selectedBankFiles : [];
    updateDragSelection(event.clientX, event.clientY);
  };

  const finishQueueSelection = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragOriginRef.current) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    dragOriginRef.current = null;
    setSelectionBox(null);
  };

  const goNextFromStep1 = () => {
    if (!caseName.trim()) {
      message.warning("请输入案件名称");
      return;
    }
    setStep(2);
  };

  const startImport = async () => {
    const name = caseName.trim();
    if (!name) {
      message.warning("请输入案件名称");
      setStep(1);
      return;
    }

    let importQueue;
    try {
      importQueue = await importForm.getAllPayloads();
    } catch (err) {
      message.warning((err as Error).message || "请至少选择一批导入数据");
      return;
    }

    if (!importQueue.length) {
      message.warning("请至少选择一批导入数据");
      return;
    }

    setRunning(true);
    setPhase("importing");
    setProgress({ percent: 2, message: "正在创建案件…" });

    try {
      const created = await api.createCase({ case_name: name });
      const caseId = created.case_id;
      persistSelectedCaseId(caseId);
      emitCaseChanged(caseId);

      const batchIds: string[] = [];
      const uploadWeight = 70;

      for (let index = 0; index < importQueue.length; index += 1) {
        const item = importQueue[index];
        const { values, files } = item;
        const label = SOURCE_LABELS[values.source_type];
        const base = 8 + Math.round((index / importQueue.length) * uploadWeight);
        setProgress({
          percent: base,
          message: `正在导入${label}（${index + 1}/${importQueue.length}）…`,
        });

        const { task_id } = await api.uploadFiles(
          values.source_type,
          files,
          values.bank_name || "默认来源",
          values.batch_name,
          undefined,
          item.sheetAssignments
        );
        const status = await pollTask(task_id, (task) => {
          const slice = uploadWeight / importQueue.length;
          setProgress({
            percent: Math.min(8 + uploadWeight, base + Math.round((task.progress / 100) * slice * 0.9)),
            message: task.message || `正在导入${label}…`,
          });
        });
        const result = (status.result || {}) as Record<string, unknown>;
        const batchId = String(result.import_batch_id || "");
        const rowsTotal = Number(result.rows_total ?? 0);
        const failedFiles = Number(result.failed_files ?? 0);
        if (!batchId) {
          throw new Error(`${label} 导入完成但未返回批次编号`);
        }
        if (rowsTotal <= 0) {
          throw new Error(
            `${label} 导入未产生有效数据（${failedFiles} 个文件失败），请检查文件后重试；勿重复添加相同来源`
          );
        }
        batchIds.push(batchId);
      }

      setProgress({ percent: 90, message: "正在绑定批次到案件…" });
      await api.bindCaseBatches(caseId, batchIds);
      setProgress({ percent: 100, message: "导入完成" });

      setLinkingCaseId(caseId);
      setPhase("linking");
      setStep(3);
      message.success("数据导入完成，请完成人物标识关联");
    } catch (err) {
      message.error((err as Error).message || "新建案件失败");
      setPhase("draft");
      setProgress({ percent: 0, message: "" });
    } finally {
      setRunning(false);
    }
  };

  const enterCockpit = () => {
    if (!linkingCaseId) return;
    message.success("已进入融合分析驾驶舱");
    onComplete(linkingCaseId);
  };

  const wizardHead = (
    <div className="fusion-wizard-head">
      <Text className="fusion-wizard-step-label">新建案件 · 第 {step} / 3 步</Text>
      <div className="fusion-wizard-dots">
        {[1, 2, 3].map((item) => (
          <span key={item} className={`fusion-wizard-dot${item === step ? " active" : item < step ? " done" : ""}`} />
        ))}
      </div>
    </div>
  );

  if (step === 3) {
    return (
      <div className="fusion-new-case-flow fusion-new-case-flow-step3">
        {wizardHead}
        {linkingCaseId ? (
          <PersonLinkingPanel
            caseId={linkingCaseId}
            embedded
            wizardMode
            initialAutoSetup
            onEnterCockpit={enterCockpit}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="fusion-new-case-flow">
      <div className="fusion-new-case-wizard app-card">
        {wizardHead}

        {step === 1 ? (
          <div className="fusion-wizard-body fusion-wizard-body-step1">
            <Title level={3} className="fusion-wizard-title">请输入案件名称</Title>
            <Paragraph type="secondary" className="fusion-wizard-desc">
              为本次分析起一个便于识别的名称。
            </Paragraph>
            <Input
              className="fusion-wizard-case-input"
              size="large"
              placeholder="例如：华南机电调查"
              value={caseName}
              disabled={phase !== "draft"}
              onChange={(event) => setCaseName(event.target.value)}
              onPressEnter={goNextFromStep1}
              maxLength={120}
              autoFocus
            />
            <div className="fusion-wizard-actions">
              <Button type="primary" size="large" icon={<RightOutlined />} onClick={goNextFromStep1}>
                下一步
              </Button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="fusion-wizard-body fusion-wizard-body-step2">
            <Title level={3} className="fusion-wizard-title">请导入数据</Title>
            <Paragraph type="secondary" className="fusion-wizard-desc">
              选择数据来源并上传文件，可多次添加不同批次。商务网请将多个发电厂/采购单位文件放在同一批中一并导入；银行流水可配置模板后加入待导入列表，完成后点击「开始导入」。
            </Paragraph>

            {phase === "importing" ? (
              <div className="fusion-wizard-progress">
                <Progress
                  percent={progress.percent}
                  status={progress.percent >= 100 ? "success" : "active"}
                  strokeColor={{ "0%": "#ffb366", "100%": "#d94832" }}
                  strokeWidth={12}
                />
                <Paragraph type="secondary" className="fusion-wizard-progress-text">
                  {progress.message}
                </Paragraph>
              </div>
            ) : (
              <>
                <div className="fusion-import-form-wrap fusion-wizard-import-form">{importForm.formElement}</div>

                {queuedFiles.length > 0 ? (
                  <div
                    ref={queueRef}
                    style={{ position: "relative", userSelect: selectionBox ? "none" : undefined }}
                    onPointerDown={startQueueSelection}
                    onPointerMove={(event) => {
                      if (dragOriginRef.current) updateDragSelection(event.clientX, event.clientY);
                    }}
                    onPointerUp={finishQueueSelection}
                    onPointerCancel={finishQueueSelection}
                  >
                  <List
                    className="fusion-import-queue fusion-wizard-import-queue"
                    bordered
                    header={
                      <Space direction="vertical" size={12} style={{ width: "100%" }}>
                        <Space>
                          <Text strong className="fusion-wizard-queue-title">待导入（{queuedFiles.length}）</Text>
                          {importForm.selectedBankFiles.length ? <Tag color="processing">已选 {importForm.selectedBankFiles.length} 个银行文件</Tag> : null}
                        </Space>
                        {queuedFiles.some((item) => item.sourceType === "bank") ? (
                          <div onPointerDown={(event) => event.stopPropagation()}>{importForm.bankBatchToolbar}</div>
                        ) : null}
                      </Space>
                    }
                    dataSource={queuedFiles}
                    renderItem={(item) => (
                      <List.Item
                        key={`${item.sourceType}-${item.file.name}-${item.file.lastModified}-${item.file.size}`}
                        data-bank-file-name={item.sourceType === "bank" ? item.file.name : undefined}
                        style={item.sourceType === "bank" && importForm.selectedBankFiles.includes(item.file.name) ? { background: "#fff5f0" } : undefined}
                        actions={[
                          <Button
                            key="remove"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            disabled={running}
                            onClick={() => importForm.removeFileForSource(item.sourceType, item.file)}
                          />,
                        ]}
                      >
                        <Space wrap size="middle">
                          {item.sourceType === "bank" ? (
                            <Checkbox
                              checked={importForm.selectedBankFiles.includes(item.file.name)}
                              onChange={(event) => importForm.toggleBankFileSelection(item.file.name, event.target.checked)}
                            />
                          ) : null}
                          <Tag color="volcano" className="fusion-wizard-queue-tag">{SOURCE_LABELS[item.sourceType as SourceType]}</Tag>
                          <Text className="fusion-wizard-queue-name">{item.file.name}</Text>
                          <Text type="secondary">{Math.max(1, Math.ceil(item.file.size / 1024))} KB</Text>
                          {item.sourceType === "bank" && importForm.bankAssignmentSummaries[item.file.name] ? (
                            <>
                              <Tag>{importForm.bankAssignmentSummaries[item.file.name].bankName}</Tag>
                              {importForm.bankAssignmentSummaries[item.file.name].sheetCount === 0 && importForm.bankAssignmentSummaries[item.file.name].hasPresetTemplate ? (
                                <Tag color="success">模板已预设</Tag>
                              ) : (
                                <Tag color={importForm.bankAssignmentSummaries[item.file.name].confirmedTemplates === importForm.bankAssignmentSummaries[item.file.name].sheetCount ? "success" : "warning"}>
                                  模板 {importForm.bankAssignmentSummaries[item.file.name].confirmedTemplates}/{importForm.bankAssignmentSummaries[item.file.name].sheetCount}
                                </Tag>
                              )}
                            </>
                          ) : null}
                        </Space>
                      </List.Item>
                    )}
                  />
                  {selectionBox ? (
                    <div style={{
                      position: "absolute",
                      pointerEvents: "none",
                      zIndex: 5,
                      left: selectionBox.left,
                      top: selectionBox.top,
                      width: selectionBox.width,
                      height: selectionBox.height,
                      border: "1px solid #d94832",
                      background: "rgba(217, 72, 50, 0.1)",
                    }} />
                  ) : null}
                  </div>
                ) : null}
              </>
            )}

            <div className="fusion-wizard-actions">
              <Button size="large" icon={<LeftOutlined />} disabled={running || phase === "importing"} onClick={() => setStep(1)}>
                上一步
              </Button>
              <Button
                type="primary"
                size="large"
                loading={running}
                disabled={phase === "importing" || !importForm.hasExcelFiles}
                onClick={() => void startImport()}
              >
                开始导入
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default FusionNewCaseFlow;
