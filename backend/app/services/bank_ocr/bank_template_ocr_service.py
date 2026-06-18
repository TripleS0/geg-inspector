"""Analyze bank statement images for the template wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.bank_ocr.ocr_engine import recognize_page_table, recognize_page_text
from app.services.bank_ocr.pdf_converter import expand_upload_to_page_images
from app.services.bank_ocr.table_parser import parse_header_fields, parse_structure_result_raw
from app.services.bank_ocr.layout_profiles import resolve_profile
from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.template_library import find_column, match_template, match_template_by_columns
from app.services.shared.db.sqlite_client import SqliteClient


class BankTemplateOcrAnalyzeService:
    """Run OCR on one image/PDF page and return wizard-compatible analyze payload."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self._mapping = BankMappingService(self._client)

    def analyze(
        self,
        *,
        file_path: Path,
        template_type: str,
        bank_name_hint: str = "银行数据",
        layout_profile_id: str | None = None,
        max_sample_rows: int = 50,
    ) -> dict[str, Any]:
        if template_type not in ("account_profile", "txn_detail"):
            raise ValueError("template_type 须为 account_profile 或 txn_detail")
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        page_images = expand_upload_to_page_images(path, path.parent / f"{path.stem}_ocr_pages")
        if not page_images:
            raise ValueError("未能从样本中解析出图片页面")
        image_path = page_images[0]
        profile = resolve_profile(layout_profile_id, bank_name_hint)
        page_meta = parse_header_fields(recognize_page_text(image_path), profile)
        columns, rows, _conf = parse_structure_result_raw(recognize_page_table(image_path))
        if not columns:
            raise ValueError("OCR 未识别到表格列，请换更清晰的样本或先在导入页校对")

        sample_rows = rows[:max_sample_rows]
        preview_columns = columns
        preview_grid = [[str(row.get(column) or "") for column in preview_columns] for row in sample_rows[:8]]

        tpl = match_template(bank_name_hint, "交易明细", sheet_type=template_type, client=self._client)
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

        direction_distinct: list[str] = []
        dir_col = suggested.get("txn_direction")
        if not dir_col:
            for candidate in ("借贷方向", "借贷标志", "借贷标识", "收支标志"):
                if candidate in columns:
                    dir_col = candidate
                    break
        if dir_col:
            direction_distinct = sorted({str(row.get(dir_col) or "").strip() for row in sample_rows if str(row.get(dir_col) or "").strip()})[:80]

        merged_preview: list[str] = []
        date_col = suggested.get("txn_date")
        time_col = suggested.get("txn_time_raw")
        if template_type == "txn_detail" and (date_col or time_col):
            for row in sample_rows[:6]:
                d = str(row.get(date_col, "") or "") if date_col else ""
                t = str(row.get(time_col, "") or "") if time_col else ""
                merged_preview.append(self._mapping._normalize_txn_time(d or None, t or None))

        return {
            "file_name": path.name,
            "sheet_name": "OCR交易明细",
            "template_type": template_type,
            "header_row_selected_0based": 0,
            "header_row_candidates": [{"row_0based": 0, "score": 1.0}],
            "source_headers": columns,
            "suggested_mapping": suggested,
            "direction_distinct_values": direction_distinct,
            "datetime_analysis": {"merged_preview": merged_preview},
            "sample_row_count": len(sample_rows),
            "preview_columns": preview_columns,
            "preview_grid": preview_grid,
            "ocr_page_meta": page_meta,
            "input_kind": "ocr",
        }
