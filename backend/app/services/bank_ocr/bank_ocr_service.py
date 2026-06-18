"""Run OCR pipeline for uploaded bank statement images."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.runtime_paths import uploads_dir
from app.services.bank_ocr.draft_repository import BankOcrDraftRepository
from app.services.bank_ocr.layout_profiles import resolve_profile
from app.services.bank_ocr.ocr_engine import read_image_size, recognize_page_table, recognize_page_text
from app.services.bank_ocr.pdf_converter import expand_upload_to_page_images, is_supported_upload
from app.services.bank_ocr.table_parser import (
    parse_header_fields,
    parse_structure_result,
    parse_structure_result_raw,
)
from app.services.shared.db.sqlite_client import SqliteClient


class BankOcrService:
    """Coordinate upload expansion, OCR, and draft persistence."""

    def __init__(self, client: SqliteClient) -> None:
        self._client = client
        self._repo = BankOcrDraftRepository(client)

    def process_upload(
        self,
        *,
        upload_paths: list[str],
        bank_name: str,
        batch_name: str,
        layout_profile_id: str | None = None,
    ) -> dict[str, Any]:
        if not upload_paths:
            raise ValueError("请提供至少一个图片或 PDF 文件")
        profile = resolve_profile(layout_profile_id, bank_name)
        job_id = self._repo.create_job(
            bank_name=bank_name.strip() or profile.bank_display_name,
            batch_name=batch_name.strip(),
            layout_profile_id=profile.profile_id,
        )
        job_dir = uploads_dir() / "bank_ocr" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        page_index = 0
        for upload_path in upload_paths:
            if not is_supported_upload(upload_path):
                raise ValueError(f"不支持的文件：{Path(upload_path).name}")
            source_copy = job_dir / Path(upload_path).name
            shutil.copy2(upload_path, source_copy)
            for image_path in expand_upload_to_page_images(source_copy, job_dir / "pages"):
                page_index += 1
                width, height = read_image_size(image_path)
                self._repo.add_page(
                    job_id=job_id,
                    page_index=page_index,
                    image_path=image_path,
                    width=width,
                    height=height,
                )
        if page_index == 0:
            self._repo.update_job(job_id, status="failed", error_message="未解析到任何页面图片")
            raise ValueError("未解析到任何页面图片")
        return self.run_ocr(job_id)

    def run_ocr(self, job_id: str) -> dict[str, Any]:
        job = self._repo.get_job(job_id)
        if not job:
            raise ValueError("OCR 任务不存在")
        profile = resolve_profile(job.get("layout_profile_id"), job.get("bank_name") or "")
        stored_pages = self._repo.list_pages(job_id)
        if not stored_pages:
            raise ValueError("任务没有可识别的页面")

        header: dict[str, str] = dict(job.get("header") or {})
        draft_rows: list[dict[str, Any]] = []
        global_row_index = 0
        detected_columns: list[str] = []
        for page in stored_pages:
            page_index = int(page["page_index"])
            image_path = str(page["image_path"])
            if page_index == 1 or not any(v for k, v in header.items() if not str(k).startswith("_")):
                page_header = parse_header_fields(recognize_page_text(image_path), profile) or {}
                header.update({k: v for k, v in page_header.items() if v})
            structure = recognize_page_table(image_path)
            columns, rows, confidences = parse_structure_result_raw(structure)
            if len(columns) > len(detected_columns):
                detected_columns = columns
            if not rows:
                profile_rows, profile_conf = parse_structure_result(structure, profile)
                rows, confidences = profile_rows, profile_conf
                if not detected_columns:
                    detected_columns = list(profile.table_columns)
            for cells, confidence in zip(rows, confidences):
                draft_rows.append(
                    {
                        "page_index": page_index,
                        "row_index": global_row_index,
                        "cells": cells,
                        "confidence": confidence,
                        "is_edited": False,
                    }
                )
                global_row_index += 1

        if detected_columns:
            header["_detected_columns"] = detected_columns

        self._repo.replace_draft_rows(job_id, draft_rows)
        self._repo.update_job(
            job_id,
            status="ready",
            page_count=len(stored_pages),
            header_json=header,
            error_message="",
        )
        refreshed = self._repo.get_job(job_id)
        return refreshed or {"job_id": job_id, "status": "ready"}
