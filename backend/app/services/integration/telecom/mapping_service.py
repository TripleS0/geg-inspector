"""Telecom CDR mapping service placeholder."""

from __future__ import annotations

from app.services.integration.bank.mapping_service import BankMappingService


class TelecomMappingService(BankMappingService):
    """Telecom data currently stays in raw layer; no std mapping yet."""


__all__ = ["TelecomMappingService"]
