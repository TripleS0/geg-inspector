"""WeChat transfer analysis queries and summaries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from app.services.integration.wechat.export_service import WechatExportService
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass(frozen=True)
class WechatAnalysisFilters:
    """Filter options for WeChat transfer analysis."""

    user_name: str = ""
    debit_credit_type: str = ""
    counterparty_name: str = ""
    business_type: str = ""
    purpose_type: str = ""
    amount_min: float | None = None
    amount_max: float | None = None
    start_time: str = ""
    end_time: str = ""
    day_time_start: str = ""
    day_time_end: str = ""
    remark: str = ""

    # Custom direction mapping: keys are 借贷类型 values treated as income
    income_types: tuple[str, ...] = ("入",)
    expense_types: tuple[str, ...] = ("出",)


class WechatAnalysisService:
    """Query WeChat transfer data and build statistics."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def filter_options(self, batch_id: str) -> dict[str, list[str]]:
        records = self._load_records(batch_id)
        return {
            "user_name": self._distinct(records, "user_name"),
            "debit_credit_type": self._distinct(records, "debit_credit_type"),
            "counterparty_name": self._distinct(records, "counterparty_name"),
            "business_type": self._distinct(records, "business_type"),
            "purpose_type": self._distinct(records, "purpose_type"),
            "source": self._distinct(records, "source"),
        }

    def query_records(
        self,
        batch_id: str,
        filters: WechatAnalysisFilters | None = None,
        limit: int = 5000,
    ) -> dict[str, Any]:
        active = filters or WechatAnalysisFilters()
        records = [r for r in self._load_records(batch_id) if self._match_filters(r, active)]
        records = records[: max(1, min(int(limit), 10000))]
        summary = self.summarize(records, active)
        return {
            "records": records,
            "summary": summary,
            "description": self.render_description(summary, active),
        }

    def summarize(
        self,
        records: list[dict[str, Any]],
        filters: WechatAnalysisFilters | None = None,
    ) -> dict[str, Any]:
        active = filters or WechatAnalysisFilters()
        income_types = set(active.income_types)
        expense_types = set(active.expense_types)

        in_total = 0.0
        out_total = 0.0
        counterparty_amounts: dict[str, float] = defaultdict(float)
        purpose_counts: dict[str, int] = defaultdict(int)
        business_counts: dict[str, int] = defaultdict(int)
        type_counts: dict[str, int] = defaultdict(int)

        for row in records:
            amount = float(row.get("amount_yuan") or 0)
            dc_type = self._to_text(row.get("debit_credit_type"))
            type_counts[dc_type] += 1
            purpose = self._to_text(row.get("purpose_type")) or "未分类"
            business = self._to_text(row.get("business_type")) or "未分类"
            purpose_counts[purpose] += 1
            business_counts[business] += 1

            if dc_type in income_types:
                in_total += amount
                direction = "in"
            elif dc_type in expense_types:
                out_total += amount
                direction = "out"
            else:
                direction = "other"

            counterparty = self._to_text(row.get("counterparty_name"))
            if counterparty and direction in {"in", "out"}:
                counterparty_amounts[counterparty] += amount

        top_counterparties = sorted(counterparty_amounts.items(), key=lambda x: (-x[1], x[0]))[:15]
        top_purpose = sorted(purpose_counts.items(), key=lambda x: (-x[1], x[0]))[:10]
        top_business = sorted(business_counts.items(), key=lambda x: (-x[1], x[0]))[:10]

        return {
            "record_count": len(records),
            "in_total": round(in_total, 2),
            "out_total": round(out_total, 2),
            "net_total": round(in_total - out_total, 2),
            "type_counts": dict(type_counts),
            "top_counterparties": top_counterparties,
            "top_purpose_types": top_purpose,
            "top_business_types": top_business,
            "income_types": list(active.income_types),
            "expense_types": list(active.expense_types),
        }

    def render_description(self, summary: dict[str, Any], filters: WechatAnalysisFilters) -> str:
        income_label = "、".join(filters.income_types) or "入"
        expense_label = "、".join(filters.expense_types) or "出"
        lines = [
            f"本次微信流水分析共 {summary.get('record_count', 0)} 条记录。",
            f"按借贷类型区分：收入（{income_label}）合计 {float(summary.get('in_total') or 0):,.2f} 元，"
            f"支出（{expense_label}）合计 {float(summary.get('out_total') or 0):,.2f} 元，"
            f"净流入 {float(summary.get('net_total') or 0):,.2f} 元。",
        ]
        top_cp = (summary.get("top_counterparties") or [])[:1]
        if top_cp:
            name, amount = top_cp[0]
            lines.append(f"按交易对手累计金额排序，排名第一的是 {name}，合计 {float(amount):,.2f} 元。")
        return "\n".join(lines)

    def _load_records(self, batch_id: str) -> list[dict[str, Any]]:
        export = WechatExportService(self._client)
        rows = export._load_wechat_rows(batch_id)
        records: list[dict[str, Any]] = []
        for row in rows:
            amount_fen = self._safe_int(row.get("交易金额(分)", ""))
            balance_fen = self._safe_int(row.get("账户余额(分)", ""))
            records.append(
                {
                    "source": self._to_text(row.get("数据来源")),
                    "user_id": self._to_text(row.get("用户ID")),
                    "txn_no": self._to_text(row.get("交易单号")),
                    "large_no": self._to_text(row.get("大单号")),
                    "user_name": self._to_text(row.get("用户侧账号名称")),
                    "debit_credit_type": self._to_text(row.get("借贷类型")),
                    "business_type": self._to_text(row.get("交易业务类型")),
                    "purpose_type": self._to_text(row.get("交易用途类型")),
                    "txn_time": self._to_text(row.get("交易时间")),
                    "amount_fen": amount_fen,
                    "amount_yuan": round(amount_fen / 100.0, 2),
                    "balance_fen": balance_fen,
                    "balance_yuan": round(balance_fen / 100.0, 2),
                    "user_bank_card": self._to_text(row.get("用户银行卡号")),
                    "counterparty_id": self._to_text(row.get("对手方ID")),
                    "counterparty_name": self._to_text(row.get("对手侧账户名称")),
                    "counterparty_bank_card": self._to_text(row.get("对手方银行卡号")),
                    "counterparty_bank_name": self._to_text(row.get("对手侧银行名称")),
                    "counterparty_receive_time": self._to_text(row.get("对手方接收时间")),
                    "counterparty_receive_amount_yuan": round(
                        self._safe_int(row.get("对手方接收金额(分)", "")) / 100.0, 2
                    ),
                    "remark1": self._to_text(row.get("备注1")),
                    "remark2": self._to_text(row.get("备注2")),
                }
            )
        return records

    def _match_filters(self, row: dict[str, Any], filters: WechatAnalysisFilters) -> bool:
        if filters.user_name and filters.user_name not in self._to_text(row.get("user_name")):
            return False
        if filters.debit_credit_type and filters.debit_credit_type != self._to_text(row.get("debit_credit_type")):
            return False
        if filters.counterparty_name and filters.counterparty_name not in self._to_text(row.get("counterparty_name")):
            return False
        if filters.business_type and filters.business_type != self._to_text(row.get("business_type")):
            return False
        if filters.purpose_type and filters.purpose_type != self._to_text(row.get("purpose_type")):
            return False
        if filters.remark:
            remark_text = f"{row.get('remark1', '')} {row.get('remark2', '')}"
            if filters.remark not in remark_text:
                return False
        amount = float(row.get("amount_yuan") or 0)
        if filters.amount_min is not None and amount < float(filters.amount_min):
            return False
        if filters.amount_max is not None and amount > float(filters.amount_max):
            return False
        txn_time = self._parse_time(row.get("txn_time"))
        if filters.start_time:
            start = self._parse_time(filters.start_time)
            if start and txn_time and txn_time < start:
                return False
        if filters.end_time:
            end = self._parse_time(filters.end_time)
            if end and txn_time and txn_time > end:
                return False
        if filters.day_time_start and filters.day_time_end:
            if not self._match_day_time(self._to_text(row.get("txn_time")), filters.day_time_start, filters.day_time_end):
                return False
        return True

    def _distinct(self, records: list[dict[str, Any]], field: str) -> list[str]:
        values = sorted({self._to_text(r.get(field)) for r in records if self._to_text(r.get(field))})
        return values

    def _safe_int(self, value: Any) -> int:
        text = self._to_text(value).replace(",", "")
        if not text:
            return 0
        try:
            return int(float(text))
        except ValueError:
            return 0

    def _match_day_time(self, txn_time: str, start_hms: str, end_hms: str) -> bool:
        """按日内时分秒筛选，支持跨午夜区间。"""
        raw = (txn_time or "").strip()
        if not raw:
            return False
        match = re.search(r"(\d{2})[:\.-](\d{2})[:\.-](\d{2})", raw)
        if not match:
            return False
        t = f"{match.group(1)}:{match.group(2)}:{match.group(3)}"
        if start_hms <= end_hms:
            return start_hms <= t <= end_hms
        return t >= start_hms or t <= end_hms

    def _parse_time(self, value: Any) -> datetime | None:
        text = self._to_text(value)
        if not text:
            return None
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(text[: len(fmt.replace("%", "0"))], fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("T", " ")[:19])
        except ValueError:
            return None

    def _to_text(self, value: Any) -> str:
        text = "" if value is None else str(value).strip()
        if text.lower() == "nan":
            return ""
        return text


__all__ = ["WechatAnalysisFilters", "WechatAnalysisService"]
