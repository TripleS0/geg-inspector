"""EntityFusion application entry point."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.resource_path import get_resource_path


def load_stylesheet(app: QApplication) -> None:
    """Load and apply the global QSS stylesheet."""
    style_file = get_resource_path("app", "resources", "styles.qss")
    if style_file.exists():
        app.setStyleSheet(style_file.read_text(encoding="utf-8"))


def main() -> int:
    """Start the Qt event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("数据处理工具合集")
    icon_path = get_resource_path("app", "resources", "icons", "logo.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    load_stylesheet(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
