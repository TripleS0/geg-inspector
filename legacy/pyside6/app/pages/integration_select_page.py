"""Integration source selection page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.widgets.card_button import CardButton
from app.widgets.zh_message_box import zh_information


class IntegrationSelectPage(QWidget):
    """Show available data-integration source types."""

    source_selected = Signal(str)
    back_home_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build integration source selection view."""
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        section = QWidget()
        section.setObjectName("integrationSection")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(14, 14, 14, 14)
        section_layout.setSpacing(10)

        title = QLabel("数据整合")
        title.setObjectName("pageTitle")
        section_layout.addWidget(title)

        subtitle = QLabel("请选择要导入的数据来源类型。\n其他数据入口暂未开放。")
        subtitle.setObjectName("hintLabel")
        section_layout.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self._build_card("商务网数据", "commercial_data"))
        cards.addWidget(self._build_card("银行数据", "bank_data"))
        cards.addWidget(self._build_card("其他数据", "other_data"))
        section_layout.addLayout(cards)

        back_button = QPushButton("返回首页")
        back_button.setObjectName("secondaryButton")
        back_button.clicked.connect(self.back_home_requested.emit)
        section_layout.addWidget(back_button)
        root.addWidget(section)
        root.addStretch(1)

    def _build_card(self, title: str, route_key: str) -> CardButton:
        """Create one source type card button."""
        button = CardButton(title)
        button.clicked.connect(lambda checked=False, key=route_key: self._on_card_clicked(key))
        return button

    def _on_card_clicked(self, route_key: str) -> None:
        """Handle card click; keep other_data unavailable for now."""
        if route_key == "other_data":
            zh_information(self, "提示", "其他数据入口暂未开放，后续版本再接入。")
            return
        self.source_selected.emit(route_key)
