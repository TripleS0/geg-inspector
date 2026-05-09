"""Process page with simulated progress and logs."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QPushButton, QProgressBar, QVBoxLayout, QWidget

from app.widgets.log_widget import LogWidget


class ProcessPage(QWidget):
    """Display progress status and simulation logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build process page widgets and behavior."""
        super().__init__(parent)
        self._progress_value = 0
        self._timer = QTimer(self)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._advance_progress)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("处理进度")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self.status_label = QLabel("状态：等待开始")
        root.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        self.start_button = QPushButton("模拟处理")
        self.start_button.clicked.connect(self.start_simulation)
        root.addWidget(self.start_button)

        self.log_widget = LogWidget()
        root.addWidget(self.log_widget, 1)

    def start_simulation(self) -> None:
        """Start a fake process task for UI demonstration."""
        self._progress_value = 0
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：处理中...")
        self.log_widget.append_log("开始模拟处理任务。")
        self.start_button.setEnabled(False)
        self._timer.start()

    def _advance_progress(self) -> None:
        """Tick progress and append milestone logs."""
        self._progress_value = min(self._progress_value + 8, 100)
        self.progress_bar.setValue(self._progress_value)

        if self._progress_value in {24, 56, 80}:
            self.log_widget.append_log(f"处理进度更新：{self._progress_value}%")

        if self._progress_value >= 100:
            self._timer.stop()
            self.status_label.setText("状态：处理完成（模拟）")
            self.log_widget.append_log("处理结束，结果可导出。")
            self.start_button.setEnabled(True)
