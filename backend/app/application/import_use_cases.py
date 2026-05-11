"""Import use cases for offline Web/API callers."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.application.bootstrap import bootstrap_database
from app.services.integration.commercial.ic_ingest_service import EnterpriseProfileIngestService
from app.services.integration.factory import get_integration_bundle
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass(frozen=True)
class ImportSummary:
    """Serializable import result."""

    import_batch_id: str
    source_type: str
    files_total: int
    sheets_total: int
    rows_total: int
    new_templates: int
    failed_files: int
    standardized_rows: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EnterpriseImportSummary:
    """Serializable enterprise import result."""

    import_batch_id: str
    source_type: str
    files_total: int
    rows_total: int
    failed_files: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ImportUseCase:
    """Run bank and commercial data imports without UI dependencies."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def import_source(
        self,
        *,
        file_paths: list[str],
        bank_name: str,
        source_type: str,
    ) -> ImportSummary:
        """Import files and run source-specific post-processing."""
        source_key = (source_type or "bank").strip().lower()
        if source_key not in {"bank", "commercial"}:
            raise ValueError("source_type 仅支持 bank 或 commercial")
        bundle = get_integration_bundle(source_key)
        ingest_result = bundle.ingest_cls(self._client).ingest_files(file_paths, bank_name, source_key)
        standardized_rows = 0
        if source_key == "bank":
            standardized_rows = int(bundle.mapping_cls(self._client).standardize_batch(ingest_result.import_batch_id))
        return ImportSummary(
            import_batch_id=ingest_result.import_batch_id,
            source_type=source_key,
            files_total=ingest_result.files_total,
            sheets_total=ingest_result.sheets_total,
            rows_total=ingest_result.rows_total,
            new_templates=ingest_result.new_templates,
            failed_files=ingest_result.failed_files,
            standardized_rows=standardized_rows,
        )


class EnterpriseImportUseCase:
    """Import enterprise profiles exported by Qichacha-like tools."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def import_enterprise_profiles(self, file_paths: list[str]) -> EnterpriseImportSummary:
        """Import enterprise files into the local enterprise profile table."""
        result = EnterpriseProfileIngestService(self._client).ingest_files(file_paths)
        return EnterpriseImportSummary(
            import_batch_id=result.import_batch_id,
            source_type="enterprise",
            files_total=result.files_total,
            rows_total=result.rows_total,
            failed_files=result.failed_files,
        )

    def import_qichacha_flat_rows(self, rows: list[dict]) -> EnterpriseImportSummary:
        """Import flattened Qichacha API rows as one enterprise batch."""
        result = EnterpriseProfileIngestService(self._client).ingest_qichacha_flat_rows(rows)
        return EnterpriseImportSummary(
            import_batch_id=result.import_batch_id,
            source_type="enterprise",
            files_total=result.files_total,
            rows_total=result.rows_total,
            failed_files=result.failed_files,
        )
