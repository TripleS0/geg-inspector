"""WeChat transfer analysis modules (same rules as bank, field mapping applied)."""

from __future__ import annotations

from typing import Any

from app.services.integration.bank.analysis_modules import ModuleParams, ModuleResult, run_module_on_records
from app.services.integration.wechat.analysis_service import WechatAnalysisService
from app.services.shared.db.sqlite_client import SqliteClient


def wechat_row_to_unified(row: dict[str, Any]) -> dict[str, str]:
    dc = str(row.get("debit_credit_type") or "").strip()
    if dc in ("入", "收入"):
        direction = "收入"
    elif dc in ("出", "支出"):
        direction = "支出"
    else:
        direction = dc or "未知"
    return {
        "person_name": str(row.get("user_name") or ""),
        "txn_direction": direction,
        "amount": str(row.get("amount_yuan") or ""),
        "txn_time": str(row.get("txn_time") or ""),
        "counterparty_name": str(row.get("counterparty_name") or ""),
        "counterparty_account": str(row.get("counterparty_bank_card") or ""),
        "bank_type": "微信",
        "acct_no": str(row.get("user_bank_card") or ""),
        "txn_desc": str(row.get("business_type") or ""),
        "remark": f"{row.get('remark1', '')} {row.get('remark2', '')}".strip(),
    }


def load_wechat_unified_records(batch_id: str, client: SqliteClient | None = None) -> list[dict[str, str]]:
    service = WechatAnalysisService(client)
    rows = service._load_records(batch_id)
    return [wechat_row_to_unified(row) for row in rows]


def run_wechat_module(
    batch_id: str,
    module_id: str,
    params: ModuleParams | None = None,
    client: SqliteClient | None = None,
) -> ModuleResult:
    records = load_wechat_unified_records(batch_id, client)
    return run_module_on_records(records, module_id, params, client=client)
