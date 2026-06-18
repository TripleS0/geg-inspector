"""Tests for telecom CDR integration services."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.application.analysis_use_cases import TelecomAnalysisUseCase
from app.application.bootstrap import bootstrap_database
from app.application.import_use_cases import ImportUseCase
from app.services.integration.telecom.analysis_service import TelecomAnalysisFilters, TelecomAnalysisService
from app.services.integration.telecom.carrier_templates import match_carrier_template
from app.services.integration.telecom.phone_utils import is_mobile_phone, normalize_phone
from app.services.shared.db.sqlite_client import SqliteClient


SAMPLE_ROW = {
    "序号": 1,
    "通信记录唯一标识": "cdr-1",
    "通话类型": "VoLTE语音通话",
    "话单类型": "被叫话单",
    "本机号码": "8613609047915",
    "本机IMSI号": "",
    "本机IMEI号": "",
    "本机RAC号": 0,
    "本机LAC号": 0,
    "本机基站ID": "",
    "本机CELLID": "385392734",
    "本机归属运营商": "广东移动",
    "本机通话所在地": "20",
    "对方号码": "8618565124992",
    "对方IMSI号": "",
    "对方IMEI号": "",
    "对方RAC号": "",
    "对方LAC号": "",
    "对方基站ID": "",
    "对方CELLID": "",
    "对方归属运营商": "广东联通",
    "对方通话所在地": "20",
    "对方号码归属地": "20",
    "前转主叫号码": "",
    "呼叫开始时间": "2025-06-20 10:08:03",
    "呼叫时长": 11,
    "是否群内呼叫": "",
    "群组编号": "",
    "群组名称": "",
    "短信发送接收时间": "",
}


class TelecomIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_db = os.environ.get("DATAFUSIONX_DB_PATH")
        os.environ["DATAFUSIONX_DB_PATH"] = str(Path(self._tmp.name) / "telecom.sqlite3")
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

    def _write_sample_workbook(self, rows: list[dict] | None = None) -> str:
        path = Path(self._tmp.name) / "telecom_sample.xlsx"
        df = pd.DataFrame(rows or [SAMPLE_ROW])
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="运营商话单信息")
        return str(path)

    def test_normalize_phone(self) -> None:
        self.assertEqual(normalize_phone("8613609047915"), "13609047915")
        self.assertEqual(normalize_phone("+86 136-0904-7915"), "13609047915")
        self.assertTrue(is_mobile_phone("13609047915"))

    def test_match_carrier_template(self) -> None:
        headers = list(SAMPLE_ROW.keys())
        template = match_carrier_template("运营商话单信息", headers)
        self.assertIsNotNone(template)
        self.assertEqual(template.template_id, "mobile_gd_v1")

    def test_import_and_analysis_peer_ranking(self) -> None:
        second_row = dict(SAMPLE_ROW)
        second_row["序号"] = 2
        second_row["通信记录唯一标识"] = "cdr-2"
        second_row["对方号码"] = "8618501632861"
        second_row["呼叫开始时间"] = "2025-06-20 10:34:35"
        second_row["呼叫时长"] = 0
        file_path = self._write_sample_workbook([SAMPLE_ROW, second_row])

        summary = ImportUseCase(self.client).import_source(
            file_paths=[file_path],
            bank_name="广东移动",
            source_type="telecom",
        )
        self.assertEqual(summary.rows_total, 2)
        self.assertEqual(summary.failed_files, 0)

        result = TelecomAnalysisUseCase(self.client).query_records(summary.import_batch_id)
        self.assertEqual(result["summary"]["record_count"], 2)
        peer_ranking = result["summary"]["peer_ranking"]
        self.assertEqual(len(peer_ranking), 2)
        self.assertEqual(peer_ranking[0]["call_count"], 1)
        self.assertEqual(peer_ranking[0]["local_phone"], "13609047915")

    def test_analysis_filters_local_phone(self) -> None:
        service = TelecomAnalysisService(self.client)
        row = {
            "local_phone_display": "13609047915",
            "local_phone_norm": "13609047915",
            "peer_phone_display": "18565124992",
            "peer_phone_norm": "18565124992",
            "call_type": "VoLTE语音通话",
            "bill_type": "被叫话单",
            "direction": "inbound",
            "local_carrier": "广东移动",
            "peer_carrier": "广东联通",
            "local_location": "20",
            "peer_location": "20",
            "call_time": "2025-06-20 10:08:03",
            "duration_sec": 11,
        }
        self.assertTrue(service._match_filters(row, TelecomAnalysisFilters(local_phone="136")))
        self.assertFalse(service._match_filters(row, TelecomAnalysisFilters(local_phone="999")))

    def test_hourly_distribution(self) -> None:
        service = TelecomAnalysisService(self.client)
        records = [
            {
                "local_phone_display": "13609047915",
                "local_phone_norm": "13609047915",
                "peer_phone_display": "18565124992",
                "peer_phone_norm": "18565124992",
                "call_type": "VoLTE语音通话",
                "bill_type": "被叫话单",
                "direction": "inbound",
                "local_carrier": "广东移动",
                "peer_carrier": "广东联通",
                "local_location": "20",
                "peer_location": "20",
                "call_time": "2025-06-20 10:08:03",
                "duration_sec": 11,
            }
        ]
        summary = service.summarize(records)
        hourly = summary["hourly_distribution"]
        self.assertEqual(len(hourly), 24)
        self.assertEqual(hourly[10]["count"], 1)


if __name__ == "__main__":
    unittest.main()
