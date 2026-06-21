"""Scan case-bound data against enabled fusion models and produce unified events."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.services.fusion.fusion_model_service import FusionModelService
from app.services.fusion.model_catalog import (
    COMMERCIAL_MODULE_KEYS,
    CATALOG_BY_KEY,
    MODULE_ID_BY_KEY,
    RISK_CODE_BY_KEY,
)
from app.services.integration.bank.analysis_modules import run_module
from app.services.integration.commercial.export_service import CommercialExportService
from app.services.integration.commercial.risk_rule_service import CommercialRiskAnalysisService
from app.services.integration.wechat.analysis_modules import run_wechat_module
from app.services.shared.db.sqlite_client import SqliteClient


class FusionEventService:
    def __init__(self, client: SqliteClient) -> None:
        self._client = client
        self._models = FusionModelService(client)

    def scan_events(
        self,
        case_id: int,
        *,
        start_date: str = "",
        end_date: str = "",
        keyword: str = "",
        event_type: str = "",
    ) -> dict[str, Any]:
        enabled = self._models.enabled_model_map(case_id)
        batches = self._case_batches(case_id)
        events: list[dict[str, Any]] = []
        seq = 1

        bank_batches = [b for b in batches if b["source_type"] == "bank"]
        wechat_batches = [b for b in batches if b["source_type"] == "wechat"]
        commercial_batches = [b for b in batches if b["source_type"] == "commercial"]

        for batch in bank_batches:
            batch_id = batch["import_batch_id"]
            for model_key, cfg in enabled.items():
                if not model_key.startswith("bank_"):
                    continue
                module_id = MODULE_ID_BY_KEY.get(model_key)
                if not module_id:
                    continue
                params = FusionModelService.params_to_module_params(cfg.get("params") or {})
                result = run_module(batch_id, module_id, params, self._client)
                model_def = CATALOG_BY_KEY[model_key]
                for hit in result.hit_records:
                    events.append(
                        self._txn_event(
                            seq=seq,
                            model_key=model_key,
                            event_type=model_def.event_type_label,
                            hit=hit,
                            source="bank",
                            batch_id=batch_id,
                        )
                    )
                    seq += 1

        for batch in wechat_batches:
            batch_id = batch["import_batch_id"]
            for model_key, cfg in enabled.items():
                if not model_key.startswith("wechat_"):
                    continue
                module_id = MODULE_ID_BY_KEY.get(model_key)
                if not module_id:
                    continue
                params = FusionModelService.params_to_module_params(cfg.get("params") or {})
                result = run_wechat_module(batch_id, module_id, params, self._client)
                model_def = CATALOG_BY_KEY[model_key]
                for hit in result.hit_records:
                    events.append(
                        self._txn_event(
                            seq=seq,
                            model_key=model_key,
                            event_type=model_def.event_type_label,
                            hit=hit,
                            source="wechat",
                            batch_id=batch_id,
                        )
                    )
                    seq += 1

        for batch in commercial_batches:
            batch_id = batch["import_batch_id"]
            commercial_events = self._commercial_events(seq, batch_id, enabled)
            events.extend(commercial_events)
            seq = len(events) + 1
            risk_events = self._risk_events(seq, batch_id, enabled)
            events.extend(risk_events)
            seq = len(events) + 1

        events.sort(key=lambda e: (e.get("date") or "", e.get("event_id") or ""), reverse=True)
        available_event_types = sorted({str(e.get("event_type") or "其他") for e in events})
        filtered = self._filter_events(
            events,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            event_type=event_type,
        )
        for index, event in enumerate(filtered, start=1):
            event["event_id"] = f"{index:03d}"

        summary = self._build_summary(filtered, enabled)
        return {
            "case_id": case_id,
            "total": len(filtered),
            "items": filtered,
            "available_event_types": available_event_types,
            "summary": summary,
        }

    def _commercial_events(
        self,
        start_seq: int,
        batch_id: str,
        enabled: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seq = start_seq
        active_keys = [k for k in COMMERCIAL_MODULE_KEYS if k in enabled]
        if not active_keys:
            return out

        export = CommercialExportService(self._client)
        raw_rows = export._load_commercial_rows(batch_id)
        winner_amounts: dict[str, list[tuple[str, str, float]]] = defaultdict(list)

        for row in raw_rows:
            inquiry = str(row.get("询价单号") or "").strip()
            company = str(row.get("公司名称") or "").strip()
            winner = str(row.get("中标情况") or "").strip()
            if not company:
                continue
            amount = self._safe_float(row.get("中标金额") or row.get("含税单价") or "0")
            if winner and ("中标" in winner or winner == "是"):
                winner_amounts[company].append((inquiry, winner, amount))

        if "commercial_large_win" in enabled:
            threshold = float(
                (enabled["commercial_large_win"].get("params") or {}).get("large_amount_threshold", 500_000.0)
            )
            model_def = CATALOG_BY_KEY["commercial_large_win"]
            for company, wins in winner_amounts.items():
                for inquiry, _winner, amount in wins:
                    if amount < threshold:
                        continue
                    out.append(
                        {
                            "event_id": f"{seq:03d}",
                            "event_type": model_def.event_type_label,
                            "event_type_key": "commercial_large_win",
                            "related_person": company,
                            "date": "",
                            "description": (
                                f"企业 {company} 在询价单 {inquiry or '(未知)'} 中标金额 {amount:,.2f} 元，"
                                f"超过阈值 {threshold:,.0f} 元"
                            ),
                            "source": "commercial",
                            "batch_id": batch_id,
                            "model_key": "commercial_large_win",
                        }
                    )
                    seq += 1

        if "commercial_repeat_winner" in enabled:
            min_wins = int((enabled["commercial_repeat_winner"].get("params") or {}).get("min_win_count", 3))
            model_def = CATALOG_BY_KEY["commercial_repeat_winner"]
            for company, wins in winner_amounts.items():
                if len(wins) < min_wins:
                    continue
                total = sum(amount for _, _, amount in wins)
                out.append(
                    {
                        "event_id": f"{seq:03d}",
                        "event_type": model_def.event_type_label,
                        "event_type_key": "commercial_repeat_winner",
                        "related_person": company,
                        "date": "",
                        "description": (
                            f"企业 {company} 累计中标 {len(wins)} 次，合计金额 {total:,.2f} 元"
                            f"（阈值 ≥ {min_wins} 次）"
                        ),
                        "source": "commercial",
                        "batch_id": batch_id,
                        "model_key": "commercial_repeat_winner",
                    }
                )
                seq += 1

        return out

    def _risk_events(
        self,
        start_seq: int,
        batch_id: str,
        enabled: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        active_rules = {
            RISK_CODE_BY_KEY[key]: CATALOG_BY_KEY[key]
            for key in enabled
            if key.startswith("risk_") and key in RISK_CODE_BY_KEY
        }
        if not active_rules:
            return []

        existing = self._client.query_all(
            "SELECT COUNT(*) FROM ana_risk_event WHERE import_batch_id=?;",
            (batch_id,),
        )
        if not existing or int(existing[0][0]) == 0:
            CommercialRiskAnalysisService(self._client).run_full(batch_id)

        rows = self._client.query_all(
            """
            SELECT event_id, rule_code, rule_name, enterprise_name, inquiry_no, evidence_json, created_at
            FROM ana_risk_event WHERE import_batch_id=? ORDER BY created_at DESC;
            """,
            (batch_id,),
        )
        out: list[dict[str, Any]] = []
        seq = start_seq
        for _event_id, rule_code, rule_name, enterprise, inquiry_no, evidence_json, created_at in rows:
            if rule_code not in active_rules:
                continue
            model_def = active_rules[rule_code]
            description = self._risk_description(rule_name, enterprise, inquiry_no, evidence_json)
            out.append(
                {
                    "event_id": f"{seq:03d}",
                    "event_type": model_def.event_type_label,
                    "event_type_key": f"risk_{rule_code}",
                    "related_person": enterprise or "",
                    "date": self._format_date(created_at),
                    "description": description,
                    "source": "commercial",
                    "batch_id": batch_id,
                    "model_key": f"risk_{rule_code}",
                    "rule_code": rule_code,
                }
            )
            seq += 1
        return out

    def _txn_event(
        self,
        *,
        seq: int,
        model_key: str,
        event_type: str,
        hit: dict[str, str],
        source: str,
        batch_id: str,
    ) -> dict[str, Any]:
        person = (hit.get("person_name") or hit.get("user_name") or "").strip()
        counterparty = (hit.get("counterparty_name") or "").strip()
        direction = (hit.get("txn_direction") or "").strip()
        amount = self._safe_float(hit.get("amount"))
        txn_time = (hit.get("txn_time") or "").strip()
        remark = (hit.get("remark") or "").strip()

        if model_key.endswith("large_inout") and counterparty:
            if direction == "收入":
                desc = f"收到 {counterparty} 转账 {amount:,.2f} 元"
            else:
                desc = f"向 {counterparty} 转账 {amount:,.2f} 元"
        elif remark:
            desc = remark
        else:
            desc = f"{person or '未知'} {direction} {amount:,.2f} 元"

        return {
            "event_id": f"{seq:03d}",
            "event_type": event_type,
            "event_type_key": model_key,
            "related_person": person or counterparty or "未知",
            "date": self._format_date(txn_time),
            "description": desc,
            "source": source,
            "batch_id": batch_id,
            "model_key": model_key,
        }

    def _risk_description(
        self,
        rule_name: str,
        enterprise: str,
        inquiry_no: str,
        evidence_json: str,
    ) -> str:
        parts = [f"【{rule_name}】企业 {enterprise}"]
        if inquiry_no:
            parts.append(f"询价单 {inquiry_no}")
        try:
            evidence = json.loads(evidence_json or "{}")
        except json.JSONDecodeError:
            evidence = {}
        if isinstance(evidence, dict):
            note = evidence.get("说明") or evidence.get("note") or evidence.get("口径")
            if note:
                parts.append(str(note))
            elif evidence:
                brief = "；".join(f"{k}={v}" for k, v in list(evidence.items())[:3])
                if brief:
                    parts.append(brief)
        return "，".join(parts)

    def _filter_events(
        self,
        events: list[dict[str, Any]],
        *,
        start_date: str,
        end_date: str,
        keyword: str,
        event_type: str = "",
    ) -> list[dict[str, Any]]:
        start = self._parse_date(start_date)
        end = self._parse_date(end_date)
        kw = keyword.strip().lower()
        type_filter = event_type.strip()
        out: list[dict[str, Any]] = []
        for event in events:
            if type_filter and str(event.get("event_type") or "") != type_filter:
                continue
            event_date = self._parse_date(str(event.get("date") or ""))
            if start and event_date and event_date < start:
                continue
            if end and event_date and event_date > end:
                continue
            if kw:
                blob = " ".join(
                    str(event.get(k) or "")
                    for k in ("event_type", "related_person", "description", "event_type_key")
                ).lower()
                if kw not in blob:
                    continue
            out.append(event)
        return out

    def _build_summary(self, events: list[dict[str, Any]], enabled: dict[str, dict[str, Any]]) -> dict[str, Any]:
        by_type: dict[str, int] = defaultdict(int)
        for event in events:
            by_type[str(event.get("event_type") or "其他")] += 1
        return {
            "enabled_model_count": len(enabled),
            "event_count": len(events),
            "by_event_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
        }

    def _case_batches(self, case_id: int) -> list[dict[str, str]]:
        rows = self._client.query_all(
            """
            SELECT import_batch_id, source_type
            FROM rel_case_batch WHERE case_id=? ORDER BY bound_at;
            """,
            (case_id,),
        )
        return [{"import_batch_id": str(r[0]), "source_type": str(r[1])} for r in rows]

    @staticmethod
    def _safe_float(value: Any) -> float:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        text = (value or "").strip().replace("/", "-").replace(".", "-")
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19] if " " in fmt else text[:10], fmt)
            except ValueError:
                continue
        m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
        return None

    @staticmethod
    def _format_date(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        parsed = FusionEventService._parse_date(text)
        if parsed:
            return parsed.strftime("%Y.%m.%d")
        if len(text) >= 10:
            return text[:10].replace("-", ".")
        return text
