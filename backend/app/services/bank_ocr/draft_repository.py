"""SQLite persistence for bank OCR draft jobs."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.services.shared.db.sqlite_client import SqliteClient


class BankOcrDraftRepository:
    """CRUD helpers for OCR draft tables."""

    def __init__(self, client: SqliteClient) -> None:
        self._client = client

    def create_job(
        self,
        *,
        bank_name: str,
        batch_name: str,
        layout_profile_id: str,
        status: str = "ocr_running",
    ) -> str:
        job_id = str(uuid.uuid4())
        self._client.execute(
            """
            INSERT INTO meta_ocr_job(
                job_id, status, bank_name, batch_name, layout_profile_id,
                page_count, header_json, error_message
            ) VALUES (?, ?, ?, ?, ?, 0, ?, '');
            """,
            (job_id, status, bank_name, batch_name, layout_profile_id, json.dumps({}, ensure_ascii=False)),
        )
        return job_id

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        page_count: int | None = None,
        header_json: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        fields: list[str] = ["updated_at=CURRENT_TIMESTAMP"]
        params: list[Any] = []
        if status is not None:
            fields.append("status=?")
            params.append(status)
        if page_count is not None:
            fields.append("page_count=?")
            params.append(page_count)
        if header_json is not None:
            fields.append("header_json=?")
            params.append(json.dumps(header_json, ensure_ascii=False))
        if error_message is not None:
            fields.append("error_message=?")
            params.append(error_message)
        params.append(job_id)
        self._client.execute(
            f"UPDATE meta_ocr_job SET {', '.join(fields)} WHERE job_id=?;",
            tuple(params),
        )

    def add_page(
        self,
        *,
        job_id: str,
        page_index: int,
        image_path: str,
        width: int,
        height: int,
        ocr_status: str = "ready",
    ) -> int:
        self._client.execute(
            """
            INSERT INTO meta_ocr_page(job_id, page_index, image_path, ocr_status, width, height)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (job_id, page_index, image_path, ocr_status, width, height),
        )
        rows = self._client.query_all("SELECT last_insert_rowid();")
        return int(rows[0][0])

    def replace_draft_rows(
        self,
        job_id: str,
        rows: list[dict[str, Any]],
    ) -> None:
        self._client.execute("DELETE FROM meta_ocr_draft_row WHERE job_id=?;", (job_id,))
        if not rows:
            return
        payload = [
            (
                job_id,
                int(row.get("page_index", 0)),
                int(row.get("row_index", index)),
                json.dumps(row.get("cells") or {}, ensure_ascii=False),
                json.dumps(row.get("confidence") or {}, ensure_ascii=False),
                1 if row.get("is_edited") else 0,
            )
            for index, row in enumerate(rows)
        ]
        self._client.executemany(
            """
            INSERT INTO meta_ocr_draft_row(
                job_id, page_index, row_index, cells_json, confidence_json, is_edited
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            payload,
        )

    def save_draft_rows(
        self,
        job_id: str,
        rows: list[dict[str, Any]],
        *,
        mark_edited: bool = True,
    ) -> None:
        self.replace_draft_rows(
            job_id,
            [
                {
                    **row,
                    "is_edited": True if mark_edited else bool(row.get("is_edited")),
                }
                for row in rows
            ],
        )

    def delete_job(self, job_id: str) -> None:
        self._client.execute("DELETE FROM meta_ocr_draft_row WHERE job_id=?;", (job_id,))
        self._client.execute("DELETE FROM meta_ocr_page WHERE job_id=?;", (job_id,))
        self._client.execute("DELETE FROM meta_ocr_job WHERE job_id=?;", (job_id,))

    def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if status:
            rows = self._client.query_all(
                """
                SELECT job_id, status, bank_name, batch_name, layout_profile_id,
                       page_count, header_json, error_message, created_at, updated_at
                FROM meta_ocr_job
                WHERE status=?
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (status, limit),
            )
        else:
            rows = self._client.query_all(
                """
                SELECT job_id, status, bank_name, batch_name, layout_profile_id,
                       page_count, header_json, error_message, created_at, updated_at
                FROM meta_ocr_job
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
        return [self._job_row_to_dict(row) for row in rows]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        rows = self._client.query_all(
            """
            SELECT job_id, status, bank_name, batch_name, layout_profile_id,
                   page_count, header_json, error_message, created_at, updated_at
            FROM meta_ocr_job
            WHERE job_id=?;
            """,
            (job_id,),
        )
        if not rows:
            return None
        job = self._job_row_to_dict(rows[0])
        job["pages"] = self.list_pages(job_id)
        job["rows"] = self.list_draft_rows(job_id)
        return job

    def list_pages(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._client.query_all(
            """
            SELECT page_id, page_index, image_path, ocr_status, width, height
            FROM meta_ocr_page
            WHERE job_id=?
            ORDER BY page_index ASC;
            """,
            (job_id,),
        )
        return [
            {
                "page_id": row[0],
                "page_index": row[1],
                "image_path": row[2],
                "ocr_status": row[3],
                "width": row[4],
                "height": row[5],
            }
            for row in rows
        ]

    def list_draft_rows(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._client.query_all(
            """
            SELECT row_id, page_index, row_index, cells_json, confidence_json, is_edited
            FROM meta_ocr_draft_row
            WHERE job_id=?
            ORDER BY page_index ASC, row_index ASC;
            """,
            (job_id,),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                cells = json.loads(str(row[3] or "{}"))
            except json.JSONDecodeError:
                cells = {}
            try:
                confidence = json.loads(str(row[4] or "{}"))
            except json.JSONDecodeError:
                confidence = {}
            result.append(
                {
                    "row_id": row[0],
                    "page_index": row[1],
                    "row_index": row[2],
                    "cells": cells,
                    "confidence": confidence,
                    "is_edited": bool(row[5]),
                }
            )
        return result

    def get_page_image_path(self, job_id: str, page_index: int) -> str | None:
        rows = self._client.query_all(
            """
            SELECT image_path
            FROM meta_ocr_page
            WHERE job_id=? AND page_index=?;
            """,
            (job_id, page_index),
        )
        if not rows:
            return None
        return str(rows[0][0])

    @staticmethod
    def _job_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        try:
            header = json.loads(str(row[6] or "{}"))
        except json.JSONDecodeError:
            header = {}
        return {
            "job_id": row[0],
            "status": row[1],
            "bank_name": row[2],
            "batch_name": row[3],
            "layout_profile_id": row[4],
            "page_count": row[5],
            "header": header,
            "error_message": row[7] or "",
            "created_at": row[8],
            "updated_at": row[9],
        }
