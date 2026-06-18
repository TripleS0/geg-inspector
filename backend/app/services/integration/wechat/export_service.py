"""WeChat transfer export service."""

from __future__ import annotations

from typing import Any

from app.services.integration.bank.export_service import BankExportService


class WechatExportService(BankExportService):
    """Export WeChat transfer rows using the official column layout."""

    OUTPUT_COLUMNS = [
        "数据来源",
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

    FIELD_ALIASES: dict[str, set[str]] = {
        "借贷类型": {"借贷类型", "借贷标志"},
        "交易金额(分)": {"交易金额(分)", "交易金额（分）"},
        "账户余额(分)": {"账户余额(分)", "账户余额（分）"},
        "对手方接收金额(分)": {"对手方接收金额(分)", "对手方接收金额（分）"},
    }

    def _load_batch_all_raw_fields(self, import_batch_id: str) -> tuple[list[str], list[list[str]]]:
        rows = self._load_wechat_rows(import_batch_id)
        if not rows:
            return super()._load_batch_all_raw_fields(import_batch_id)
        output_rows = [[self._to_text(row.get(col, "")) for col in self.OUTPUT_COLUMNS] for row in rows]
        return self.OUTPUT_COLUMNS, output_rows

    def _load_wechat_rows(self, import_batch_id: str) -> list[dict[str, str]]:
        file_rows = self._client.query_all(
            """
            SELECT file_id, file_name
            FROM meta_bank_files
            WHERE import_batch_id=? AND source_type='wechat';
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
            WHERE f.import_batch_id=? AND f.source_type='wechat'
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
                    if idx is None:
                        idx = self._resolve_alias_index(label_map, normalized_label_map, out_col)
                    record[out_col] = "" if idx is None else self._to_text(row[idx])
                output.append(record)
        return output

    def _resolve_alias_index(
        self,
        label_map: dict[str, int],
        normalized_label_map: dict[str, int],
        out_col: str,
    ) -> int | None:
        aliases = self.FIELD_ALIASES.get(out_col, set())
        for alias in aliases:
            idx = self._resolve_index(label_map, normalized_label_map, alias)
            if idx is not None:
                return idx
        return None

    def _resolve_index(
        self,
        label_map: dict[str, int],
        normalized_label_map: dict[str, int],
        output_col: str,
    ) -> int | None:
        aliases = self.FIELD_ALIASES.get(output_col, {output_col})
        for alias in aliases:
            idx = label_map.get(alias)
            if idx is not None:
                return idx
            normalized_idx = normalized_label_map.get(self._normalize_label(alias))
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


__all__ = ["WechatExportService"]
