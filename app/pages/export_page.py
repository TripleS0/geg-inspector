"""Export page for output path selection and simulation."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget


class ExportPage(QWidget):
    """Provide export path selection and result simulation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build export page user interface."""
        super().__init__(parent)
        self._output_path = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("导出结果")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self.choose_path_button = QPushButton("选择输出路径")
        self.choose_path_button.clicked.connect(self.choose_output_path)
        root.addWidget(self.choose_path_button)

        self.path_label = QLabel("当前路径：未选择")
        self.path_label.setWordWrap(True)
        root.addWidget(self.path_label)

        self.export_button = QPushButton("导出（模拟）")
        self.export_button.clicked.connect(self.simulate_export)
        root.addWidget(self.export_button)

        self.status_label = QLabel("状态：等待导出")
        root.addWidget(self.status_label)
        root.addStretch(1)

    def choose_output_path(self) -> None:
        """Choose output directory and update label."""
        selected = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not selected:
            return
        self._output_path = selected
        self.path_label.setText(f"当前路径：{selected}")
        self.status_label.setText("状态：已选择导出路径")

    def simulate_export(self) -> None:
        """Simulate export behavior and display status."""
        if not self._output_path:
            self.status_label.setText("状态：请先选择输出路径")
            return
        self.status_label.setText("状态：导出完成（模拟）")
