"""Main window composition for EntityFusion."""

from __future__ import annotations

from typing import List

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.navigation import NavigationGroup, NavigationItem, NavigationPanel
from app.pages.desensitization_page import DesensitizationPage
from app.pages.home_page import HomePage
from app.pages.integration_select_page import IntegrationSelectPage
from app.pages.upload_page import UploadPage
from app.router import AppRouter, Route


class MainWindow(QMainWindow):
    """Compose application shell with navigation and pages."""

    def __init__(self) -> None:
        """Initialize shell layout and register all pages."""
        super().__init__()
        self.setWindowTitle("数据处理工具-广东电力开发有限公司")
        self.resize(1460, 900)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.navigation = NavigationPanel(self._build_navigation_groups())
        self.navigation.route_selected.connect(self._handle_route_selected)

        content = QWidget()
        content.setObjectName("appContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 0)
        content_layout.setSpacing(12)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("mainPageStack")
        self.page_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.page_stack, 1)

        self.status_tip = QLabel("EntityFusion UI阶段：仅展示交互流程，不执行数据处理逻辑。")
        self.status_tip.setObjectName("statusTip")
        content_layout.addWidget(self.status_tip)

        root_layout.addWidget(self.navigation)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self.router = AppRouter(self.page_stack)
        self._register_pages()
        self._go_home()

    def _build_navigation_groups(self) -> List[NavigationGroup]:
        """Build grouped menu configuration for easy extension."""
        return [
            NavigationGroup(
                title="数据处理",
                items=[
                    NavigationItem("home", "首页"),
                    NavigationItem("data_integration", "文件管理"),
                    NavigationItem("bank_data", "流水分析"),
                    NavigationItem("data_desensitization", "数据脱敏"),
                    NavigationItem("upload", "结果导出"),
                ],
            ),
            NavigationGroup(
                title="系统工具",
                items=[
                    NavigationItem("other_tools", "日志查看"),
                    NavigationItem("comming_soon", "帮助文档"),
                ],
            ),
        ]

    def _register_pages(self) -> None:
        """Register all page widgets to router."""
        self.home_page = HomePage()
        self.integration_select_page = IntegrationSelectPage()
        self.upload_page = UploadPage()
        self.desensitization_page = DesensitizationPage()
        other_tools_page = self._build_tool_placeholder_page(
            "其他工具",
            "其他工具模块预留。\n后续可接入更多平台能力。",
        )
        coming_soon_page = self._build_coming_soon_page()

        self.home_page.quick_navigate.connect(self._handle_quick_entry)
        self.integration_select_page.source_selected.connect(self._handle_route_selected)
        self.integration_select_page.back_home_requested.connect(self._go_home)
        self.upload_page.back_home_requested.connect(self._go_home)
        self.upload_page.back_to_source_select_requested.connect(
            lambda: self._handle_quick_entry("data_integration")
        )
        self.desensitization_page.back_home_requested.connect(self._go_home)

        self.router.register_page(Route("home", "首页"), self.home_page)
        self.router.register_page(Route("data_integration", "数据整合"), self.integration_select_page)
        self.router.register_page(Route("data_desensitization", "数据脱敏"), self.desensitization_page)
        self.router.register_page(Route("other_tools", "其他"), other_tools_page)
        self.router.register_page(Route("upload", "文件上传"), self.upload_page)
        self.router.register_page(Route("comming_soon", "敬请期待"), coming_soon_page)

        # Data-entry menus currently point to upload page as unified input entry.
        self.router.add_alias("commercial_data", "upload")
        self.router.add_alias("bank_data", "upload")
        self.router.add_alias("other_data", "upload")

    def _build_coming_soon_page(self) -> QWidget:
        """Create placeholder page for future expansion tools."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("扩展功能")
        title.setObjectName("pageTitle")
        desc = QLabel("敬请期待\n后续可接入数据分析、图谱、风控等工具模块。")
        desc.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch(1)
        return widget

    def _build_tool_placeholder_page(self, title_text: str, description_text: str) -> QWidget:
        """Create placeholder page for non-implemented tool modules."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel(title_text)
        title.setObjectName("pageTitle")
        desc = QLabel(description_text)
        desc.setWordWrap(True)
        back_button = self._build_back_home_button()
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(back_button)
        layout.addStretch(1)
        return widget

    def _build_back_home_button(self) -> QPushButton:
        """Create a reusable back-home button."""
        button = QPushButton("返回首页")
        button.setObjectName("secondaryButton")
        button.clicked.connect(self._go_home)
        return button

    def _go_home(self) -> None:
        """Set default active route after startup."""
        self.navigation.set_active("home")
        self.router.switch_to("home")
        self.status_tip.setText("首页总览：请选择工具模块。点击“数据整合”后可选择商务网/银行/其他数据来源。")

    def _handle_route_selected(self, route_key: str) -> None:
        """Switch routed page and update shell status."""
        if route_key == "commercial_data":
            self.upload_page.set_entry_name("商务网数据")
        elif route_key == "bank_data":
            self.upload_page.set_entry_name("银行数据")
        elif route_key == "other_data":
            self.upload_page.set_entry_name("其他数据")
        elif route_key == "upload":
            self.upload_page.set_entry_name("通用上传入口")

        self.router.switch_to(route_key)
        status_map = {
            "home": "首页总览：展示平台可用工具。",
            "data_integration": "数据整合：请先选择来源类型（商务网/银行/其他）。",
            "data_desensitization": "数据脱敏：支持 .xlsx/.xls/.txt 文件脱敏处理。",
            "other_tools": "日志查看：模块预留，后续可扩展。",
            "commercial_data": "商务网数据：请在上传页导入该类文件，可返回首页。",
            "bank_data": "银行数据：请在上传页导入该类文件，可返回首页。",
            "other_data": "其他数据：请在上传页导入该类文件，可返回首页。",
            "upload": "文件上传：支持文件/文件夹选择与拖拽。",
            "comming_soon": "扩展功能：敬请期待，后续可增加分析、图谱、风控等插件模块。",
        }
        self.status_tip.setText(status_map.get(route_key, "EntityFusion"))

    def _handle_quick_entry(self, route_key: str) -> None:
        """Handle home quick cards and sync nav selection."""
        self.navigation.set_active(route_key)
        self._handle_route_selected(route_key)
