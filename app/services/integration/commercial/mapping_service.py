"""Commercial-source mapping service.

Current phase reuses bank standardization behavior.
"""

from __future__ import annotations

from app.services.integration.bank.mapping_service import BankMappingService


class CommercialMappingService(BankMappingService):
    """Temporary commercial implementation based on bank mapping flow."""


__all__ = ["CommercialMappingService"]

