import { useState } from "react";
import {
  Button,
  Input,
  List,
  Progress,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, LeftOutlined, PlusOutlined, RightOutlined } from "@ant-design/icons";
import { api, emitCaseChanged, persistSelectedCaseId, pollTask } from "../../api";
import PersonLinkingPanel from "./PersonLinkingPanel";
import { SOURCE_LABELS, SourceType } from "../data-import/constants";
import { useDataImportForm, type DataImportPayload } from "../data-import/DataImportForm";

const { Paragraph, Text, Title } = Typography;

interface ImportQueueItem extends DataImportPayload {
  id: string;
}

interface FusionNewCaseFlowProps {
  onComplete: (caseId: number) => void;
}

type FlowStep = 1 | 2 | 3;
type FlowPhase = "draft" | "importing" | "linking";

function FusionNewCaseFlow({ onComplete }: FusionNewCaseFlowProps) {
  const [step, setStep] = useState<FlowStep>(1);
  const [caseName, setCaseName] = useState("");
  const [queue, setQueue] = useState<ImportQueueItem[]>([]);
  const [phase, setPhase] = useState<FlowPhase>("draft");
  const [linkingCaseId, setLinkingCaseId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ percent: 0, message: "" });
  const importForm = useDataImportForm({ allowOcr: false, compact: false });

  const addBatch = async () => {
    try {
      const payload = await importForm.getPayload();
      if (payload.bankImportMode === "ocr") {
        message.warning("新建案件流程暂不支持 OCR，请使用 Excel 导入");
        return;
      }
      const fileKey = payload.files.map((f) => f.name).join("|");
      const dup = queue.some(
        (item) => item.values.source_type === payload.values.source_type && item.files.map((f) => f.name).join("|") === fileKey
      );
      if (dup) {
        message.warning("该数据来源与文件已在待导入列表中，请勿重复添加");
        return;
      }
      setQueue((prev) => [
        ...prev,
        { ...payload, id: `${Date.now()}-${payload.values.batch_name || payload.files[0]?.name}` },
      ]);
      importForm.reset();
      message.success("已添加到导入队列");
    } catch (err) {
      message.warning((err as Error).message);
    }
  };

  const removeBatch = (id: string) => {
    setQueue((prev) => prev.filter((item) => item.id !== id));
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
    if (!queue.length) {
      message.warning("请至少添加一批导入数据");
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

      for (let index = 0; index < queue.length; index += 1) {
        const item = queue[index];
        const { values, files } = item;
        const label = SOURCE_LABELS[values.source_type];
        const base = 8 + Math.round((index / queue.length) * uploadWeight);
        setProgress({
          percent: base,
          message: `正在导入${label}（${index + 1}/${queue.length}）…`,
        });

        const { task_id } = await api.uploadFiles(
          values.source_type,
          files,
          values.bank_name || "默认来源",
          values.batch_name
        );
        const status = await pollTask(task_id, (task) => {
          const slice = uploadWeight / queue.length;
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
              选择数据来源并上传文件，可多次添加不同批次。商务网请将多个发电厂/采购单位文件放在同一批中一并导入，完成后点击「开始导入」。
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
                <Space wrap className="fusion-wizard-import-actions">
                  <Button size="large" icon={<PlusOutlined />} disabled={running} onClick={() => void addBatch()}>
                    添加本批数据
                  </Button>
                </Space>

                {queue.length > 0 ? (
                  <List
                    className="fusion-import-queue fusion-wizard-import-queue"
                    bordered
                    header={<Text strong className="fusion-wizard-queue-title">待导入（{queue.length}）</Text>}
                    dataSource={queue}
                    renderItem={(item) => (
                      <List.Item
                        actions={[
                          <Button
                            key="remove"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            disabled={running}
                            onClick={() => removeBatch(item.id)}
                          />,
                        ]}
                      >
                        <Space wrap size="middle">
                          <Tag color="volcano" className="fusion-wizard-queue-tag">{SOURCE_LABELS[item.values.source_type as SourceType]}</Tag>
                          <Text className="fusion-wizard-queue-name">{item.values.batch_name || item.files[0]?.name}</Text>
                          <Text type="secondary">{item.files.length} 个文件</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
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
                disabled={phase === "importing" || !queue.length}
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
