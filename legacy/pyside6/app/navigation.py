"""Left navigation panel for platform-style menu groups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.resource_path import get_resource_path


@dataclass(frozen=True)
class NavigationItem:
    """Menu item metadata for one route."""

    route_key: str
    label: str


@dataclass(frozen=True)
class NavigationGroup:
    """Menu group metadata for grouped rendering."""

    title: str
    items: List[NavigationItem]


class NavigationPanel(QFrame):
    """Render grouped navigation and expose route selection signal."""

    route_selected = Signal(str)

    def __init__(self, groups: Iterable[NavigationGroup], parent: QWidget | None = None) -> None:
        """Build the navigation menu from group configuration."""
        super().__init__(parent)
        self.setObjectName("navigationPanel")
        self.setFixedWidth(262)
        self._buttons: dict[str, QPushButton] = {}
        self._active_route: str | None = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 14, 12, 10)
        root_layout.setSpacing(12)

        brand_row = QWidget()
        brand_row.setObjectName("navigationBrandRow")
        brand_layout = QHBoxLayout(brand_row)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)

        logo_label = QLabel()
        logo_label.setObjectName("navigationLogo")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._load_nav_logo(logo_label)
        brand_layout.addWidget(logo_label)

        title = QLabel("数据处理工具合集")
        title.setObjectName("navigationTitle")
        subtitle = QLabel("整合 · 脱敏 · 分析")
        subtitle.setObjectName("navigationSubtitle")

        title_column = QWidget()
        title_layout = QVBoxLayout(title_column)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        title_layout.addWidget(subtitle)
        title_layout.addWidget(title)

        brand_layout.addWidget(title_column, 1)
        root_layout.addWidget(brand_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        scroll_layout = QVBoxLayout(container)
        scroll_layout.setContentsMargins(0, 8, 0, 8)
        scroll_layout.setSpacing(12)

        for group in groups:
            group_widget = self._build_group(group)
            scroll_layout.addWidget(group_widget)

        scroll_layout.addStretch(1)
        scroll.setWidget(container)
        root_layout.addWidget(scroll)

        footer = QLabel("当前用户：admin")
        footer.setObjectName("navigationFooter")
        root_layout.addWidget(footer)

    def _load_nav_logo(self, logo_label: QLabel) -> None:
        """Load navigation logo from resources/icons."""
        logo_path = get_resource_path("app", "resources", "icons", "logo.png")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo_label.setPixmap(
                    pixmap.scaledToHeight(34, Qt.TransformationMode.SmoothTransformation)
                )
                return
        logo_label.setText("LOGO")

    def _build_group(self, group: NavigationGroup) -> QWidget:
        """Create one visual navigation section."""
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel(group.title)
        title.setObjectName("navigationGroupTitle")
        layout.addWidget(title)

        for item in group.items:
            button = QPushButton(item.label)
            button.setObjectName("navigationButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, key=item.route_key: self._on_item_clicked(key))
            self._buttons[item.route_key] = button
            layout.addWidget(button)

        return wrapper

    def _on_item_clicked(self, route_key: str) -> None:
        """Handle internal click and forward route key."""
        self.set_active(route_key)
        self.route_selected.emit(route_key)

    def set_active(self, route_key: str) -> None:
        """Update selected style state for navigation buttons."""
        if self._active_route == route_key:
            return
        for key, button in self._buttons.items():
            button.setChecked(key == route_key)
        self._active_route = route_key
