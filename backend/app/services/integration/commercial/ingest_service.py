"""Commercial-source ingest service with dedicated parsing rules."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import pandas as pd

from app.services.integration.bank.ingest_service import BankIngestService, IngestResult
from app.services.integration.commercial.flat_ingest import (
    detect_flat_format,
    parse_new_commercial_sheet,
    parse_old_commercial_sheet,
    _format_source_ref,
)


class CommercialIngestService(BankIngestService):
    """Ingest commercial procurement files into normalized line-level raw rows."""

    BASE_COLUMNS = [
        "数据来源",
        "询价单号",
        "摘要",
        "采购单位",
        "寻源策略",
        "询价类别",
        "预估去税总额",
        "公布中标信息",
        "提交人/时间",
        "报价截止时间",
        "报价方式",
        "联系人手机",
        "联系人邮箱",
        "状态",
        "询价类型",
        "预估含税总额",
        "寻源范围",
        "要求到货日期",
        "质疑截止时间",
        "报价类别",
        "固定电话",
        "货币",
        "中标原因",
        "中标供应商",
        "备注",
    ]

    DETAIL_COLUMNS = [
        "序号",
        "物资编码/来源采购申请代码--物资描述",
        "型号规格",
        "品牌/厂家/产地",
        "补充说明",
        "单位",
        "数量",
        "预估单价 (含税)",
        "预估总价 (含税)",
        "公司名称",
        "含税单价(元)",
        "总价(元)",
        "税率",
        "产地",
        "品牌",
        "交货日期",
        "供应商备注",
        "不含税合计总价(元)",
        "税额(元)",
        "含税合计总价(元)",
        "中标金额(元)",
        "中标总金额（元）",
    ]

    OUTPUT_COLUMNS = BASE_COLUMNS + DETAIL_COLUMNS

    def ingest_files(self, file_paths: list[str], bank_name: str, source_type: str = "commercial") -> IngestResult:
        """Ingest commercial files and flatten into one normalized detail sheet per file."""
        import_batch_id = str(uuid4())
        sheets_total = 0
        rows_total = 0
        new_templates = 0
        failed_files = 0

        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                failed_files += 1
                self._write_log(import_batch_id, file_path, "error", "文件不存在或不可读取")
                continue
            if path.suffix.lower() not in {".xlsx", ".xls"}:
                self._write_log(import_batch_id, file_path, "warning", "非Excel文件，已跳过")
                continue

            try:
                workbook = self._read_workbook_fallback(path, pd)
                detail_df = self._parse_commercial_workbook(
                    workbook,
                    bank_name=bank_name,
                    source_file_stem=path.stem,
                )
            except Exception as err:
                failed_files += 1
                self._write_log(import_batch_id, file_path, "error", f"商务网解析失败: {err}")
                continue

            if detail_df.empty:
                self._write_log(import_batch_id, file_path, "warning", "未提取到有效明细行，已跳过")
                continue

            file_hash = self._hash_file(path)
            file_id = self._insert_file_record(import_batch_id, path, file_hash, bank_name, source_type)
            sheet_name = "商务网明细"
            raw_columns = [str(col).strip() for col in detail_df.columns]
            fingerprint = self._build_fingerprint(bank_name, source_type, sheet_name, raw_columns)
            raw_table_name, is_new = self._ensure_schema_registry(
                bank_name=bank_name,
                source_type=source_type,
                sheet_name=sheet_name,
                fingerprint=fingerprint,
                columns=raw_columns,
                source_path=path,
            )
            if is_new:
                new_templates += 1

            inserted_rows = self._insert_raw_rows(
                raw_table_name=raw_table_name,
                dataframe=detail_df.fillna(""),
                bank_name=bank_name,
                import_batch_id=import_batch_id,
                source_file_id=file_id,
                source_sheet=sheet_name,
                fingerprint=fingerprint,
                source_type=source_type,
            )
            rows_total += inserted_rows
            sheets_total += 1
            self._insert_sheet_record(
                file_id=file_id,
                sheet_name=sheet_name,
                fingerprint=fingerprint,
                raw_table_name=raw_table_name,
                rows_imported=inserted_rows,
                source_type=source_type,
            )
            self._write_log(
                import_batch_id,
                str(path),
                "info",
                f"商务网解析完成，明细行 {inserted_rows}，表 {raw_table_name}",
            )

        return IngestResult(
            import_batch_id=import_batch_id,
            files_total=len(file_paths),
            sheets_total=sheets_total,
            rows_total=rows_total,
            new_templates=new_templates,
            failed_files=failed_files,
        )

    def _parse_commercial_workbook(
        self,
        workbook: dict[str, Any],
        bank_name: str = "",
        source_file_stem: str = "",
    ) -> pd.DataFrame:
        """Parse workbook into normalized line-level commercial rows."""
        header_ctx: dict[str, str] = {}
        records: list[dict[str, str]] = []
        for sheet_name, raw_df in workbook.items():
            if raw_df is None or raw_df.empty:
                continue
            df = raw_df.astype(object).fillna("")
            flat_format = detect_flat_format(df)
            if flat_format == "old":
                records.extend(
                    parse_old_commercial_sheet(
                        df,
                        purchaser=bank_name,
                        output_columns=self.OUTPUT_COLUMNS,
                        source_file=source_file_stem,
                        source_sheet=str(sheet_name),
                    )
                )
                continue
            if flat_format == "new":
                records.extend(
                    parse_new_commercial_sheet(
                        df,
                        purchaser=bank_name,
                        output_columns=self.OUTPUT_COLUMNS,
                        source_file=source_file_stem,
                        source_sheet=str(sheet_name),
                    )
                )
                continue
            if df.shape[1] <= 8:
                header_ctx.update(self._extract_header_context(df))
                continue
            records.extend(
                self._extract_detail_rows(
                    df,
                    header_ctx,
                    source_file=source_file_stem,
                    source_sheet=str(sheet_name),
                )
            )
        if not records:
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        return pd.DataFrame(records, columns=self.OUTPUT_COLUMNS).fillna("")

    def _extract_header_context(self, df: pd.DataFrame) -> dict[str, str]:
        """Extract key/value metadata from narrow header sheets."""
        key_map = {
            "询价单号": "询价单号",
            "摘要": "摘要",
            "采购单位": "采购单位",
            "寻源策略": "寻源策略",
            "询价类别": "询价类别",
            "预估去税总额": "预估去税总额",
            "公布中标信息": "公布中标信息",
            "提交人/时间": "提交人/时间",
            "报价截止时间": "报价截止时间",
            "报价方式": "报价方式",
            "联系人手机": "联系人手机",
            "联系人邮箱": "联系人邮箱",
            "状态": "状态",
            "询价类型": "询价类型",
            "预估含税总额": "预估含税总额",
            "寻源范围": "寻源范围",
            "要求到货日期": "要求到货日期",
            "质疑截止时间": "质疑截止时间",
            "报价类别": "报价类别",
            "固定电话": "固定电话",
            "货币": "货币",
            "中标原因": "中标原因",
            "中标供应商": "中标供应商",
            "备注": "备注",
        }
        out: dict[str, str] = {}
        for _, row in df.iterrows():
            values = [self._to_text(v) for v in row.tolist()]
            for idx in range(0, max(0, len(values) - 1), 2):
                raw_key = values[idx]
                raw_value = values[idx + 1] if idx + 1 < len(values) else ""
                if not raw_key:
                    continue
                std_key = key_map.get(raw_key)
                if std_key and raw_value:
                    out[std_key] = raw_value
        return out

    def _extract_detail_rows(
        self,
        df: pd.DataFrame,
        header_ctx: dict[str, str],
        source_file: str = "",
        source_sheet: str = "",
    ) -> list[dict[str, str]]:
        """Expand wide supplier blocks into one row per detail x supplier."""
        header_row = self._find_detail_header_row(df)
        if header_row < 0:
            return []
        supplier_blocks = self._build_supplier_blocks(df, header_row)
        if not supplier_blocks:
            return []
        summary_rows = self._find_summary_rows(df, header_row)
        rows: list[dict[str, str]] = []
        for idx in range(header_row + 1, len(df)):
            row = df.iloc[idx]
            first_cell = self._to_text(row.iloc[0] if len(row) > 0 else "")
            if not first_cell:
                continue
            if self._looks_like_summary_key(first_cell):
                continue
            if not self._is_valid_detail_row(first_cell):
                continue
            excel_row = idx + 1
            for block in supplier_blocks:
                record = {key: header_ctx.get(key, "") for key in self.BASE_COLUMNS}
                record["数据来源"] = _format_source_ref(source_file, source_sheet, excel_row)
                record.update(
                    {
                        "序号": first_cell,
                        "物资编码/来源采购申请代码--物资描述": self._cell(row, 1),
                        "型号规格": self._cell(row, 2),
                        "品牌/厂家/产地": self._cell(row, 3),
                        "补充说明": self._cell(row, 4),
                        "单位": self._cell(row, 5),
                        "数量": self._cell(row, 6),
                        "预估单价 (含税)": self._cell(row, 7),
                        "预估总价 (含税)": self._cell(row, 8),
                        "公司名称": block["supplier_name"],
                        "含税单价(元)": "",
                        "总价(元)": "",
                        "税率": "",
                        "产地": "",
                        "品牌": "",
                        "交货日期": "",
                        "供应商备注": "",
                        "中标总金额（元）": "",
                    }
                )
                for col_idx in range(int(block["start_col"]), int(block["end_col"]) + 1):
                    field = self._map_supplier_subheader(self._to_text(df.iloc[header_row, col_idx]))
                    if not field:
                        continue
                    record[field] = self._cell(row, col_idx)
                record.update(self._extract_summary_values(df, block, summary_rows))
                if not any(record.get(name, "") for name in ("含税单价(元)", "总价(元)", "税率", "产地", "品牌")):
                    continue
                rows.append(record)
        return rows

    def _extract_summary_values(
        self, raw_df: pd.DataFrame, block: dict[str, Any], summary_rows: dict[str, int]
    ) -> dict[str, str]:
        """Extract supplier-level totals from summary rows."""
        out = {
            "不含税合计总价(元)": "",
            "税额(元)": "",
            "含税合计总价(元)": "",
            "中标金额(元)": "",
        }
        summary_map = {
            "不含税合计总价(元)": "不含税合计总价",
            "税额(元)": "税金",
            "含税合计总价(元)": "含税合计总价",
            "中标金额(元)": "中标金额",
        }
        start_col = int(block["start_col"])
        end_col = int(block["end_col"])
        for out_key, token in summary_map.items():
            row_idx = summary_rows.get(token)
            if row_idx is None:
                continue
            row = raw_df.iloc[row_idx]
            values = [self._to_text(row.iloc[col]) for col in range(start_col, end_col + 1)]
            first_non_empty = next((x for x in values if x), "")
            out[out_key] = first_non_empty
        return out

    def _find_summary_rows(self, df: pd.DataFrame, header_row: int) -> dict[str, int]:
        """Locate summary rows by label in first column."""
        mapping: dict[str, int] = {}
        for idx in range(header_row + 1, len(df)):
            label = self._to_text(df.iloc[idx, 0] if df.shape[1] > 0 else "")
            if not label:
                continue
            if "不含税合计总价" in label:
                mapping["不含税合计总价"] = idx
            elif "税金" in label or "税额" in label:
                mapping["税金"] = idx
            elif "含税合计总价" in label:
                mapping["含税合计总价"] = idx
            elif "中标金额" in label:
                mapping["中标金额"] = idx
        return mapping

    def _build_supplier_blocks(self, df: pd.DataFrame, header_row: int) -> list[dict[str, Any]]:
        """Build supplier column blocks from the row above detail headers."""
        supplier_row = header_row - 1 if header_row > 0 else header_row
        if supplier_row < 0:
            return []
        blocks: list[dict[str, Any]] = []
        col = 9
        total_cols = df.shape[1]
        while col < total_cols:
            supplier = self._to_text(df.iloc[supplier_row, col])
            if not supplier:
                col += 1
                continue
            start = col
            while col + 1 < total_cols and self._to_text(df.iloc[supplier_row, col + 1]) == supplier:
                col += 1
            end = col
            blocks.append({"supplier_name": supplier, "start_col": start, "end_col": end})
            col += 1
        return blocks

    def _map_supplier_subheader(self, text: str) -> str:
        value = self._to_text(text)
        if "含税单价" in value:
            return "含税单价(元)"
        if "总价" in value and "合计" not in value:
            return "总价(元)"
        if "税率" in value:
            return "税率"
        if "产地" in value:
            return "产地"
        if value == "品牌" or "品牌" in value:
            return "品牌"
        if "交货" in value or "到货" in value:
            return "交货日期"
        if "备注" in value:
            return "供应商备注"
        return ""

    def _find_detail_header_row(self, df: pd.DataFrame) -> int:
        """Find row containing detail headers like 序号/物资编码/单位/数量."""
        for idx in range(min(20, len(df))):
            text_row = [self._to_text(x) for x in df.iloc[idx].tolist()]
            joined = "|".join(text_row)
            if "序号" in joined and "单位" in joined and "数量" in joined:
                if idx + 1 < len(df):
                    next_row = "|".join([self._to_text(x) for x in df.iloc[idx + 1].tolist()])
                    if "含税单价" in next_row or "税率" in next_row:
                        return idx + 1
                return idx
        return -1

    def _is_valid_detail_row(self, first_cell: str) -> bool:
        """Keep rows with numeric-like sequence id and skip title rows."""
        text = self._to_text(first_cell)
        if not text:
            return False
        if self._looks_like_summary_key(text):
            return False
        return bool(re.fullmatch(r"\d+(\.0+)?", text))

    def _looks_like_summary_key(self, text: str) -> bool:
        value = self._to_text(text)
        tokens = ("合计", "税金", "中标金额", "总价")
        return any(tok in value for tok in tokens)

    def _cell(self, row: pd.Series, idx: int) -> str:
        if idx >= len(row):
            return ""
        return self._to_text(row.iloc[idx])

    def _to_text(self, value: Any) -> str:
        text = "" if value is None else str(value).strip()
        if text.lower() == "nan":
            return ""
        return text


__all__ = ["CommercialIngestService", "IngestResult"]

