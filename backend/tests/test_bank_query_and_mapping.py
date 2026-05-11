from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.query_service import BankQueryFilters, BankQueryService
from app.services.shared.db.sqlite_client import SqliteClient


class BankQueryAndMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.sqlite3"
        self.client = SqliteClient(str(self.db_path))
        self._bootstrap()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _bootstrap(self) -> None:
        sql_file = Path(__file__).resolve().parents[1] / "app" / "resources" / "sql" / "bootstrap_sqlite.sql"
        sql_text = sql_file.read_text(encoding="utf-8")
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.executescript(sql_text)
            conn.commit()
        finally:
            conn.close()

    def test_enrich_person_name_from_account(self) -> None:
        self.client.execute(
            """
            INSERT INTO std_bank_account(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name, raw_payload)
            VALUES ('batch1', '农业银行', '开户信息', 'fp-a', '6222001', '张三', '{}');
            """
        )
        self.client.execute(
            """
            INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name,
                                     txn_time, txn_amount, txn_direction, counterparty_name, counterparty_account, summary, raw_payload)
            VALUES ('batch1', '农业银行', '交易明细', 'fp-t', '6222001', '',
                    '2026-01-01 12:00:00', '100.00', '收入', '李四', '95588', '转账', '{}');
            """
        )
        svc = BankMappingService(self.client)
        svc._enrich_person_names("batch1")
        rows = self.client.query_all(
            "SELECT person_name FROM std_bank_txn WHERE import_batch_id='batch1' AND acct_no='6222001' LIMIT 1;"
        )
        self.assertEqual(rows[0][0], "张三")

    def test_conflict_marks_remark(self) -> None:
        self.client.execute(
            """
            INSERT INTO std_bank_account(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name, raw_payload)
            VALUES ('batch2', '工商银行', '开户信息', 'fp-a1', '6222333', '王五', '{}');
            """
        )
        self.client.execute(
            """
            INSERT INTO std_bank_account(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name, raw_payload)
            VALUES ('batch2', '工商银行', '开户信息', 'fp-a2', '6222333', '赵六', '{}');
            """
        )
        self.client.execute(
            """
            INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name,
                                     txn_time, txn_amount, txn_direction, counterparty_name, counterparty_account, summary, raw_payload)
            VALUES ('batch2', '工商银行', '交易明细', 'fp-t', '6222333', '',
                    '2026-01-01 12:00:00', '100.00', '收入', '测试', '10086', '转账', '{}');
            """
        )
        svc = BankMappingService(self.client)
        svc._record_account_conflicts("batch2")
        svc._enrich_person_names("batch2")
        rows = self.client.query_all(
            "SELECT remark FROM std_bank_txn WHERE import_batch_id='batch2' AND acct_no='6222333' LIMIT 1;"
        )
        self.assertIn("姓名待核实", rows[0][0] or "")

    def test_query_filters_bank_export_disclaimer_rows(self) -> None:
        self.client.execute(
            """
            INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,
                                     person_name, acct_no, txn_time, txn_amount, currency, txn_direction,
                                     counterparty_name, counterparty_account, summary, balance, raw_payload)
            VALUES ('batch-disclaimer', '农业银行', '交易明细', 'fp', '来源A',
                    '数据截至2025年11月05日，以上结果通过广东农行有权机关综合查控平台导出，非实时数据，实际内容以我行生产系统为准。',
                    '', '', '', 'CNY', '未知', '', '', '', '', '{}');
            """
        )
        self.client.execute(
            """
            INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,
                                     person_name, acct_no, txn_time, txn_amount, currency, txn_direction,
                                     counterparty_name, counterparty_account, summary, balance, raw_payload)
            VALUES ('batch-disclaimer', '农业银行', '交易明细', 'fp', '来源A',
                    '张三', '6222001', '2026-01-01 12:00:00', '100.00', 'CNY', '收入',
                    '李四', '95588', '转账', '', '{}');
            """
        )
        records = BankQueryService(self.client).query_unified_records("batch-disclaimer")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["person_name"], "张三")

    def test_query_and_description(self) -> None:
        self.client.execute(
            """
            INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,
                                     acct_no, person_name, txn_time, txn_amount, currency, txn_direction,
                                     counterparty_name, counterparty_account, summary, balance, raw_payload)
            VALUES ('batch3', '建设银行', '交易明细', 'fp', '来源A',
                    '6222111', '张三', '2026-02-01 09:00:00', '200.50', 'CNY', '收入',
                    '李四', '8888', '工资', '1000.00', '{}');
            """
        )
        service = BankQueryService(self.client)
        filters = BankQueryFilters(person_name="张三", start_time="2026-02-01 00:00:00", end_time="2026-02-02 00:00:00")
        records = service.query_unified_records("batch3", filters)
        self.assertEqual(len(records), 1)
        summary = service.summarize(records)
        desc = service.render_description(filters, summary)
        self.assertIn("张三", desc)
        self.assertIn("1笔", desc)


if __name__ == "__main__":
    unittest.main()
