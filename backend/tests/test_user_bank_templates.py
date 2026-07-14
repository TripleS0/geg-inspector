from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.template_library import (
    clear_template_cache,
    infer_bank_name,
    infer_bank_name_by_columns,
    infer_file_purpose,
    match_template,
    match_template_by_columns,
)
from app.services.integration.bank.user_bank_template_repository import UserBankTemplateRepository
from app.services.shared.db.sqlite_client import SqliteClient


class UserBankTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.sqlite3"
        self.client = SqliteClient(str(self.db_path))
        self._bootstrap()
        clear_template_cache()

    def tearDown(self) -> None:
        clear_template_cache()
        self._tmpdir.cleanup()

    def _bootstrap(self) -> None:
        sql_file = Path(__file__).resolve().parents[1] / "app" / "resources" / "sql" / "bootstrap_sqlite.sql"
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.executescript(sql_file.read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()

    def test_user_template_matches_before_builtin_and_infers_bank(self) -> None:
        repo = UserBankTemplateRepository(self.client)
        repo.create(
            display_name="测试银行流水",
            template_type="txn_detail",
            bank_display_name="测试银行",
            bank_keywords=["测试银行"],
            sheet_keywords=["专属流水"],
            field_map={"acct_no": ["测试账号"], "txn_amount": ["测试金额"]},
            signature_columns=["测试账号", "测试金额"],
            match_priority=100,
        )

        by_name = match_template("测试银行", "专属流水", sheet_type="txn_detail", client=self.client)
        self.assertIsNotNone(by_name)
        self.assertEqual(by_name.bank_display_name, "测试银行")

        by_columns = match_template_by_columns(["测试账号", "测试金额"], sheet_type="txn_detail", client=self.client)
        self.assertIsNotNone(by_columns)
        self.assertEqual(by_columns.template_id, by_name.template_id)
        self.assertEqual(
            infer_bank_name_by_columns(["测试账号", "测试金额"], sheet_type="txn_detail", client=self.client),
            "测试银行",
        )

    def test_seed_default_mappings_uses_user_template(self) -> None:
        repo = UserBankTemplateRepository(self.client)
        repo.create(
            display_name="测试银行流水",
            template_type="txn_detail",
            bank_display_name="测试银行",
            bank_keywords=["测试银行"],
            sheet_keywords=["流水"],
            field_map={
                "acct_no": ["账户列"],
                "txn_amount": ["金额列"],
                "txn_direction": ["方向列"],
            },
            signature_columns=["账户列", "金额列", "方向列"],
        )
        self.client.execute(
            """
            INSERT INTO meta_schema_registry
            (bank_name, source_type, template_fingerprint, template_version, sheet_name, raw_table_name, schema_json, template_type)
            VALUES (?, 'bank', ?, 1, ?, ?, ?, 'txn_detail');
            """,
            (
                "测试银行",
                "fp-user",
                "流水",
                "raw_bank_test",
                json.dumps({"columns": ["账户列", "金额列", "方向列"]}, ensure_ascii=False),
            ),
        )

        svc = BankMappingService(self.client)
        svc.seed_default_mappings("fp-user", "测试银行", "流水", "txn_detail")

        rows = self.client.query_all(
            """
            SELECT raw_field_name, std_field_name
            FROM meta_field_mapping
            WHERE template_fingerprint='fp-user'
            ORDER BY std_field_name;
            """
        )
        self.assertEqual(
            rows,
            [("账户列", "acct_no"), ("金额列", "txn_amount"), ("方向列", "txn_direction")],
        )

    def test_direction_rules_and_double_column_time(self) -> None:
        svc = BankMappingService(self.client)
        self.assertEqual(svc._normalize_direction_with_rules("1.0", "100.00", {"1": "支出"}), "支出")
        self.assertEqual(svc._normalize_direction_with_rules("", "1000.00", {}), "收入")
        self.assertEqual(svc._normalize_direction_with_rules(None, "-1000.00", {}), "支出")
        self.assertEqual(
            svc._normalize_txn_time_extended(
                "2024-05-20",
                "12:30:01",
                {"formats": ["%Y-%m-%d %H:%M:%S"]},
            ),
            "2024-05-20 12:30:01",
        )

    def test_new_transfer_bank_formats_match_builtin_templates(self) -> None:
        self.assertEqual(
            infer_bank_name(
                "脱敏_Dgmx广州AB公司.xlsx",
                ["对公明细"],
                client=self.client,
            ),
            "农业银行",
        )
        abc_profile = match_template(
            "农业银行",
            "个人客户主档（账户信息）",
            sheet_type="account_profile",
            client=self.client,
        )
        self.assertIsNotNone(abc_profile)
        self.assertEqual(abc_profile.template_id, "abc_person_account_v1")

        icbc_account = match_template_by_columns(
            ["姓名", "证件号码", "账号类型", "账号", "开户日期", "开户网点", "账号对应卡号"],
            sheet_type="account_profile",
            client=self.client,
        )
        self.assertIsNotNone(icbc_account)
        self.assertEqual(icbc_account.template_id, "icbc_account_v1")

        icbc_card_txn = match_template_by_columns(
            ["卡号", "交易日期", "记账时间", "借贷标志", "交易币种", "交易金额", "对方卡号/账号"],
            sheet_type="txn_detail",
            client=self.client,
        )
        self.assertIsNotNone(icbc_card_txn)
        self.assertEqual(icbc_card_txn.template_id, "icbc_txn_v2")
        self.assertEqual(icbc_card_txn.direction_rules, {"1": "支出", "2": "收入"})

        cgb_account = match_template(
            "广发银行",
            "开户资料",
            sheet_type="account_profile",
            client=self.client,
        )
        self.assertIsNotNone(cgb_account)
        self.assertEqual(cgb_account.template_id, "cgb_account_v1")

    def test_bank_and_sheet_match_before_shared_columns(self) -> None:
        # The ABC personal and corporate transaction exports have many of the
        # same columns. The filename/Sheet classification must keep them apart.
        abc_personal = match_template(
            "农业银行",
            "个人客户明细",
            sheet_type="txn_detail",
            client=self.client,
        )
        abc_corporate = match_template(
            "农业银行",
            "对公明细",
            sheet_type="txn_detail",
            client=self.client,
        )
        self.assertIsNotNone(abc_personal)
        self.assertIsNotNone(abc_corporate)
        self.assertEqual(abc_personal.template_id, "abc_txn_v1")
        self.assertEqual(abc_corporate.template_id, "abc_corp_txn_v1")

    def test_filename_marks_account_profile_before_generic_sheet_name(self) -> None:
        self.assertEqual(infer_file_purpose("工商银行开户信息.xlsx"), "account_profile")
        self.assertEqual(infer_file_purpose("建设银行交易明细.xlsx"), "txn_detail")
        self.assertIsNone(infer_file_purpose("广发银行.xlsx"))

    def test_icbc_account_profile_keeps_account_and_card_identifiers(self) -> None:
        columns = ["姓名", "证件号码", "账号", "开户日期", "账号对应卡号"]
        self.client.execute(
            """
            INSERT INTO meta_schema_registry
            (bank_name, source_type, template_fingerprint, template_version, sheet_name,
             raw_table_name, schema_json, status, template_type)
            VALUES ('工商银行', 'bank', 'fp-icbc-account', 1, 'Sheet1',
                    'raw_bank_icbc_account', ?, 'pending_mapping', 'account_profile');
            """,
            (json.dumps({"columns": columns}, ensure_ascii=False),),
        )
        self.client.execute(
            """
            CREATE TABLE raw_bank_icbc_account (
                import_batch_id TEXT, bank_name TEXT, source_file_id INTEGER,
                source_sheet TEXT, template_fingerprint TEXT, raw_payload TEXT
            );
            """
        )
        payload = {
            "姓名": "李**",
            "证件号码": "441424********2851",
            "账号": "200202*********7962",
            "开户日期": "2007-03-01",
            "账号对应卡号": "622200*********7228",
        }
        self.client.execute(
            """
            INSERT INTO raw_bank_icbc_account
            (import_batch_id, bank_name, source_file_id, source_sheet, template_fingerprint, raw_payload)
            VALUES ('batch-icbc', '工商银行', NULL, 'Sheet1', 'fp-icbc-account', ?);
            """,
            (json.dumps(payload, ensure_ascii=False),),
        )

        svc = BankMappingService(self.client)
        svc.seed_default_mappings("fp-icbc-account", "工商银行", "Sheet1", "account_profile")
        inserted = svc._standardize_account_table(
            "batch-icbc", "fp-icbc-account", "raw_bank_icbc_account", "Sheet1", "工商银行"
        )
        self.assertEqual(inserted, 2)
        accounts = self.client.query_all(
            "SELECT bank_name, acct_no, person_name FROM std_bank_account WHERE import_batch_id='batch-icbc' ORDER BY acct_no;"
        )
        self.assertEqual(
            accounts,
            [
                ("工商银行", "200202*********7962", "李**"),
                ("工商银行", "622200*********7228", "李**"),
            ],
        )

        self.client.executemany(
            """
            INSERT INTO std_bank_txn
            (import_batch_id, bank_name, source_sheet, template_fingerprint,
             person_name, acct_no, raw_payload)
            VALUES ('batch-icbc', '工商银行', 'Sheet1', 'fp-icbc-txn', '', ?, '{}');
            """,
            [("200202*********7962",), ("622200*********7228",)],
        )
        svc._enrich_person_names("batch-icbc")
        txn_owners = self.client.query_all(
            """
            SELECT acct_no, person_name
            FROM std_bank_txn
            WHERE import_batch_id='batch-icbc'
            ORDER BY acct_no;
            """
        )
        self.assertEqual(
            txn_owners,
            [("200202*********7962", "李**"), ("622200*********7228", "李**")],
        )


if __name__ == "__main__":
    unittest.main()
