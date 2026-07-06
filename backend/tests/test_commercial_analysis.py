"""Tests for commercial bid analysis filters and statistics."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.integration.commercial.analysis_service import (
    CommercialAnalysisFilters,
    CommercialAnalysisService,
)


def _record(
    company: str,
    inquiry_no: str,
    *,
    is_winner: bool = False,
    win_amount: float = 0.0,
    purchaser: str = "采购单位A",
    inquiry_time: str = "2024-06-01 10:00:00",
) -> dict:
    return {
        "source": "测试来源",
        "inquiry_no": inquiry_no,
        "purchaser": purchaser,
        "company_name": company,
        "winner": company if is_winner else "其他公司",
        "is_winner": is_winner,
        "win_amount": win_amount,
        "item_name": "物资",
        "quote_price": "100",
        "quantity": "1",
        "remark": "",
        "inquiry_time": inquiry_time,
    }


class CommercialAnalysisFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CommercialAnalysisService()
        self.batch_id = "batch-analysis-test"

    def _query(self, records: list[dict], filters: CommercialAnalysisFilters | None = None, limit: int = 5000):
        with patch.object(self.service, "_load_records", return_value=records):
            with patch.object(self.service, "_risk_summary_map", return_value={}):
                return self.service.query_records(self.batch_id, filters, limit=limit)

    def test_participation_min_excludes_low_participation_companies(self) -> None:
        records = [
            _record("高频企业有限公司", f"Q-H-{idx}") for idx in range(120)
        ] + [_record("低频企业有限公司", f"Q-L-{idx}") for idx in range(3)]

        result = self._query(records, CommercialAnalysisFilters(participation_min=100))
        summary = result["summary"]["company_summary"]

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["company_name"], "高频企业有限公司")
        self.assertEqual(summary[0]["participation_count"], 120)
        self.assertEqual(result["summary"]["company_count"], 1)

    def test_participation_min_accurate_when_record_limit_is_low(self) -> None:
        """Record limit must not shrink participation counts used for filtering."""
        records = [_record("高频企业有限公司", f"Q-{idx}") for idx in range(150)]
        records += [_record("低频企业有限公司", f"Q-LOW-{idx}") for idx in range(5)]

        result = self._query(records, CommercialAnalysisFilters(participation_min=100), limit=50)
        summary = result["summary"]["company_summary"]

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["participation_count"], 150)
        self.assertLessEqual(len(result["records"]), 50)

    def test_participation_min_zero_or_none_means_no_extra_filter(self) -> None:
        records = [_record("甲公司", "Q-1"), _record("乙公司", "Q-2")]

        none_result = self._query(records, CommercialAnalysisFilters(participation_min=None))
        zero_result = self._query(records, CommercialAnalysisFilters(participation_min=0))

        self.assertEqual(none_result["summary"]["company_count"], 2)
        self.assertEqual(zero_result["summary"]["company_count"], 2)

    def test_only_winners_filters_non_winning_rows(self) -> None:
        records = [
            _record("甲公司", "Q-1", is_winner=True, win_amount=1000.0),
            _record("甲公司", "Q-2", is_winner=False, win_amount=0.0),
            _record("乙公司", "Q-3", is_winner=False, win_amount=0.0),
        ]

        result = self._query(records, CommercialAnalysisFilters(only_winners=True))
        summary = {row["company_name"]: row for row in result["summary"]["company_summary"]}

        self.assertEqual(summary["甲公司"]["participation_count"], 1)
        self.assertEqual(summary["甲公司"]["win_count"], 1)
        self.assertNotIn("乙公司", summary)

    def test_amount_min_filters_by_win_amount(self) -> None:
        records = [
            _record("甲公司", "Q-1", is_winner=True, win_amount=500.0),
            _record("乙公司", "Q-2", is_winner=True, win_amount=5000.0),
        ]

        result = self._query(records, CommercialAnalysisFilters(amount_min=1000))
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"乙公司"})

    def test_amount_max_filters_by_win_amount(self) -> None:
        records = [
            _record("甲公司", "Q-1", is_winner=True, win_amount=500.0),
            _record("乙公司", "Q-2", is_winner=True, win_amount=5000.0),
        ]

        result = self._query(records, CommercialAnalysisFilters(amount_max=1000))
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"甲公司"})

    def test_company_name_substring_filter(self) -> None:
        records = [
            _record("广州甲公司", "Q-1"),
            _record("深圳乙公司", "Q-2"),
        ]

        result = self._query(records, CommercialAnalysisFilters(company_name="广州"))
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"广州甲公司"})

    def test_purchaser_filter(self) -> None:
        records = [
            _record("甲公司", "Q-1", purchaser="珠海电厂"),
            _record("乙公司", "Q-2", purchaser="广州电厂"),
        ]

        result = self._query(records, CommercialAnalysisFilters(purchaser="珠海电厂"))
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"甲公司"})

    def test_inquiry_no_filter(self) -> None:
        records = [
            _record("甲公司", "Q-1001"),
            _record("乙公司", "Q-2002"),
        ]

        result = self._query(records, CommercialAnalysisFilters(inquiry_no="Q-1001"))
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"甲公司"})

    def test_winner_filter(self) -> None:
        records = [
            _record("甲公司", "Q-1", is_winner=True, win_amount=100.0),
            _record("乙公司", "Q-2", is_winner=False, win_amount=0.0),
        ]

        result = self._query(records, CommercialAnalysisFilters(winner="甲公司"))
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertIn("甲公司", names)
        self.assertNotIn("乙公司", names)

    def test_date_range_filter(self) -> None:
        records = [
            _record("甲公司", "Q-1", inquiry_time="2024-01-15 10:00:00"),
            _record("乙公司", "Q-2", inquiry_time="2024-06-15 10:00:00"),
        ]

        result = self._query(
            records,
            CommercialAnalysisFilters(start_time="2024-06-01 00:00:00", end_time="2024-06-30 23:59:59"),
        )
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"乙公司"})

    def test_date_range_excludes_records_without_inquiry_time(self) -> None:
        records = [
            _record("甲公司", "Q-1", inquiry_time=""),
            _record("乙公司", "Q-2", inquiry_time="2024-06-15 10:00:00"),
        ]

        result = self._query(
            records,
            CommercialAnalysisFilters(start_time="2024-06-01 00:00:00", end_time="2024-06-30 23:59:59"),
        )
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"乙公司"})

    def test_combined_participation_min_and_amount_min(self) -> None:
        records = [
            _record("高频中标公司", f"Q-HW-{idx}", is_winner=True, win_amount=2000.0)
            for idx in range(110)
        ] + [
            _record("高频未达标公司", f"Q-HL-{idx}", is_winner=True, win_amount=100.0)
            for idx in range(110)
        ] + [_record("低频公司", f"Q-L-{idx}", is_winner=True, win_amount=5000.0) for idx in range(3)]

        result = self._query(
            records,
            CommercialAnalysisFilters(participation_min=100, amount_min=1000),
        )
        names = {row["company_name"] for row in result["summary"]["company_summary"]}

        self.assertEqual(names, {"高频中标公司"})

    def test_load_records_treats_partial_status_as_winner(self) -> None:
        from app.services.integration.commercial.export_service import CommercialExportService

        raw_rows = [
            {
                "数据来源": "book / sheet1 / 第3行",
                "询价单号": "Q-1",
                "采购单位": "采购单位A",
                "公司名称": "甲公司",
                "中标供应商": "",
                "状态": "部分预中标",
                "中标金额(元)": "",
                "物资编码/来源采购申请代码--物资描述": "物资",
                "含税单价(元)": "100",
                "数量": "1",
                "备注": "",
                "总价(元)": "5000",
                "含税合计总价(元)": "5000",
            }
        ]
        with patch.object(CommercialExportService, "_load_commercial_rows", return_value=raw_rows):
            records = self.service._load_records(self.batch_id)
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["is_winner"])
        self.assertEqual(records[0]["win_amount"], 5000.0)
        self.assertEqual(records[0]["bid_status"], "部分预中标")
        self.assertEqual(records[0]["source"], "book / sheet1 / 第3行")

    def test_summary_counts_match_filtered_company_summary(self) -> None:
        records = [_record("甲公司", f"Q-A-{idx}") for idx in range(105)]
        records += [_record("乙公司", f"Q-B-{idx}") for idx in range(8)]

        result = self._query(records, CommercialAnalysisFilters(participation_min=100))
        summary = result["summary"]

        self.assertEqual(summary["company_count"], len(summary["company_summary"]))
        self.assertTrue(all(int(row["participation_count"]) >= 100 for row in summary["company_summary"]))


if __name__ == "__main__":
    unittest.main()
