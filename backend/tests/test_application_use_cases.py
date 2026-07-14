"""Use-case-level tests covering bootstrap, dataset, analysis and export."""

from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.application.analysis_use_cases import BankAnalysisUseCase, CommercialRiskUseCase
from app.application.bootstrap import bootstrap_database
from app.application.dataset_use_cases import DatasetUseCase
from app.application.export_use_cases import ExportUseCase
from app.application.task_store import TaskStore
from app.services.integration.bank.query_service import BankQueryFilters
from app.services.shared.db.sqlite_client import SqliteClient


class UseCaseEnvironmentTests(unittest.TestCase):
    """Run use cases against a temporary database file."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "use_cases.sqlite3")
        from app import runtime_paths as rp
        importlib.reload(rp)
        self.client = SqliteClient()
        bootstrap_database(self.client)

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("DATAFUSIONX_DB_PATH", None)
        else:
            os.environ["DATAFUSIONX_DB_PATH"] = self._old_db
        from app import runtime_paths as rp
        importlib.reload(rp)

    def test_bootstrap_persists_schema(self) -> None:
        rows = self.client.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('meta_schema_version', 'ana_task', 'std_bank_txn', 'cfg_risk_rule', 'meta_ocr_job');"
        )
        names = {row[0] for row in rows}
        for required in {"meta_schema_version", "ana_task", "std_bank_txn", "cfg_risk_rule", "meta_ocr_job"}:
            self.assertIn(required, names)
        version_rows = self.client.query_all("SELECT version FROM meta_schema_version ORDER BY version;")
        self.assertEqual([row[0] for row in version_rows], [1, 2, 3, 4])

    def test_dataset_use_case_lists_seeded_batches(self) -> None:
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('demo.xlsx', '/tmp/demo.xlsx', 'h1', 'BankA', 'bank', 'batch-A', 'imported');"
        )
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('biz.xlsx', '/tmp/biz.xlsx', 'h2', 'BizA', 'commercial', 'batch-B', 'imported');"
        )
        uc = DatasetUseCase(self.client)
        all_batches = uc.list_batches()
        self.assertEqual({b.import_batch_id for b in all_batches}, {"batch-A", "batch-B"})
        bank_only = uc.list_batches(source_type="bank")
        self.assertEqual([b.source_type for b in bank_only], ["bank"])

    def test_dataset_merged_batches_includes_enterprise(self) -> None:
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('demo.xlsx', '/tmp/demo.xlsx', 'h1', 'BankA', 'bank', 'batch-A', 'imported');"
        )
        self.client.execute(
            "INSERT INTO std_enterprise_profile (import_batch_id, source_file_name, enterprise_name, enterprise_name_norm,"
            " credit_code, shareholders_json, key_persons_json, raw_payload)"
            " VALUES ('ent-1', 'x', 'Co', 'co', '', '[]', '[]', '{}');"
        )
        uc = DatasetUseCase(self.client)
        merged = uc.list_batches_merged(limit=50)
        ids = {b.import_batch_id for b in merged}
        types = {b.import_batch_id: b.source_type for b in merged}
        self.assertIn("batch-A", ids)
        self.assertIn("ent-1", ids)
        self.assertEqual(types["ent-1"], "enterprise")

    def test_batch_name_set_rename_and_delete(self) -> None:
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('demo.xlsx', '/tmp/demo.xlsx', 'h1', 'BankA', 'bank', 'batch-named', 'imported');"
        )
        uc = DatasetUseCase(self.client)
        uc.set_batch_name("batch-named", "张三建行流水", "bank")
        listed = uc.list_batches(source_type="bank")
        self.assertEqual(listed[0].batch_name, "张三建行流水")
        updated = uc.rename_batch("batch-named", "张三2月流水")
        self.assertEqual(updated.batch_name, "张三2月流水")
        uc.delete_import_batch("batch-named")
        rows = self.client.query_all(
            "SELECT COUNT(*) FROM meta_import_batch WHERE import_batch_id='batch-named';"
        )
        self.assertEqual(int(rows[0][0]), 0)

    def test_delete_import_batch_blocked_when_bound_to_case(self) -> None:
        self.client.execute(
            "INSERT INTO std_case(case_name, description, status) VALUES ('测试案件', '', 'active');"
        )
        case_id = int(self.client.query_all("SELECT case_id FROM std_case LIMIT 1;")[0][0])
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('demo.xlsx', '/tmp/demo.xlsx', 'h1', 'BankA', 'bank', 'batch-bound', 'imported');"
        )
        self.client.execute(
            "INSERT INTO rel_case_batch(case_id, import_batch_id, source_type) VALUES (?, 'batch-bound', 'bank');",
            (case_id,),
        )
        uc = DatasetUseCase(self.client)
        with self.assertRaisesRegex(ValueError, "已绑定案件"):
            uc.delete_import_batch("batch-bound")
        self.assertEqual(
            int(
                self.client.query_all(
                    "SELECT COUNT(*) FROM meta_bank_files WHERE import_batch_id='batch-bound';"
                )[0][0]
            ),
            1,
        )

    def test_delete_import_batch_bank_and_enterprise(self) -> None:
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('demo.xlsx', '/tmp/demo.xlsx', 'h1', 'BankA', 'bank', 'batch-del', 'imported');"
        )
        self.client.execute(
            "INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,"
            " acct_no, person_name, txn_time, txn_amount, currency, txn_direction,"
            " counterparty_name, counterparty_account, summary, balance, raw_payload)"
            " VALUES ('batch-del', 'BankA', 's', 'fp', '来源',"
            " '6222001', '张三', '2026-02-01 09:00:00', '200.00', 'CNY', '收入',"
            " '李四', '8888', '工资', '1000.00', '{}');"
        )
        uc = DatasetUseCase(self.client)
        uc.delete_import_batch("batch-del")
        self.assertEqual(
            self.client.query_all("SELECT COUNT(*) FROM meta_bank_files WHERE import_batch_id='batch-del';")[0][0],
            0,
        )
        self.assertEqual(
            self.client.query_all("SELECT COUNT(*) FROM std_bank_txn WHERE import_batch_id='batch-del';")[0][0],
            0,
        )

        self.client.execute(
            "INSERT INTO std_enterprise_profile (import_batch_id, source_file_name, enterprise_name, enterprise_name_norm,"
            " credit_code, shareholders_json, key_persons_json, raw_payload)"
            " VALUES ('ent-del', 'x', 'Co', 'co', '', '[]', '[]', '{}');"
        )
        eid_row = self.client.query_all(
            "SELECT enterprise_id FROM std_enterprise_profile WHERE import_batch_id='ent-del';"
        )
        eid = int(eid_row[0][0])
        self.client.execute(
            "INSERT INTO rel_biz_enterprise_match (import_batch_id, inquiry_no, biz_company_name, biz_company_name_norm,"
            " enterprise_id, enterprise_name, match_score, match_method)"
            " VALUES ('comm-1', 'q1', 'Co', 'co', ?, 'Co', 1.0, 'test');",
            (eid,),
        )
        uc.delete_import_batch("ent-del")
        self.assertEqual(
            self.client.query_all("SELECT COUNT(*) FROM std_enterprise_profile WHERE import_batch_id='ent-del';")[0][0],
            0,
        )
        self.assertEqual(
            self.client.query_all("SELECT COUNT(*) FROM rel_biz_enterprise_match WHERE enterprise_id=?;", (eid,))[0][0],
            0,
        )

        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('wx.xlsx', '/tmp/wx.xlsx', 'h2', '微信', 'wechat', 'batch-wx-del', 'imported');"
        )
        uc.delete_import_batch("batch-wx-del")
        self.assertEqual(
            self.client.query_all("SELECT COUNT(*) FROM meta_bank_files WHERE import_batch_id='batch-wx-del';")[0][0],
            0,
        )

    def test_bank_analysis_filter_options_handles_empty_batch(self) -> None:
        uc = BankAnalysisUseCase(self.client)
        opts = uc.filter_options("non-existing")
        for key in ("bank_type", "person_name", "acct_no", "counterparty_name", "counterparty_account"):
            self.assertIn(key, opts)
            self.assertEqual(opts[key], [])

    def test_bank_analysis_query_returns_record(self) -> None:
        self.client.execute(
            "INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,"
            " acct_no, person_name, txn_time, txn_amount, currency, txn_direction,"
            " counterparty_name, counterparty_account, summary, balance, raw_payload)"
            " VALUES ('batch-A', 'BankA', 's', 'fp', '来源',"
            " '6222001', '张三', '2026-02-01 09:00:00', '200.00', 'CNY', '收入',"
            " '李四', '8888', '工资', '1000.00', '{}');"
        )
        result = BankAnalysisUseCase(self.client).query_records("batch-A")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["person_name"], "张三")
        self.assertIn("交易总览", result.description)

    def test_bank_analysis_quick_query_matches_all_tokens(self) -> None:
        self.client.execute(
            "INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,"
            " acct_no, person_name, txn_time, txn_amount, currency, txn_direction,"
            " counterparty_name, counterparty_account, summary, balance, raw_payload)"
            " VALUES ('batch-Q', '建设银行', 's', 'fp', '来源',"
            " '6222001', '李芳', '2026-02-01 09:00:00', '200.00', 'CNY', '收入',"
            " '李军', '8888', '转账', '1000.00', '{}');"
        )
        self.client.execute(
            "INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,"
            " acct_no, person_name, txn_time, txn_amount, currency, txn_direction,"
            " counterparty_name, counterparty_account, summary, balance, raw_payload)"
            " VALUES ('batch-Q', '工商银行', 's', 'fp', '来源',"
            " '6222002', '李芳', '2026-02-01 10:00:00', '300.00', 'CNY', '收入',"
            " '李军', '9999', '转账', '1300.00', '{}');"
        )
        result = BankAnalysisUseCase(self.client).query_records(
            "batch-Q",
            BankQueryFilters(quick_query="李芳 建设 李军"),
        )
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["bank_type"], "建设银行")

    def test_bank_analysis_quick_query_matches_all_supported_record_fields(self) -> None:
        self.client.execute(
            "INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,"
            " acct_no, person_name, txn_time, txn_amount, currency, txn_direction,"
            " counterparty_name, counterparty_account, summary, remark, balance, raw_payload)"
            " VALUES ('batch-quick-fields', '工商银行', 's', 'fp', '交易流水',"
            " '62220011234', '张三', '2026-02-01 10:00:00', '300.00', 'CNY', '支出',"
            " '李四', '955881234', '货款转账', '柜面办理', '1300.00', '{}');"
        )
        query = BankAnalysisUseCase(self.client)
        for keyword in ("工商银行", "622200", "支出", "李四", "95588", "货款", "柜面"):
            with self.subTest(keyword=keyword):
                result = query.query_records(
                    "batch-quick-fields",
                    BankQueryFilters(quick_query=keyword),
                )
                self.assertEqual(len(result.records), 1)

    def test_bank_quick_query_uses_owner_bank_not_counterparty_name(self) -> None:
        self.client.executemany(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                acct_no, txn_time, txn_amount, currency, txn_direction,
                counterparty_name, raw_payload
            ) VALUES ('batch-owner-bank', ?, 's', 'fp', ?, '2026-02-01 10:00:00',
                      '100.00', 'CNY', '收入', ?, '{}');
            """,
            [
                ("建设银行", "CCB-001", "李四"),
                ("农业银行", "ABC-001", "建设银行"),
            ],
        )
        result = BankAnalysisUseCase(self.client).query_records(
            "batch-owner-bank",
            BankQueryFilters(quick_query="建设银行"),
        )
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["bank_type"], "建设银行")

    def test_person_fund_summary_groups_cross_bank_accounts_by_identity(self) -> None:
        batch_id = "batch-person-funds"
        self.client.executemany(
            """
            INSERT INTO std_bank_account(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, id_no, raw_payload
            ) VALUES (?, ?, '开户信息', 'fp', ?, ?, ?, '{}');
            """,
            [
                (batch_id, "工商银行", "李艾", "ICBC-001", "440106199001010011"),
                (batch_id, "建设银行", "李艾", "CCB-002", "440106199001010011"),
                (batch_id, "建设银行", "李艾", "ICBC-001", "440106198801010022"),
                (batch_id, "工商银行", "张三", "CP-1", "440106199002020022"),
            ],
        )
        self.client.executemany(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                acct_no, txn_time, txn_amount, txn_direction,
                counterparty_name, counterparty_account, raw_payload
            ) VALUES (?, ?, '交易明细', 'fp', ?, '2026-07-01 10:00:00', ?, ?, ?, ?, '{}');
            """,
            [
                (batch_id, "工商银行", "ICBC-001", "100.00", "支出", "张三", "CP-1"),
                (batch_id, "建设银行", "CCB-002", "200.00", "支出", "京东商城有限公司", "CP-2"),
                (batch_id, "建设银行", "ICBC-001", "900.00", "支出", "其他人", "CP-9"),
            ],
        )

        uc = BankAnalysisUseCase(self.client)
        options = uc.person_identities(batch_id)
        self.assertEqual(len(options), 3)
        li_ai = next(item for item in options if item["person_name"] == "李艾" and item["id_no"] == "440106199001010011")
        self.assertIn("ICBC-001", li_ai["account_nos"])
        result = uc.person_fund_summary(batch_id, "李艾", "440106199001010011")
        self.assertEqual(result["summary"]["bank_count"], 2)
        self.assertEqual(result["summary"]["account_count"], 2)
        self.assertEqual(result["summary"]["out_total"], 300.0)
        self.assertEqual({row["bank_type"] for row in result["groups"]}, {"工商银行", "建设银行"})
        self.assertNotIn("其他人", {row["counterparty_name"] for row in result["groups"]})
        self.assertEqual(result["summary"]["organization_counterparty_count"], 1)
        self.assertEqual(len(result["organization_groups"]), 1)
        self.assertEqual(result["organization_groups"][0]["counterparty_category"], "company_platform")

    def test_commercial_risk_lists_after_no_run(self) -> None:
        uc = CommercialRiskUseCase(self.client)
        self.assertEqual(uc.list_events("missing"), [])
        self.assertEqual(uc.list_summary("missing"), [])

    def test_task_store_lifecycle(self) -> None:
        store = TaskStore(self.client)
        task_id = store.create("import_bank")
        self.assertTrue(task_id)
        store.update(task_id, status="running", progress=20, message="处理中")
        record = store.get(task_id)
        self.assertEqual(record["status"], "running")
        self.assertEqual(record["progress"], 20)
        store.update(task_id, status="succeeded", progress=100, message="完成", result={"batch": "x"})
        finished = store.get(task_id)
        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["result"], {"batch": "x"})

    def test_export_use_case_writes_xlsx(self) -> None:
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('demo.xlsx', '/tmp/demo.xlsx', 'hash', 'BankA', 'bank', 'batch-X', 'imported');"
        )
        self.client.execute(
            "INSERT INTO meta_bank_sheets (file_id, sheet_name, header_row_no, template_fingerprint, source_type, raw_table_name, rows_imported)"
            " VALUES (1, 'sheet1', 1, 'fp1', 'bank', 'raw_demo_sheet1', 1);"
        )
        self.client.execute(
            "INSERT INTO meta_schema_registry (bank_name, source_type, template_fingerprint, sheet_name, raw_table_name, schema_json, status)"
            " VALUES ('BankA', 'bank', 'fp1', 'sheet1', 'raw_demo_sheet1', '{\"columns\":[\"src_amount\"]}', 'pending_mapping');"
        )
        self.client.execute(
            "CREATE TABLE IF NOT EXISTS raw_demo_sheet1 (raw_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " import_batch_id TEXT, bank_name TEXT, source_type TEXT, source_file_id INTEGER,"
            " source_sheet TEXT, template_fingerprint TEXT, row_no INTEGER, raw_payload TEXT, src_amount TEXT);"
        )
        self.client.execute(
            "INSERT INTO raw_demo_sheet1(import_batch_id, bank_name, source_type, source_file_id, source_sheet,"
            " template_fingerprint, row_no, raw_payload, src_amount) VALUES"
            " ('batch-X','BankA','bank',1,'sheet1','fp1',1,'{\"金额\":\"100.00\"}','100.00');"
        )
        target = Path(self._tmp.name) / "merged.xlsx"
        result = ExportUseCase(self.client).export_batch("batch-X", "bank", str(target))
        self.assertTrue(Path(result.output_path).exists())


if __name__ == "__main__":
    unittest.main()
