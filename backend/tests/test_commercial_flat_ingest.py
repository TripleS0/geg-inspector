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
    is_win_status,
    parse_new_commercial_sheet,
    parse_old_commercial_sheet,
)
from app.services.integration.commercial.ingest_service import CommercialIngestService
from app.services.integration.commercial.export_service import CommercialExportService
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

    def test_is_win_status_supports_partial_and_pre_win(self) -> None:
        self.assertTrue(is_win_status("已中标"))
        self.assertTrue(is_win_status("已预中标"))
        self.assertTrue(is_win_status("部分中标"))
        self.assertTrue(is_win_status("部分预中标"))
        self.assertFalse(is_win_status("未中标"))

    def test_parse_old_format_partial_pre_win_counts_as_winner(self) -> None:
        rows = [
            [
                "Q1003",
                "P001",
                "SU003",
                "2010-06-10",
                "丙公司",
                "部分预中标",
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
            source_file="demo",
            source_sheet="旧商务网数据",
        )
        self.assertEqual(records[0]["中标金额(元)"], "85000")
        self.assertEqual(records[0]["中标供应商"], "丙公司")
        self.assertEqual(records[0]["数据来源"], "demo / 旧商务网数据 / 第2行")

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

    def test_parse_new_format_uses_win_price_over_bid_price(self) -> None:
        rows = [
            [
                "GZCT014420",
                "联合中标项目",
                "邀请",
                "工程",
                "询价",
                120000,
                "Q2306010001",
                "广州熹润贸易有限公司",
                11600.02,
                "2023-06-29 08:26:15",
                "广州熹润贸易有限公司,东莞市利东机电设备有限公司",
                113510,
                "经办人A",
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
        self.assertEqual(records[0]["中标金额(元)"], "113510")
        self.assertEqual(records[0]["总价(元)"], "11600.02")
        self.assertEqual(records[0]["状态"], "已中标")

    def test_parse_new_format_no_winner_when_inquiry_win_price_all_empty(self) -> None:
        rows = [
            [
                "SRC004",
                "无中标价格项目",
                "邀请",
                "工程",
                "询价",
                50000,
                "Q2205000003",
                "甲公司",
                48000,
                "2022-05-23",
                "甲公司",
                "",
                "赵六",
                "",
                "",
                "2022-05-24",
                "",
                "",
                "",
            ],
            [
                "SRC004",
                "无中标价格项目",
                "邀请",
                "工程",
                "询价",
                50000,
                "Q2205000004",
                "乙公司",
                49000,
                "2022-05-23",
                "甲公司",
                "",
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
            _sheet_df(NEW_HEADERS, rows),
            purchaser="珠海发电厂",
            output_columns=self.output_columns,
        )
        self.assertEqual(len(records), 2)
        for row in records:
            self.assertEqual(row["状态"], "未中标")
            self.assertEqual(row["中标供应商"], "")
            self.assertEqual(row["中标金额(元)"], "")

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

    def test_normalize_purchaser_label(self) -> None:
        from app.services.integration.commercial.flat_ingest import normalize_purchaser_label

        self.assertEqual(
            normalize_purchaser_label("419b69cd619d4e838df99ac9960fed9a_珠海发电厂"),
            "珠海发电厂",
        )
        self.assertEqual(normalize_purchaser_label("金湾电厂"), "金湾电厂")
        self.assertEqual(normalize_purchaser_label("raw_abc_商务网明细"), "abc_商务网明细")

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

        export = CommercialExportService(self.client)
        rows = export._load_commercial_rows(summary.import_batch_id)
        sources = {row.get("数据来源", "") for row in rows}
        self.assertTrue(any("旧商务网数据" in src for src in sources), sources)
        self.assertTrue(any("新商务网数据" in src for src in sources), sources)
        self.assertFalse(any("商务网明细" in src for src in sources), sources)

    def _write_old_flat_file(self, path: Path, project_code: str, company: str) -> None:
        rows = [
            [
                "B001",
                project_code,
                "S001",
                "2024-01-01",
                company,
                "已中标",
                100000,
                f"项目{project_code}",
                "工程招标",
                "",
                "",
                "2024-01-02",
                "",
                120000,
                "经办人",
            ],
        ]
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            _sheet_df(OLD_HEADERS, rows).to_excel(
                writer,
                index=False,
                header=False,
                sheet_name="旧网数据",
            )

    def test_multi_file_single_batch_merged(self) -> None:
        path_a = Path(self._tmp.name) / "A发电厂数据.xlsx"
        path_b = Path(self._tmp.name) / "B发电厂数据.xlsx"
        self._write_old_flat_file(path_a, "QA1001", "甲公司")
        self._write_old_flat_file(path_b, "QB1002", "乙公司")

        summary = ImportUseCase(self.client).import_source(
            file_paths=[str(path_a), str(path_b)],
            bank_name="默认来源",
            source_type="commercial",
            batch_name="多发电厂批次",
        )
        self.assertEqual(summary.failed_files, 0)
        self.assertEqual(summary.files_total, 2)
        self.assertEqual(summary.rows_total, 2)

        export = CommercialExportService(self.client)
        rows = export._load_commercial_rows(summary.import_batch_id)
        purchasers = {row.get("采购单位", "") for row in rows}
        self.assertIn("A发电厂数据", purchasers)
        self.assertIn("B发电厂数据", purchasers)

        table_rows = self.client.query_all(
            """
            SELECT DISTINCT s.raw_table_name
            FROM meta_bank_sheets s
            JOIN meta_bank_files f ON f.file_id=s.file_id
            WHERE f.import_batch_id=?;
            """,
            (summary.import_batch_id,),
        )
        self.assertEqual(len(table_rows), 1)

    def test_append_files_to_existing_commercial_batch(self) -> None:
        path_a = Path(self._tmp.name) / "A发电厂数据.xlsx"
        path_b = Path(self._tmp.name) / "B发电厂数据.xlsx"
        self._write_old_flat_file(path_a, "QA2001", "甲公司")
        self._write_old_flat_file(path_b, "QB2002", "乙公司")

        first = ImportUseCase(self.client).import_source(
            file_paths=[str(path_a)],
            bank_name="默认来源",
            source_type="commercial",
            batch_name="追加测试批次",
        )
        second = ImportUseCase(self.client).import_source(
            file_paths=[str(path_b)],
            bank_name="默认来源",
            source_type="commercial",
            import_batch_id=first.import_batch_id,
        )
        self.assertEqual(first.import_batch_id, second.import_batch_id)
        rows = CommercialExportService(self.client)._load_commercial_rows(first.import_batch_id)
        self.assertEqual(len(rows), 2)

    def test_append_by_same_batch_name_creates_separate_batches(self) -> None:
        path_a = Path(self._tmp.name) / "A发电厂数据.xlsx"
        path_b = Path(self._tmp.name) / "B发电厂数据.xlsx"
        self._write_old_flat_file(path_a, "QA3001", "甲公司")
        self._write_old_flat_file(path_b, "QB3002", "乙公司")

        first = ImportUseCase(self.client).import_source(
            file_paths=[str(path_a)],
            bank_name="默认来源",
            source_type="commercial",
            batch_name="统一商务网批次",
        )
        second = ImportUseCase(self.client).import_source(
            file_paths=[str(path_b)],
            bank_name="默认来源",
            source_type="commercial",
            batch_name="统一商务网批次",
        )
        self.assertNotEqual(first.import_batch_id, second.import_batch_id)
        rows_first = CommercialExportService(self.client)._load_commercial_rows(first.import_batch_id)
        rows_second = CommercialExportService(self.client)._load_commercial_rows(second.import_batch_id)
        self.assertEqual(len(rows_first), 1)
        self.assertEqual(len(rows_second), 1)

    def test_merge_existing_commercial_batches(self) -> None:
        path_a = Path(self._tmp.name) / "A发电厂数据.xlsx"
        path_b = Path(self._tmp.name) / "B发电厂数据.xlsx"
        self._write_old_flat_file(path_a, "QA4001", "甲公司")
        self._write_old_flat_file(path_b, "QB4002", "乙公司")

        batch_a = ImportUseCase(self.client).import_source(
            file_paths=[str(path_a)],
            bank_name="默认来源",
            source_type="commercial",
            batch_name="金湾电厂",
        )
        batch_b = ImportUseCase(self.client).import_source(
            file_paths=[str(path_b)],
            bank_name="默认来源",
            source_type="commercial",
            batch_name="珠海发电厂",
        )
        from app.application.dataset_use_cases import DatasetUseCase

        merged = DatasetUseCase(self.client).merge_import_batches(
            batch_a.import_batch_id,
            [batch_b.import_batch_id],
            batch_name="2024商务网合并",
        )
        self.assertEqual(merged.file_count, 2)
        rows = CommercialExportService(self.client)._load_commercial_rows(merged.import_batch_id)
        self.assertEqual(len(rows), 2)

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
