import { Button, Space, Tag, Typography } from "antd";
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  PartitionOutlined,
  ProjectOutlined,
  RightOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";

const { Paragraph, Text, Title } = Typography;

export type WorkflowStepKey = "cases" | "import" | "batches" | "person-linking" | "fusion-cockpit";

export interface WorkflowStepStatus {
  key: WorkflowStepKey;
  title: string;
  desc: string;
  to: string;
  done: boolean;
  metric?: string;
  icon: ReactNode;
  disabled?: boolean;
  disabledReason?: string;
}

export interface WorkflowSnapshot {
  caseCount: number;
  batchCount: number;
  boundBatchCount: number;
  personCount: number;
  linkedIdentifierCount: number;
  pendingCandidateCount: number;
  selectedCaseId: number | null;
}

export const DEFAULT_WORKFLOW_SNAPSHOT: WorkflowSnapshot = {
  caseCount: 0,
  batchCount: 0,
  boundBatchCount: 0,
  personCount: 0,
  linkedIdentifierCount: 0,
  pendingCandidateCount: 0,
  selectedCaseId: null,
};

export function buildWorkflowSteps(snapshot: WorkflowSnapshot): WorkflowStepStatus[] {
  const query = snapshot.selectedCaseId ? `?case=${snapshot.selectedCaseId}` : "";
  const hasCase = snapshot.caseCount > 0;
  const hasBatch = snapshot.batchCount > 0;
  const hasBoundBatch = snapshot.boundBatchCount > 0;
  const hasLinkedPerson = snapshot.personCount > 0 && snapshot.linkedIdentifierCount > 0;
  return [
    {
      key: "cases",
      title: "建立案件",
      desc: "创建案件并确定本次分析边界。",
      to: "/fusion-cockpit/new",
      done: hasCase,
      metric: `${snapshot.caseCount} 个案件`,
      icon: <ProjectOutlined />,
    },
    {
      key: "import",
      title: "导入数据",
      desc: "导入银行、微信、话单、工商或商务网文件。",
      to: "/fusion-cockpit/new",
      done: hasBatch,
      metric: `${snapshot.batchCount} 个批次`,
      icon: <CloudUploadOutlined />,
    },
    {
      key: "batches",
      title: "绑定批次",
      desc: "把导入批次加入案件，形成分析范围。",
      to: "/fusion-cockpit/open",
      done: hasBoundBatch,
      metric: `${snapshot.boundBatchCount} 个已绑定`,
      icon: <AppstoreOutlined />,
      disabled: !hasCase || !hasBatch,
      disabledReason: !hasCase ? "请先建立案件" : !hasBatch ? "请先导入数据" : undefined,
    },
    {
      key: "person-linking",
      title: "人物关联",
      desc: "扫描并归并姓名、手机、微信、银行卡等标识。",
      to: `/person-linking${query}`,
      done: hasLinkedPerson,
      metric: `${snapshot.personCount} 人 · ${snapshot.linkedIdentifierCount} 标识`,
      icon: <TeamOutlined />,
      disabled: !hasCase || !hasBoundBatch,
      disabledReason: !hasCase ? "请先建立案件" : !hasBoundBatch ? "请先绑定批次" : undefined,
    },
    {
      key: "fusion-cockpit",
      title: "融合分析",
      desc: "进入驾驶舱：单人全景、双人关系或标识符自由检索。",
      to: `/fusion-cockpit${query}`,
      done: hasLinkedPerson,
      metric: hasLinkedPerson ? "可分析" : "待人物关联",
      icon: <PartitionOutlined />,
      disabled: !hasLinkedPerson,
      disabledReason: "请先完成人物关联",
    },
  ];
}

export function getNextWorkflowStep(steps: WorkflowStepStatus[], currentKey?: WorkflowStepKey) {
  const currentIndex = currentKey ? steps.findIndex((item) => item.key === currentKey) : -1;
  if (currentIndex === steps.length - 1) return null;
  if (currentIndex >= 0) {
    return steps.slice(currentIndex + 1).find((item) => !item.done && !item.disabled) ?? steps[currentIndex + 1] ?? null;
  }
  return steps.find((item) => !item.done && !item.disabled) ?? steps.find((item) => !item.done) ?? null;
}

interface WorkflowGuideProps {
  steps: WorkflowStepStatus[];
  currentKey?: WorkflowStepKey;
  compact?: boolean;
}

function WorkflowStepLink({ step, children }: { step: WorkflowStepStatus; children: ReactNode }) {
  if (step.disabled) {
    return <div className="workflow-guide-step-shell disabled" title={step.disabledReason}>{children}</div>;
  }
  return <Link to={step.to} className="workflow-guide-step-link">{children}</Link>;
}

function WorkflowGuide({ steps, currentKey, compact = false }: WorkflowGuideProps) {
  const nextStep = getNextWorkflowStep(steps, currentKey);
  const completed = steps.filter((item) => item.done).length;
  const isLastStep = currentKey === steps[steps.length - 1]?.key;

  return (
    <div className={compact ? "workflow-guide compact" : "workflow-guide"}>
      <div className="workflow-guide-head">
        <div>
          <Text className="context-label">当前流程</Text>
          <Title level={5} style={{ margin: "4px 0 0" }}>{completed}/{steps.length} 步已完成</Title>
        </div>
        {nextStep && !isLastStep && !nextStep.disabled && (
          <Link to={nextStep.to}>
            <Button type="primary" icon={<RightOutlined />}>下一步：{nextStep.title}</Button>
          </Link>
        )}
        {isLastStep && <Tag color="green">已到最后一步</Tag>}
      </div>
      <div className="workflow-guide-steps">
        {steps.map((step, index) => (
          <WorkflowStepLink step={step} key={step.key}>
            <div
              className={[
                "workflow-guide-step",
                step.done ? "done" : "",
                step.disabled ? "disabled" : "",
                step.key === currentKey ? "active" : "",
              ].filter(Boolean).join(" ")}
            >
              <span className="workflow-guide-index">{step.done ? <CheckCircleOutlined /> : index + 1}</span>
              <span className="workflow-guide-icon">{step.icon}</span>
              <span className="workflow-guide-copy">
                <strong>{step.title}</strong>
                {!compact && <Paragraph>{step.disabled ? step.disabledReason : step.desc}</Paragraph>}
              </span>
              {step.metric && <Tag>{step.metric}</Tag>}
            </div>
          </WorkflowStepLink>
        ))}
      </div>
      {nextStep && !compact && !isLastStep && !nextStep.disabled && (
        <Space className="workflow-guide-next" wrap>
          <Text type="secondary">建议继续：</Text>
          <Link to={nextStep.to}>{nextStep.desc}</Link>
        </Space>
      )}
    </div>
  );
}

export default WorkflowGuide;
