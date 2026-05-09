"""Home page of EntityFusion UI."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGridLayout, QLabel, QHBoxLayout, QVBoxLayout, QWidget

from app.resource_path import get_resource_path
from app.widgets.card_button import CardButton


class HomePage(QWidget):
    """Provide product intro and quick entry cards."""

    quick_navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build home page layout and card actions."""
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        hero = QWidget()
        hero.setObjectName("dashboardHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(6)

        title_image_label = QLabel()
        title_image_label.setObjectName("homeTitleImage")
        title_image_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._load_title_image(title_image_label)
        hero_layout.addWidget(title_image_label)

        page_title = QLabel("欢迎使用数据处理工具合集")
        page_title.setObjectName("pageTitle")
        hero_layout.addWidget(page_title)

        subtitle = QLabel("统一处理数据整合、数据脱敏、银行流水分析等场景，提升分析效率。")
        subtitle.setObjectName("homeSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)
        root.addWidget(hero)

        cards_section = QWidget()
        cards_section.setObjectName("dashboardSection")
        cards_layout = QHBoxLayout(cards_section)
        cards_layout.setContentsMargins(12, 12, 12, 12)
        cards_layout.setSpacing(12)
        cards_layout.addWidget(self._build_card("数据整合", "data_integration"))
        cards_layout.addWidget(self._build_card("数据脱敏", "data_desensitization"))
        cards_layout.addWidget(self._build_card("流水分析", "bank_data"))
        cards_layout.addWidget(self._build_card("结果导出", "upload"))
        root.addWidget(cards_section)

        status_section = QWidget()
        status_section.setObjectName("dashboardSection")
        status_layout = QGridLayout(status_section)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setHorizontalSpacing(14)
        status_layout.setVerticalSpacing(10)
        status_layout.addWidget(QLabel("最近文件："), 0, 0)
        status_layout.addWidget(QLabel("请从“文件管理”导入并处理最新数据"), 0, 1)
        status_layout.addWidget(QLabel("系统状态："), 1, 0)
        status_layout.addWidget(QLabel("服务正常"), 1, 1)
        status_layout.addWidget(QLabel("可用模块："), 2, 0)
        status_layout.addWidget(QLabel("数据整合 / 数据脱敏 / 银行流水分析"), 2, 1)
        root.addWidget(status_section)
        root.addStretch(1)

    def _load_title_image(self, title_image_label: QLabel) -> None:
        """Load full-name brand image to replace text title."""
        image_path = get_resource_path("app", "resources", "icons", "quan_ming.png")
        if image_path.exists():
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                title_image_label.setPixmap(
                    pixmap.scaledToHeight(56, Qt.TransformationMode.SmoothTransformation)
                )
                return
        title_image_label.setText("数据处理工具-广东电力开发有限公司")

    def _build_card(self, text: str, route_key: str) -> CardButton:
        """Create one quick jump card."""
        button = CardButton(text)
        button.clicked.connect(lambda checked=False, key=route_key: self.quick_navigate.emit(key))
        return button
