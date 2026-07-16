from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.integration.bank.bank_catalog_repository import BankCatalogRepository
from app.services.integration.bank.bank_template_wizard_service import BankTemplateWizardService
from app.services.integration.bank.ingest_service import BankIngestService
from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.user_bank_template_repository import UserBankTemplateRepository
from app.services.shared.db.sqlite_client import SqliteClient


class BankCatalogAssignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = SqliteClient(str(self.root / "test.sqlite3"))
        sql_file = Path(__file__).resolve().parents[1] / "app" / "resources" / "sql" / "bootstrap_sqlite.sql"
        conn = sqlite3.connect(str(self.client.db_path))
        try:
            conn.executescript(sql_file.read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_one_file_owns_bank_and_each_sheet_owns_template(self) -> None:
        path = self.root / "建设银行综合数据.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame([{
                "账户名称": "张三", "账号": "6217000100000001", "证件号码": "44010101", "开户日期": "2024-01-01"
            }]).to_excel(writer, sheet_name="开户信息", index=False)
            pd.DataFrame([{
                "客户名称": "张三", "交易卡号": "6217000100000001", "交易日期": "2024-02-01",
                "交易时间": "10:30:00", "借贷方向": "贷", "交易金额": "100.00", "对方户名": "李四"
            }]).to_excel(writer, sheet_name="交易明细", index=False)

        bank = BankCatalogRepository(self.client).get_by_name("建设银行")
        self.assertIsNotNone(bank)
        assignments = {
            str(path): {
                "bank_id": bank.bank_id,
                "sheets": {
                    "开户信息": {"template_id": "ccb_account_v1"},
                    "交易明细": {"template_id": "ccb_txn_v1"},
                },
            }
        }
        result = BankIngestService(self.client).ingest_files([str(path)], "默认来源", sheet_assignments=assignments)
        standardized = BankMappingService(self.client).standardize_batch(result.import_batch_id)
        self.assertGreaterEqual(standardized, 2)

        files = self.client.query_all("SELECT bank_id, bank_name FROM meta_bank_files WHERE import_batch_id=?;", (result.import_batch_id,))
        self.assertEqual(files, [(bank.bank_id, "建设银行")])
        sheets = self.client.query_all(
            "SELECT sheet_name, selected_template_id, template_type, template_snapshot_json FROM meta_bank_sheets ORDER BY sheet_name;"
        )
        self.assertEqual([(row[0], row[1], row[2]) for row in sheets], [
            ("交易明细", "ccb_txn_v1", "txn_detail"),
            ("开户信息", "ccb_account_v1", "account_profile"),
        ])
        self.assertTrue(all(json.loads(str(row[3])).get("bank_id") == bank.bank_id for row in sheets))

    def test_same_headers_with_different_selected_templates_do_not_collide(self) -> None:
        bank = BankCatalogRepository(self.client).get_by_name("建设银行")
        repo = UserBankTemplateRepository(self.client)
        common = dict(
            template_type="txn_detail", bank_display_name="建设银行", bank_id=bank.bank_id,
            bank_keywords=["建设银行"], sheet_keywords=["流水"],
            signature_columns=["账号", "时间", "金额"],
        )
        first_id = repo.create(
            display_name="姓名A模板", field_map={"person_name": ["姓名A"], "acct_no": ["账号"], "txn_time_raw": ["时间"], "txn_amount": ["金额"], "txn_direction": ["方向"]},
            direction_rules={"D": "支出"}, **common,
        )
        second_id = repo.create(
            display_name="姓名B模板", field_map={"person_name": ["姓名B"], "acct_no": ["账号"], "txn_time_raw": ["时间"], "txn_amount": ["金额"], "txn_direction": ["方向"]},
            direction_rules={"D": "收入"}, **common,
        )
        paths: list[Path] = []
        for index in (1, 2):
            path = self.root / f"建设银行流水{index}.xlsx"
            pd.DataFrame([{"姓名A": "甲", "姓名B": "乙", "账号": str(index), "时间": "2024-01-01", "金额": "10", "方向": "D"}]).to_excel(path, sheet_name="流水", index=False)
            paths.append(path)
        assignments = {
            str(paths[0]): {"bank_id": bank.bank_id, "sheets": {"流水": {"template_id": first_id}}},
            str(paths[1]): {"bank_id": bank.bank_id, "sheets": {"流水": {"template_id": second_id}}},
        }
        result = BankIngestService(self.client).ingest_files([str(path) for path in paths], "默认来源", sheet_assignments=assignments)
        snapshots = [json.loads(str(row[0])) for row in self.client.query_all("SELECT template_snapshot_json FROM meta_bank_sheets ORDER BY file_id;")]
        self.assertEqual([item["direction_rules"]["D"] for item in snapshots], ["支出", "收入"])
        BankMappingService(self.client).standardize_batch(result.import_batch_id)
        rows = self.client.query_all(
            "SELECT person_name, txn_direction FROM std_bank_txn WHERE import_batch_id=? ORDER BY acct_no;",
            (result.import_batch_id,),
        )
        self.assertEqual(rows, [("甲", "支出"), ("乙", "收入")])
        fingerprints = self.client.query_all("SELECT COUNT(DISTINCT template_fingerprint) FROM meta_bank_sheets;")
        self.assertEqual(fingerprints[0][0], 2)

    def test_generic_sheet_name_does_not_choose_icbc_without_evidence(self) -> None:
        path = self.root / "未知银行.xlsx"
        pd.DataFrame([{"姓名": "张三", "金额": "10"}]).to_excel(path, sheet_name="Sheet1", index=False)
        preview = BankTemplateWizardService(self.client).preview_import(path)
        self.assertEqual(preview["suggested_bank_id"], "")
        self.assertEqual(preview["sheets"][0]["suggested_template_id"], "")

    def test_custom_bank_is_independent_and_reusable_by_templates(self) -> None:
        catalog = BankCatalogRepository(self.client)
        bank = catalog.create("长沙银行", ["长沙银行", "长沙行"])
        repo = UserBankTemplateRepository(self.client)
        template_ids = [
            repo.create(
                display_name=f"长沙银行流水模板{index}", template_type="txn_detail",
                bank_display_name=bank.display_name, bank_id=bank.bank_id,
                bank_keywords=bank.aliases, sheet_keywords=[f"流水{index}"],
                field_map={"acct_no": ["账号"], "txn_time_raw": ["时间"], "txn_amount": ["金额"]},
            )
            for index in (1, 2)
        ]
        self.assertTrue(all(repo.get_by_template_id(template_id).bank_id == bank.bank_id for template_id in template_ids))
        renamed = catalog.update(bank.bank_id, display_name="长沙银行股份有限公司")
        self.assertEqual(renamed.bank_id, bank.bank_id)
        self.assertTrue(all(repo.get_by_template_id(template_id).bank_display_name == renamed.display_name for template_id in template_ids))
        disabled = catalog.update(bank.bank_id, is_active=0)
        self.assertEqual(disabled.is_active, 0)

    def test_file_level_template_is_used_before_sheet_preview_finishes(self) -> None:
        bank = BankCatalogRepository(self.client).get_by_name("建设银行")
        path = self.root / "建设银行交易流水.xlsx"
        pd.DataFrame([{
            "客户名称": "张三", "交易卡号": "6217000100000001", "交易日期": "2024-02-01",
            "交易时间": "10:30:00", "借贷方向": "贷", "交易金额": "100.00",
        }]).to_excel(path, sheet_name="Sheet1", index=False)
        result = BankIngestService(self.client).ingest_files(
            [str(path)],
            "默认来源",
            sheet_assignments={
                str(path): {
                    "bank_id": bank.bank_id,
                    "default_txn_template_id": "ccb_txn_v1",
                    "sheets": {},
                }
            },
        )
        rows = self.client.query_all(
            "SELECT selected_template_id FROM meta_bank_sheets WHERE file_id=(SELECT file_id FROM meta_bank_files WHERE import_batch_id=?);",
            (result.import_batch_id,),
        )
        self.assertEqual(rows, [("ccb_txn_v1",)])


if __name__ == "__main__":
    unittest.main()
