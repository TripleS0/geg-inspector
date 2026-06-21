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
import { ArrowDownOutlined, DeleteOutlined, PlusOutlined } from "@ant-design/icons";
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

type FlowPhase = "draft" | "linking" | "done";

function FusionNewCaseFlow({ onComplete }: FusionNewCaseFlowProps) {
  const [caseName, setCaseName] = useState("");
  const [queue, setQueue] = useState<ImportQueueItem[]>([]);
  const [phase, setPhase] = useState<FlowPhase>("draft");
  const [linkingCaseId, setLinkingCaseId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ percent: 0, message: "" });
  const importForm = useDataImportForm({ allowOcr: false, compact: true });

  const addBatch = async () => {
    try {
      const payload = await importForm.getPayload();
      if (payload.bankImportMode === "ocr") {
        message.warning("新建案件流程暂不支持 OCR，请使用 Excel 导入或前往数据管理");
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

  const resetAll = () => {
    if (phase !== "draft") return;
    setCaseName("");
    setQueue([]);
    importForm.reset();
    setProgress({ percent: 0, message: "" });
    setLinkingCaseId(null);
    setPhase("draft");
  };

  const startImport = async () => {
    const name = caseName.trim();
    if (!name) {
      message.warning("请输入案件名称");
      return;
    }
    if (!queue.length) {
      message.warning("请至少添加一批导入数据");
      return;
    }

    setRunning(true);
    setProgress({ percent: 2, message: "正在创建案件…" });

    try {
      const created = await api.createCase({ case_name: name });
      const caseId = created.case_id;
      persistSelectedCaseId(caseId);
      emitCaseChanged(caseId);

      const batchIds: string[] = [];
      const uploadWeight = 50;
      const bindWeight = 10;

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
        const batchId = String(status.result?.import_batch_id || "");
        if (!batchId) {
          throw new Error(`${label} 导入完成但未返回批次编号`);
        }
        batchIds.push(batchId);
      }

      setProgress({ percent: 8 + uploadWeight, message: "正在绑定批次到案件…" });
      await api.bindCaseBatches(caseId, batchIds);
      setProgress({ percent: 8 + uploadWeight + bindWeight, message: "数据导入完成，请继续人物标识关联…" });

      setLinkingCaseId(caseId);
      setPhase("linking");
      message.success("数据导入完成，请完成人物标识关联");
    } catch (err) {
      message.error((err as Error).message || "新建案件失败");
      setProgress({ percent: 0, message: "" });
    } finally {
      setRunning(false);
    }
  };

  const enterCockpit = () => {
    if (!linkingCaseId) return;
    setPhase("done");
    setProgress({ percent: 100, message: "人物关联已完成，正在进入融合分析驾驶舱…" });
    message.success("已进入融合分析驾驶舱");
    onComplete(linkingCaseId);
  };

  const draftLocked = phase !== "draft";

  return (
    <div className="fusion-hub-panel fusion-new-case-flow">
      <div className={`fusion-flow-step app-card${draftLocked ? " fusion-flow-step-locked" : ""}`}>
        <Text className="fusion-flow-step-label">步骤 1</Text>
        <Title level={5}>请输入案件名</Title>
        <Input
          size="large"
          placeholder="例如：华南机电调查"
          value={caseName}
          disabled={running || draftLocked}
          onChange={(event) => setCaseName(event.target.value)}
          maxLength={120}
        />
      </div>

      <div className="fusion-flow-arrow" aria-hidden>
        <ArrowDownOutlined />
      </div>

      <div className={`fusion-flow-step app-card fusion-flow-import${draftLocked ? " fusion-flow-step-locked" : ""}`}>
        <Text className="fusion-flow-step-label">步骤 2</Text>
        <Title level={5}>请导入数据</Title>
        <Paragraph type="secondary">
          与数据管理相同的导入方式：先选择数据来源，填写批次信息并上传文件；可多次添加不同来源的数据批次。
        </Paragraph>

        {!draftLocked ? (
          <>
            <div className="fusion-import-form-wrap">{importForm.formElement}</div>
            <Space wrap style={{ marginTop: 12 }}>
              <Button icon={<PlusOutlined />} disabled={running} onClick={() => void addBatch()}>
                添加本批数据
              </Button>
            </Space>
          </>
        ) : null}

        {queue.length > 0 ? (
          <List
            className="fusion-import-queue"
            size="small"
            bordered
            header={<Text strong>已导入批次（{queue.length}）</Text>}
            dataSource={queue}
            renderItem={(item) => (
              <List.Item
                actions={
                  draftLocked
                    ? undefined
                    : [
                        <Button
                          key="remove"
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          disabled={running}
                          onClick={() => removeBatch(item.id)}
                        />,
                      ]
                }
              >
                <Space wrap>
                  <Tag color="volcano">{SOURCE_LABELS[item.values.source_type as SourceType]}</Tag>
                  <Text>{item.values.batch_name || item.files[0]?.name}</Text>
                  <Text type="secondary">{item.files.length} 个文件 · {item.values.bank_name || "默认来源"}</Text>
                </Space>
              </List.Item>
            )}
          />
        ) : null}

        {phase === "draft" ? (
          <Space wrap style={{ marginTop: 16 }}>
            <Button type="primary" loading={running} onClick={() => void startImport()}>
              开始导入
            </Button>
            <Button disabled={running} onClick={resetAll}>
              清空
            </Button>
          </Space>
        ) : null}

        {phase !== "draft" && progress.percent > 0 ? (
          <div style={{ marginTop: 16 }}>
            <Progress
              percent={Math.min(progress.percent, phase === "done" ? 100 : 68)}
              status={phase === "done" ? "success" : "active"}
              strokeColor={{ "0%": "#ffb366", "100%": "#d94832" }}
            />
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>{progress.message}</Paragraph>
          </div>
        ) : null}
      </div>

      <div className="fusion-flow-arrow" aria-hidden>
        <ArrowDownOutlined />
      </div>

      <div className={`fusion-flow-step app-card fusion-flow-linking${phase === "draft" ? " fusion-flow-step-pending" : ""}`}>
        <Text className="fusion-flow-step-label">步骤 3</Text>
        <Title level={5}>人物标识关联</Title>
        {linkingCaseId ? (
          <PersonLinkingPanel caseId={linkingCaseId} embedded initialAutoSetup onEnterCockpit={enterCockpit} />
        ) : (
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            数据导入完成后，在此扫描候选标识、机器预关联，并从候选池确认人物归属。
          </Paragraph>
        )}
      </div>

      <div className="fusion-flow-arrow" aria-hidden>
        <ArrowDownOutlined />
      </div>

      <div className="fusion-flow-step app-card fusion-flow-progress">
        <Text className="fusion-flow-step-label">步骤 4</Text>
        <Title level={5}>进入融合分析</Title>
        {phase === "done" ? (
          <>
            <Progress percent={100} status="success" strokeColor={{ "0%": "#ffb366", "100%": "#d94832" }} />
            <Paragraph style={{ marginBottom: 0 }}>人物关联已完成，已进入融合分析驾驶舱。</Paragraph>
          </>
        ) : phase === "linking" ? (
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            完成人物标识关联后，点击步骤 3 中的「进入融合分析驾驶舱」。
          </Paragraph>
        ) : (
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            完成导入与人物关联后，将自动进入融合分析驾驶舱。
          </Paragraph>
        )}
      </div>
    </div>
  );
}

export default FusionNewCaseFlow;
