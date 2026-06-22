import { Alert } from "antd";
import { useSearchParams } from "react-router-dom";
import FusionEventManagePanel from "../components/fusion/FusionEventManagePanel";
import FusionModelManagePanel from "../components/fusion/FusionModelManagePanel";
import { useEffectiveCase } from "../hooks/useEffectiveCase";

type FusionSectionPageProps = {
  section: "events" | "models";
};

function FusionSectionPage({ section }: FusionSectionPageProps) {
  const [searchParams] = useSearchParams();
  const { cases, effectiveCaseId, selectedCase } = useEffectiveCase();
  const caseParam = searchParams.get("case");
  const caseId = caseParam ? Number(caseParam) : effectiveCaseId;
  const hasValidCase = caseId !== null && !Number.isNaN(caseId) && cases.some((item) => item.case_id === caseId);
  const currentCase = cases.find((item) => item.case_id === caseId) ?? selectedCase;

  if (!hasValidCase) {
    return (
      <Alert
        type="info"
        showIcon
        message="请先选择或打开案件"
        description="在顶部「当前案件」下拉框中选择案件，或点击「打开案件」进入已有案件。"
      />
    );
  }

  if (section === "events") {
    return <FusionEventManagePanel caseId={caseId!} caseName={currentCase?.case_name} />;
  }

  return <FusionModelManagePanel caseId={caseId!} caseName={currentCase?.case_name} />;
}

export default FusionSectionPage;
