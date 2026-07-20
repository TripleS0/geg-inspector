"""Bank multi-sheet ingest service for local SQLite raw layer."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.shared.db.sqlite_client import SqliteClient
from app.services.integration.bank.bank_catalog_repository import BankCatalogRepository
from app.services.integration.bank.template_library import (
    BankTemplate,
    find_column,
    get_template_by_id,
    infer_bank_name,
    infer_bank_name_by_columns,
    infer_file_purpose,
    infer_sheet_purpose,
    infer_sheet_purpose_by_columns,
    match_template,
)


@dataclass(frozen=True)
class IngestResult:
    """Summary returned after one ingest batch."""

    import_batch_id: str
    files_total: int
    sheets_total: int
    rows_total: int
    new_templates: int
    failed_files: int


class BankIngestService:
    """Ingest bank excel files into SQLite raw/meta tables."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        """Initialize service with DB client."""
        self._client = client or SqliteClient()

    def ingest_files(self, file_paths: list[str], bank_name: str, source_type: str = "bank", sheet_assignments: dict[str, Any] | None = None) -> IngestResult:
        """Ingest multiple files and return aggregated summary."""
        self._ensure_meta_columns()
        catalog = BankCatalogRepository(self._client)
        try:
            import pandas as pd
        except ImportError as err:
            raise RuntimeError("缺少 pandas 依赖，请先执行: pip install -r requirements.txt") from err

        import_batch_id = str(uuid4())
        sheets_total = 0
        rows_total = 0
        new_templates = 0
        failed_files = 0

        for file_path in file_paths:
            path = Path(file_path)
            file_config = (sheet_assignments or {}).get(str(path), {})
            explicit_format = isinstance(file_config, dict) and "sheets" in file_config
            file_assignments = file_config.get("sheets", {}) if explicit_format else file_config
            if not path.exists() or not path.is_file():
                failed_files += 1
                self._write_log(import_batch_id, file_path, "error", "文件不存在或不可读取")
                continue

            if path.suffix.lower() not in {".xlsx", ".xls"}:
                self._write_log(import_batch_id, file_path, "warning", "非Excel文件，已跳过")
                continue

            try:
                workbook = self._read_workbook_fallback(path, pd)
            except Exception as err:
                failed_files += 1
                self._write_log(import_batch_id, file_path, "error", f"读取Excel失败: {err}")
                continue

            file_hash = self._hash_file(path)
            requested_bank_id = str(file_config.get("bank_id") or "").strip() if explicit_format else ""
            bank_record = catalog.get(requested_bank_id) if requested_bank_id else None
            if bank_record is None:
                inferred_name = infer_bank_name(path.name, list(workbook.keys()), fallback=bank_name, client=self._client)
                bank_record = catalog.get_by_name(inferred_name)
            if bank_record is None or not bank_record.is_active:
                raise ValueError(f"文件 {path.name} 尚未确认有效的银行分类")
            effective_bank_name = bank_record.display_name
            file_type = infer_file_purpose(path.name)
            file_id = self._insert_file_record(import_batch_id, path, file_hash, effective_bank_name, bank_record.bank_id, source_type)

            for sheet_name, dataframe in workbook.items():
                assignment = file_assignments.get(str(sheet_name), {})
                # The browser preserves the uploaded filename. It is a useful
                # signal for files such as "工商银行开户信息.xlsx" whose Sheet is generic.
                sheet_type_early = file_type or infer_sheet_purpose(f"{path.name} {sheet_name}")
                default_template_id = str((
                    file_config.get("default_account_template_id")
                    if sheet_type_early == "account_profile"
                    else file_config.get("default_txn_template_id")
                ) or "")
                selected_template = get_template_by_id(
                    str(assignment.get("template_id") or default_template_id or ""), self._client
                )
                tpl_early = selected_template or match_template(
                    effective_bank_name,
                    str(sheet_name),
                    sheet_type=sheet_type_early,
                    client=self._client,
                )
                fixed_hdr = None
                if tpl_early is not None and tpl_early.header_row_hint is not None:
                    fixed_hdr = int(tpl_early.header_row_hint)
                dataframe, header_row = self._normalize_sheet_dataframe(
                    dataframe, pd, fixed_header_row=fixed_hdr
                )
                if dataframe.empty or dataframe.shape[1] == 0:
                    self._write_log(
                        import_batch_id,
                        str(path),
                        "warning",
                        f"Sheet[{sheet_name}] 未识别到有效数据区，已跳过",
                    )
                    continue
                sheets_total += 1
                dataframe = dataframe.fillna("")
                raw_columns = [str(col).strip() for col in dataframe.columns]
                sheet_bank_name = effective_bank_name
                # An explicit filename convention wins; otherwise use the
                # actual columns to distinguish account profiles and records.
                st_col = file_type or infer_sheet_purpose_by_columns(raw_columns, fallback=sheet_type_early)
                if not assignment.get("template_id"):
                    resolved_default_id = str((
                        file_config.get("default_account_template_id")
                        if st_col == "account_profile"
                        else file_config.get("default_txn_template_id")
                    ) or "")
                    if resolved_default_id:
                        selected_template = get_template_by_id(resolved_default_id, self._client)
                if explicit_format and selected_template is None:
                    raise ValueError(f"文件 {path.name} 的 Sheet[{sheet_name}] 尚未确认模板")
                if selected_template is not None and selected_template.bank_display_name != effective_bank_name:
                    raise ValueError(f"Sheet[{sheet_name}] 选择的模板不属于 {effective_bank_name}")
                if selected_template is not None:
                    sheet_bank_name = effective_bank_name
                    st_col = selected_template.template_type
                fingerprint = self._build_fingerprint(
                    sheet_bank_name, source_type, sheet_name, raw_columns,
                    selected_template.template_id if selected_template else "",
                )
                raw_table_name, is_new = self._ensure_schema_registry(
                    bank_name=sheet_bank_name,
                    source_type=source_type,
                    sheet_name=sheet_name,
                    fingerprint=fingerprint,
                    columns=raw_columns,
                    source_path=path,
                    template_type=st_col,
                )
                if is_new:
                    new_templates += 1
                if selected_template is not None:
                    self._apply_selected_template_mapping(fingerprint, raw_columns, selected_template)

                inserted_rows = self._insert_raw_rows(
                    raw_table_name=raw_table_name,
                    dataframe=dataframe,
                    bank_name=sheet_bank_name,
                    import_batch_id=import_batch_id,
                    source_file_id=file_id,
                    source_sheet=sheet_name,
                    fingerprint=fingerprint,
                    source_type=source_type,
                )
                rows_total += inserted_rows
                self._insert_sheet_record(
                    file_id=file_id,
                    sheet_name=sheet_name,
                    fingerprint=fingerprint,
                    raw_table_name=raw_table_name,
                    rows_imported=inserted_rows,
                    source_type=source_type,
                    selected_template_id=selected_template.template_id if selected_template else "",
                    template_type=st_col,
                    template_snapshot=self._template_snapshot(selected_template, raw_columns, bank_record.bank_id),
                )
                self._write_log(
                    import_batch_id,
                    str(path),
                    "info",
                    f"Sheet[{sheet_name}] 入库完成，写入 {inserted_rows} 行，表 {raw_table_name}，表头行={header_row + 1}",
                )

        return IngestResult(
            import_batch_id=import_batch_id,
            files_total=len(file_paths),
            sheets_total=sheets_total,
            rows_total=rows_total,
            new_templates=new_templates,
            failed_files=failed_files,
        )

    def _read_workbook_fallback(self, path: Path, pd: Any) -> dict[str, Any]:
        """Read xlsx/xls with explicit engines; fallback to html-table style xls."""
        suffix = path.suffix.lower()
        tried: list[str] = []
        if suffix == ".xls" and self._looks_like_html(path):
            try:
                return self._read_html_tables(path, pd)
            except Exception as err:
                tried.append(f"html-first: {err}")

        if suffix == ".xlsx":
            engines = ("openpyxl", None)
        else:
            engines = ("xlrd", "openpyxl", None)

        for engine in engines:
            try:
                if engine:
                    return pd.read_excel(path, sheet_name=None, dtype=object, engine=engine, header=None)
                return pd.read_excel(path, sheet_name=None, dtype=object, header=None)
            except Exception as err:
                tried.append(f"{engine or 'auto'}: {err}")

        # Some vendor ".xls" files are actually HTML tables.
        if suffix == ".xls":
            try:
                workbook = self._read_html_tables(path, pd)
                if workbook:
                    return workbook
            except Exception as err:
                tried.append(f"html: {err}")

        raise RuntimeError("；".join(tried) if tried else "未知读取错误")

    def _read_html_tables(self, path: Path, pd: Any) -> dict[str, Any]:
        """Read html tables from disguised xls/html exports."""
        tables = pd.read_html(path, encoding="utf-8", header=None)
        workbook: dict[str, Any] = {}
        for idx, df in enumerate(tables, start=1):
            workbook[f"HTML表{idx}"] = df.astype(object).fillna("")
        return workbook

    def _looks_like_html(self, path: Path) -> bool:
        """Best-effort detect html-like xls content by file header bytes."""
        try:
            head = path.read_bytes()[:4096].decode("latin-1", errors="ignore").lower()
        except Exception:
            return False
        return "<html" in head or "<table" in head or "<!doctype html" in head

    def _normalize_sheet_dataframe(
        self,
        dataframe: Any,
        pd: Any,
        *,
        fixed_header_row: int | None = None,
    ) -> tuple[Any, int]:
        """Auto-detect header row and normalize column names."""
        df = dataframe.copy()
        if df is None or df.empty:
            return pd.DataFrame(), 0

        # Remove fully empty rows first to avoid long title blocks.
        df = df.fillna("")
        df = df[df.apply(lambda row: any(str(v).strip() for v in row.tolist()), axis=1)].reset_index(drop=True)
        if df.empty:
            return pd.DataFrame(), 0

        if fixed_header_row is not None and 0 <= fixed_header_row < len(df):
            header_row = fixed_header_row
        else:
            header_row = self._detect_header_row(df)
        header_values = df.iloc[header_row].tolist() if header_row < len(df) else []
        normalized_headers = self._normalize_headers(header_values, df.shape[1])
        data = df.iloc[header_row + 1 :].reset_index(drop=True)
        if data.empty:
            return pd.DataFrame(columns=normalized_headers), header_row
        data.columns = normalized_headers
        data = data[data.apply(lambda row: any(str(v).strip() for v in row.tolist()), axis=1)].reset_index(drop=True)
        return data, header_row

    def _detect_header_row(self, df: Any) -> int:
        """Score first rows and pick the most likely header line."""
        max_scan = min(40, len(df))
        best_row = 0
        best_score = float("-inf")
        for row_idx in range(max_scan):
            raw = ["" if v is None else str(v).strip() for v in df.iloc[row_idx].tolist()]
            non_empty = [x for x in raw if x]
            if len(non_empty) < 2:
                continue

            unique_ratio = len(set(non_empty)) / max(1, len(non_empty))
            keyword_hits = sum(1 for x in non_empty if self._looks_like_business_header(x))
            unnamed_hits = sum(1 for x in non_empty if x.lower().startswith("unnamed"))
            long_text_penalty = sum(1 for x in non_empty if len(x) >= 28)

            data_like_hits = 0
            preview_end = min(len(df), row_idx + 6)
            for i in range(row_idx + 1, preview_end):
                next_row = ["" if v is None else str(v).strip() for v in df.iloc[i].tolist()]
                data_like_hits += sum(1 for x in next_row if self._looks_like_data_value(x))

            score = (
                len(non_empty) * 1.5
                + unique_ratio * 4
                + keyword_hits * 3
                + data_like_hits * 0.3
                - unnamed_hits * 2
                - long_text_penalty * 0.8
            )
            if score > best_score:
                best_score = score
                best_row = row_idx
        return best_row

    def _normalize_headers(self, header_values: list[Any], width: int) -> list[str]:
        """Clean headers: remove unnamed/empty and dedupe names."""
        headers: list[str] = []
        seen: dict[str, int] = {}
        for idx in range(width):
            raw = str(header_values[idx]).strip() if idx < len(header_values) else ""
            raw = re.sub(r"\s+", " ", raw)
            if not raw or raw.lower().startswith("unnamed"):
                raw = f"字段{idx + 1}"
            base = raw
            seq = seen.get(base, 0) + 1
            seen[base] = seq
            headers.append(base if seq == 1 else f"{base}_{seq}")
        return headers

    def _looks_like_business_header(self, text: str) -> bool:
        tokens = (
            "日期",
            "时间",
            "金额",
            "余额",
            "账号",
            "户名",
            "摘要",
            "凭证",
            "交易",
            "对手方",
            "编号",
            "银行",
        )
        return any(tok in text for tok in tokens)

    def _looks_like_data_value(self, text: str) -> bool:
        if not text:
            return False
        if re.fullmatch(r"[-+]?\d+(\.\d+)?", text):
            return True
        if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text):
            return True
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
            return True
        if len(text) <= 20 and any(ch.isdigit() for ch in text):
            return True
        return False

    def _hash_file(self, path: Path) -> str:
        """Calculate SHA256 for dedupe and tracing."""
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _build_fingerprint(
        self,
        bank_name: str,
        source_type: str,
        sheet_name: str,
        columns: list[str],
        template_id: str = "",
    ) -> str:
        """Build template fingerprint from bank/sheet/columns."""
        payload = json.dumps(
            {
                "bank": bank_name.strip().lower(),
                "source_type": source_type.strip().lower(),
                "sheet": sheet_name.strip().lower(),
                "columns": [col.strip().lower() for col in columns],
                "template_id": template_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _ensure_schema_registry(
        self,
        bank_name: str,
        source_type: str,
        sheet_name: str,
        fingerprint: str,
        columns: list[str],
        source_path: Path,
        template_type: str | None = None,
    ) -> tuple[str, bool]:
        """Ensure registry row exists and return raw table name."""
        template_type = template_type or infer_sheet_purpose(sheet_name)
        template_type = infer_sheet_purpose_by_columns(columns, fallback=template_type)
        existing = self._client.query_all(
            "SELECT raw_table_name FROM meta_schema_registry WHERE template_fingerprint=? LIMIT 1;",
            (fingerprint,),
        )
        if existing:
            raw_table_name = str(existing[0][0])
            self._client.execute(
                """
                UPDATE meta_schema_registry
                SET template_type=?, bank_name=?, sheet_name=?
                WHERE template_fingerprint=?;
                """,
                (template_type, bank_name, sheet_name, fingerprint),
            )
            self._ensure_raw_table_source_type_column(raw_table_name)
            return raw_table_name, False

        raw_table_name = self._build_raw_table_name_from_source(source_path, sheet_name, fingerprint)
        self._create_raw_table(raw_table_name, columns)
        self._client.execute(
            """
            INSERT INTO meta_schema_registry
            (bank_name, source_type, template_fingerprint, template_version, sheet_name, raw_table_name, schema_json, status, template_type)
            VALUES (?, ?, ?, 1, ?, ?, ?, 'pending_mapping', ?);
            """,
            (bank_name, source_type, fingerprint, sheet_name, raw_table_name, json.dumps({"columns": columns}), template_type),
        )
        return raw_table_name, True

    def _ensure_meta_columns(self) -> None:
        """Backfill new metadata columns on legacy DB."""
        schema_info = self._client.query_all("PRAGMA table_info(meta_schema_registry);")
        names = {str(row[1]) for row in schema_info}
        if "template_type" not in names:
            self._client.execute(
                "ALTER TABLE meta_schema_registry ADD COLUMN template_type TEXT NOT NULL DEFAULT 'txn_detail';"
            )
        sheet_info = self._client.query_all("PRAGMA table_info(meta_bank_sheets);")
        sheet_names = {str(row[1]) for row in sheet_info}
        if "selected_template_id" not in sheet_names:
            self._client.execute("ALTER TABLE meta_bank_sheets ADD COLUMN selected_template_id TEXT NOT NULL DEFAULT '';" )
        if "template_type" not in sheet_names:
            self._client.execute("ALTER TABLE meta_bank_sheets ADD COLUMN template_type TEXT NOT NULL DEFAULT 'txn_detail';")
        if "template_snapshot_json" not in sheet_names:
            self._client.execute("ALTER TABLE meta_bank_sheets ADD COLUMN template_snapshot_json TEXT NOT NULL DEFAULT '{}';")
        file_info = self._client.query_all("PRAGMA table_info(meta_bank_files);")
        file_names = {str(row[1]) for row in file_info}
        if "bank_id" not in file_names:
            self._client.execute("ALTER TABLE meta_bank_files ADD COLUMN bank_id TEXT NOT NULL DEFAULT '';")

    def _apply_selected_template_mapping(self, fingerprint: str, columns: list[str], template: BankTemplate) -> None:
        self._client.execute("DELETE FROM meta_field_mapping WHERE template_fingerprint=?;", (fingerprint,))
        for std_field, aliases in template.field_map.items():
            source = find_column(columns, aliases)
            if source:
                self._client.execute("INSERT INTO meta_field_mapping (template_fingerprint, raw_field_name, std_field_name, template_type, transform_rule, priority, is_active) VALUES (?, ?, ?, ?, 'identity', 10, 1);", (fingerprint, source, std_field, template.template_type))

    def _template_snapshot(self, template: BankTemplate | None, columns: list[str], bank_id: str) -> dict[str, Any]:
        if template is None:
            return {}
        field_map: dict[str, str] = {}
        for std_field, aliases in template.field_map.items():
            source = find_column(columns, aliases)
            if source:
                field_map[std_field] = source
        return {
            "template_id": template.template_id,
            "template_type": template.template_type,
            "bank_id": bank_id,
            "field_map": field_map,
            "direction_rules": dict(template.direction_rules or {}),
            "datetime_patterns": template.datetime_patterns,
        }

    def _create_raw_table(self, raw_table_name: str, columns: list[str]) -> None:
        """Create raw table with dynamic source columns."""
        source_columns = []
        for column in columns:
            col_name = self._safe_ident(column)[:50]
            source_columns.append(f"\"src_{col_name}\" TEXT")
        source_cols_sql = ", ".join(source_columns) if source_columns else ""
        if source_cols_sql:
            source_cols_sql = f", {source_cols_sql}"
        sql = f"""
        CREATE TABLE IF NOT EXISTS "{raw_table_name}" (
            raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_batch_id TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'bank',
            source_file_id INTEGER,
            source_sheet TEXT NOT NULL,
            template_fingerprint TEXT NOT NULL,
            row_no INT NOT NULL,
            raw_payload TEXT NOT NULL
            {source_cols_sql}
        );
        """
        self._client.execute(sql)
        self._ensure_raw_table_source_type_column(raw_table_name)

    def _ensure_raw_table_source_type_column(self, raw_table_name: str) -> None:
        """Add source_type to legacy raw tables created before that column existed."""
        info = self._client.query_all(f'PRAGMA table_info("{raw_table_name}");')
        names = {str(row[1]) for row in info}
        if "source_type" in names:
            return
        self._client.execute(
            f'ALTER TABLE "{raw_table_name}" ADD COLUMN source_type TEXT NOT NULL DEFAULT \'bank\';'
        )

    def _insert_raw_rows(
        self,
        raw_table_name: str,
        dataframe: Any,
        bank_name: str,
        import_batch_id: str,
        source_file_id: int,
        source_sheet: str,
        fingerprint: str,
        source_type: str,
    ) -> int:
        """Insert dataframe rows into target raw table."""
        records = dataframe.to_dict(orient="records")
        source_columns = [f"src_{self._safe_ident(col)[:50]}" for col in dataframe.columns]
        quoted_columns = ", ".join([f"\"{column}\"" for column in source_columns])
        fixed_columns = (
            "import_batch_id, bank_name, source_file_id, source_sheet, "
            "source_type, template_fingerprint, row_no, raw_payload"
        )
        all_columns = f"{fixed_columns}, {quoted_columns}" if quoted_columns else fixed_columns
        values_placeholder = ", ".join(["?"] * (8 + len(source_columns)))
        sql = f"INSERT INTO \"{raw_table_name}\" ({all_columns}) VALUES ({values_placeholder});"

        rows: list[tuple[Any, ...]] = []
        for index, row in enumerate(records, start=1):
            raw_payload = json.dumps(row, ensure_ascii=False, default=str)
            source_values = [str(row.get(col, "")) for col in dataframe.columns]
            rows.append(
                (
                    import_batch_id,
                    bank_name,
                    source_file_id,
                    source_sheet,
                    source_type,
                    fingerprint,
                    index,
                    raw_payload,
                    *source_values,
                )
            )
        self._client.executemany(sql, rows)
        return len(rows)

    def _insert_file_record(
        self,
        batch_id: str,
        path: Path,
        file_hash: str,
        bank_name: str,
        bank_id: str,
        source_type: str,
    ) -> int:
        """Insert one file record and return file id."""
        self._client.execute(
            """
            INSERT INTO meta_bank_files
            (file_name, file_path, file_hash, bank_name, bank_id, source_type, import_batch_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'imported');
            """,
            (path.name, str(path), file_hash, bank_name, bank_id, source_type, batch_id),
        )
        rows = self._client.query_all(
            """
            SELECT file_id FROM meta_bank_files
            WHERE import_batch_id=? AND file_hash=?
            ORDER BY file_id DESC LIMIT 1;
            """,
            (batch_id, file_hash),
        )
        return int(rows[0][0])

    def _insert_sheet_record(
        self,
        file_id: int,
        sheet_name: str,
        fingerprint: str,
        raw_table_name: str,
        rows_imported: int,
        source_type: str,
        selected_template_id: str = "",
        template_type: str = "txn_detail",
        template_snapshot: dict[str, Any] | None = None,
    ) -> None:
        """Insert one sheet-level metadata row."""
        self._client.execute(
            """
            INSERT INTO meta_bank_sheets
            (file_id, sheet_name, header_row_no, template_fingerprint, source_type, raw_table_name, rows_imported, selected_template_id, template_type, template_snapshot_json)
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?);
            """,
            (file_id, sheet_name, fingerprint, source_type, raw_table_name, rows_imported, selected_template_id, template_type, json.dumps(template_snapshot or {}, ensure_ascii=False)),
        )

    def _write_log(self, batch_id: str, file_path: str, level: str, message: str) -> None:
        """Write ingest runtime logs into database."""
        self._client.execute(
            """
            INSERT INTO meta_ingest_logs (import_batch_id, file_path, level, message)
            VALUES (?, ?, ?, ?);
            """,
            (batch_id, file_path, level, message),
        )

    def _safe_ident(self, raw: str) -> str:
        """Sanitize dynamic identifiers to safe ascii style."""
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in raw.strip().lower())
        cleaned = cleaned.strip("_")
        return cleaned or "col"

    def _safe_ident_user_table_part(self, raw: str, max_len: int = 72) -> str:
        """表名片段：保留大小写与 Unicode 字母数字，不强制小写，尽量贴近原始文件名/工作表名。"""
        raw_text = str(raw)
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in raw_text.strip())
        cleaned = cleaned.strip("_")
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        if not cleaned:
            cleaned = "data"
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len].rstrip("_")
        return cleaned

    def _table_name_exists(self, name: str) -> bool:
        """Whether a physical table name already exists in sqlite_master."""
        rows = self._client.query_all(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
            (name,),
        )
        return bool(rows)

    def _build_raw_table_name_from_source(self, path: Path, sheet_name: str, fingerprint: str) -> str:
        """按「原文件名（无扩展名）_工作表名」生成 raw 表名；冲突时追加指纹片段保证唯一。"""
        stem = self._safe_ident_user_table_part(path.stem, max_len=56)
        sh = self._safe_ident_user_table_part(str(sheet_name), max_len=40)
        base = f"raw_{stem}_{sh}"
        if len(base) > 120:
            base = base[:120].rstrip("_")
        candidate = base
        n = 0
        while self._table_name_exists(candidate):
            n += 1
            if n > 300:
                candidate = f"raw_{fingerprint[:24]}_{n}"
                continue
            if n == 1:
                candidate = f"{base}_{fingerprint[:8]}"
            else:
                candidate = f"{base}_{fingerprint[:8]}_{n}"
        return candidate
