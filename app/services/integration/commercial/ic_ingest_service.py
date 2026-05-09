"""Enterprise profile ingest service for Qichacha xlsx exports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import pandas as pd

from app.services.shared.db.sqlite_client import SqliteClient


@dataclass
class EnterpriseIngestResult:
    """Batch result for enterprise profile import."""

    import_batch_id: str
    files_total: int
    rows_total: int
    failed_files: int


def normalize_enterprise_name(name: str) -> str:
    """Normalize enterprise name for matching."""
    text = (name or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\(（][^)\）]*[\)）]", "", text)
    text = re.sub(r"\s+", "", text)
    return text


class EnterpriseProfileIngestService:
    """Import enterprise basic info from Qichacha xlsx files."""

    COL_ALIASES = {
        "enterprise_name": ["企业名称", "公司名称", "单位名称", "名称", "Name", "query_keyword"],
        "credit_code": ["统一社会信用代码", "信用代码", "社会信用代码", "CreditCode"],
        "reg_status": ["经营状态", "登记状态", "状态", "Status"],
        "legal_person": ["法定代表人", "法人", "法人代表", "OperName"],
        "reg_capital": ["注册资本", "RegistCapi", "RecCap"],
        "establish_date": ["成立日期", "注册日期", "StartDate", "TermStart"],
        "industry": ["所属行业", "行业", "EconKind"],
        "region": ["所属地区", "地区", "登记机关地区", "BelongOrg"],
        "shareholders": ["股东信息", "股东", "股东名单"],
        "key_persons": ["主要人员", "高管信息", "关键人员"],
    }

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def ingest_files(self, file_paths: list[str]) -> EnterpriseIngestResult:
        """Import enterprise profile xlsx files."""
        import_batch_id = str(uuid4())
        rows_total = 0
        failed_files = 0
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists() or path.suffix.lower() not in {".xlsx", ".xls"}:
                failed_files += 1
                continue
            try:
                workbook = pd.read_excel(path, sheet_name=None, dtype=str)
                for _, df in workbook.items():
                    if df is None or df.empty:
                        continue
                    rows_total += self._ingest_sheet(import_batch_id, path.name, df.fillna(""))
            except Exception:
                failed_files += 1
        return EnterpriseIngestResult(
            import_batch_id=import_batch_id,
            files_total=len(file_paths),
            rows_total=rows_total,
            failed_files=failed_files,
        )

    def ingest_qichacha_flat_rows(
        self,
        rows: list[Mapping[str, Any]],
        *,
        source_label: str = "qichacha_api",
    ) -> EnterpriseIngestResult:
        """将企查查 API 扁平行写入 std_enterprise_profile（单批次）。"""
        import_batch_id = str(uuid4())
        if not rows:
            return EnterpriseIngestResult(
                import_batch_id=import_batch_id,
                files_total=0,
                rows_total=0,
                failed_files=0,
            )
        out_rows: list[tuple[str, ...]] = []
        for raw in rows:
            name = str(raw.get("Name") or raw.get("query_keyword") or "").strip()
            if not name:
                continue
            prov = str(raw.get("Area_Province") or "").strip()
            city = str(raw.get("Area_City") or "").strip()
            county = str(raw.get("Area_County") or "").strip()
            region_parts = [p for p in (prov, city, county) if p]
            region = " ".join(region_parts) if region_parts else str(raw.get("BelongOrg") or "").strip()
            reg_cap = str(raw.get("RegistCapi") or raw.get("RecCap") or "").strip()
            est = str(raw.get("StartDate") or raw.get("TermStart") or "").strip()
            credit = str(raw.get("CreditCode") or "").strip()
            status = str(raw.get("Status") or "").strip()
            legal = str(raw.get("OperName") or "").strip()
            industry = str(raw.get("EconKind") or "").strip()
            payload = {str(k): _json_safe(v) for k, v in raw.items()}
            out_rows.append(
                (
                    import_batch_id,
                    source_label,
                    name,
                    normalize_enterprise_name(name),
                    credit,
                    status,
                    legal,
                    reg_cap,
                    est,
                    industry,
                    region,
                    "[]",
                    "[]",
                    json.dumps(payload, ensure_ascii=False),
                )
            )
        if not out_rows:
            return EnterpriseIngestResult(
                import_batch_id=import_batch_id,
                files_total=0,
                rows_total=0,
                failed_files=0,
            )
        self._client.executemany(
            """
            INSERT INTO std_enterprise_profile(
                import_batch_id, source_file_name, enterprise_name, enterprise_name_norm, credit_code,
                reg_status, legal_person, reg_capital, establish_date, industry, region,
                shareholders_json, key_persons_json, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            out_rows,
        )
        return EnterpriseIngestResult(
            import_batch_id=import_batch_id,
            files_total=1,
            rows_total=len(out_rows),
            failed_files=0,
        )

    def _find_col(self, columns: list[str], alias_key: str) -> str:
        alias_list = self.COL_ALIASES.get(alias_key, [])
        for alias in alias_list:
            if alias in columns:
                return alias
        return ""

    def _ingest_sheet(self, import_batch_id: str, file_name: str, df: pd.DataFrame) -> int:
        columns = [str(c).strip() for c in df.columns]
        enterprise_col = self._find_col(columns, "enterprise_name")
        if not enterprise_col:
            return 0
        credit_col = self._find_col(columns, "credit_code")
        status_col = self._find_col(columns, "reg_status")
        legal_col = self._find_col(columns, "legal_person")
        capital_col = self._find_col(columns, "reg_capital")
        date_col = self._find_col(columns, "establish_date")
        industry_col = self._find_col(columns, "industry")
        region_col = self._find_col(columns, "region")
        shareholders_col = self._find_col(columns, "shareholders")
        key_persons_col = self._find_col(columns, "key_persons")
        rows: list[tuple[str, ...]] = []
        for _, row in df.iterrows():
            name = str(row.get(enterprise_col, "")).strip()
            if not name:
                continue
            payload = {str(k): str(v) for k, v in row.to_dict().items()}
            shareholders = str(row.get(shareholders_col, "")).strip() if shareholders_col else ""
            key_persons = str(row.get(key_persons_col, "")).strip() if key_persons_col else ""
            rows.append(
                (
                    import_batch_id,
                    file_name,
                    name,
                    normalize_enterprise_name(name),
                    str(row.get(credit_col, "")).strip() if credit_col else "",
                    str(row.get(status_col, "")).strip() if status_col else "",
                    str(row.get(legal_col, "")).strip() if legal_col else "",
                    str(row.get(capital_col, "")).strip() if capital_col else "",
                    str(row.get(date_col, "")).strip() if date_col else "",
                    str(row.get(industry_col, "")).strip() if industry_col else "",
                    str(row.get(region_col, "")).strip() if region_col else "",
                    json.dumps([shareholders], ensure_ascii=False) if shareholders else "[]",
                    json.dumps([key_persons], ensure_ascii=False) if key_persons else "[]",
                    json.dumps(payload, ensure_ascii=False),
                )
            )
        if not rows:
            return 0
        self._client.executemany(
            """
            INSERT INTO std_enterprise_profile(
                import_batch_id, source_file_name, enterprise_name, enterprise_name_norm, credit_code,
                reg_status, legal_person, reg_capital, establish_date, industry, region,
                shareholders_json, key_persons_json, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rows,
        )
        return len(rows)


def _json_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


__all__ = ["EnterpriseProfileIngestService", "EnterpriseIngestResult", "normalize_enterprise_name"]

