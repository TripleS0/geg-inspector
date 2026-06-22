import { useNavigate } from "react-router-dom";
import FusionExportCasePanel from "../components/fusion/FusionExportCasePanel";
import FusionNewCaseFlow from "../components/fusion/FusionNewCaseFlow";
import FusionOpenCasePanel from "../components/fusion/FusionOpenCasePanel";
import { useEffectiveCase } from "../hooks/useEffectiveCase";

type FusionCaseActionPageProps = {
  action: "new" | "open" | "export";
};

function FusionCaseActionPage({ action }: FusionCaseActionPageProps) {
  const navigate = useNavigate();
  const { cases, loading, effectiveCaseId, refreshCases, selectCase } = useEffectiveCase();

  const enterCockpit = (caseId: number) => {
    selectCase(caseId);
    navigate("/fusion-cockpit");
  };

  if (action === "new") {
    return (
      <div className="fusion-case-action-page">
        <FusionNewCaseFlow onComplete={enterCockpit} />
      </div>
    );
  }

  if (action === "open") {
    return (
      <div className="fusion-case-action-page">
        <FusionOpenCasePanel
          cases={cases}
          loading={loading}
          currentCaseId={effectiveCaseId}
          onOpen={enterCockpit}
          onRefresh={() => void refreshCases()}
          onSwitchToNew={() => navigate("/fusion-cockpit/new")}
        />
      </div>
    );
  }

  return (
    <div className="fusion-case-action-page">
      <FusionExportCasePanel caseName={cases.find((item) => item.case_id === effectiveCaseId)?.case_name} />
    </div>
  );
}

export default FusionCaseActionPage;
