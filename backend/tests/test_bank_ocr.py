"""Tests for bank OCR parsing, drafts, and commit pipeline."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.application.bootstrap import bootstrap_database
from app.services.bank_ocr.commit_service import BankOcrCommitService
from app.services.bank_ocr.draft_repository import BankOcrDraftRepository
from app.services.bank_ocr.layout_profiles import CEB_TXN_V1
from app.services.bank_ocr.pdf_converter import expand_upload_to_page_images, is_supported_upload
from app.services.bank_ocr.upload_formats import SUPPORTED_UPLOAD_SUFFIXES
from app.services.bank_ocr.table_parser import (
    merge_deposit_withdrawal,
    parse_header_fields,
    parse_table_html,
    parse_table_html_raw,
)
from app.services.integration.bank.template_library import BUILTIN_TEMPLATES
from app.services.shared.db.sqlite_client import SqliteClient


class BankOcrUploadFormatTests(unittest.TestCase):
    def test_supported_upload_suffixes_at_least_five_image_types(self) -> None:
        image_suffixes = {s for s in SUPPORTED_UPLOAD_SUFFIXES if s != ".pdf"}
        self.assertGreaterEqual(len(image_suffixes), 5)
        for ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".svg"):
            self.assertIn(ext, SUPPORTED_UPLOAD_SUFFIXES)

    def test_is_supported_upload(self) -> None:
        self.assertTrue(is_supported_upload("scan.PNG"))
        self.assertTrue(is_supported_upload("/tmp/flow.svg"))
        self.assertFalse(is_supported_upload("data.xlsx"))
        self.assertFalse(is_supported_upload("note.txt"))

    def test_expand_raster_images_to_png(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in ("sample.png", "sample.jpg", "sample.bmp", "sample.webp"):
                src = tmp_path / name
                Image.new("RGB", (120, 80), color=(240, 240, 240)).save(src)
                pages = expand_upload_to_page_images(src, tmp_path / name / "out")
                self.assertEqual(len(pages), 1)
                self.assertTrue(Path(pages[0]).is_file())
                self.assertEqual(Path(pages[0]).suffix.lower(), ".png")

    def test_expand_svg_to_png_when_cairosvg_available(self) -> None:
        try:
            import cairosvg  # noqa: F401
        except ImportError:
            self.skipTest("cairosvg 未安装")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            svg = tmp_path / "stmt.svg"
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
                '<rect width="200" height="100" fill="white"/>'
                '<text x="10" y="40" font-size="14">交易日期</text>'
                "</svg>",
                encoding="utf-8",
            )
            pages = expand_upload_to_page_images(svg, tmp_path / "out")
            self.assertEqual(len(pages), 1)
            self.assertTrue(Path(pages[0]).stat().st_size > 0)


class BankOcrParserTests(unittest.TestCase):
    def test_parse_table_html_maps_ceb_columns(self) -> None:
        html = """
        <table>
          <tr>
            <td>客户账号</td><td>交易日期</td><td>交易流水号</td><td>存入金额</td>
            <td>检出金额</td><td>账户余额</td><td>摘要</td><td>对方账号</td><td>对方名称</td>
          </tr>
          <tr>
            <td>622666123456</td><td>20240104</td><td>901v5abc</td><td>1,200.00</td>
            <td></td><td>5,000.00</td><td>薪资类代发</td><td></td><td>财付通</td>
          </tr>
        </table>
        """
        rows, conf = parse_table_html(html, CEB_TXN_V1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["交易日期"], "20240104")
        self.assertEqual(rows[0]["存入金额"], "1,200.00")
        self.assertGreater(conf[0]["交易日期"], 0.9)

    def test_parse_table_html_raw_keeps_original_columns(self) -> None:
        html = """
        <table>
          <tr>
            <td>客户账号</td><td>交易日期</td><td>存入金额</td><td>检出金额</td><td>摘要</td>
          </tr>
          <tr>
            <td>622666123456</td><td>20240104</td><td>1,200.00</td><td></td><td>薪资类代发</td>
          </tr>
        </table>
        """
        columns, rows, conf = parse_table_html_raw(html)
        self.assertIn("存入金额", columns)
        self.assertIn("检出金额", columns)
        self.assertNotIn("交易金额", columns)
        self.assertEqual(rows[0]["存入金额"], "1,200.00")
        self.assertGreater(conf[0]["交易日期"], 0.9)

    def test_merge_deposit_withdrawal(self) -> None:
        income = merge_deposit_withdrawal({"存入金额": "100.00", "检出金额": ""}, CEB_TXN_V1)
        self.assertEqual(income["交易金额"], "100.00")
        self.assertEqual(income["借贷方向"], "收入")
        out = merge_deposit_withdrawal({"存入金额": "", "检出金额": "25.00"}, CEB_TXN_V1)
        self.assertEqual(out["交易金额"], "25.00")
        self.assertEqual(out["借贷方向"], "支出")

    def test_parse_header_fields(self) -> None:
        lines = [
            ("客户姓名: 张三", 0.9),
            ("客户账号: 622666123456", 0.9),
            ("对账日期: 20030101-20240313", 0.9),
        ]
        header = parse_header_fields(lines, CEB_TXN_V1)
        self.assertEqual(header["客户姓名"], "张三")
        self.assertEqual(header["客户账号"], "622666123456")
        self.assertIn("20030101", header["对账日期"])

    def test_ceb_template_exists(self) -> None:
        ids = {item.template_id for item in BUILTIN_TEMPLATES}
        self.assertIn("ceb_txn_v1", ids)


class BankOcrRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        self._old_home = os.environ.get("DATAFUSIONX_HOME")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "ocr.sqlite3")
        os.environ["DATAFUSIONX_HOME"] = self._tmp.name
        from app import runtime_paths as rp
        importlib.reload(rp)
        self.client = bootstrap_database(SqliteClient())
        self.repo = BankOcrDraftRepository(self.client)

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("DATAFUSIONX_DB_PATH", None)
        else:
            os.environ["DATAFUSIONX_DB_PATH"] = self._old_db
        if self._old_home is None:
            os.environ.pop("DATAFUSIONX_HOME", None)
        else:
            os.environ["DATAFUSIONX_HOME"] = self._old_home
        from app import runtime_paths as rp
        importlib.reload(rp)

    def test_create_save_and_commit_job(self) -> None:
        job_id = self.repo.create_job(
            bank_name="光大银行",
            batch_name="测试批次",
            layout_profile_id="ceb_txn_v1",
            status="ready",
        )
        self.repo.add_page(job_id=job_id, page_index=1, image_path="/tmp/page1.png", width=100, height=100)
        self.repo.replace_draft_rows(
            job_id,
            [
                {
                    "page_index": 1,
                    "row_index": 0,
                    "cells": {
                        "客户账号": "622666123456",
                        "交易日期": "20240104",
                        "交易流水号": "SN001",
                        "存入金额": "100.00",
                        "检出金额": "",
                        "账户余额": "1000.00",
                        "摘要": "测试",
                        "对方账号": "",
                        "对方名称": "微信",
                    },
                    "confidence": {"交易日期": 0.95},
                }
            ],
        )
        self.repo.update_job(
            job_id,
            header_json={
                "客户姓名": "张三",
                "客户账号": "622666123456",
                "_detected_columns": [
                    "客户账号",
                    "交易日期",
                    "交易流水号",
                    "存入金额",
                    "检出金额",
                    "账户余额",
                    "摘要",
                    "对方账号",
                    "对方名称",
                ],
            },
        )
        job = self.repo.get_job(job_id)
        assert job is not None
        self.assertEqual(len(job["rows"]), 1)

        commit = BankOcrCommitService(self.client)
        with patch("app.application.import_use_cases.get_integration_bundle") as bundle_mock:
            ingest_mock = bundle_mock.return_value.ingest_cls.return_value
            ingest_mock.ingest_files.return_value = type(
                "R",
                (),
                {
                    "import_batch_id": "batch-ocr-1",
                    "files_total": 1,
                    "sheets_total": 1,
                    "rows_total": 1,
                    "new_templates": 0,
                    "failed_files": 0,
                },
            )()
            mapping_mock = bundle_mock.return_value.mapping_cls.return_value
            result = commit.commit_job(job_id)
            mapping_mock.standardize_batch.assert_not_called()
        self.assertEqual(result["import_batch_id"], "batch-ocr-1")
        self.assertEqual(result["commit_mode"], "raw")
        updated = self.repo.get_job(job_id)
        assert updated is not None
        self.assertEqual(updated["status"], "committed")

    def test_use_case_save_rows_and_header(self) -> None:
        from app.application.bank_ocr_use_cases import BankOcrUseCase

        uc = BankOcrUseCase(self.client)
        job_id = self.repo.create_job(
            bank_name="光大银行",
            batch_name="草稿",
            layout_profile_id="ceb_txn_v1",
            status="ready",
        )
        saved = uc.save_rows(
            job_id,
            [
                {
                    "page_index": 1,
                    "row_index": 0,
                    "cells": {"交易日期": "20240105", "存入金额": "10.00"},
                    "confidence": {"交易日期": 1},
                }
            ],
        )
        self.assertEqual(saved["rows"][0]["cells"]["交易日期"], "20240105")
        header_saved = uc.save_header(job_id, {"客户姓名": "李四"})
        self.assertEqual(header_saved["header"]["客户姓名"], "李四")


if __name__ == "__main__":
    unittest.main()
