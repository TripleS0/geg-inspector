"""Load wechat / telecom / commercial rows from dynamic raw tables for data center."""

from __future__ import annotations

import re
from typing import Any, Callable

from app.services.integration.commercial.export_service import CommercialExportService
from app.services.integration.telecom.export_service import TelecomExportService
from app.services.integration.wechat.export_service import WechatExportService
from app.services.shared.db.sqlite_client import SqliteClient

SOURCE_LABELS: dict[str, str] = {
    "bank": "银行流水",
    "wechat": "微信转账",
    "telecom": "通讯话单",
    "commercial": "商务网",
    "enterprise": "工商信息",
}


class RawCenterRecordLoader:
    """Expose raw-layer import rows as data-center records."""

    RAW_SOURCE_TYPES = frozenset({"wechat", "telecom", "commercial"})

    def __init__(self, client: SqliteClient) -> None:
        self._client = client

    def load_records(
        self,
        batch_scopes: list[tuple[str, str]],
        *,
        source_type: str | None = None,
        keyword: str = "",
    ) -> list[dict[str, Any]]:
        st_filter = (source_type or "all").strip()
        kw = (keyword or "").strip().lower()
        items: list[dict[str, Any]] = []
        for batch_id, batch_source in batch_scopes:
            if batch_source not in self.RAW_SOURCE_TYPES:
                continue
            if st_filter not in ("all", batch_source):
                continue
            if batch_source == "wechat":
                rows = self._load_wechat(batch_id)
            elif batch_source == "telecom":
                rows = self._load_telecom(batch_id)
            else:
                rows = self._load_commercial(batch_id)
            for row in rows:
                if kw and kw not in " ".join(
                    str(row.get(k) or "") for k in ("content", "source_file", "import_batch_id", "record_date")
                ).lower():
                    continue
                items.append(row)
        items.sort(key=lambda r: (r.get("_sort_key") or "", r.get("record_id") or 0), reverse=True)
        for row in items:
            row.pop("_sort_key", None)
        return items

    def count_records(
        self,
        batch_scopes: list[tuple[str, str]],
        *,
        source_type: str | None = None,
        keyword: str = "",
    ) -> int:
        return len(self.load_records(batch_scopes, source_type=source_type, keyword=keyword))

    def source_counts(self, batch_scopes: list[tuple[str, str]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for batch_id, batch_source in batch_scopes:
            if batch_source not in self.RAW_SOURCE_TYPES:
                continue
            if batch_source == "wechat":
                cnt = len(self._load_wechat(batch_id))
            elif batch_source == "telecom":
                cnt = len(self._load_telecom(batch_id))
            else:
                cnt = len(self._load_commercial(batch_id))
            counts[batch_source] = counts.get(batch_source, 0) + cnt
        return counts

    def _load_wechat(self, batch_id: str) -> list[dict[str, Any]]:
        export = WechatExportService(self._client)

        def map_row(raw_id: int, raw_table: str, row: dict[str, str], source_file: str) -> dict[str, Any]:
            user = row.get("用户侧账号名称", "")
            cp = row.get("对手侧账户名称", "")
            amount_fen = row.get("交易金额(分)", "")
            amount_yuan = ""
            try:
                if str(amount_fen).strip():
                    amount_yuan = f"{int(str(amount_fen).replace(',', '')) / 100:.2f}元"
            except ValueError:
                amount_yuan = str(amount_fen)
            content = f"{user} → {cp} {amount_yuan}".strip()
            txn_time = row.get("交易时间", "")
            return self._record(raw_id, raw_table, "wechat", batch_id, content, txn_time, source_file or row.get("数据来源", ""))

        return self._load_dynamic_rows(batch_id, "wechat", map_row, fallback_loader=export._load_wechat_rows)

    def _load_telecom(self, batch_id: str) -> list[dict[str, Any]]:
        export = TelecomExportService(self._client)

        def map_row(raw_id: int, raw_table: str, row: dict[str, str], source_file: str) -> dict[str, Any]:
            caller = row.get("主叫号码", "") or row.get("本机号码", "")
            callee = row.get("被叫号码", "") or row.get("对方号码", "")
            txn_time = row.get("呼叫开始时间", "") or row.get("短信发送接收时间", "")
            content = f"{caller} → {callee}".strip(" →")
            return self._record(raw_id, raw_table, "telecom", batch_id, content, txn_time, source_file or row.get("数据来源", ""))

        return self._load_dynamic_rows(batch_id, "telecom", map_row, fallback_loader=export._load_telecom_rows)

    def _load_commercial(self, batch_id: str) -> list[dict[str, Any]]:
        export = CommercialExportService(self._client)

        def map_row(raw_id: int, raw_table: str, row: dict[str, str], source_file: str) -> dict[str, Any]:
            company = row.get("公司名称", "")
            inquiry = row.get("询价单号", "")
            winner = row.get("中标供应商", "") or row.get("中标情况", "")
            content = " · ".join(p for p in [company, inquiry, winner] if p)
            record_date = row.get("中标日期", "") or row.get("询价日期", "")
            return self._record(raw_id, raw_table, "commercial", batch_id, content, record_date, source_file or row.get("数据来源", ""))

        return self._load_dynamic_rows(batch_id, "commercial", map_row, fallback_loader=export._load_commercial_rows)

    def _load_dynamic_rows(
        self,
        batch_id: str,
        source_type: str,
        map_row: Callable[[int, str, dict[str, str], str], dict[str, Any]],
        *,
        fallback_loader: Callable[[str], list[dict[str, str]]] | None = None,
    ) -> list[dict[str, Any]]:
        file_rows = self._client.query_all(
            """
            SELECT file_id, file_name
            FROM meta_bank_files
            WHERE import_batch_id=? AND source_type=?;
            """,
            (batch_id, source_type),
        )
        file_name_map = {int(row[0]): str(row[1]) for row in file_rows if row and row[0] is not None}
        if not file_name_map:
            return []

        sheet_rows = self._client.query_all(
            """
            SELECT DISTINCT s.raw_table_name
            FROM meta_bank_sheets s
            JOIN meta_bank_files f ON f.file_id=s.file_id
            WHERE f.import_batch_id=? AND f.source_type=?
            ORDER BY s.raw_table_name;
            """,
            (batch_id, source_type),
        )
        table_names = [str(row[0]) for row in sheet_rows if row and row[0]]
        if not table_names:
            return []

        export = WechatExportService(self._client)
        output: list[dict[str, Any]] = []
        for table in table_names:
            info = self._client.query_all(f"PRAGMA table_info({self._client.quote_ident(table)});")
            src_cols = [str(x[1]) for x in info if str(x[1]).startswith("src_")]
            if not src_cols:
                continue
            sql_cols = ", ".join(self._client.quote_ident(c) for c in src_cols)
            raw_rows = self._client.query_all(
                f"""
                SELECT raw_id, source_file_id, source_sheet, {sql_cols}
                FROM {self._client.quote_ident(table)}
                WHERE import_batch_id=?
                ORDER BY raw_id;
                """,
                (batch_id,),
            )
            label_map = {export._display_src_name(c): idx for idx, c in enumerate(src_cols, start=3)}
            normalized_label_map = {export._normalize_label(k): v for k, v in label_map.items()}
            for row in raw_rows:
                raw_id = int(row[0])
                source_file_id = int(row[1]) if row[1] is not None else 0
                file_name = file_name_map.get(source_file_id, "")
                source_sheet = str(row[2] or "")
                source_file = export._build_row_source_name(file_name, source_sheet, fallback_table=table)
                record: dict[str, str] = {}
                for label, idx in label_map.items():
                    record[label] = str(row[idx] or "")
                output.append(map_row(raw_id, table, record, source_file))
        return output

    def _record(
        self,
        raw_id: int,
        raw_table: str,
        source_type: str,
        batch_id: str,
        content: str,
        record_date: str,
        source_file: str,
    ) -> dict[str, Any]:
        sort_key = (record_date or "").replace("/", "-").replace(".", "-")
        return {
            "record_kind": "raw",
            "record_id": raw_id,
            "raw_table": raw_table,
            "source_type": source_type,
            "source_type_label": SOURCE_LABELS.get(source_type, source_type),
            "import_batch_id": batch_id,
            "content": content or "—",
            "record_date": self._format_date(record_date),
            "source_file": source_file or "—",
            "_sort_key": sort_key,
        }

    @staticmethod
    def _format_date(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "—"
        text = text.replace("T", " ").replace("/", ".")
        m = re.match(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", text)
        if m:
            return f"{m.group(1)}.{int(m.group(2))}.{int(m.group(3))}"
        if len(text) >= 10:
            return text[:10].replace("-", ".")
        return text

    def delete_raw_record(self, raw_table: str, raw_id: int) -> bool:
        if not raw_table or not re.match(r"^[A-Za-z0-9_]+$", raw_table):
            return False
        self._client.execute(
            f"DELETE FROM {self._client.quote_ident(raw_table)} WHERE raw_id=?;",
            (raw_id,),
        )
        return True
