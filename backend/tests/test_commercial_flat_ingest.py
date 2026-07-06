"""Tests for flat old/new commercial-network ingest parsing."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.application.bootstrap import bootstrap_database
from app.application.import_use_cases import ImportUseCase
from app.services.integration.commercial.flat_ingest import (
    detect_flat_format,
    parse_new_commercial_sheet,
    parse_old_commercial_sheet,
)
from app.services.integration.commercial.ingest_service import CommercialIngestService
from app.services.shared.db.sqlite_client import SqliteClient

OLD_HEADERS = [
    "投标编码",
    "项目编码",
    "供应商编码",
    "投标日期",
    "供应商名称",
    "中标状态",
    "报价金额（元）",
    "项目名称",
    "项目类型",
    "起草时间",
    "发布时间",
    "投标截止时间",
    "开标日期",
    "项目预算（元）",
    "经办人",
]

NEW_HEADERS = [
    "寻源单号",
    "寻源标题",
    "寻源范围",
    "项目类别",
    "寻源类别",
    "项目预算（元）",
    "投标编号",
    "投标单位",
    "投标价格（元）",
    "投标时间",
    "中标单位",
    "中标价格(元)",
    "经办人",
    "发起时间",
    "发布时间",
    "投标截止时间",
    "开标时间",
    "决标时间",
    "中标公告发布时间",
]


def _sheet_df(headers: list[str], rows: list[list[object]]) -> pd.DataFrame:
    return pd.DataFrame([headers, *rows])


class CommercialFlatIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "commercial_flat.sqlite3")
        from app import runtime_paths as rp

        importlib.reload(rp)
        self.client = SqliteClient()
        bootstrap_database(self.client)
        self.output_columns = CommercialIngestService(self.client).OUTPUT_COLUMNS

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("DATAFUSIONX_DB_PATH", None)
        else:
            os.environ["DATAFUSIONX_DB_PATH"] = self._old_db
        from app import runtime_paths as rp

        importlib.reload(rp)

    def test_detect_flat_format(self) -> None:
        old_df = _sheet_df(OLD_HEADERS, [])
        new_df = _sheet_df(NEW_HEADERS, [])
        wide_df = pd.DataFrame([["序号", "单位", "数量", "A", "B", "C", "D", "E", "F", "G"]])
        self.assertEqual(detect_flat_format(old_df), "old")
        self.assertEqual(detect_flat_format(new_df), "new")
        self.assertIsNone(detect_flat_format(wide_df))

    def test_parse_old_format_winner_and_amount(self) -> None:
        rows = [
            [
                "Q1001",
                "P001",
                "SU001",
                "2010-06-10",
                "甲公司",
                "未中标",
                100000,
                "测试项目",
                "工程招标",
                "",
                "",
                "2010-06-10 08:30",
                "",
                120000,
                "张三",
            ],
            [
                "Q1002",
                "P001",
                "SU002",
                "2010-06-10",
                "乙公司",
                "未中标",
                90000,
                "测试项目",
                "工程招标",
                "",
                "",
                "2010-06-10 08:30",
                "",
                120000,
                "张三",
            ],
            [
                "Q1003",
                "P001",
                "SU003",
                "2010-06-10",
                "丙公司",
                "已中标",
                85000,
                "测试项目",
                "工程招标",
                "",
                "",
                "2010-06-10 08:30",
                "",
                120000,
                "张三",
            ],
        ]
        records = parse_old_commercial_sheet(
            _sheet_df(OLD_HEADERS, rows),
            purchaser="珠海发电厂",
            output_columns=self.output_columns,
        )
        self.assertEqual(len(records), 3)
        winner_rows = [row for row in records if row["公司名称"] == "丙公司"]
        self.assertEqual(len(winner_rows), 1)
        winner_row = winner_rows[0]
        self.assertEqual(winner_row["询价单号"], "P001")
        self.assertEqual(winner_row["采购单位"], "珠海发电厂")
        self.assertEqual(winner_row["中标供应商"], "丙公司")
        self.assertEqual(winner_row["中标金额(元)"], "85000")
        self.assertEqual(winner_row["总价(元)"], "85000")
        loser_row = next(row for row in records if row["公司名称"] == "甲公司")
        self.assertEqual(loser_row["中标金额(元)"], "")

    def test_parse_new_format_winner_by_company_match(self) -> None:
        rows = [
            [
                "SRC001",
                "测试寻源",
                "邀请",
                "工程",
                "询价",
                95000,
                "Q2205001332",
                "甲公司",
                92600,
                "2022-05-23",
                "甲公司",
                92600,
                "李四",
                "",
                "",
                "2022-05-24",
                "",
                "",
                "",
            ],
            [
                "SRC001",
                "测试寻源",
                "邀请",
                "工程",
                "询价",
                95000,
                "Q2205001381",
                "乙公司",
                99200,
                "2022-05-23",
                "甲公司",
                92600,
                "李四",
                "",
                "",
                "2022-05-24",
                "",
                "",
                "",
            ],
        ]
        records = parse_new_commercial_sheet(
            _sheet_df(NEW_HEADERS, rows),
            purchaser="金湾电厂",
            output_columns=self.output_columns,
        )
        self.assertEqual(len(records), 2)
        winner_row = next(row for row in records if row["公司名称"] == "甲公司")
        loser_row = next(row for row in records if row["公司名称"] == "乙公司")
        self.assertEqual(winner_row["中标金额(元)"], "92600")
        self.assertEqual(winner_row["状态"], "已中标")
        self.assertEqual(loser_row["中标金额(元)"], "")
        self.assertEqual(loser_row["状态"], "未中标")

    def test_parse_new_format_empty_winner(self) -> None:
        rows = [
            [
                "SRC002",
                "无中标项目",
                "公开",
                "工程",
                "询价",
                10000,
                "Q2205000001",
                "甲公司",
                9800,
                "2022-05-23",
                "",
                "",
                "王五",
                "",
                "",
                "2022-05-24",
                "",
                "",
                "",
            ],
        ]
        records = parse_new_commercial_sheet(
            _sheet_df(NEW_HEADERS, rows),
            purchaser="珠海发电厂",
            output_columns=self.output_columns,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["中标供应商"], "")
        self.assertEqual(records[0]["中标金额(元)"], "")
        self.assertEqual(records[0]["状态"], "未中标")

    def test_parse_new_format_realigns_split_title(self) -> None:
        rows = [
            [
                "GZCT014930",
                "ZHP11794 机二班  ",
                " 2号机2B汽泵平衡鼓泄漏流量计取样管接头加固",
                "邀请",
                "物资",
                "询价",
                28000,
                "Q2306010377",
                "上海子力工业在线技术服务有限公司",
                28000,
                "2023-06-29 08:26:15",
                "上海子力工业在线技术服务有限公司",
                28000,
                "廖婕",
                "",
                "",
                "2023-06-29 09:38:46",
                "",
                "",
                "",
            ],
        ]
        records = parse_new_commercial_sheet(
            _sheet_df(NEW_HEADERS, rows),
            purchaser="珠海发电厂",
            output_columns=self.output_columns,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["公司名称"], "上海子力工业在线技术服务有限公司")
        self.assertEqual(records[0]["中标供应商"], "上海子力工业在线技术服务有限公司")
        self.assertEqual(records[0]["中标金额(元)"], "28000")
        self.assertNotIn("2023-06-29", records[0]["中标供应商"])

    def test_distinct_winners_excludes_datetime(self) -> None:
        from app.services.integration.commercial.analysis_service import CommercialAnalysisService

        records = [
            {"winner": "甲公司"},
            {"winner": "2023-06-29 08:26:15"},
        ]
        winners = CommercialAnalysisService._distinct_winners(records)
        self.assertEqual(winners, ["甲公司"])
        headers = list(NEW_HEADERS)
        headers[11] = "中标价格（元）"
        rows = [
            [
                "SRC003",
                "列名变体",
                "邀请",
                "工程",
                "询价",
                50000,
                "Q2205000002",
                "甲公司",
                48000,
                "2022-05-23",
                "甲公司",
                48000,
                "赵六",
                "",
                "",
                "2022-05-24",
                "",
                "",
                "",
            ],
        ]
        records = parse_new_commercial_sheet(
            _sheet_df(headers, rows),
            purchaser="珠海发电厂",
            output_columns=self.output_columns,
        )
        self.assertEqual(records[0]["中标金额(元)"], "48000")

    def _write_flat_workbook(self, old_rows: list[list[object]], new_rows: list[list[object]]) -> str:
        path = Path(self._tmp.name) / "flat_commercial.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            _sheet_df(OLD_HEADERS, old_rows).to_excel(
                writer,
                index=False,
                header=False,
                sheet_name="旧商务网数据",
            )
            _sheet_df(NEW_HEADERS, new_rows).to_excel(
                writer,
                index=False,
                header=False,
                sheet_name="新商务网数据",
            )
        return str(path)

    def test_import_flat_workbook(self) -> None:
        old_rows = [
            [
                "Q1001",
                "P100",
                "SU001",
                "2010-06-10",
                "旧网甲公司",
                "已中标",
                120000,
                "旧项目",
                "工程招标",
                "",
                "",
                "2010-06-10 08:30",
                "",
                150000,
                "经办A",
            ],
        ]
        new_rows = [
            [
                "SRC100",
                "新寻源",
                "邀请",
                "工程",
                "询价",
                80000,
                "Q2205009999",
                "新网乙公司",
                76000,
                "2022-05-23",
                "新网乙公司",
                76000,
                "经办B",
                "",
                "",
                "2022-05-24",
                "",
                "",
                "",
            ],
        ]
        file_path = self._write_flat_workbook(old_rows, new_rows)
        summary = ImportUseCase(self.client).import_source(
            file_paths=[file_path],
            bank_name="珠海发电厂",
            source_type="commercial",
        )
        self.assertEqual(summary.failed_files, 0)
        self.assertEqual(summary.rows_total, 2)

    def test_import_legacy_wide_workbook(self) -> None:
        mock_path = Path(__file__).resolve().parents[2] / "mock-data" / "02_commercial_商务网询价.xlsx"
        if not mock_path.exists():
            self.skipTest("mock commercial workbook not found")
        summary = ImportUseCase(self.client).import_source(
            file_paths=[str(mock_path)],
            bank_name="默认来源",
            source_type="commercial",
        )
        self.assertEqual(summary.failed_files, 0)
        self.assertGreater(summary.rows_total, 0)


if __name__ == "__main__":
    unittest.main()
