"""Card-style push button used on home page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget


class CardButton(QPushButton):
    """A reusable card-like action button."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        """Create a large card button."""
        super().__init__(text, parent)
        self.setObjectName("cardButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(104)
