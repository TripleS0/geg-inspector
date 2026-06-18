"""Unit tests for bank fixed analysis module helpers."""

from __future__ import annotations

import unittest

from app.services.integration.bank.analysis_modules import (
    ModuleParams,
    aggregate_large_flow,
    build_amount_rounded_counts,
    classify_special_amount,
    classify_special_time,
    festival_tags_for_solar_date,
    filter_large_transactions,
    _zhdate_class,
)


def _row(**kwargs: str) -> dict[str, str]:
    base = {
        "data_source": "",
        "bank_type": "",
        "person_name": "",
        "acct_no": "",
        "txn_time": "",
        "txn_direction": "",
        "currency": "CNY",
        "amount": "0",
        "balance": "",
        "counterparty_name": "",
        "counterparty_account": "",
        "txn_desc": "",
        "remark": "",
    }
    base.update(kwargs)
    return base


class BankAnalysisModulesTests(unittest.TestCase):
    def test_filter_large_transactions_uses_abs_amount(self) -> None:
        recs = [
            _row(amount="50000"),
            _row(amount="-120000"),
            _row(amount="99,999.00"),
        ]
        out = filter_large_transactions(recs, 100_000.0)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["amount"], "-120000")

    def test_aggregate_large_flow_by_counterparty_account(self) -> None:
        recs = [
            _row(amount="1000", txn_direction="收入", counterparty_account="A1", counterparty_name="X"),
            _row(amount="300", txn_direction="支出", counterparty_account="A1", counterparty_name="X"),
            _row(amount="500", txn_direction="收入", counterparty_account="B2", counterparty_name="Y"),
        ]
        rows = aggregate_large_flow(recs, top_n=10)
        self.assertEqual(len(rows), 2)
        by_acct = {r["counterparty_account"]: r for r in rows}
        self.assertIn("A1", by_acct)
        self.assertAlmostEqual(by_acct["A1"]["in_total"], 1000.0)
        self.assertAlmostEqual(by_acct["A1"]["out_total"], 300.0)
        self.assertAlmostEqual(by_acct["A1"]["net"], 700.0)
        self.assertAlmostEqual(by_acct["B2"]["net"], 500.0)

    def test_aggregate_large_flow_fallback_name_when_no_account(self) -> None:
        recs = [
            _row(amount="200", txn_direction="收入", counterparty_account="", counterparty_name="仅名"),
            _row(amount="100", txn_direction="支出", counterparty_account="", counterparty_name="仅名"),
        ]
        rows = aggregate_large_flow(recs, top_n=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["counterparty_name"], "仅名")
        self.assertAlmostEqual(rows[0]["net"], 100.0)

    def test_classify_special_time_night_not_midnight_as_dawn(self) -> None:
        night = classify_special_time(_row(txn_time="2026-05-08 23:30:00"))
        self.assertTrue(any("深夜" in t for t in night))
        midnight = classify_special_time(_row(txn_time="2026-05-08 00:00:00"))
        self.assertFalse(any("凌晨" in t for t in midnight))
        dawn = classify_special_time(_row(txn_time="2026-05-08 00:01:00"))
        self.assertTrue(any("凌晨" in t for t in dawn))

    def test_classify_special_time_no_weekend_tag(self) -> None:
        sat = classify_special_time(_row(txn_time="2026-05-09 10:00:00"))
        self.assertFalse(any("周末" in t for t in sat))

    def test_classify_special_time_empty_when_unparseable(self) -> None:
        self.assertEqual(classify_special_time(_row(txn_time="not-a-date")), [])

    def test_classify_special_time_survives_zhdate_edge_dates(self) -> None:
        """zhdate may reject some solar dates near lunar new year; must not crash."""
        tags = classify_special_time(_row(txn_time="2025-01-28 21:07:25"))
        self.assertIsInstance(tags, list)

    def test_classify_special_time_solar_festivals(self) -> None:
        new_year = classify_special_time(_row(txn_time="2026-01-01 12:00:00"))
        self.assertTrue(any("元旦" in t or "法定" in t for t in new_year), new_year)
        self.assertTrue(
            any("情人节" in t for t in classify_special_time(_row(txn_time="2026-02-14 09:00:00")))
        )
        self.assertTrue(any("5·20" in t for t in classify_special_time(_row(txn_time="2026-05-20 18:00:00"))))

    def test_festival_tags_qixi_matches_zhdate(self) -> None:
        if _zhdate_class() is None:
            self.skipTest("zhdate 未安装，跳过农历七夕校验")
        from datetime import datetime

        try:
            from zhdate import ZhDate  # type: ignore[import-not-found]
        except ImportError:
            self.skipTest("zhdate 未安装")
        solar = ZhDate(2025, 7, 7, leap_month=False).to_datetime()
        tags = festival_tags_for_solar_date(solar)
        self.assertTrue(any("七夕" in t for t in tags), tags)
        self.assertFalse(any("周末" in t for t in tags))
        lunar_back = ZhDate.from_datetime(solar)
        self.assertEqual(lunar_back.lunar_month, 7)
        self.assertEqual(lunar_back.lunar_day, 7)
        self.assertFalse(lunar_back.leap_month)

    def test_sensitive_amount_whitelist_520_family(self) -> None:
        params = ModuleParams()
        for amt in ("520", "521", "1314"):
            counts = build_amount_rounded_counts([_row(amount=amt)])
            tags = classify_special_amount(_row(amount=amt), params, counts)
            self.assertTrue(any("敏感金额" in t for t in tags), tags)


class ModuleParamsTests(unittest.TestCase):
    def test_module_params_defaults(self) -> None:
        p = ModuleParams()
        self.assertEqual(p.large_amount_threshold, 100_000.0)
        self.assertEqual(p.top_n, 15)
        self.assertEqual(p.repeat_amount_min_count, 3)
        self.assertIn(520.0, p.special_amount_whitelist)
        self.assertIn(521.0, p.special_amount_whitelist)
        self.assertIn(1314.0, p.special_amount_whitelist)


if __name__ == "__main__":
    unittest.main()
