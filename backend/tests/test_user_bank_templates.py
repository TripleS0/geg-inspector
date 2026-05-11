from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.template_library import (
    clear_template_cache,
    infer_bank_name_by_columns,
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


if __name__ == "__main__":
    unittest.main()
