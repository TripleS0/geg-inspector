"""Application use cases for bank OCR import."""

from __future__ import annotations

from typing import Any

from app.application.bootstrap import bootstrap_database
from app.services.bank_ocr.bank_ocr_service import BankOcrService
from app.services.bank_ocr.commit_service import BankOcrCommitService
from app.services.bank_ocr.draft_repository import BankOcrDraftRepository
from app.services.bank_ocr.layout_profiles import LAYOUT_PROFILES
from app.services.shared.db.sqlite_client import SqliteClient


class BankOcrUseCase:
    """Orchestrate OCR upload, proofreading, and commit."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)
        self._repo = BankOcrDraftRepository(self._client)
        self._ocr = BankOcrService(self._client)
        self._commit = BankOcrCommitService(self._client)

    def process_upload(
        self,
        *,
        upload_paths: list[str],
        bank_name: str,
        batch_name: str,
        layout_profile_id: str | None = None,
    ) -> dict[str, Any]:
        job = self._ocr.process_upload(
            upload_paths=upload_paths,
            bank_name=bank_name,
            batch_name=batch_name,
            layout_profile_id=layout_profile_id,
        )
        return self._public_job(job)

    def list_jobs(self, *, status: str | None = None) -> dict[str, Any]:
        jobs = self._repo.list_jobs(status=status)
        return {"items": jobs}

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self._repo.get_job(job_id)
        if not job:
            raise ValueError("OCR 任务不存在")
        return self._public_job(job)

    def save_rows(self, job_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        job = self._repo.get_job(job_id)
        if not job:
            raise ValueError("OCR 任务不存在")
        if job["status"] == "committed":
            raise ValueError("已录入任务不可再修改")
        self._repo.save_draft_rows(job_id, rows)
        return self.get_job(job_id)

    def save_header(self, job_id: str, header: dict[str, Any]) -> dict[str, Any]:
        job = self._repo.get_job(job_id)
        if not job:
            raise ValueError("OCR 任务不存在")
        if job["status"] == "committed":
            raise ValueError("已录入任务不可再修改")
        existing = dict(job.get("header") or {})
        merged = dict(header)
        if "_detected_columns" in existing and "_detected_columns" not in merged:
            merged["_detected_columns"] = existing["_detected_columns"]
        self._repo.update_job(job_id, header_json=merged)
        return self.get_job(job_id)

    def commit(self, job_id: str) -> dict[str, Any]:
        return self._commit.commit_job(job_id)

    def delete_job(self, job_id: str) -> dict[str, Any]:
        job = self._repo.get_job(job_id)
        if not job:
            raise ValueError("OCR 任务不存在")
        if job["status"] == "committed":
            raise ValueError("已录入任务不可删除")
        self._repo.delete_job(job_id)
        return {"job_id": job_id, "deleted": True}

    def list_profiles(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "profile_id": profile.profile_id,
                    "bank_display_name": profile.bank_display_name,
                    "table_columns": list(profile.table_columns),
                    "header_fields": list(profile.header_fields),
                }
                for profile in LAYOUT_PROFILES.values()
            ]
        }

    @staticmethod
    def _public_job(job: dict[str, Any]) -> dict[str, Any]:
        profile_id = job.get("layout_profile_id")
        profile = LAYOUT_PROFILES.get(str(profile_id or ""))
        header = dict(job.get("header") or {})
        detected_columns = header.get("_detected_columns")
        if isinstance(detected_columns, list) and detected_columns:
            table_columns = [str(column) for column in detected_columns]
        elif profile:
            table_columns = list(profile.table_columns)
        else:
            table_columns = []
        public_header = {k: v for k, v in header.items() if not str(k).startswith("_")}
        header_fields = list(profile.header_fields) if profile else []
        for key in public_header:
            if key not in header_fields:
                header_fields.append(str(key))
        return {
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "bank_name": job.get("bank_name"),
            "batch_name": job.get("batch_name"),
            "layout_profile_id": profile_id,
            "table_columns": table_columns,
            "header_fields": header_fields,
            "page_count": job.get("page_count", 0),
            "header": public_header,
            "error_message": job.get("error_message") or "",
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "commit_mode": "raw",
            "pages": [
                {
                    "page_id": page.get("page_id"),
                    "page_index": page.get("page_index"),
                    "ocr_status": page.get("ocr_status"),
                    "width": page.get("width"),
                    "height": page.get("height"),
                }
                for page in (job.get("pages") or [])
            ],
            "rows": job.get("rows") or [],
        }
