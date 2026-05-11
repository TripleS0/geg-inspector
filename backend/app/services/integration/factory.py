"""Factory for selecting integration services by source type."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.integration.bank.export_service import BankExportService
from app.services.integration.bank.ingest_service import BankIngestService
from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.commercial.export_service import CommercialExportService
from app.services.integration.commercial.ingest_service import CommercialIngestService
from app.services.integration.commercial.mapping_service import CommercialMappingService


@dataclass(frozen=True)
class IntegrationServiceBundle:
    """Container for source-specific integration service classes."""

    ingest_cls: type
    mapping_cls: type
    export_cls: type


def get_integration_bundle(source_type: str) -> IntegrationServiceBundle:
    """Return service classes for source type."""
    key = (source_type or "").strip().lower()
    if key == "commercial":
        return IntegrationServiceBundle(
            ingest_cls=CommercialIngestService,
            mapping_cls=CommercialMappingService,
            export_cls=CommercialExportService,
        )
    # bank/other currently share bank flow; keep extension point here.
    return IntegrationServiceBundle(
        ingest_cls=BankIngestService,
        mapping_cls=BankMappingService,
        export_cls=BankExportService,
    )

