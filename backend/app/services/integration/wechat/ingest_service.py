"""WeChat transfer ingest service with fixed column layout."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from app.services.integration.bank.ingest_service import BankIngestService, IngestResult


class WechatIngestService(BankIngestService):
    """Ingest WeChat transfer Excel files using the official export column layout."""

    OUTPUT_COLUMNS = [
        "用户ID",
        "交易单号",
        "大单号",
        "用户侧账号名称",
        "借贷类型",
        "交易业务类型",
        "交易用途类型",
        "交易时间",
        "交易金额(分)",
        "账户余额(分)",
        "用户银行卡号",
        "用户侧网银联单号",
        "网联/银联",
        "第三方账户名称",
        "对手方ID",
        "对手侧账户名称",
        "对手方银行卡号",
        "对手侧银行名称",
        "对手侧网银联单号",
        "网联/银联.1",
        "基金公司信息",
        "间联/非间联交易",
        "第三方账户名称.1",
        "对手方接收时间",
        "对手方接收金额(分)",
        "备注1",
        "备注2",
    ]

    REQUIRED_COLUMNS = {"交易单号", "借贷类型", "交易时间", "交易金额(分)"}

    HEADER_ALIASES = {
        "借贷标志": "借贷类型",
        "借贷类型": "借贷类型",
        "交易金额（分）": "交易金额(分)",
        "交易金额(分)": "交易金额(分)",
        "账户余额（分）": "账户余额(分)",
        "账户余额(分)": "账户余额(分)",
        "对手方接收金额（分）": "对手方接收金额(分)",
        "对手方接收金额(分)": "对手方接收金额(分)",
    }

    def ingest_files(self, file_paths: list[str], bank_name: str, source_type: str = "wechat") -> IngestResult:
        """Ingest WeChat transfer files into normalized raw rows."""
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
                detail_df = self._parse_wechat_workbook(workbook)
            except Exception as err:
                failed_files += 1
                self._write_log(import_batch_id, file_path, "error", f"微信流水解析失败: {err}")
                continue

            if detail_df.empty:
                failed_files += 1
                self._write_log(import_batch_id, file_path, "warning", "未识别到有效微信流水行，已跳过")
                continue

            file_hash = self._hash_file(path)
            file_id = self._insert_file_record(import_batch_id, path, file_hash, bank_name, "", source_type)
            sheet_name = "微信流水"
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
                f"微信流水解析完成，明细行 {inserted_rows}，表 {raw_table_name}",
            )

        return IngestResult(
            import_batch_id=import_batch_id,
            files_total=len(file_paths),
            sheets_total=sheets_total,
            rows_total=rows_total,
            new_templates=new_templates,
            failed_files=failed_files,
        )

    def _parse_wechat_workbook(self, workbook: dict[str, Any]) -> pd.DataFrame:
        """Parse workbook sheets into normalized WeChat transfer rows."""
        records: list[dict[str, str]] = []
        for _, raw_df in workbook.items():
            if raw_df is None or raw_df.empty:
                continue
            normalized_df, _header_row = self._normalize_sheet_dataframe(raw_df, pd)
            if normalized_df.empty:
                continue
            normalized = self._normalize_wechat_dataframe(normalized_df)
            if normalized.empty:
                continue
            for _, row in normalized.iterrows():
                record = {col: self._to_text(row.get(col, "")) for col in self.OUTPUT_COLUMNS}
                if not record.get("交易单号"):
                    continue
                records.append(record)
        if not records:
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        return pd.DataFrame(records, columns=self.OUTPUT_COLUMNS).fillna("")

    def _normalize_wechat_dataframe(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Map source headers to the canonical WeChat export layout."""
        df = raw_df.copy()
        rename_map: dict[Any, str] = {}
        for col in df.columns:
            label = self._to_text(col)
            canonical = self.HEADER_ALIASES.get(label, label)
            if canonical in self.OUTPUT_COLUMNS:
                rename_map[col] = canonical
        df = df.rename(columns=rename_map)
        present = {self._to_text(c) for c in df.columns}
        if not self.REQUIRED_COLUMNS.issubset(present):
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)

        out = pd.DataFrame(index=df.index, columns=self.OUTPUT_COLUMNS)
        for col in self.OUTPUT_COLUMNS:
            if col in df.columns:
                out[col] = df[col].map(self._format_cell)
            else:
                out[col] = ""
        return out

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


__all__ = ["WechatIngestService", "IngestResult"]
