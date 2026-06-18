"""WeChat transfer mapping service placeholder."""

from __future__ import annotations

from app.services.integration.bank.mapping_service import BankMappingService


class WechatMappingService(BankMappingService):
    """WeChat data currently stays in raw layer; no std mapping yet."""


__all__ = ["WechatMappingService"]
