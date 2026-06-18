"""Commit proofread OCR rows into the bank raw import pipeline (no auto-standardization)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook

from app.application.import_use_cases import ImportUseCase
from app.runtime_paths import exports_dir
from app.services.bank_ocr.draft_repository import BankOcrDraftRepository
from app.services.bank_ocr.layout_profiles import LayoutProfile, resolve_profile
from app.services.shared.db.sqlite_client import SqliteClient

_META_COLUMNS_KEY = "_detected_columns"


class BankOcrCommitService:
    """Generate temporary Excel with raw OCR columns and ingest without mapping."""

    def __init__(self, client: SqliteClient) -> None:
        self._client = client
        self._repo = BankOcrDraftRepository(client)

    def commit_job(self, job_id: str) -> dict[str, Any]:
        job = self._repo.get_job(job_id)
        if not job:
            raise ValueError("OCR 任务不存在")
        if job["status"] == "committed":
            raise ValueError("该 OCR 任务已录入，请勿重复提交")
        if job["status"] not in {"ready", "ocr_running"}:
            raise ValueError(f"当前状态不可录入：{job['status']}")
        rows = job.get("rows") or []
        if not rows:
            raise ValueError("没有可录入的交易行，请先完成 OCR 校对")
        profile = resolve_profile(job.get("layout_profile_id"), job.get("bank_name") or "")
        header = dict(job.get("header") or {})
        columns = self._resolve_columns(header, rows, profile)
        export_rows = self._build_raw_export_rows(rows, header, columns)
        self._validate_raw_export_rows(export_rows, columns)
        xlsx_path = self._write_excel(job_id, columns, export_rows)
        summary = ImportUseCase(self._client).import_source(
            file_paths=[str(xlsx_path)],
            bank_name=str(job.get("bank_name") or profile.bank_display_name),
            source_type="bank",
            batch_name=str(job.get("batch_name") or "").strip() or None,
            standardize=False,
        )
        self._repo.update_job(job_id, status="committed")
        result = summary.to_dict()
        result["job_id"] = job_id
        result["xlsx_path"] = str(xlsx_path)
        result["commit_mode"] = "raw"
        result["column_count"] = len(columns)
        return result

    def _resolve_columns(
        self,
        header: dict[str, Any],
        rows: list[dict[str, Any]],
        profile: LayoutProfile,
    ) -> list[str]:
        detected = header.get(_META_COLUMNS_KEY)
        if isinstance(detected, list) and detected:
            return [str(column) for column in detected]
        from_rows: list[str] = []
        for row in rows:
            for key in (row.get("cells") or {}).keys():
                if key not in from_rows:
                    from_rows.append(str(key))
        if from_rows:
            return from_rows
        return list(profile.table_columns)

    def _build_raw_export_rows(
        self,
        rows: list[dict[str, Any]],
        header: dict[str, Any],
        columns: list[str],
    ) -> list[dict[str, str]]:
        export_rows: list[dict[str, str]] = []
        for row in rows:
            cells = dict(row.get("cells") or {})
            export_row = {column: str(cells.get(column) or "").strip() for column in columns}
            for meta_key, meta_value in header.items():
                if meta_key.startswith("_") or not meta_value:
                    continue
                if meta_key not in export_row or not export_row.get(meta_key):
                    export_row[meta_key] = str(meta_value).strip()
            if any(export_row.values()):
                export_rows.append(export_row)
        return export_rows

    def _validate_raw_export_rows(self, rows: list[dict[str, str]], columns: list[str]) -> None:
        if not rows:
            raise ValueError("校对结果为空，无法录入")
        if not columns:
            raise ValueError("未识别到任何列名")

    def _write_excel(self, job_id: str, columns: list[str], rows: list[dict[str, str]]) -> Path:
        out_dir = exports_dir() / "bank_ocr"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{job_id}.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "交易明细"
        sheet.append(columns)
        for row in rows:
            sheet.append([row.get(column, "") for column in columns])
        workbook.save(path)
        return path
