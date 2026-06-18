"""Telecom CDR export service."""

from __future__ import annotations

from typing import Any

from app.services.integration.bank.export_service import BankExportService
from app.services.integration.telecom.carrier_templates import CANONICAL_COLUMNS


class TelecomExportService(BankExportService):
    """Export telecom CDR rows using the canonical carrier layout."""

    OUTPUT_COLUMNS = ["数据来源", *CANONICAL_COLUMNS]

    def _load_batch_all_raw_fields(self, import_batch_id: str) -> tuple[list[str], list[list[str]]]:
        rows = self._load_telecom_rows(import_batch_id)
        if not rows:
            return super()._load_batch_all_raw_fields(import_batch_id)
        output_rows = [[self._to_text(row.get(col, "")) for col in self.OUTPUT_COLUMNS] for row in rows]
        return self.OUTPUT_COLUMNS, output_rows

    def _load_telecom_rows(self, import_batch_id: str) -> list[dict[str, str]]:
        file_rows = self._client.query_all(
            """
            SELECT file_id, file_name
            FROM meta_bank_files
            WHERE import_batch_id=? AND source_type='telecom';
            """,
            (import_batch_id,),
        )
        file_name_map = {int(row[0]): str(row[1]) for row in file_rows if row and row[0] is not None}
        if not file_name_map:
            return []

        sheet_rows = self._client.query_all(
            """
            SELECT DISTINCT s.raw_table_name
            FROM meta_bank_sheets s
            JOIN meta_bank_files f ON f.file_id=s.file_id
            WHERE f.import_batch_id=? AND f.source_type='telecom'
            ORDER BY s.raw_table_name;
            """,
            (import_batch_id,),
        )
        table_names = [str(row[0]) for row in sheet_rows if row and row[0]]
        if not table_names:
            return []

        output: list[dict[str, str]] = []
        for table in table_names:
            info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
            src_cols = [str(x[1]) for x in info if str(x[1]).startswith("src_")]
            if not src_cols:
                continue
            sql_cols = ", ".join(self._client.quote_ident(c) for c in src_cols)
            raw_rows = self._client.query_all(
                f"""
                SELECT source_file_id, source_sheet, {sql_cols}
                FROM {self._client.quote_ident(table)}
                WHERE import_batch_id=?
                ORDER BY raw_id;
                """,
                (import_batch_id,),
            )
            label_map = {self._display_src_name(c): idx for idx, c in enumerate(src_cols, start=2)}
            normalized_label_map = {self._normalize_label(k): v for k, v in label_map.items()}
            for row in raw_rows:
                source_file_id = int(row[0]) if row[0] is not None else 0
                file_name = file_name_map.get(source_file_id, "")
                source_sheet = self._to_text(row[1])
                record: dict[str, str] = {
                    "数据来源": self._build_row_source_name(file_name, source_sheet, fallback_table=table)
                }
                for out_col in self.OUTPUT_COLUMNS[1:]:
                    idx = self._resolve_index(label_map, normalized_label_map, out_col)
                    record[out_col] = "" if idx is None else self._to_text(row[idx])
                output.append(record)
        return output

    def _resolve_index(
        self,
        label_map: dict[str, int],
        normalized_label_map: dict[str, int],
        output_col: str,
    ) -> int | None:
        idx = label_map.get(output_col)
        if idx is not None:
            return idx
        normalized_idx = normalized_label_map.get(self._normalize_label(output_col))
        if normalized_idx is not None:
            return normalized_idx
        return None

    def _normalize_label(self, value: str) -> str:
        text = self._to_text(value)
        return "".join(ch for ch in text if ch.isalnum())

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() == "nan":
            return ""
        return text


__all__ = ["TelecomExportService"]
