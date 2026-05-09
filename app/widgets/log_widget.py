"""Reusable readonly log output widget."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LogWidget(QPlainTextEdit):
    """Provide timestamped append-only logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize log viewer."""
        super().__init__(parent)
        self.setObjectName("logWidget")
        self.setReadOnly(True)
        self.setPlaceholderText("日志输出区域...")

    def append_log(self, message: str) -> None:
        """Append one timestamped log line."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.appendPlainText(f"[{timestamp}] {message}")
