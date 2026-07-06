"""Tests for commercial co-bidding pattern analysis."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.integration.commercial.co_bid_analysis_service import (
    CoBidAnalysisParams,
    CommercialCoBidAnalysisService,
    _alternation_score,
)
from app.services.shared.db.sqlite_client import SqliteClient


def _record(
    inquiry_no: str,
    company_name: str,
    *,
    is_winner: bool = False,
    purchaser: str = "采购甲",
    inquiry_time: str = "",
) -> dict:
    return {
        "source": "",
        "inquiry_no": inquiry_no,
        "purchaser": purchaser,
        "company_name": company_name,
        "winner": company_name if is_winner else "",
        "is_winner": is_winner,
        "win_amount": 1000.0 if is_winner else 0.0,
        "item_name": "物资",
        "quote_price": "",
        "quantity": "",
        "remark": "",
        "inquiry_time": inquiry_time,
        "bid_status": "已中标" if is_winner else "未中标",
    }


class CommercialCoBidAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CommercialCoBidAnalysisService(SqliteClient())

    def test_alternation_score(self) -> None:
        self.assertEqual(_alternation_score([]), 0.0)
        self.assertEqual(_alternation_score(["a"]), 0.0)
        self.assertEqual(_alternation_score(["a", "b", "a", "b"]), 1.0)
        self.assertEqual(_alternation_score(["a", "a", "b"]), 0.5)

    def test_detects_high_co_bid(self) -> None:
        rows = []
        for idx in range(1, 6):
            rows.append(_record(f"Q{idx}", "目标公司甲", is_winner=False, inquiry_time=f"2024-01-0{idx}"))
            rows.append(_record(f"Q{idx}", "陪标公司乙", is_winner=False, inquiry_time=f"2024-01-0{idx}"))
            rows.append(_record(f"Q{idx}", "常胜公司丙", is_winner=True, inquiry_time=f"2024-01-0{idx}"))
        with patch(
            "app.services.integration.commercial.co_bid_analysis_service.CommercialAnalysisService._load_records",
            return_value=rows,
        ):
            result = self.service.analyze(
                "batch-1",
                CoBidAnalysisParams(company_name="目标公司甲"),
            )
        self.assertEqual(result["participation_count"], 5)
        companions = {c["company_name"]: c for c in result["companions"]}
        self.assertIn("陪标公司乙", companions)
        partner = companions["陪标公司乙"]
        self.assertGreaterEqual(partner["shared_inquiries"], 5)
        self.assertIn("高频陪标", partner["patterns"])
        self.assertNotIn("陪标不中", partner["patterns"])

    def test_detects_rotating_win(self) -> None:
        rows = []
        sequence = [
            ("目标公司甲", True),
            ("陪标公司乙", False),
            ("陪标公司乙", True),
            ("目标公司甲", False),
            ("目标公司甲", True),
            ("陪标公司乙", False),
            ("陪标公司乙", True),
            ("目标公司甲", False),
        ]
        for idx, (winner, target_won) in enumerate(sequence, start=1):
            inq = f"R{idx:02d}"
            t = f"2024-02-{idx:02d}"
            rows.append(_record(inq, "目标公司甲", is_winner=target_won, inquiry_time=t))
            rows.append(_record(inq, "陪标公司乙", is_winner=not target_won, inquiry_time=t))
        with patch(
            "app.services.integration.commercial.co_bid_analysis_service.CommercialAnalysisService._load_records",
            return_value=rows,
        ):
            result = self.service.analyze(
                "batch-1",
                CoBidAnalysisParams(company_name="目标公司甲"),
            )
        partner = next(c for c in result["companions"] if c["company_name"] == "陪标公司乙")
        self.assertIn("轮流中标", partner["patterns"])
        self.assertGreaterEqual(partner["pattern_detail"]["rotating_win"]["alternation_score"], 0.55)

    def test_empty_company_name(self) -> None:
        result = self.service.analyze("batch-1", CoBidAnalysisParams(company_name=""))
        self.assertEqual(result["participation_count"], 0)
        self.assertIn("请指定", result["description"])


    def test_fuzzy_company_name_match(self) -> None:
        rows = [
            _record("Q1", "珠海某某机电设备有限公司", is_winner=False),
            _record("Q1", "陪标公司乙", is_winner=True),
        ]
        with patch(
            "app.services.integration.commercial.co_bid_analysis_service.CommercialAnalysisService._load_records",
            return_value=rows,
        ):
            result = self.service.analyze("batch-1", CoBidAnalysisParams(company_name="机电设备"))
        self.assertEqual(result["target_company"], "珠海某某机电设备有限公司")
        self.assertEqual(result["participation_count"], 1)


if __name__ == "__main__":
    unittest.main()
