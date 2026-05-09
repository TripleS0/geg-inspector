"""Data desensitization tool page integrated from legacy project."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.services.desensitization.desensitizer_service import (
    collect_supported_files,
    process_single_file,
)
from app.widgets.file_list_widget import FileListWidget
from app.widgets.log_widget import LogWidget


class _DesensitizeWorker(QObject):
    """Background worker for desensitization batch tasks."""

    log_message = Signal(str)
    progress_changed = Signal(int, int)
    finished = Signal(int, int)

    def __init__(self, files: list[Path]) -> None:
        """Store files for threaded processing."""
        super().__init__()
        self._files = files

    def run(self) -> None:
        """Execute batch processing in worker thread."""
        total = len(self._files)
        success_count = 0
        finished_count = 0
        max_workers = min(4, max(1, total))
        self.log_message.emit(f"开始处理，共 {total} 个文件。")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(process_single_file, f): f for f in self._files}
            for future in concurrent.futures.as_completed(future_map):
                source_file = future_map[future]
                finished_count += 1
                try:
                    in_file, out_file = future.result()
                    success_count += 1
                    self.log_message.emit(f"[成功] {in_file} -> {out_file}")
                except Exception as err:
                    self.log_message.emit(f"[失败] {source_file}，错误：{err}")
                self.progress_changed.emit(finished_count, total)

        self.log_message.emit(f"任务结束：成功 {success_count}/{total}")
        self.finished.emit(success_count, total)


class DesensitizationPage(QWidget):
    """Provide full desensitization UI and processing workflow."""

    back_home_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build page widgets and connect events."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _DesensitizeWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel("数据脱敏")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        desc = QLabel("支持 .xlsx / .xls / .txt 文件脱敏，输出到原目录下“脱敏结果”文件夹。")
        desc.setObjectName("hintLabel")
        desc.setWordWrap(True)
        root.addWidget(desc)

        tool_card = QWidget()
        tool_card.setObjectName("desensToolbar")
        tool_layout = QVBoxLayout(tool_card)
        tool_layout.setContentsMargins(12, 12, 12, 12)
        tool_layout.setSpacing(8)

        button_row = QHBoxLayout()
        self.select_file_button = QPushButton("选择文件")
        self.select_folder_button = QPushButton("选择文件夹")
        self.start_button = QPushButton("开始脱敏")
        self.back_button = QPushButton("返回首页")
        self.back_button.setObjectName("secondaryButton")
        button_row.addWidget(self.select_file_button)
        button_row.addWidget(self.select_folder_button)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.back_button)
        button_row.addStretch(1)
        tool_layout.addLayout(button_row)
        root.addWidget(tool_card)

        self.file_list_widget = FileListWidget()
        root.addWidget(self.file_list_widget, 1)

        status_card = QWidget()
        status_card.setObjectName("desensStatusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("状态：等待选择文件")
        status_layout.addWidget(self.status_label)
        root.addWidget(status_card)

        self.log_widget = LogWidget()
        root.addWidget(self.log_widget, 1)

        self.select_file_button.clicked.connect(self.select_files)
        self.select_folder_button.clicked.connect(self.select_folder)
        self.start_button.clicked.connect(self.start_processing)
        self.back_button.clicked.connect(self.back_home_requested.emit)

    def select_files(self) -> None:
        """Choose input files and append to list."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择脱敏文件",
            "",
            "支持文件 (*.xlsx *.xls *.txt);;All Files (*.*)",
        )
        if files:
            self.file_list_widget.add_files(files)

    def select_folder(self) -> None:
        """Choose input folder and append supported files recursively."""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not folder:
            return
        files = collect_supported_files([Path(folder)])
        self.file_list_widget.add_files([str(file) for file in files])

    def start_processing(self) -> None:
        """Start threaded desensitization task."""
        if self._thread is not None and self._thread.isRunning():
            self.log_widget.append_log("已有任务在运行，请稍候。")
            return

        files = self._collect_files_from_list()
        files = collect_supported_files(files)
        if not files:
            self.log_widget.append_log("未找到可处理的 .xlsx / .xls / .txt 文件。")
            self.status_label.setText("状态：未选择有效文件")
            return

        self.progress_bar.setValue(0)
        self.status_label.setText(f"状态：准备处理 {len(files)} 个文件")
        self.start_button.setEnabled(False)

        self._thread = QThread(self)
        self._worker = _DesensitizeWorker(files)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.log_message.connect(self.log_widget.append_log)
        self._worker.progress_changed.connect(self._on_progress_changed)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _collect_files_from_list(self) -> list[Path]:
        """Read current list widget entries as paths."""
        files: list[Path] = []
        for index in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(index)
            if item is None:
                continue
            files.append(Path(item.text()))
        return files

    def _on_progress_changed(self, finished_count: int, total: int) -> None:
        """Update progress bar and status."""
        ratio = int((finished_count / max(total, 1)) * 100)
        self.progress_bar.setValue(ratio)
        self.status_label.setText(f"状态：处理中 {finished_count}/{total}")

    def _on_finished(self, success_count: int, total: int) -> None:
        """Handle worker completion and reset ui state."""
        self.status_label.setText(f"状态：处理完成，成功 {success_count}/{total}")
        self.progress_bar.setValue(100 if total > 0 else 0)
        self.start_button.setEnabled(True)
