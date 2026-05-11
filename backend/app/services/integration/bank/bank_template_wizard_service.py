"""Analyze bank Excel samples for the template wizard (headers, mapping hints, previews)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.integration.bank.ingest_service import BankIngestService
from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.template_library import (
    find_column,
    match_template,
    match_template_by_columns,
)
from app.services.shared.db.sqlite_client import SqliteClient

STD_FIELDS_TXN = frozenset(
    {
        "person_name",
        "acct_no",
        "txn_date",
        "txn_time_raw",
        "txn_direction",
        "currency",
        "txn_amount",
        "balance",
        "counterparty_name",
        "counterparty_account",
        "summary",
        "remark",
        "txn_org_no",
        "txn_org_name",
    }
)
STD_FIELDS_ACCOUNT = frozenset({"person_name", "acct_no", "id_no", "mobile", "open_date"})


def allowed_std_fields(template_type: str) -> frozenset[str]:
    if template_type == "account_profile":
        return STD_FIELDS_ACCOUNT
    return STD_FIELDS_TXN


def validate_field_map(template_type: str, field_map: dict[str, list[str]]) -> None:
    allowed = allowed_std_fields(template_type)
    for k in field_map:
        if k not in allowed:
            raise ValueError(f"未知标准字段: {k}")


def _score_header_row(ingest: BankIngestService, df: Any, row_idx: int) -> float:
    raw = ["" if v is None else str(v).strip() for v in df.iloc[row_idx].tolist()]
    non_empty = [x for x in raw if x]
    if len(non_empty) < 2:
        return float("-inf")
    unique_ratio = len(set(non_empty)) / max(1, len(non_empty))
    keyword_hits = sum(1 for x in non_empty if ingest._looks_like_business_header(x))
    unnamed_hits = sum(1 for x in non_empty if x.lower().startswith("unnamed"))
    long_text_penalty = sum(1 for x in non_empty if len(x) >= 28)
    data_like_hits = 0
    preview_end = min(len(df), row_idx + 6)
    for i in range(row_idx + 1, preview_end):
        next_row = ["" if v is None else str(v).strip() for v in df.iloc[i].tolist()]
        data_like_hits += sum(1 for x in next_row if ingest._looks_like_data_value(x))
    return (
        len(non_empty) * 1.5
        + unique_ratio * 4
        + keyword_hits * 3
        + data_like_hits * 0.3
        - unnamed_hits * 2
        - long_text_penalty * 0.8
    )


class BankTemplateWizardService:
    """Build wizard analyze payloads from a local Excel path."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self._ingest = BankIngestService(self._client)
        self._mapping = BankMappingService(self._client)

    def list_sheet_names(self, file_path: Path) -> list[str]:
        try:
            import pandas as pd
        except ImportError as err:
            raise RuntimeError("缺少 pandas") from err
        path = Path(file_path)
        with pd.ExcelFile(path) as xl:
            return [str(x) for x in xl.sheet_names]

    def analyze(
        self,
        *,
        file_path: Path,
        sheet_name: str,
        template_type: str,
        bank_name_hint: str = "银行数据",
        header_row_0based: int | None = None,
        max_sample_rows: int = 50,
    ) -> dict[str, Any]:
        if template_type not in ("account_profile", "txn_detail"):
            raise ValueError("template_type 须为 account_profile 或 txn_detail")
        try:
            import pandas as pd
        except ImportError as err:
            raise RuntimeError("缺少 pandas") from err
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        workbook = self._ingest._read_workbook_fallback(path, pd)
        if not sheet_name.strip():
            sheet_name = next(iter(workbook.keys()))
        if sheet_name not in workbook:
            raise ValueError(f"无此 sheet: {sheet_name}")
        raw_df = workbook[sheet_name]
        raw_trim = raw_df.copy().fillna("")
        raw_trim = raw_trim[
            raw_trim.apply(lambda row: any(str(v).strip() for v in row.tolist()), axis=1)
        ].reset_index(drop=True)

        max_scan = min(30, len(raw_trim))
        header_candidates: list[dict[str, Any]] = []
        for row_idx in range(max_scan):
            score = _score_header_row(self._ingest, raw_trim, row_idx)
            header_candidates.append({"row_0based": row_idx, "score": round(score, 4)})

        df_norm, hdr = self._ingest._normalize_sheet_dataframe(
            raw_df,
            pd,
            fixed_header_row=header_row_0based,
        )
        columns = [str(c).strip() for c in df_norm.columns]

        tpl = match_template(
            bank_name_hint, sheet_name, sheet_type=template_type, client=self._client
        )
        if tpl is None:
            tpl = match_template_by_columns(columns, sheet_type=template_type, client=self._client)
        suggested: dict[str, str] = {}
        if tpl is not None:
            for std_field, aliases in tpl.field_map.items():
                col = find_column(columns, aliases)
                if col:
                    suggested[str(std_field)] = col
        else:
            keyword_to_std = self._mapping._keyword_to_std(template_type)
            sorted_pairs = sorted(keyword_to_std.items(), key=lambda kv: len(kv[0]), reverse=True)
            assigned_std: set[str] = set()
            for column in columns:
                for keyword, std_field in sorted_pairs:
                    if keyword not in column:
                        continue
                    if std_field == "acct_no":
                        bad_tokens = ("类型", "状态", "余额", "序号", "网点", "日期")
                        if any(tok in column for tok in bad_tokens):
                            continue
                    if std_field in assigned_std:
                        break
                    suggested[std_field] = column
                    assigned_std.add(std_field)
                    break

        sample = df_norm.head(max_sample_rows).fillna("")
        preview_grid = sample.astype(str).head(8).values.tolist()

        direction_distinct: list[str] = []
        dir_col = suggested.get("txn_direction")
        if dir_col and dir_col in sample.columns:
            direction_distinct = sorted(
                {str(x).strip() for x in sample[dir_col].tolist() if str(x).strip()}
            )[:80]

        merged_preview: list[str] = []
        date_col = suggested.get("txn_date")
        time_col = suggested.get("txn_time_raw")
        if template_type == "txn_detail" and (date_col or time_col):
            for _, row in sample.head(6).iterrows():
                d = str(row.get(date_col, "") or "") if date_col else ""
                t = str(row.get(time_col, "") or "") if time_col else ""
                merged_preview.append(self._mapping._normalize_txn_time(d or None, t or None))

        return {
            "file_name": path.name,
            "sheet_name": sheet_name,
            "template_type": template_type,
            "header_row_selected_0based": hdr,
            "header_row_candidates": header_candidates,
            "source_headers": columns,
            "suggested_mapping": suggested,
            "direction_distinct_values": direction_distinct,
            "datetime_analysis": {"merged_preview": merged_preview},
            "sample_row_count": int(len(sample)),
            "preview_grid": preview_grid,
            "preview_columns": list(sample.columns.astype(str)),
        }
