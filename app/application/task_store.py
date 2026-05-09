"""SQLite-backed task status store for local API jobs."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.application.bootstrap import bootstrap_database
from app.services.shared.db.sqlite_client import SqliteClient


class TaskStore:
    """Persist background task state for polling from the Web UI."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def create(self, task_type: str, message: str = "等待执行") -> str:
        """Create a task row and return its id."""
        task_id = str(uuid4())
        self._client.execute(
            """
            INSERT INTO ana_task(task_id, task_type, status, progress, message)
            VALUES (?, ?, 'pending', 0, ?);
            """,
            (task_id, task_type, message),
        )
        return task_id

    def update(
        self,
        task_id: str,
        *,
        status: str,
        progress: int,
        message: str,
        result: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> None:
        """Update task status."""
        self._client.execute(
            """
            UPDATE ana_task
            SET status=?, progress=?, message=?, result_json=?, error_message=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE task_id=?;
            """,
            (
                status,
                max(0, min(int(progress), 100)),
                message,
                json.dumps(result or {}, ensure_ascii=False),
                error_message,
                task_id,
            ),
        )

    def get(self, task_id: str) -> dict[str, Any]:
        """Return one task as a dict."""
        rows = self._client.query_all(
            """
            SELECT task_id, task_type, status, progress, message, result_json,
                   error_message, created_at, updated_at
            FROM ana_task
            WHERE task_id=?;
            """,
            (task_id,),
        )
        if not rows:
            raise KeyError(task_id)
        row = rows[0]
        try:
            result = json.loads(str(row[5] or "{}"))
        except json.JSONDecodeError:
            result = {}
        return {
            "task_id": row[0],
            "task_type": row[1],
            "status": row[2],
            "progress": row[3],
            "message": row[4],
            "result": result,
            "error_message": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }
