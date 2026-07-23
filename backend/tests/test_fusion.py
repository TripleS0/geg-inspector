"""Fusion case, person linking and cockpit tests."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.application.bootstrap import bootstrap_database
from app.application.case_use_cases import CaseUseCase
from app.application.fusion_use_cases import FusionUseCase
from app.services.shared.db.sqlite_client import SqliteClient


class FusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "fusion.sqlite3")
        from app import runtime_paths as rp

        importlib.reload(rp)
        self.client = SqliteClient()
        bootstrap_database(self.client)
        self.case_uc = CaseUseCase(self.client)
        self.fusion_uc = FusionUseCase(self.client)

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("DATAFUSIONX_DB_PATH", None)
        else:
            os.environ["DATAFUSIONX_DB_PATH"] = self._old_db
        from app import runtime_paths as rp

        importlib.reload(rp)

    def test_schema_has_fusion_tables(self) -> None:
        rows = self.client.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('std_case', 'rel_case_batch', 'std_person', 'std_person_link', 'rel_identifier_candidate');"
        )
        names = {row[0] for row in rows}
        self.assertEqual(
            names,
            {"std_case", "rel_case_batch", "std_person", "std_person_link", "rel_identifier_candidate"},
        )
        versions = [row[0] for row in self.client.query_all("SELECT version FROM meta_schema_version ORDER BY version;")]
        self.assertIn(2, versions)

    def test_case_bind_discover_and_cockpit(self) -> None:
        batch_bank = "batch-bank-1"
        batch_wechat = "batch-wechat-1"
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('bank.xlsx', '/tmp/bank.xlsx', 'h1', 'CCB', 'bank', ?, 'imported');",
            (batch_bank,),
        )
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('wechat.xlsx', '/tmp/wechat.xlsx', 'h2', 'WeChat', 'wechat', ?, 'imported');",
            (batch_wechat,),
        )
        self.client.execute(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint, source_name,
                person_name, acct_no, txn_time, txn_amount, currency, txn_direction,
                counterparty_name, counterparty_account, summary, balance, raw_payload
            ) VALUES (?, 'CCB', 'sheet1', 'fp', 'src',
                '张伟', '6217003010128475936', '2025-06-01 10:00:00', '1000.00', 'CNY', '支出',
                '李强', '6228480402564890173', '往来款', '9000.00', '{}');
            """,
            (batch_bank,),
        )
        self.client.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_wechat_demo (
                raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id TEXT,
                bank_name TEXT,
                source_type TEXT,
                source_file_id INTEGER,
                source_sheet TEXT,
                template_fingerprint TEXT,
                row_no INTEGER,
                raw_payload TEXT,
                src_用户侧账号名称 TEXT,
                src_对手侧账户名称 TEXT,
                src_借贷类型 TEXT,
                src_交易时间 TEXT,
                src_交易金额分 TEXT,
                src_用户银行卡号 TEXT
            );
            """
        )
        self.client.execute(
            """
            INSERT INTO raw_wechat_demo(
                import_batch_id, bank_name, source_type, source_file_id, source_sheet,
                template_fingerprint, row_no, raw_payload,
                src_用户侧账号名称, src_对手侧账户名称, src_借贷类型, src_交易时间, src_交易金额分, src_用户银行卡号
            ) VALUES (?, 'WeChat', 'wechat', 1, 'sheet1', 'fp', 1, '{}',
                '张伟', '李强', '出', '2025-06-02 11:00:00', '50000', '6217003010128475936');
            """,
            (batch_wechat,),
        )
        self.client.execute(
            """
            INSERT INTO meta_bank_sheets(file_id, sheet_name, header_row_no, template_fingerprint, source_type, raw_table_name, rows_imported)
            SELECT file_id, 'sheet1', 1, 'fp', 'wechat', 'raw_wechat_demo', 1
            FROM meta_bank_files WHERE import_batch_id=? LIMIT 1;
            """,
            (batch_wechat,),
        )

        case = self.case_uc.create_case(case_name="测试案件")
        self.case_uc.bind_batches(case.case_id, [batch_bank, batch_wechat])

        discover = self.fusion_uc.discover(case.case_id)
        self.assertGreater(discover["inserted"], 0)

        auto = self.fusion_uc.auto_link(case.case_id, rediscover=False)
        self.assertGreater(auto["persons_created"], 0)
        self.assertGreater(auto["links_created"], 0)

        persons = self.fusion_uc.list_persons(case.case_id)
        names = {p["display_name"] for p in persons}
        self.assertIn("张伟", names)
        self.assertIn("李强", names)

        zhang = next(p for p in persons if p["display_name"] == "张伟")
        linked_types = {l["identifier_type"] for l in zhang["links"]}
        self.assertIn("bank_acct", linked_types)

        zhang_phone = next((c for c in self.fusion_uc.list_candidates(case.case_id) if c["identifier_type"] == "bank_acct" and "6217003010128475936" in c["identifier_norm"]), None)
        self.assertIsNone(zhang_phone)

        li_name = next((c for c in self.fusion_uc.list_candidates(case.case_id) if c["display_value"] == "李强"), None)
        self.assertIsNone(li_name)

        li = next(p for p in persons if p["display_name"] == "李强")

        cockpit = self.fusion_uc.person_cockpit(case.case_id, zhang["person_id"])
        self.assertGreater(cockpit["kpis"]["total_records"], 0)
        self.assertIn("bank_txn", cockpit["records_by_type"])
        relation = self.fusion_uc.relation_cockpit(case.case_id, zhang["person_id"], li["person_id"])
        self.assertTrue(relation["summary_text"])
        self.assertGreaterEqual(len(relation["direct_records"]), 1)

        anchor = self.fusion_uc.anchor_cockpit(case.case_id, "auto", "6217003010128475936")
        self.assertEqual(anchor["anchor"]["type"], "bank_card")
        self.assertGreater(anchor["kpis"]["total_records"], 0)
        self.assertIn("bank_txn", anchor["records_by_type"])
        self.assertTrue(anchor["linked_persons"])
        self.assertEqual(anchor["linked_persons"][0]["display_name"], "张伟")

        suggestions = self.fusion_uc.suggest_anchors(case.case_id, "6217", limit=10)
        self.assertTrue(any("6217" in item["display_value"] or "6217" in item["identifier_norm"] for item in suggestions["items"]))
        bank_suggestions = self.fusion_uc.suggest_anchors(case.case_id, "6217", limit=10, anchor_type="bank_card")
        self.assertTrue(
            any(item["identifier_type"] in {"bank_card", "bank_acct"} for item in bank_suggestions["items"]),
            bank_suggestions["items"],
        )

    def test_anchor_cockpit_enterprise_and_commercial(self) -> None:
        batch_ent = "batch-ent-anchor"
        batch_comm = "batch-comm-anchor"
        self.client.execute(
            """
            INSERT INTO std_enterprise_profile(
                import_batch_id, source_file_name, enterprise_name, enterprise_name_norm,
                credit_code, legal_person, shareholders_json, key_persons_json, raw_payload
            ) VALUES (?, 'e.xlsx', '华南机电设备有限公司', '华南机电设备有限公司', '91440101MA5D2K8M3X', '张伟', '["王五"]', '[]', '{}');
            """,
            (batch_ent,),
        )
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('comm.xlsx', '/tmp/c.xlsx', 'h3', '商务', 'commercial', ?, 'imported');",
            (batch_comm,),
        )
        self.client.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_comm_anchor (
                raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id TEXT,
                bank_name TEXT,
                source_type TEXT,
                source_file_id INTEGER,
                source_sheet TEXT,
                template_fingerprint TEXT,
                row_no INTEGER,
                raw_payload TEXT,
                src_询价单号 TEXT,
                src_公司名称 TEXT,
                src_采购单位 TEXT,
                src_中标供应商 TEXT,
                src_中标金额 TEXT,
                src_物资名称 TEXT
            );
            """
        )
        self.client.execute(
            """
            INSERT INTO raw_comm_anchor(
                import_batch_id, bank_name, source_type, source_file_id, source_sheet,
                template_fingerprint, row_no, raw_payload,
                src_询价单号, src_公司名称, src_采购单位, src_中标供应商, src_中标金额, src_物资名称
            ) VALUES (?, '商务', 'commercial', 1, 'sheet1', 'fp', 1, '{}',
                'XJ001', '华南机电设备有限公司', '某甲方单位', '华南机电设备有限公司', '100000', '电缆');
            """,
            (batch_comm,),
        )
        self.client.execute(
            """
            INSERT INTO meta_bank_sheets(file_id, sheet_name, header_row_no, template_fingerprint, source_type, raw_table_name, rows_imported)
            SELECT file_id, 'sheet1', 1, 'fp', 'commercial', 'raw_comm_anchor', 1
            FROM meta_bank_files WHERE import_batch_id=? LIMIT 1;
            """,
            (batch_comm,),
        )
        case = self.case_uc.create_case(case_name="锚点企业")
        self.case_uc.bind_batches(case.case_id, [batch_ent, batch_comm])
        self.fusion_uc.discover(case.case_id)
        self.fusion_uc.auto_link(case.case_id, rediscover=False)

        anchor = self.fusion_uc.anchor_cockpit(case.case_id, "enterprise_name", "华南机电设备有限公司")
        self.assertEqual(anchor["anchor"]["type"], "enterprise_name")
        self.assertIsNotNone(anchor.get("enterprise_roles"))
        self.assertEqual(anchor["enterprise_roles"]["legal_person"], "张伟")
        self.assertIn("enterprise", anchor["records_by_type"])
        if anchor["records_by_type"].get("commercial"):
            self.assertTrue(any("中标" in (r.get("role_hint") or "") for r in anchor["records_by_type"]["commercial"]))

        purchaser_anchor = self.fusion_uc.anchor_cockpit(case.case_id, "enterprise_name", "某甲方单位")
        self.assertGreaterEqual(purchaser_anchor["kpis"]["commercial_count"], 1)
        if purchaser_anchor.get("commercial_roles"):
            self.assertGreater(purchaser_anchor["commercial_roles"]["purchaser_count"], 0)

    def test_auto_link_service(self) -> None:
        batch_id = "batch-bank-auto"
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('bank.xlsx', '/tmp/bank.xlsx', 'h1', 'CCB', 'bank', ?, 'imported');",
            (batch_id,),
        )
        self.client.execute(
            """
            INSERT INTO std_bank_account(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, mobile, id_no, source_name, raw_payload
            ) VALUES (?, 'CCB', 's', 'fp', '王磊', '6214850209847362510', '13602295841', '440106199008216734', 'src', '{}');
            """,
            (batch_id,),
        )
        case = self.case_uc.create_case(case_name="自动关联")
        self.case_uc.bind_batches(case.case_id, [batch_id])
        result = self.fusion_uc.auto_link(case.case_id, rediscover=True)
        self.assertGreaterEqual(result["links_created"], 3)
        persons = self.fusion_uc.list_persons(case.case_id)
        wang = next((p for p in persons if p["display_name"] == "王磊"), None)
        self.assertIsNotNone(wang)
        types = {l["identifier_type"] for l in wang["links"]}  # type: ignore[union-attr]
        self.assertTrue({"person_name", "bank_acct", "phone"}.issubset(types))

    def test_bank_counterparty_does_not_auto_create_person(self) -> None:
        batch_id = "batch-bank-counterparty"
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('bank.xlsx', '/tmp/bank.xlsx', 'counterparty-hash', '建设银行', 'bank', ?, 'imported');",
            (batch_id,),
        )
        self.client.execute(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, txn_time, txn_amount, txn_direction,
                counterparty_name, counterparty_account, raw_payload
            ) VALUES (?, '建设银行', '交易明细', 'fp', '张三', 'CCB-001',
                      '2026-07-01 10:00:00', '88.00', '支出', '京东商城', 'JD-001', '{}');
            """,
            (batch_id,),
        )
        case = self.case_uc.create_case(case_name="交易对手候选")
        self.case_uc.bind_batches(case.case_id, [batch_id])

        self.fusion_uc.auto_link(case.case_id, rediscover=True)

        names = {person["display_name"] for person in self.fusion_uc.list_persons(case.case_id)}
        self.assertIn("张三", names)
        self.assertNotIn("京东商城", names)
        pending = self.fusion_uc.list_candidates(case.case_id)
        self.assertTrue(any(item["display_value"] == "京东商城" for item in pending))

    def test_auto_link_groups_bank_cards_by_name_and_id_across_banks(self) -> None:
        batch_id = "batch-bank-identities"
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('banks.xlsx', '/tmp/banks.xlsx', 'identity-hash', '多银行', 'bank', ?, 'imported');",
            (batch_id,),
        )
        self.client.executemany(
            """
            INSERT INTO std_bank_account(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, id_no, source_name, raw_payload
            ) VALUES (?, ?, '开户信息', 'fp', '李**', ?, ?, 'src', '{}');
            """,
            [
                (batch_id, "工商银行", "6222000000000001", "441424********2851"),
                (batch_id, "建设银行", "6222000000000001", "441424********2851"),
                (batch_id, "农业银行", "6228480000000003", "440106********1132"),
            ],
        )
        case = self.case_uc.create_case(case_name="同名脱敏人物")
        self.case_uc.bind_batches(case.case_id, [batch_id])

        self.fusion_uc.auto_link(case.case_id, rediscover=True)

        persons = [p for p in self.fusion_uc.list_persons(case.case_id) if p["display_name"] == "李**"]
        self.assertEqual(len(persons), 2)
        cards_by_id = {
            next(link["identifier_norm"] for link in person["links"] if link["identifier_type"] == "id_no"):
            {
                link["identifier_norm"]
                for link in person["links"]
                if link["identifier_type"] == "bank_acct"
            }
            for person in persons
        }
        self.assertEqual(
            cards_by_id["441424********2851"],
            {"工商银行|6222000000000001", "建设银行|6222000000000001"},
        )
        self.assertEqual(cards_by_id["440106********1132"], {"农业银行|6228480000000003"})

    def test_person_cockpit_does_not_mix_same_card_number_between_banks(self) -> None:
        batch_id = "batch-bank-card-collision"
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('collision.xlsx', '/tmp/collision.xlsx', 'collision-hash', '多银行', 'bank', ?, 'imported');",
            (batch_id,),
        )
        shared_card = "6222000000009999"
        self.client.executemany(
            """
            INSERT INTO std_bank_account(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, id_no, source_name, raw_payload
            ) VALUES (?, ?, '开户信息', 'fp', ?, ?, ?, 'src', '{}');
            """,
            [
                (batch_id, "工商银行", "李**", shared_card, "441424********2851"),
                (batch_id, "建设银行", "王**", shared_card, "440106********1132"),
            ],
        )
        self.client.executemany(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, txn_time, txn_amount, txn_direction, raw_payload
            ) VALUES (?, ?, '交易明细', 'fp', '', ?, '2026-07-01 10:00:00', ?, '收入', '{}');
            """,
            [
                (batch_id, "工商银行", shared_card, "100.00"),
                (batch_id, "建设银行", shared_card, "200.00"),
            ],
        )
        case = self.case_uc.create_case(case_name="跨行同卡号隔离")
        self.case_uc.bind_batches(case.case_id, [batch_id])
        self.fusion_uc.auto_link(case.case_id, rediscover=True)

        persons = {p["display_name"]: p for p in self.fusion_uc.list_persons(case.case_id)}
        first = self.fusion_uc.person_cockpit(case.case_id, persons["李**"]["person_id"])
        second = self.fusion_uc.person_cockpit(case.case_id, persons["王**"]["person_id"])
        self.assertEqual([row["amount"] for row in first["records_by_type"]["bank_txn"]], [100.0])
        self.assertEqual([row["amount"] for row in second["records_by_type"]["bank_txn"]], [200.0])

    def test_auto_link_enterprise_to_legal_person(self) -> None:
        batch_ent = "batch-ent-legal"
        batch_bank = "batch-bank-legal"
        self.client.execute(
            """
            INSERT INTO std_enterprise_profile(
                import_batch_id, source_file_name, enterprise_name, enterprise_name_norm,
                credit_code, legal_person, shareholders_json, key_persons_json, raw_payload
            ) VALUES (?, 'e.xlsx', '广州瀚海科技有限公司', '广州瀚海科技有限公司', '91440101MA5HAI001X',
                '林浩然', '["刘芳（持股30%）"]', '["周明（监事）"]', '{}');
            """,
            (batch_ent,),
        )
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('bank.xlsx', '/tmp/bank.xlsx', 'h1', 'CCB', 'bank', ?, 'imported');",
            (batch_bank,),
        )
        self.client.execute(
            """
            INSERT INTO std_bank_account(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, mobile, id_no, source_name, raw_payload
            ) VALUES (?, 'CCB', 's', 'fp', '林浩然', '6217001000100010001', '13810001001', '440103198503120001', 'src', '{}');
            """,
            (batch_bank,),
        )
        self.client.execute(
            """
            INSERT INTO std_bank_account(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, mobile, id_no, source_name, raw_payload
            ) VALUES (?, 'CCB', 's', 'fp', '刘芳', '6212261000500050001', '13510005005', '440103198811020005', 'src', '{}');
            """,
            (batch_bank,),
        )
        case = self.case_uc.create_case(case_name="工商法人关联")
        self.case_uc.bind_batches(case.case_id, [batch_ent, batch_bank])
        self.fusion_uc.auto_link(case.case_id, rediscover=True)

        persons = {p["display_name"]: p for p in self.fusion_uc.list_persons(case.case_id)}
        lin = persons["林浩然"]
        liu = persons["刘芳"]
        lin_ent = [l for l in lin["links"] if l["identifier_type"] == "enterprise_name"]
        liu_ent = [l for l in liu["links"] if l["identifier_type"] == "enterprise_name"]
        self.assertEqual(len(lin_ent), 1)
        self.assertEqual(lin_ent[0]["identifier_value"], "广州瀚海科技有限公司")
        self.assertEqual(liu_ent, [])

        pending_ent = [
            c for c in self.fusion_uc.list_candidates(case.case_id)
            if c["identifier_type"] == "enterprise_name"
        ]
        self.assertEqual(pending_ent, [])

    def test_auto_link_enterprise_when_commercial_candidate_exists(self) -> None:
        batch_ent = "batch-ent-comm-dup"
        batch_comm = "batch-comm-dup"
        self.client.execute(
            """
            INSERT INTO std_enterprise_profile(
                import_batch_id, source_file_name, enterprise_name, enterprise_name_norm,
                credit_code, legal_person, shareholders_json, key_persons_json, raw_payload
            ) VALUES (?, 'e.xlsx', '广州瀚海科技有限公司', '广州瀚海科技有限公司', '91440101MA5HAI001X',
                '林浩然', '[]', '[]', '{}');
            """,
            (batch_ent,),
        )
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('comm.xlsx', '/tmp/c.xlsx', 'h3', '商务', 'commercial', ?, 'imported');",
            (batch_comm,),
        )
        self.client.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_comm_ent_dup (
                raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id TEXT,
                bank_name TEXT,
                source_type TEXT,
                source_file_id INTEGER,
                source_sheet TEXT,
                template_fingerprint TEXT,
                row_no INTEGER,
                raw_payload TEXT,
                src_公司名称 TEXT
            );
            """
        )
        self.client.execute(
            """
            INSERT INTO raw_comm_ent_dup(
                import_batch_id, bank_name, source_type, source_file_id, source_sheet,
                template_fingerprint, row_no, raw_payload, src_公司名称
            ) VALUES (?, '商务', 'commercial', 1, 'sheet1', 'fp', 1, '{}', '广州瀚海科技有限公司');
            """,
            (batch_comm,),
        )
        self.client.execute(
            """
            INSERT INTO meta_bank_sheets(file_id, sheet_name, header_row_no, template_fingerprint, source_type, raw_table_name, rows_imported)
            SELECT file_id, 'sheet1', 1, 'fp', 'commercial', 'raw_comm_ent_dup', 1
            FROM meta_bank_files WHERE import_batch_id=? LIMIT 1;
            """,
            (batch_comm,),
        )
        case = self.case_uc.create_case(case_name="商务工商重复企业")
        self.case_uc.bind_batches(case.case_id, [batch_comm, batch_ent])
        self.fusion_uc.discover(case.case_id)
        self.fusion_uc.auto_link(case.case_id, rediscover=False)

        persons = {p["display_name"]: p for p in self.fusion_uc.list_persons(case.case_id)}
        lin = persons["林浩然"]
        ent = [l for l in lin["links"] if l["identifier_type"] == "enterprise_name"]
        self.assertEqual(len(ent), 1)
        self.assertEqual(ent[0]["identifier_value"], "广州瀚海科技有限公司")

    def test_mark_no_match_and_record_detail(self) -> None:
        batch_id = "batch-ent-1"
        self.client.execute(
            """
            INSERT INTO std_enterprise_profile(
                import_batch_id, source_file_name, enterprise_name, enterprise_name_norm,
                credit_code, legal_person, shareholders_json, key_persons_json, raw_payload
            ) VALUES (?, 'x.xlsx', '华南机电设备有限公司', '华南机电设备有限公司', '91440101MA5D2K8M3X', '张伟', '[]', '[]', '{"企业名称":"华南机电设备有限公司"}');
            """,
            (batch_id,),
        )
        case = self.case_uc.create_case(case_name="工商案件")
        self.case_uc.bind_batches(case.case_id, [batch_id])
        self.fusion_uc.discover(case.case_id)
        candidates = self.fusion_uc.list_candidates(case.case_id)
        self.assertTrue(candidates)
        candidate_id = candidates[0]["candidate_id"]
        self.fusion_uc.mark_candidate_no_match(case.case_id, candidate_id)
        pending = self.fusion_uc.list_candidates(case.case_id)
        self.assertFalse(any(c["candidate_id"] == candidate_id for c in pending))

        detail = self.fusion_uc.record_detail(
            json.dumps(
                {
                    "layer": "std",
                    "table": "std_enterprise_profile",
                    "pk": {"enterprise_id": 1},
                },
                ensure_ascii=False,
            )
        )
        self.assertEqual(detail["layer"], "std")
        self.assertIn("fields", detail)

    def test_wechat_amount_reads_sanitized_raw_column(self) -> None:
        from app.services.fusion.fusion_query_service import FusionQueryService

        batch_wechat = "batch-wechat-amt"
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('wechat.xlsx', '/tmp/wechat.xlsx', 'h2', 'WeChat', 'wechat', ?, 'imported');",
            (batch_wechat,),
        )
        self.client.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_wechat_amt (
                raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id TEXT,
                bank_name TEXT,
                source_type TEXT,
                source_file_id INTEGER,
                source_sheet TEXT,
                template_fingerprint TEXT,
                row_no INTEGER,
                raw_payload TEXT,
                src_用户侧账号名称 TEXT,
                src_对手侧账户名称 TEXT,
                src_借贷类型 TEXT,
                src_交易时间 TEXT,
                src_交易金额_分 TEXT,
                src_用户银行卡号 TEXT
            );
            """
        )
        self.client.execute(
            """
            INSERT INTO raw_wechat_amt(
                import_batch_id, bank_name, source_type, source_file_id, source_sheet,
                template_fingerprint, row_no, raw_payload,
                src_用户侧账号名称, src_对手侧账户名称, src_借贷类型, src_交易时间, src_交易金额_分, src_用户银行卡号
            ) VALUES (?, 'WeChat', 'wechat', 1, 'sheet1', 'fp', 1, '{}',
                '张伟', '李强', '出', '2025-06-02 11:00:00', '50000', '6217003010128475936');
            """,
            (batch_wechat,),
        )
        self.client.execute(
            """
            INSERT INTO meta_bank_sheets(file_id, sheet_name, header_row_no, template_fingerprint, source_type, raw_table_name, rows_imported)
            SELECT file_id, 'sheet1', 1, 'fp', 'wechat', 'raw_wechat_amt', 1
            FROM meta_bank_files WHERE import_batch_id=? LIMIT 1;
            """,
            (batch_wechat,),
        )
        case = self.case_uc.create_case(case_name="微信金额")
        self.case_uc.bind_batches(case.case_id, [batch_wechat])
        self.fusion_uc.auto_link(case.case_id, rediscover=True)
        zhang = next(p for p in self.fusion_uc.list_persons(case.case_id) if p["display_name"] == "张伟")
        cockpit = self.fusion_uc.person_cockpit(case.case_id, zhang["person_id"])
        self.assertEqual(cockpit["kpis"]["wechat_txn_count"], 1)
        self.assertGreater(cockpit["kpis"]["wechat_out_amount"], 0)
        wx = cockpit["records_by_type"]["wechat"][0]
        self.assertEqual(wx["amount"], 500.0)

        svc = FusionQueryService(self.client)
        self.assertEqual(svc._raw_field({"交易金额_分": "12345"}, "交易金额(分)"), "12345")

    def test_graph_explore_same_name_bank_cards_have_txn_path(self) -> None:
        """同名不同身份证的两张卡，应能通过 bank_txn 直连出路径（不因姓名塌缩）。"""
        batch_id = "batch-graph-same-name-cards"
        self.client.execute(
            "INSERT INTO meta_bank_files (file_name, file_path, file_hash, bank_name, source_type, import_batch_id, status)"
            " VALUES ('bank.xlsx', '/tmp/bank-graph.xlsx', 'graph-same-name', '建设银行', 'bank', ?, 'imported');",
            (batch_id,),
        )
        self.client.executemany(
            """
            INSERT INTO std_bank_account(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, id_no, source_name, raw_payload
            ) VALUES (?, ?, '开户信息', 'fp', '李**', ?, ?, 'src', '{}');
            """,
            [
                (batch_id, "建设银行", "3328134432", "440106********1111"),
                (batch_id, "工商银行", "6222087735", "440106********2222"),
            ],
        )
        self.client.executemany(
            """
            INSERT INTO std_bank_txn(
                import_batch_id, bank_name, source_sheet, template_fingerprint,
                person_name, acct_no, txn_time, txn_amount, txn_direction,
                counterparty_name, counterparty_account, summary, raw_payload
            ) VALUES (?, '建设银行', '交易明细', 'fp', '李**', '332813*********4432',
                      ?, ?, ?, '李**', '622208*********7735', ?, '{}');
            """,
            [
                (batch_id, "2012-05-31 15:36:57", "2590.00", "收入", "转帐存入"),
                (batch_id, "2012-09-24 22:46:00", "30000.00", "支出", "转帐支取"),
                (batch_id, "2012-11-19 14:40:30", "30000.00", "收入", "转帐存入"),
            ],
        )
        case = self.case_uc.create_case(case_name="图谱同名卡路径")
        self.case_uc.bind_batches(case.case_id, [batch_id])
        self.fusion_uc.auto_link(case.case_id, rediscover=True)

        persons = [p for p in self.fusion_uc.list_persons(case.case_id) if p["display_name"] == "李**"]
        self.assertEqual(len(persons), 2)

        graph = self.fusion_uc.explore_graph(
            case.case_id,
            {
                "anchors": [
                    {"type": "bank_card", "value": "3328134432"},
                    {"type": "bank_card", "value": "6222087735"},
                ],
                "relation_types": ["bank_txn", "identifier"],
                "display_level": 1,
                "min_weight": 1,
            },
        )
        self.assertGreaterEqual(graph["summary"]["path_count"], 1)
        self.assertTrue(any("bank_txn" in (p.get("relation_types") or []) for p in graph["paths"]))
        txn_edges = [e for e in graph["edges"] if e["type"] == "bank_txn"]
        self.assertTrue(txn_edges)
        self.assertGreaterEqual(max(e["record_count"] for e in txn_edges), 3)

        # Same-name persons: edge detail must resolve via counterparty account, not display name.
        edge = max(txn_edges, key=lambda item: int(item.get("record_count") or 0))
        detail = self.fusion_uc.graph_selection_detail(
            case.case_id,
            {
                "kind": "edge",
                "source": edge["source"],
                "target": edge["target"],
                "edge_type": "bank_txn",
            },
        )
        self.assertGreaterEqual(len(detail["records"]), 3)
        self.assertTrue(all(r["record_type"] == "bank_txn" for r in detail["records"]))

        persons_sorted = sorted(persons, key=lambda p: p["person_id"])
        person_detail = self.fusion_uc.graph_selection_detail(
            case.case_id,
            {
                "kind": "edge",
                "source": f"person:{persons_sorted[0]['person_id']}",
                "target": f"person:{persons_sorted[1]['person_id']}",
                "edge_type": "bank_txn",
            },
        )
        self.assertGreaterEqual(len(person_detail["records"]), 3)


if __name__ == "__main__":
    unittest.main()
