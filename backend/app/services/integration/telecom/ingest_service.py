"""Telecom CDR ingest service with carrier template matching."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from app.services.integration.bank.ingest_service import BankIngestService, IngestResult
from app.services.integration.telecom.carrier_templates import (
    CANONICAL_COLUMNS,
    match_carrier_template,
)


class TelecomIngestService(BankIngestService):
    """Ingest carrier CDR Excel files into normalized raw rows."""

    OUTPUT_COLUMNS = list(CANONICAL_COLUMNS)

    def ingest_files(
        self,
        file_paths: list[str],
        bank_name: str,
        source_type: str = "telecom",
        *,
        carrier_template_id: str = "",
    ) -> IngestResult:
        """Ingest telecom CDR files into normalized raw rows."""
        self._ensure_meta_columns()
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
                failed_files += 1
                self._write_log(import_batch_id, file_path, "warning", "非Excel文件，已跳过")
                continue

            try:
                workbook = self._read_workbook_fallback(path, pd)
                parsed = self._parse_telecom_workbook(workbook, carrier_template_id)
            except Exception as err:
                failed_files += 1
                self._write_log(import_batch_id, file_path, "error", f"运营商话单解析失败: {err}")
                continue

            if parsed.empty:
                failed_files += 1
                self._write_log(import_batch_id, file_path, "warning", "未识别到有效运营商话单行，已跳过")
                continue

            file_hash = self._hash_file(path)
            file_id = self._insert_file_record(import_batch_id, path, file_hash, bank_name, "", source_type)
            sheet_name = "运营商话单信息"
            raw_columns = [str(col).strip() for col in parsed.columns]
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
                dataframe=parsed.fillna(""),
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
                f"运营商话单解析完成，明细行 {inserted_rows}，表 {raw_table_name}",
            )

        return IngestResult(
            import_batch_id=import_batch_id,
            files_total=len(file_paths),
            sheets_total=sheets_total,
            rows_total=rows_total,
            new_templates=new_templates,
            failed_files=failed_files,
        )

    def _parse_telecom_workbook(self, workbook: dict[str, Any], carrier_template_id: str) -> pd.DataFrame:
        records: list[dict[str, str]] = []
        for sheet_name, raw_df in workbook.items():
            if raw_df is None or raw_df.empty:
                continue
            normalized_df, _header_row = self._normalize_sheet_dataframe(raw_df, pd)
            if normalized_df.empty:
                continue
            headers = [self._to_text(c) for c in normalized_df.columns]
            template = match_carrier_template(str(sheet_name), headers, carrier_hint=carrier_template_id)
            if template is None:
                continue
            normalized = self._normalize_telecom_dataframe(normalized_df, template)
            if normalized.empty:
                continue
            for _, row in normalized.iterrows():
                local_phone = self._to_text(row.get("本机号码"))
                peer_phone = self._to_text(row.get("对方号码"))
                call_time = self._resolve_call_time(row)
                if not local_phone or not peer_phone or not call_time:
                    continue
                record = {col: self._to_text(row.get(col, "")) for col in self.OUTPUT_COLUMNS}
                record["呼叫开始时间"] = call_time
                records.append(record)
        if not records:
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        return pd.DataFrame(records, columns=self.OUTPUT_COLUMNS).fillna("")

    def _normalize_telecom_dataframe(self, raw_df: pd.DataFrame, template) -> pd.DataFrame:
        df = raw_df.copy()
        rename_map: dict[Any, str] = {}
        for col in df.columns:
            label = self._to_text(col)
            canonical = label
            for target, aliases in template.field_map.items():
                if label == target or label in aliases:
                    canonical = target
                    break
            if canonical in self.OUTPUT_COLUMNS:
                rename_map[col] = canonical
        df = df.rename(columns=rename_map)
        present = {self._to_text(c) for c in df.columns}
        if not template.required_columns.issubset(present):
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)

        out = pd.DataFrame(index=df.index, columns=self.OUTPUT_COLUMNS)
        for col in self.OUTPUT_COLUMNS:
            if col in df.columns:
                out[col] = df[col].map(self._format_cell)
            else:
                out[col] = ""
        return out

    def _resolve_call_time(self, row: pd.Series) -> str:
        call_time = self._format_cell(row.get("呼叫开始时间", ""))
        if call_time:
            return call_time
        return self._format_cell(row.get("短信发送接收时间", ""))

    def _format_cell(self, value: Any) -> str:
        if hasattr(value, "strftime"):
            try:
                return value.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        text = self._to_text(value)
        if not text:
            return ""
        if text.endswith(".0") and text.replace(".0", "").isdigit():
            return text[:-2]
        return text

    def _to_text(self, value: Any) -> str:
        text = "" if value is None else str(value).strip()
        if text.lower() == "nan":
            return ""
        return text


__all__ = ["TelecomIngestService", "IngestResult"]
