"""Telecom CDR analysis queries and summaries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from app.services.integration.telecom.export_service import TelecomExportService
from app.services.integration.telecom.phone_utils import display_phone, normalize_phone
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass(frozen=True)
class TelecomAnalysisFilters:
    """Filter options for telecom CDR analysis."""

    quick_query: str = ""
    local_phone: str = ""
    peer_phone: str = ""
    call_type: str = ""
    bill_type: str = ""
    direction: str = ""
    local_carrier: str = ""
    peer_carrier: str = ""
    peer_location: str = ""
    local_location: str = ""
    duration_min: int | None = None
    duration_max: int | None = None
    start_time: str = ""
    end_time: str = ""
    day_time_start: str = ""
    day_time_end: str = ""


class TelecomAnalysisService:
    """Query telecom CDR data and build call statistics."""

    OUTBOUND_BILL_TYPES = frozenset({"主叫话单", "主叫", "MO"})
    INBOUND_BILL_TYPES = frozenset({"被叫话单", "被叫", "MT"})

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def filter_options(self, batch_id: str) -> dict[str, list[str]]:
        records = self._load_records(batch_id)
        return {
            "local_phone": self._distinct(records, "local_phone_display"),
            "peer_phone": self._distinct(records, "peer_phone_display"),
            "call_type": self._distinct(records, "call_type"),
            "bill_type": self._distinct(records, "bill_type"),
            "direction": self._distinct(records, "direction"),
            "local_carrier": self._distinct(records, "local_carrier"),
            "peer_carrier": self._distinct(records, "peer_carrier"),
            "peer_location": self._distinct(records, "peer_location"),
            "local_location": self._distinct(records, "local_location"),
            "source": self._distinct(records, "source"),
        }

    def query_records(
        self,
        batch_id: str,
        filters: TelecomAnalysisFilters | None = None,
        limit: int = 5000,
    ) -> dict[str, Any]:
        active = filters or TelecomAnalysisFilters()
        all_records = self._load_records(batch_id)
        matched = [r for r in all_records if self._match_filters(r, active)]
        summary = self.summarize(matched, active)
        records = matched[: max(1, min(int(limit), 10000))]
        return {
            "records": records,
            "summary": summary,
            "description": self.render_description(summary, active),
        }

    def summarize(
        self,
        records: list[dict[str, Any]],
        filters: TelecomAnalysisFilters | None = None,
    ) -> dict[str, Any]:
        _ = filters
        direction_counts: dict[str, int] = defaultdict(int)
        call_type_counts: dict[str, int] = defaultdict(int)
        peer_location_counts: dict[str, int] = defaultdict(int)
        peer_carrier_counts: dict[str, int] = defaultdict(int)
        hourly_counts: dict[int, int] = defaultdict(int)
        daily_counts: dict[str, int] = defaultdict(int)
        peer_stats: dict[tuple[str, str], dict[str, Any]] = {}

        total_duration_sec = 0
        for row in records:
            direction = self._to_text(row.get("direction")) or "unknown"
            direction_counts[direction] += 1
            call_type = self._to_text(row.get("call_type")) or "未分类"
            call_type_counts[call_type] += 1
            peer_location = self._to_text(row.get("peer_location")) or "未知"
            peer_location_counts[peer_location] += 1
            peer_carrier = self._to_text(row.get("peer_carrier")) or "未知"
            peer_carrier_counts[peer_carrier] += 1

            duration = int(row.get("duration_sec") or 0)
            total_duration_sec += duration
            call_time = self._parse_time(row.get("call_time"))
            if call_time:
                hourly_counts[call_time.hour] += 1
                daily_counts[call_time.strftime("%Y-%m-%d")] += 1

            local_key = self._to_text(row.get("local_phone_norm"))
            peer_key = self._to_text(row.get("peer_phone_norm"))
            if not local_key or not peer_key:
                continue
            key = (local_key, peer_key)
            stat = peer_stats.setdefault(
                key,
                {
                    "local_phone": self._to_text(row.get("local_phone_display")) or local_key,
                    "peer_phone": self._to_text(row.get("peer_phone_display")) or peer_key,
                    "call_count": 0,
                    "total_duration_sec": 0,
                    "outbound_count": 0,
                    "inbound_count": 0,
                    "first_call_time": "",
                    "last_call_time": "",
                },
            )
            stat["call_count"] += 1
            stat["total_duration_sec"] += duration
            if direction == "outbound":
                stat["outbound_count"] += 1
            elif direction == "inbound":
                stat["inbound_count"] += 1
            call_time_text = self._to_text(row.get("call_time"))
            if call_time_text:
                if not stat["first_call_time"] or call_time_text < stat["first_call_time"]:
                    stat["first_call_time"] = call_time_text
                if not stat["last_call_time"] or call_time_text > stat["last_call_time"]:
                    stat["last_call_time"] = call_time_text

        peer_ranking = sorted(
            peer_stats.values(),
            key=lambda item: (-int(item["call_count"]), -int(item["total_duration_sec"]), item["peer_phone"]),
        )[:30]
        hourly_distribution = [
            {"hour": hour, "count": hourly_counts.get(hour, 0)} for hour in range(24)
        ]
        daily_distribution = sorted(
            [{"date": day, "count": count} for day, count in daily_counts.items()],
            key=lambda item: item["date"],
        )
        top_peer_locations = sorted(peer_location_counts.items(), key=lambda x: (-x[1], x[0]))[:10]
        top_peer_carriers = sorted(peer_carrier_counts.items(), key=lambda x: (-x[1], x[0]))[:10]

        return {
            "record_count": len(records),
            "total_duration_sec": total_duration_sec,
            "total_duration_min": round(total_duration_sec / 60.0, 1),
            "direction_counts": dict(direction_counts),
            "call_type_counts": dict(call_type_counts),
            "peer_location_counts": dict(peer_location_counts),
            "peer_carrier_counts": dict(peer_carrier_counts),
            "hourly_distribution": hourly_distribution,
            "daily_distribution": daily_distribution,
            "peer_ranking": peer_ranking,
            "top_peer_locations": top_peer_locations,
            "top_peer_carriers": top_peer_carriers,
        }

    def render_description(self, summary: dict[str, Any], filters: TelecomAnalysisFilters) -> str:
        lines = [
            f"本次通讯话单分析共 {summary.get('record_count', 0)} 条记录，"
            f"累计通话时长 {float(summary.get('total_duration_min') or 0):,.1f} 分钟。",
        ]
        direction_counts = summary.get("direction_counts") or {}
        outbound = int(direction_counts.get("outbound") or 0)
        inbound = int(direction_counts.get("inbound") or 0)
        if outbound or inbound:
            lines.append(f"其中主叫 {outbound} 次，被叫 {inbound} 次。")
        peer_ranking = summary.get("peer_ranking") or []
        if peer_ranking:
            top = peer_ranking[0]
            lines.append(
                f"通联频次最高的是 {top.get('peer_phone', '')}，"
                f"与本机 {top.get('local_phone', '')} 通话 {int(top.get('call_count') or 0)} 次，"
                f"累计时长 {int(top.get('total_duration_sec') or 0)} 秒。"
            )
        if filters.local_phone:
            lines.append(f"当前筛选本机号码包含：{filters.local_phone}。")
        if filters.peer_phone:
            lines.append(f"当前筛选对方号码包含：{filters.peer_phone}。")
        return "\n".join(lines)

    def _load_records(self, batch_id: str) -> list[dict[str, Any]]:
        export = TelecomExportService(self._client)
        rows = export._load_telecom_rows(batch_id)
        records: list[dict[str, Any]] = []
        for row in rows:
            local_raw = self._to_text(row.get("本机号码"))
            peer_raw = self._to_text(row.get("对方号码"))
            call_time = self._to_text(row.get("呼叫开始时间")) or self._to_text(row.get("短信发送接收时间"))
            bill_type = self._to_text(row.get("话单类型"))
            call_type = self._to_text(row.get("通话类型"))
            records.append(
                {
                    "source": self._to_text(row.get("数据来源")),
                    "record_id": self._to_text(row.get("通信记录唯一标识")),
                    "call_type": call_type,
                    "bill_type": bill_type,
                    "direction": self._derive_direction(bill_type, call_type),
                    "local_phone_display": display_phone(local_raw),
                    "peer_phone_display": display_phone(peer_raw),
                    "local_phone_norm": normalize_phone(local_raw),
                    "peer_phone_norm": normalize_phone(peer_raw),
                    "local_carrier": self._to_text(row.get("本机归属运营商")),
                    "peer_carrier": self._to_text(row.get("对方归属运营商")),
                    "local_location": self._to_text(row.get("本机通话所在地")),
                    "peer_location": self._to_text(row.get("对方号码归属地")) or self._to_text(row.get("对方通话所在地")),
                    "call_time": call_time,
                    "duration_sec": self._safe_int(row.get("呼叫时长")),
                    "group_name": self._to_text(row.get("群组名称")),
                    "group_no": self._to_text(row.get("群组编号")),
                    "forward_caller": self._to_text(row.get("前转主叫号码")),
                    "local_cell_id": self._to_text(row.get("本机CELLID")),
                    "peer_cell_id": self._to_text(row.get("对方CELLID")),
                }
            )
        return records

    def _derive_direction(self, bill_type: str, call_type: str) -> str:
        if bill_type in self.OUTBOUND_BILL_TYPES:
            return "outbound"
        if bill_type in self.INBOUND_BILL_TYPES:
            return "inbound"
        text = f"{bill_type} {call_type}"
        if "主叫" in text or "发送" in text:
            return "outbound"
        if "被叫" in text or "接收" in text:
            return "inbound"
        if "短信" in text:
            return "sms"
        return "unknown"

    def _match_filters(self, row: dict[str, Any], filters: TelecomAnalysisFilters) -> bool:
        for token in self._quick_tokens(filters.quick_query):
            haystack = " ".join(
                self._to_text(row.get(key))
                for key in (
                    "local_phone_display",
                    "peer_phone_display",
                    "local_phone_norm",
                    "peer_phone_norm",
                    "call_type",
                    "bill_type",
                    "direction",
                    "local_carrier",
                    "peer_carrier",
                    "local_location",
                    "peer_location",
                    "group_name",
                    "group_no",
                    "forward_caller",
                    "source",
                )
            )
            if token not in haystack and token not in DIRECTION_TEXT.get(self._to_text(row.get("direction")), ""):
                return False
        if filters.local_phone:
            haystack = f"{row.get('local_phone_display', '')} {row.get('local_phone_norm', '')}"
            if filters.local_phone not in haystack:
                return False
        if filters.peer_phone:
            haystack = f"{row.get('peer_phone_display', '')} {row.get('peer_phone_norm', '')}"
            if filters.peer_phone not in haystack:
                return False
        if filters.call_type and filters.call_type != self._to_text(row.get("call_type")):
            return False
        if filters.bill_type and filters.bill_type != self._to_text(row.get("bill_type")):
            return False
        if filters.direction and filters.direction != self._to_text(row.get("direction")):
            return False
        if filters.local_carrier and filters.local_carrier != self._to_text(row.get("local_carrier")):
            return False
        if filters.peer_carrier and filters.peer_carrier != self._to_text(row.get("peer_carrier")):
            return False
        if filters.peer_location and filters.peer_location not in self._to_text(row.get("peer_location")):
            return False
        if filters.local_location and filters.local_location not in self._to_text(row.get("local_location")):
            return False
        duration = int(row.get("duration_sec") or 0)
        if filters.duration_min is not None and duration < int(filters.duration_min):
            return False
        if filters.duration_max is not None and duration > int(filters.duration_max):
            return False
        call_time = self._parse_time(row.get("call_time"))
        if filters.start_time:
            start = self._parse_time(filters.start_time)
            if start and call_time and call_time < start:
                return False
        if filters.end_time:
            end = self._parse_time(filters.end_time)
            if end and call_time and call_time > end:
                return False
        if filters.day_time_start and filters.day_time_end:
            if not self._match_day_time(self._to_text(row.get("call_time")), filters.day_time_start, filters.day_time_end):
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

    def _match_day_time(self, call_time: str, start_hms: str, end_hms: str) -> bool:
        """按日内时分秒筛选，支持跨午夜区间。"""
        raw = (call_time or "").strip()
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

    def _quick_tokens(self, query: str) -> list[str]:
        return [token for token in re.split(r"\s+", (query or "").strip()) if token]


DIRECTION_TEXT = {
    "outbound": "主叫 呼出 发送",
    "inbound": "被叫 呼入 接收",
    "sms": "短信",
    "unknown": "其他",
}


__all__ = ["TelecomAnalysisFilters", "TelecomAnalysisService"]
