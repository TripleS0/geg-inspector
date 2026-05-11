"""File list widget for uploaded input files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QWidget


class FileListWidget(QListWidget):
    """Display selected files and avoid duplicate entries."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize list widget style and behavior."""
        super().__init__(parent)
        self.setObjectName("fileListWidget")
        self.setAlternatingRowColors(True)
        self._placeholder_text = ""

    def add_file(self, file_path: str | Path) -> None:
        """Add one file path to list if not already present."""
        normalized = str(Path(file_path).resolve())
        if self._contains_path(normalized):
            return
        self.addItem(QListWidgetItem(normalized))

    def add_files(self, file_paths: Iterable[str | Path]) -> None:
        """Add multiple file paths."""
        for file_path in file_paths:
            self.add_file(file_path)

    def _contains_path(self, file_path: str) -> bool:
        """Check whether list already includes the file path."""
        for index in range(self.count()):
            item = self.item(index)
            if item and item.text() == file_path:
                return True
        return False

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        """Set custom placeholder text shown when list is empty."""
        self._placeholder_text = text
        self.viewport().update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Draw default list, then placeholder if empty."""
        super().paintEvent(event)
        if self.count() > 0 or not self._placeholder_text:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor("#5b6b85"))
        painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder_text)
        painter.end()
