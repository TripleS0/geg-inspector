"""Export use cases for reports and merged workbooks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from app.application.bootstrap import bootstrap_database
from app.runtime_paths import exports_dir
from app.services.integration.commercial.analysis_service import CommercialAnalysisService
from app.services.integration.commercial.risk_export_service import CommercialRiskExportService
from app.services.integration.factory import get_integration_bundle
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass(frozen=True)
class ExportResult:
    """Serializable export result."""

    output_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ExportUseCase:
    """Write Excel exports without UI file dialogs."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def export_batch(self, batch_id: str, source_type: str, output_path: str | None = None) -> ExportResult:
        """Export a bank or commercial merged workbook."""
        source_key = (source_type or "bank").strip().lower()
        target = output_path or str(exports_dir() / f"{source_key}_merged_{batch_id[:8]}.xlsx")
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        service = get_integration_bundle(source_key).export_cls(self._client)
        return ExportResult(service.export_batch_to_xlsx(batch_id, target))

    def export_commercial_risk_report(
        self,
        batch_id: str,
        output_path: str | None = None,
    ) -> ExportResult:
        """Export commercial risk report workbook."""
        target = output_path or str(exports_dir() / f"risk_report_{batch_id[:8]}.xlsx")
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        return ExportResult(CommercialRiskExportService(self._client).export_risk_report(batch_id, target))

    def export_commercial_analysis_report(
        self,
        batch_id: str,
        output_path: str | None = None,
    ) -> ExportResult:
        """Export commercial bid statistics report as Word."""
        target = output_path or str(exports_dir() / f"commercial_analysis_{batch_id[:8]}.docx")
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        return ExportResult(CommercialAnalysisService(self._client).export_statistics_report(batch_id, target))
