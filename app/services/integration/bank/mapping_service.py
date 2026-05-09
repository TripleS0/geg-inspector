"""Field mapping and standardization service for bank integration."""

from __future__ import annotations

import json
from datetime import datetime, time

from app.services.shared.db.sqlite_client import SqliteClient
from app.services.integration.bank.template_library import (
    BankTemplate,
    find_column,
    infer_bank_name,
    infer_bank_name_by_columns,
    infer_sheet_purpose,
    match_template_by_columns,
    match_template,
)


class BankMappingService:
    """Manage field mappings and write standard layer rows."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        """Initialize mapping service."""
        self._client = client or SqliteClient()

    def save_mapping(
        self,
        template_fingerprint: str,
        raw_field_name: str,
        std_field_name: str,
        template_type: str = "txn_detail",
        transform_rule: str = "identity",
        priority: int = 100,
    ) -> None:
        """Insert or update one mapping rule."""
        self._client.execute(
            """
            INSERT INTO meta_field_mapping
            (template_fingerprint, raw_field_name, std_field_name, template_type, transform_rule, priority, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT (template_fingerprint, raw_field_name, std_field_name)
            DO UPDATE SET
                template_type=excluded.template_type,
                transform_rule=excluded.transform_rule,
                priority=excluded.priority,
                is_active=1;
            """,
            (template_fingerprint, raw_field_name, std_field_name, template_type, transform_rule, priority),
        )

    def standardize_batch(self, import_batch_id: str) -> int:
        """Write mapped raw records into std_bank_txn for one batch."""
        self._ensure_std_columns()
        self._ensure_meta_columns()
        sheet_rows = self._client.query_all(
            """
            SELECT DISTINCT s.template_fingerprint, s.raw_table_name, s.sheet_name, f.bank_name,
                   COALESCE(r.template_type, 'txn_detail') AS template_type
            FROM meta_bank_sheets
            s JOIN meta_bank_files f ON f.file_id=s.file_id
              LEFT JOIN meta_schema_registry r ON r.template_fingerprint=s.template_fingerprint
            WHERE f.import_batch_id=?;
            """,
            (import_batch_id,),
        )

        inserted = 0
        for template_fingerprint, raw_table_name, sheet_name, bank_name, template_type in sheet_rows:
            sheet_type = str(template_type or infer_sheet_purpose(str(sheet_name)))
            self.seed_default_mappings(str(template_fingerprint), str(bank_name), str(sheet_name), sheet_type)
            if sheet_type == "account_profile":
                inserted += self._standardize_account_table(
                    import_batch_id, str(template_fingerprint), str(raw_table_name), str(sheet_name), str(bank_name)
                )
                continue
            inserted += self._standardize_table(
                import_batch_id, str(template_fingerprint), str(raw_table_name), str(sheet_name), str(bank_name)
            )
        self._enrich_person_names(import_batch_id)
        return inserted

    def seed_default_mappings(
        self, template_fingerprint: str, bank_name: str, sheet_name: str, template_type: str = "txn_detail"
    ) -> None:
        """Seed basic mappings by keyword heuristics when missing."""
        count_rows = self._client.query_all(
            "SELECT COUNT(1) FROM meta_field_mapping WHERE template_fingerprint=?;",
            (template_fingerprint,),
        )
        if count_rows and int(count_rows[0][0]) > 0:
            if template_type != "account_profile":
                return
            # 开户模板：始终向下合并关键词映射（旧库可能映射错列或缺列，不能只因有映射就跳过）

        rows = self._client.query_all(
            "SELECT schema_json FROM meta_schema_registry WHERE template_fingerprint=? LIMIT 1;",
            (template_fingerprint,),
        )
        if not rows:
            return
        schema_json = rows[0][0]
        schema_dict = schema_json if isinstance(schema_json, dict) else json.loads(schema_json)
        columns = [str(col) for col in schema_dict.get("columns", [])]

        if template_type != "account_profile":
            template = match_template(bank_name, sheet_name)
            if template is None:
                template = match_template_by_columns(columns)
            if template is not None:
                for std_field, aliases in template.field_map.items():
                    col = find_column(columns, aliases)
                    if col:
                        self.save_mapping(template_fingerprint, col, std_field, template_type, "identity", 10)
                return

        keyword_to_std = self._keyword_to_std(template_type)
        # 长关键词优先，避免「账号」误匹配「账号对应卡号」「账号类型」等列
        sorted_pairs = sorted(keyword_to_std.items(), key=lambda kv: len(kv[0]), reverse=True)
        for column in columns:
            for keyword, std_field in sorted_pairs:
                if keyword not in column:
                    continue
                if std_field == "acct_no":
                    bad_tokens = ("类型", "状态", "余额", "序号", "网点", "日期")
                    if any(tok in column for tok in bad_tokens):
                        continue
                self.save_mapping(template_fingerprint, column, std_field, template_type, "identity", 100)
                break

    def _keyword_to_std(self, template_type: str) -> dict[str, str]:
        if template_type == "account_profile":
            return {
                "客户名称": "person_name",
                "账户名称": "person_name",
                "户名": "person_name",
                "姓名": "person_name",
                "账号": "acct_no",
                "账号对应卡号": "acct_no",
                "账户": "acct_no",
                "卡号": "acct_no",
                "身份证": "id_no",
                "证件号": "id_no",
                "证件号码": "id_no",
                "手机号": "mobile",
                "联系电话": "mobile",
                "开户日期": "open_date",
                "开户时间": "open_date",
            }
        return {
            "客户名称": "person_name",
            "姓名": "person_name",
            "交易卡号": "acct_no",
            "账号": "acct_no",
            "账户": "acct_no",
            "交易时间": "txn_time_raw",
            "发生时间": "txn_time_raw",
            "日期": "txn_date",
            "交易金额": "txn_amount",
            "金额": "txn_amount",
            "余额": "balance",
            "币种": "currency",
            "对方户名": "counterparty_name",
            "对手名": "counterparty_name",
            "对方账户": "counterparty_account",
            "对方账号": "counterparty_account",
            "对手账号": "counterparty_account",
            "借贷方向": "txn_direction",
            "借贷标志": "txn_direction",
            "借贷标识": "txn_direction",
            "摘要": "summary",
            "注释": "summary",
            "备注": "summary",
            "交易机构号": "txn_org_no",
            "交易机构名称": "txn_org_name",
            "交易行号": "txn_org_no",
            "交易行名": "txn_org_name",
            "网点号": "txn_org_no",
            "交易场所简称": "txn_org_name",
            "交易行": "txn_org_no",
        }

    def _standardize_table(
        self,
        import_batch_id: str,
        template_fingerprint: str,
        raw_table_name: str,
        sheet_name: str,
        bank_name: str,
    ) -> int:
        """Standardize one template table by mapping rules."""
        mapping_rows = self._client.query_all(
            """
            SELECT raw_field_name, std_field_name
            FROM meta_field_mapping
            WHERE template_fingerprint=? AND is_active=1
            ORDER BY priority ASC;
            """,
            (template_fingerprint,),
        )
        if not mapping_rows:
            return 0

        raw_rows = self._client.query_all(
            f"""
            SELECT import_batch_id, bank_name, source_file_id, source_sheet, template_fingerprint, raw_payload
            FROM "{raw_table_name}"
            WHERE import_batch_id=?;
            """,
            (import_batch_id,),
        )
        if not raw_rows:
            return 0

        template = match_template(bank_name, sheet_name)
        header_bank_name = bank_name
        if template is None:
            schema_rows = self._client.query_all(
                "SELECT schema_json FROM meta_schema_registry WHERE template_fingerprint=? LIMIT 1;",
                (template_fingerprint,),
            )
            if schema_rows:
                schema_json = schema_rows[0][0]
                schema_dict = schema_json if isinstance(schema_json, dict) else json.loads(schema_json)
                schema_columns = [str(col) for col in schema_dict.get("columns", [])]
                template = match_template_by_columns(schema_columns)
                header_bank_name = infer_bank_name_by_columns(schema_columns, fallback=bank_name)
        mapped_records = []
        for row in raw_rows:
            payload = row[5]
            payload_dict = payload if isinstance(payload, dict) else json.loads(payload)
            std_fields = {
                "person_name": None,
                "acct_no": None,
                "txn_date": None,
                "txn_time_raw": None,
                "txn_direction": None,
                "txn_time": None,
                "txn_amount": None,
                "currency": None,
                "balance": None,
                "counterparty_name": None,
                "counterparty_account": None,
                "summary": None,
                "txn_org_no": None,
                "txn_org_name": None,
            }
            for raw_field, std_field in mapping_rows:
                if std_field in std_fields and raw_field in payload_dict:
                    std_fields[std_field] = str(payload_dict[raw_field])

            txn_time = self._normalize_txn_time(std_fields.get("txn_date"), std_fields.get("txn_time_raw"))
            txn_amount = self._normalize_amount(std_fields.get("txn_amount"))
            direction = self._normalize_direction(std_fields.get("txn_direction"), txn_amount)
            counterparty_name = self._normalize_counterparty_name(std_fields.get("counterparty_name"))
            counterparty_account = self._normalize_counterparty_account(std_fields.get("counterparty_account"))
            summary = (std_fields.get("summary") or "").strip()
            source_name = self._build_source_name(row[2], row[3], raw_table_name)
            remark = self._build_risk_remark(txn_time, txn_amount, summary)
            currency = self._normalize_currency(std_fields.get("currency"))
            if self._looks_like_account_row(
                txn_time=txn_time,
                txn_amount=txn_amount,
                txn_direction=direction,
                counterparty_name=counterparty_name,
                counterparty_account=counterparty_account,
            ):
                continue
            row_bank_name = self._resolve_row_bank_name(
                source_file_id=row[2],
                source_sheet=row[3],
                fallback_bank=header_bank_name,
                template=template,
            )

            mapped_records.append(
                (
                    row[0],
                    row_bank_name,
                    row[2],
                    row[3],
                    row[4],
                    "bank",
                    std_fields.get("person_name") or "",
                    self._normalize_acct_no(std_fields.get("acct_no")),
                    txn_time,
                    txn_amount,
                    currency,
                    direction,
                    std_fields["balance"],
                    counterparty_name,
                    self._normalize_acct_no(counterparty_account),
                    summary,
                    (std_fields.get("txn_org_no") or "").strip(),
                    (std_fields.get("txn_org_name") or "").strip(),
                    source_name,
                    remark,
                    json.dumps(payload_dict, ensure_ascii=False),
                )
            )

        self._client.executemany(
            """
            INSERT INTO std_bank_txn
            (import_batch_id, bank_name, source_file_id, source_sheet, template_fingerprint, source_type,
             person_name, acct_no, txn_time, txn_amount, currency, txn_direction, balance, counterparty_name, counterparty_account,
             summary, txn_org_no, txn_org_name, source_name, remark, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            mapped_records,
        )
        return len(mapped_records)

    def _standardize_account_table(
        self,
        import_batch_id: str,
        template_fingerprint: str,
        raw_table_name: str,
        sheet_name: str,
        bank_name: str,
    ) -> int:
        """Standardize one account profile table into std_bank_account."""
        mapping_rows = self._client.query_all(
            """
            SELECT raw_field_name, std_field_name
            FROM meta_field_mapping
            WHERE template_fingerprint=? AND is_active=1
              AND (template_type='account_profile' OR std_field_name IN ('person_name','acct_no','id_no','mobile','open_date'))
            ORDER BY priority ASC;
            """,
            (template_fingerprint,),
        )
        if not mapping_rows:
            return 0
        raw_rows = self._client.query_all(
            f"""
            SELECT import_batch_id, bank_name, source_file_id, source_sheet, template_fingerprint, raw_payload
            FROM "{raw_table_name}"
            WHERE import_batch_id=?;
            """,
            (import_batch_id,),
        )
        if not raw_rows:
            return 0
        mapped_records: list[tuple[object, ...]] = []
        for row in raw_rows:
            payload = row[5]
            payload_dict = payload if isinstance(payload, dict) else json.loads(payload)
            fields = {"person_name": "", "acct_no": "", "id_no": "", "mobile": "", "open_date": ""}
            acct_candidates: list[tuple[int, str]] = []
            for raw_field, std_field in mapping_rows:
                if std_field not in fields or raw_field not in payload_dict:
                    continue
                value = self._clean_cell_text(str(payload_dict[raw_field]))
                if not value:
                    continue
                if std_field == "acct_no":
                    candidate = self._normalize_acct_no(value)
                    if not self._looks_like_acct_no(candidate):
                        continue
                    acct_candidates.append((self._acct_field_priority(raw_field), candidate))
                    continue
                if std_field == "person_name":
                    if not self._looks_like_person_name(value):
                        continue
                # account_profile采用首个有效值，避免后续宽泛关键词覆盖关键字段
                if fields[std_field]:
                    continue
                fields[std_field] = value
            if acct_candidates:
                acct_candidates.sort(key=lambda x: x[0], reverse=True)
                fields["acct_no"] = acct_candidates[0][1]
            acct_no = self._normalize_acct_no(fields["acct_no"].strip())
            if not acct_no:
                continue
            source_name = self._build_source_name(row[2], row[3], raw_table_name)
            open_date = self._normalize_txn_time(fields.get("open_date"), None)
            mapped_records.append(
                (
                    row[0],
                    infer_bank_name_by_columns(list(payload_dict.keys()), fallback=str(row[1] or bank_name)),
                    row[2],
                    str(row[3] or sheet_name),
                    row[4],
                    "bank",
                    fields["person_name"],
                    acct_no,
                    fields["id_no"],
                    fields["mobile"],
                    open_date,
                    source_name,
                    json.dumps(payload_dict, ensure_ascii=False),
                )
            )
        if not mapped_records:
            return 0
        self._client.executemany(
            """
            INSERT INTO std_bank_account
            (import_batch_id, bank_name, source_file_id, source_sheet, template_fingerprint, source_type,
             person_name, acct_no, id_no, mobile, open_date, source_name, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            mapped_records,
        )
        self._record_account_conflicts(import_batch_id)
        return len(mapped_records)

    def _record_account_conflicts(self, import_batch_id: str) -> None:
        """Record account conflicts for same bank/acct with multiple owner names."""
        rows = self._client.query_all(
            """
            SELECT bank_name, acct_no, GROUP_CONCAT(DISTINCT person_name)
            FROM std_bank_account
            WHERE import_batch_id=? AND person_name IS NOT NULL AND TRIM(person_name) <> ''
            GROUP BY bank_name, acct_no
            HAVING COUNT(DISTINCT person_name) > 1;
            """,
            (import_batch_id,),
        )
        inserts: list[tuple[str, str, str, str, str]] = []
        for bank_name, acct_no, names in rows:
            inserts.append(
                (
                    import_batch_id,
                    str(bank_name or ""),
                    str(acct_no or ""),
                    "同卡号对应多个开户姓名",
                    json.dumps({"person_names": str(names or "").split(",")}, ensure_ascii=False),
                )
            )
        if inserts:
            self._client.executemany(
                """
                INSERT INTO std_bank_account_conflict
                (import_batch_id, bank_name, acct_no, conflict_reason, conflict_payload)
                VALUES (?, ?, ?, ?, ?);
                """,
                inserts,
            )

    def _enrich_person_names(self, import_batch_id: str) -> None:
        """Backfill txn person_name from account table when account owner is unique."""
        self._client.execute(
            """
            UPDATE std_bank_txn
            SET acct_no=TRIM(REPLACE(COALESCE(acct_no, ''), ' ', ''))
            WHERE import_batch_id=?;
            """,
            (import_batch_id,),
        )
        self._client.execute(
            """
            UPDATE std_bank_account
            SET acct_no=TRIM(REPLACE(COALESCE(acct_no, ''), ' ', ''))
            WHERE import_batch_id=?;
            """,
            (import_batch_id,),
        )
        unique_rows = self._client.query_all(
            """
            SELECT acct_no, MAX(person_name) AS person_name
            FROM std_bank_account
            WHERE import_batch_id=? AND person_name IS NOT NULL AND TRIM(person_name) <> ''
            GROUP BY acct_no
            HAVING COUNT(DISTINCT person_name)=1;
            """,
            (import_batch_id,),
        )
        exact_map: dict[str, str] = {}
        key_map: dict[str, str] = {}
        for acct_no, person_name in unique_rows:
            acct = self._normalize_acct_no(str(acct_no or ""))
            name = str(person_name or "").strip()
            if not acct or not name:
                continue
            exact_map[acct] = name
            key = self._acct_match_key(acct)
            if key:
                if key in key_map and key_map[key] != name:
                    key_map[key] = ""
                else:
                    key_map[key] = name

        txn_rows = self._client.query_all(
            """
            SELECT std_id, acct_no
            FROM std_bank_txn
            WHERE import_batch_id=?
              AND (person_name IS NULL OR TRIM(person_name)='');
            """,
            (import_batch_id,),
        )
        for std_id, acct_no in txn_rows:
            acct = self._normalize_acct_no(str(acct_no or ""))
            if not acct:
                continue
            name = exact_map.get(acct, "")
            if not name:
                key = self._acct_match_key(acct)
                name = key_map.get(key, "") if key else ""
            if not name:
                continue
            self._client.execute(
                """
                UPDATE std_bank_txn
                SET person_name=?
                WHERE std_id=?;
                """,
                (name, int(std_id)),
            )

        self._client.execute(
            """
            UPDATE std_bank_txn
            SET remark=CASE
                WHEN remark IS NULL OR TRIM(remark)=''
                THEN '姓名待核实'
                WHEN INSTR(remark, '姓名待核实')=0
                THEN remark || '; 姓名待核实'
                ELSE remark
            END
            WHERE import_batch_id=?
              AND (person_name IS NULL OR TRIM(person_name)='')
              AND EXISTS (
                SELECT 1
                FROM std_bank_account_conflict c
                WHERE c.import_batch_id=std_bank_txn.import_batch_id
                  AND c.bank_name=std_bank_txn.bank_name
                  AND c.acct_no=std_bank_txn.acct_no
              );
            """,
            (import_batch_id,),
        )

    def _ensure_std_columns(self) -> None:
        """Ensure newer std columns exist for legacy databases."""
        info = self._client.query_all("PRAGMA table_info(std_bank_txn);")
        col_names = {str(row[1]) for row in info}
        wanted = {
            "person_name": "TEXT",
            "acct_no": "TEXT",
            "txn_direction": "TEXT",
            "txn_org_no": "TEXT",
            "txn_org_name": "TEXT",
            "source_name": "TEXT",
            "remark": "TEXT",
            "currency": "TEXT",
        }
        for name, typ in wanted.items():
            if name not in col_names:
                self._client.execute(f'ALTER TABLE std_bank_txn ADD COLUMN "{name}" {typ};')
        account_info = self._client.query_all(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='std_bank_account' LIMIT 1;"
        )
        if not account_info:
            self._client.execute(
                """
                CREATE TABLE IF NOT EXISTS std_bank_account (
                    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_batch_id TEXT NOT NULL,
                    bank_name TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'bank',
                    source_file_id INTEGER,
                    source_sheet TEXT NOT NULL,
                    template_fingerprint TEXT NOT NULL,
                    person_name TEXT,
                    acct_no TEXT NOT NULL,
                    id_no TEXT,
                    mobile TEXT,
                    open_date TEXT,
                    source_name TEXT,
                    raw_payload TEXT NOT NULL,
                    standardized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        conflict_info = self._client.query_all(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='std_bank_account_conflict' LIMIT 1;"
        )
        if not conflict_info:
            self._client.execute(
                """
                CREATE TABLE IF NOT EXISTS std_bank_account_conflict (
                    conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_batch_id TEXT NOT NULL,
                    bank_name TEXT NOT NULL,
                    acct_no TEXT NOT NULL,
                    conflict_reason TEXT NOT NULL,
                    conflict_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def _ensure_meta_columns(self) -> None:
        """Ensure registry/mapping has template_type in legacy DB."""
        schema_info = self._client.query_all("PRAGMA table_info(meta_schema_registry);")
        schema_cols = {str(row[1]) for row in schema_info}
        if "template_type" not in schema_cols:
            self._client.execute(
                "ALTER TABLE meta_schema_registry ADD COLUMN template_type TEXT NOT NULL DEFAULT 'txn_detail';"
            )
        mapping_info = self._client.query_all("PRAGMA table_info(meta_field_mapping);")
        mapping_cols = {str(row[1]) for row in mapping_info}
        if "template_type" not in mapping_cols:
            self._client.execute(
                "ALTER TABLE meta_field_mapping ADD COLUMN template_type TEXT NOT NULL DEFAULT 'txn_detail';"
            )

    def _normalize_txn_time(self, txn_date: str | None, txn_time_raw: str | None) -> str:
        """Normalize date/time into single timestamp string."""
        date_text = (txn_date or "").strip()
        time_text = (txn_time_raw or "").strip()
        raw = time_text if time_text else date_text
        if not raw:
            return ""

        if date_text and time_text and len(date_text) <= 10 and ":" in time_text:
            raw = f"{date_text} {time_text}"
        if date_text and time_text and len(date_text) <= 10 and "." in time_text:
            raw = f"{date_text} {time_text.replace('.', ':')}"
        if date_text and time_text and len(date_text) <= 10 and "-" in time_text and ":" not in time_text:
            raw = f"{date_text} {time_text}"
        raw = raw.replace("/", "-").replace("T", " ")
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d-%H-%M-%S",
            "%Y-%m-%d",
            "%Y%m%d%H%M%S",
            "%Y%m%d",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        return raw

    def _normalize_amount(self, value: str | None) -> str:
        text = (value or "").strip().replace(",", "")
        if not text:
            return ""
        try:
            return f"{float(text):.2f}"
        except ValueError:
            return text

    def _normalize_currency(self, value: str | None) -> str:
        text = (value or "").strip().upper()
        if not text:
            return "CNY"
        if text in {"RMB", "CNY", "人民币"}:
            return "CNY"
        return text

    def _normalize_acct_no(self, value: str | None) -> str:
        text = (value or "").strip().replace(" ", "")
        if not text:
            return ""
        if text.endswith(".0"):
            head = text[:-2]
            if head.isdigit():
                return head
        return text

    @staticmethod
    def _clean_cell_text(value: str) -> str:
        """Strip Excel/control noise from field text."""
        text = (value or "").replace("\t", "").replace("\r", "").replace("\n", " ").strip()
        return text

    def _looks_like_acct_no(self, value: str) -> bool:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        return len(digits) >= 10

    def _looks_like_person_name(self, value: str) -> bool:
        text = (value or "").strip()
        if not text:
            return False
        # 若全是数字/符号则不是姓名
        digits = sum(1 for ch in text if ch.isdigit())
        if digits >= max(2, len(text) // 2):
            return False
        return True

    def _acct_field_priority(self, raw_field_name: str) -> int:
        name = self._clean_cell_text(raw_field_name)
        score = 0
        if "账号对应卡号" in name:
            score += 100
        if "卡号" in name:
            score += 60
        if "账号" in name:
            score += 20
        if "类型" in name or "状态" in name or "余额" in name or "序号" in name:
            score -= 80
        return score

    def _acct_match_key(self, acct_no: str) -> str:
        digits = "".join(ch for ch in (acct_no or "") if ch.isdigit())
        if len(digits) >= 10:
            return f"{digits[:6]}_{digits[-4:]}"
        return ""

    def _looks_like_account_row(
        self,
        txn_time: str,
        txn_amount: str,
        txn_direction: str,
        counterparty_name: str,
        counterparty_account: str,
    ) -> bool:
        """Guardrail: skip rows that look like account profile instead of transaction."""
        has_time = bool((txn_time or "").strip())
        has_amt = bool((txn_amount or "").strip())
        has_cp = bool((counterparty_name or "").strip()) or bool((counterparty_account or "").strip())
        known_direction = txn_direction in {"收入", "支出"}
        return (not has_time) and (not has_amt) and (not has_cp) and (not known_direction)

    def _normalize_direction(self, direction: str | None, amount: str) -> str:
        text = (direction or "").strip()
        if text:
            if any(k in text for k in ("贷", "收入", "入账", "收")):
                return "收入"
            if any(k in text for k in ("借", "支出", "付出", "付款")):
                return "支出"
        try:
            return "收入" if float(amount) > 0 else ("支出" if float(amount) < 0 else "未知")
        except ValueError:
            return "未知"

    def _normalize_counterparty_name(self, value: str | None) -> str:
        text = (value or "").strip()
        return text or "未知对手"

    def _normalize_counterparty_account(self, value: str | None) -> str:
        text = (value or "").strip()
        return text or "未知账号"

    def _build_source_name(self, source_file_id: object, source_sheet: object, raw_table_name: str) -> str:
        """Build source text as file_stem_sheet."""
        file_name = ""
        try:
            if source_file_id is not None:
                rows = self._client.query_all("SELECT file_name FROM meta_bank_files WHERE file_id=? LIMIT 1;", (source_file_id,))
                if rows:
                    file_name = str(rows[0][0])
        except Exception:
            file_name = ""
        stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        sheet = "" if source_sheet is None else str(source_sheet).strip()
        if stem and sheet:
            return f"{stem}_{sheet}"
        if stem:
            return stem
        if sheet:
            return sheet
        return raw_table_name

    def _build_risk_remark(self, txn_time: str, txn_amount: str, summary: str) -> str:
        """Build semicolon-joined risk tags."""
        tags: list[str] = []
        amt = None
        try:
            amt = round(float(txn_amount), 2)
        except Exception:
            amt = None
        if amt == 520.00:
            tags.append("特殊金额=520")
        if amt == 1314.00:
            tags.append("特殊金额=1314")

        dt = self._parse_dt(txn_time)
        summary_has_transfer = "转账" in summary
        if dt is not None:
            t = dt.time()
            if time(0, 0, 0) <= t <= time(8, 0, 0):
                tags.append("凌晨转账")
            mmdd = dt.strftime("%m-%d")
            special_dates = {
                "02-14": "情人节",
                "05-20": "5月20日",
                "12-31": "跨年日",
                "01-01": "跨年日",
            }
            if mmdd in special_dates and summary_has_transfer:
                tags.append(f"特殊日期转账={special_dates[mmdd]}")
            qixi = self._qixi_dates().get(dt.year)
            if qixi and dt.strftime("%Y-%m-%d") == qixi and summary_has_transfer:
                tags.append("特殊日期转账=七夕节")
        if summary_has_transfer and amt == 520.00:
            tags.append("520转账")
        return "; ".join(dict.fromkeys(tags))

    def _parse_dt(self, text: str) -> datetime | None:
        value = (text or "").strip().replace("/", "-")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    def _qixi_dates(self) -> dict[int, str]:
        """Static qixi mapping for common investigation years."""
        return {
            2024: "2024-08-10",
            2025: "2025-08-29",
            2026: "2026-08-19",
            2027: "2027-08-08",
            2028: "2028-08-26",
            2029: "2029-08-16",
            2030: "2030-08-05",
        }

    def _resolve_bank_display_name(self, original: str, template: BankTemplate | None) -> str:
        """Resolve clean bank display name for export."""
        if template is not None and template.bank_display_name:
            return template.bank_display_name
        text = (original or "").strip()
        if not text:
            return "未知银行"
        return text

    def _resolve_row_bank_name(
        self,
        source_file_id: object,
        source_sheet: object,
        fallback_bank: str,
        template: BankTemplate | None,
    ) -> str:
        """Resolve bank name at row level using template + file/sheet hints."""
        if template is not None and template.bank_display_name:
            return template.bank_display_name
        file_name = ""
        try:
            if source_file_id is not None:
                rows = self._client.query_all(
                    "SELECT file_name FROM meta_bank_files WHERE file_id=? LIMIT 1;",
                    (source_file_id,),
                )
                if rows:
                    file_name = str(rows[0][0])
        except Exception:
            file_name = ""
        sheet = "" if source_sheet is None else str(source_sheet)
        return infer_bank_name(file_name, [sheet], fallback=fallback_bank)

    def _guess_source_type(self, raw_table_name: str) -> str:
        """Infer source type from raw table naming convention."""
        if raw_table_name.startswith("raw_bank_"):
            return "bank"
        if raw_table_name.startswith("raw_commercial_"):
            return "commercial"
        return "other"
