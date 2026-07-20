from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.query_service import UNKNOWN_PERSON_ID_PREFIX, BankQueryFilters, BankQueryService
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

    def test_enrich_person_name_is_scoped_by_bank(self) -> None:
        self.client.executemany(
            """
            INSERT INTO std_bank_account
            (import_batch_id, bank_name, source_sheet, template_fingerprint,
             acct_no, person_name, raw_payload)
            VALUES ('batch-multi-bank', ?, '开户信息', 'fp-a', '622200******1234', ?, '{}');
            """,
            [("工商银行", "李**"), ("建设银行", "王**")],
        )
        self.client.executemany(
            """
            INSERT INTO std_bank_txn
            (import_batch_id, bank_name, source_sheet, template_fingerprint,
             acct_no, person_name, raw_payload)
            VALUES ('batch-multi-bank', ?, '交易明细', 'fp-t', '622200******1234', '', '{}');
            """,
            [("工商银行",), ("建设银行",)],
        )

        BankMappingService(self.client)._enrich_person_names("batch-multi-bank")

        rows = self.client.query_all(
            """
            SELECT bank_name, person_name
            FROM std_bank_txn
            WHERE import_batch_id='batch-multi-bank'
            ORDER BY bank_name;
            """
        )
        self.assertEqual(rows, [("工商银行", "李**"), ("建设银行", "王**")])

    def test_abc_transaction_uses_only_customer_account_in_current_row(self) -> None:
        self.client.execute(
            """
            CREATE TABLE raw_abc_txn_test (
                import_batch_id TEXT,
                bank_name TEXT,
                source_file_id INTEGER,
                source_sheet TEXT,
                template_fingerprint TEXT,
                raw_payload TEXT
            );
            """
        )
        self.client.executemany(
            """
            INSERT INTO meta_field_mapping(
                template_fingerprint, raw_field_name, std_field_name,
                template_type, transform_rule, priority, is_active
            ) VALUES ('fp-abc', ?, ?, 'txn_detail', 'identity', ?, 1);
            """,
            [
                ("客户账号", "acct_no", 10),
                ("核算账号", "acct_no", 20),
                ("交易日期", "txn_date", 10),
                ("交易金额", "txn_amount", 10),
            ],
        )
        rows = [
            {"客户账号": "622848*********8312", "核算账号": "056901100934811", "交易日期": "20070124", "交易金额": "1000"},
            {"客户账号": "", "核算账号": "056901100934811", "交易日期": "20070209", "交易金额": "-10"},
        ]
        self.client.executemany(
            """
            INSERT INTO raw_abc_txn_test(
                import_batch_id, bank_name, source_file_id, source_sheet,
                template_fingerprint, raw_payload
            ) VALUES ('batch-abc', '农业银行', 1, '个人客户明细', 'fp-abc', ?);
            """,
            [(json.dumps(row, ensure_ascii=False),) for row in rows],
        )

        BankMappingService(self.client)._standardize_table(
            "batch-abc", "fp-abc", "raw_abc_txn_test", "个人客户明细", "农业银行"
        )

        accounts = self.client.query_all(
            "SELECT acct_no FROM std_bank_txn WHERE import_batch_id='batch-abc' ORDER BY std_id;"
        )
        self.assertEqual(accounts, [("622848*********8312",), ("",)])

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

    def test_query_filters_disclaimer_when_text_is_in_account_column(self) -> None:
        disclaimer = "数据截至2025年11月05日，以上结果通过平台导出，非实时数据，实际内容以我行生产系统为准。"
        self.client.execute(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                acct_no, txn_time, txn_amount, txn_direction, raw_payload
            ) VALUES ('batch-disclaimer-acct', '农业银行', '交易明细', 'fp', ?, '2025-11-05 00:00:00', '0.00', '未知', '{}');
            """,
            (disclaimer,),
        )
        records = BankQueryService(self.client).query_unified_records("batch-disclaimer-acct")
        self.assertEqual(records, [])

    def test_purge_export_notice_rows_removes_existing_bad_rows(self) -> None:
        disclaimer = "数据截至2025年11月05日，非实时数据，实际内容以我行生产系统为准。"
        self.client.execute(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                acct_no, txn_time, txn_amount, txn_direction, raw_payload
            ) VALUES ('batch-purge-notice', '农业银行', '交易明细', 'fp',
                      ?, '2025-11-05 00:00:00', '0.00', '未知', '{}');
            """,
            (disclaimer,),
        )
        deleted = BankMappingService(self.client).purge_export_notice_rows("batch-purge-notice")
        self.assertEqual(deleted, 1)
        rows = self.client.query_all(
            "SELECT COUNT(*) FROM std_bank_txn WHERE import_batch_id='batch-purge-notice';"
        )
        self.assertEqual(rows[0][0], 0)

    def test_counterparty_name_matches_account_profile_without_id_number(self) -> None:
        self.client.execute(
            """
            INSERT INTO std_bank_account(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name, id_no, raw_payload)
            VALUES ('batch-person-name', '农业银行', '开户信息', 'fp', '6222001', '李四', '', '{}');
            """
        )
        self.client.execute(
            """
            INSERT INTO std_bank_account(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name, id_no, raw_payload)
            VALUES ('batch-person-name', '建设银行', '开户信息', 'fp', '6222002', '王五', '440101********1234', '{}');
            """
        )
        service = BankQueryService(self.client)
        names, accounts = service._known_person_counterparties("batch-person-name")
        self.assertIn("李四", names)
        self.assertNotIn("6222001", accounts)
        self.assertEqual(service._counterparty_category("李四", "", names, accounts), "individual_or_unknown")
        self.assertEqual(service._counterparty_category("未知主体A", "6222001", names, accounts), "company_platform")
        self.assertEqual(service._counterparty_category("张三", "", names, accounts), "individual_or_unknown")
        self.assertEqual(service._counterparty_category("李**", "", names, accounts), "individual_or_unknown")

    def test_unknown_person_collects_unassigned_account_transactions(self) -> None:
        self.client.execute(
            """
            INSERT INTO std_bank_account(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name, raw_payload)
            VALUES ('batch-unknown-person', '农业银行', '账户信息', 'fp', '057901100381814', '', '{}');
            """
        )
        self.client.execute(
            """
            INSERT INTO std_bank_txn(import_batch_id, bank_name, source_sheet, template_fingerprint, acct_no, person_name,
                                     txn_time, txn_amount, txn_direction, counterparty_name, counterparty_account, raw_payload)
            VALUES ('batch-unknown-person', '农业银行', '交易明细', 'fp', '', '',
                    '2026-01-01 00:00:00', '100.00', '收入', '未知对手', '', '{}');
            """
        )
        service = BankQueryService(self.client)
        identities = [item for item in service.list_person_identities('batch-unknown-person') if item['id_no'].startswith(UNKNOWN_PERSON_ID_PREFIX)]
        account_identity = next(item for item in identities if item['unknown_acct_no'])
        account_result = service.summarize_person_funds('batch-unknown-person', account_identity['person_name'], account_identity['id_no'])
        self.assertEqual(account_result['accounts'][0]['acct_no'], '057901100381814')
        txn_identity = next(item for item in identities if not item['unknown_acct_no'])
        txn_result = service.summarize_person_funds('batch-unknown-person', txn_identity['person_name'], txn_identity['id_no'])
        self.assertEqual(len(txn_result['records']), 1)
        self.assertEqual(txn_result['records'][0]['person_name'], '姓名未知')

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
