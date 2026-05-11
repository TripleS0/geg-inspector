from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from app.application.bootstrap import bootstrap_database
from app.services.integration.commercial.risk_rule_service import CommercialRiskAnalysisService, _split_company_names
from app.services.shared.db.sqlite_client import SqliteClient


class CommercialRiskRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "risk.sqlite3")
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

    def test_split_company_names(self) -> None:
        self.assertEqual(
            _split_company_names("甲公司(Q231201001)、乙公司；丙公司（Q230500002）\n丁公司/戊公司"),
            ["甲公司", "乙公司", "丙公司", "丁公司", "戊公司"],
        )

    def test_context_splits_multiple_winners_and_companies(self) -> None:
        svc = CommercialRiskAnalysisService(self.client)
        ctx = svc._build_context(
            [
                {
                    "询价单号": "Q1",
                    "公司名称": "甲公司、乙公司",
                    "中标供应商": "甲公司、乙公司",
                }
            ]
        )
        self.assertEqual(ctx["inquiry_companies"]["Q1"], {"甲公司", "乙公司"})
        self.assertEqual(ctx["inquiry_winners"]["Q1"], {"甲公司", "乙公司"})
        self.assertNotIn("Q1", ctx["inquiry_winner"])

    def test_r006_skips_inquiries_with_multiple_winners(self) -> None:
        svc = CommercialRiskAnalysisService(self.client)
        rows = [
            {"询价单号": "Q1", "公司名称": "甲公司", "中标供应商": "甲公司"},
            {"询价单号": "Q1", "公司名称": "乙公司", "中标供应商": "乙公司"},
            {"询价单号": "Q2", "公司名称": "丙公司", "中标供应商": "丙公司"},
            {"询价单号": "Q2", "公司名称": "丁公司", "中标供应商": "丁公司"},
            {"询价单号": "Q3", "公司名称": "戊公司", "中标供应商": "戊公司"},
            {"询价单号": "Q3", "公司名称": "己公司", "中标供应商": "己公司"},
        ]
        ctx = svc._build_context(rows)
        svc._rule_r006(
            "batch-r006",
            "轮流中标",
            1.0,
            {"min_distinct_winners": 3, "window_size": 3},
            ctx,
        )

        rows = self.client.query_all("SELECT COUNT(*) FROM ana_risk_event WHERE import_batch_id='batch-r006';")
        self.assertEqual(rows[0][0], 0)

    def test_r006_events_attach_to_real_winners(self) -> None:
        svc = CommercialRiskAnalysisService(self.client)
        rows = [
            {"询价单号": "Q1", "公司名称": "甲公司", "中标供应商": "甲公司"},
            {"询价单号": "Q2", "公司名称": "乙公司", "中标供应商": "乙公司"},
            {"询价单号": "Q3", "公司名称": "丙公司", "中标供应商": "丙公司"},
        ]
        ctx = svc._build_context(rows)
        svc._rule_r006(
            "batch-r006-real",
            "轮流中标",
            1.0,
            {"min_distinct_winners": 3, "window_size": 3},
            ctx,
        )

        events = self.client.query_all(
            """
            SELECT enterprise_name
            FROM ana_risk_event
            WHERE import_batch_id='batch-r006-real'
            ORDER BY enterprise_name;
            """
        )
        names = [row[0] for row in events]
        self.assertEqual(names, ["丙公司", "乙公司", "甲公司"])
        self.assertNotIn("轮换模式", names)


if __name__ == "__main__":
    unittest.main()
