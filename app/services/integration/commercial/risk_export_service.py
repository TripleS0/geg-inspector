"""Export commercial risk analysis to Excel (three sheets)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.shared.db.sqlite_client import SqliteClient


class CommercialRiskExportService:
    """Write 风险事件明细 / 企业风险汇总 / 规则配置快照."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def export_risk_report(self, commercial_batch_id: str, output_path: str) -> str:
        try:
            import pandas as pd
        except ImportError as err:
            raise RuntimeError("缺少 pandas，请先执行: pip install -r requirements.txt") from err

        out_file = Path(output_path)
        if out_file.suffix.lower() != ".xlsx":
            out_file = out_file.with_suffix(".xlsx")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        ev_rows = self._client.query_all(
            """
            SELECT event_id, rule_code, rule_name, risk_level, risk_score,
                   enterprise_name, inquiry_no, evidence_json, created_at
            FROM ana_risk_event
            WHERE import_batch_id=?
            ORDER BY event_id;
            """,
            (commercial_batch_id,),
        )
        ev_data = [
            [
                r[0],
                r[1],
                r[2],
                r[3],
                r[4],
                r[5],
                r[6],
                self._pretty_json(r[7]),
                r[8],
            ]
            for r in ev_rows
        ]
        sum_rows = self._client.query_all(
            """
            SELECT summary_id, enterprise_name, total_score, hit_count, risk_level, detail_json, created_at
            FROM ana_risk_summary
            WHERE import_batch_id=?
            ORDER BY total_score DESC, hit_count DESC;
            """,
            (commercial_batch_id,),
        )
        sum_data = []
        for r in sum_rows:
            detail = self._parse_json(r[5])
            by_rule = detail.get("by_rule", {})
            sum_data.append(
                [
                    r[0],
                    r[1],
                    detail.get("participation_count", 0),
                    detail.get("win_count", 0),
                    detail.get("win_amount", 0),
                    r[2],
                    r[3],
                    r[4],
                    self._pretty_json(by_rule),
                    r[6],
                ]
            )
        rule_rows = self._client.query_all(
            """
            SELECT rule_code, rule_name, enabled, weight, params_json, version, updated_at
            FROM cfg_risk_rule
            ORDER BY rule_code;
            """
        )
        rule_data = [
            [r[0], r[1], r[2], r[3], self._pretty_json(r[4]), r[5], r[6]] for r in rule_rows
        ]

        with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
            pd.DataFrame(
                ev_data,
                columns=[
                    "事件ID",
                    "规则代码",
                    "规则名称",
                    "风险等级",
                    "风险分",
                    "企业",
                    "询价单号",
                    "证据JSON",
                    "时间",
                ],
            ).to_excel(writer, index=False, sheet_name="风险事件明细")
            pd.DataFrame(
                sum_data,
                columns=[
                    "汇总ID",
                    "企业",
                    "参标次数",
                    "中标次数",
                    "中标金额",
                    "总分",
                    "命中次数",
                    "等级",
                    "分规则计数JSON",
                    "时间",
                ],
            ).to_excel(writer, index=False, sheet_name="企业风险汇总")
            pd.DataFrame(
                rule_data,
                columns=["规则代码", "规则名称", "启用", "权重", "参数JSON", "版本", "更新时间"],
            ).to_excel(writer, index=False, sheet_name="规则配置快照")
        return str(out_file)

    @staticmethod
    def _pretty_json(text: str | None) -> str:
        if not text:
            return ""
        try:
            return json.dumps(json.loads(text), ensure_ascii=False)
        except Exception:
            return str(text)

    @staticmethod
    def _parse_json(text: str | None) -> dict:
        if not text:
            return {}
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
            return {}
        except Exception:
            return {}


__all__ = ["CommercialRiskExportService"]
