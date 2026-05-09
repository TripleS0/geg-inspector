"""Upload page for file and folder selection."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.integration.common.bootstrap import run_bootstrap
from app.services.integration.factory import get_integration_bundle
from app.services.shared.db.sqlite_client import SqliteClient
from app.widgets.bank_filter_dialog import BankFilterDialog
from app.widgets.commercial_risk_dialog import CommercialRiskDialog
from app.widgets.db_browser_dialog import DbBrowserDialog
from app.widgets.file_list_widget import FileListWidget
from app.widgets.log_widget import LogWidget
from app.widgets.zh_message_box import zh_critical, zh_information


class _AutoPipelineWorker(QObject):
    """Background worker: bootstrap -> ingest -> optional standardize."""

    log_message = Signal(str)
    progress_changed = Signal(int)
    status_message = Signal(str)
    finished_ok = Signal(str, str)
    failed = Signal(str)

    def __init__(self, excel_files: list[str], bank_name: str, source_type: str) -> None:
        super().__init__()
        self._excel_files = excel_files
        self._bank_name = bank_name
        self._source_type = source_type

    def run(self) -> None:
        """Execute pipeline in worker thread."""
        try:
            self.status_message.emit("状态：准备处理（校验环境）...")
            self.progress_changed.emit(5)
            if self._source_type == "commercial":
                self.log_message.emit("已启动自动处理流程：初始化数据库 -> 入库（商务网） -> 可导出。")
            else:
                self.log_message.emit("已启动自动处理流程：初始化数据库 -> 入库 -> 标准化。")

            client = SqliteClient()
            self.status_message.emit("状态：处理中（初始化数据库结构）...")
            self.progress_changed.emit(15)
            run_bootstrap(client)
            self.log_message.emit("数据库检查完成。")
            self.progress_changed.emit(28)

            self.status_message.emit(f"状态：处理中（入库：{self._bank_name}）...")
            self.progress_changed.emit(40)
            bundle = get_integration_bundle(self._source_type)
            ingest_service = bundle.ingest_cls()
            ingest_result = ingest_service.ingest_files(
                self._excel_files, self._bank_name, self._source_type
            )
            batch_id = ingest_result.import_batch_id
            self.log_message.emit(
                f"入库完成：batch={ingest_result.import_batch_id}，sheet={ingest_result.sheets_total}，"
                f"行数={ingest_result.rows_total}，失败文件={ingest_result.failed_files}"
            )
            self.progress_changed.emit(68)

            if self._source_type == "commercial":
                self.log_message.emit(
                    "商务网来源：已执行头信息提取 + 明细展开 + 基础信息补全，跳过银行标准化写入。"
                )
                self.progress_changed.emit(88)
            else:
                self.status_message.emit("状态：处理中（银行标准化）...")
                self.progress_changed.emit(78)
                mapping_service = bundle.mapping_cls()
                count = mapping_service.standardize_batch(batch_id)
                self.log_message.emit(f"标准化完成：写入标准层 {count} 行。")
                self.progress_changed.emit(90)

            self.status_message.emit("状态：处理完成，正在收尾...")
            self.progress_changed.emit(97)
            self.finished_ok.emit(batch_id, self._source_type)
        except Exception as err:
            self.failed.emit(str(err))


class _EnterpriseImportWorker(QObject):
    """Background: bootstrap + Qichacha enterprise xlsx ingest."""

    log_message = Signal(str)
    progress_changed = Signal(int)
    status_message = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, excel_files: list[str]) -> None:
        super().__init__()
        self._excel_files = excel_files

    def run(self) -> None:
        try:
            from app.services.integration.commercial.ic_ingest_service import EnterpriseProfileIngestService

            self.status_message.emit("状态：导入工商数据（初始化库表）...")
            self.progress_changed.emit(10)
            client = SqliteClient()
            run_bootstrap(client)
            self.log_message.emit("数据库检查完成，开始写入企业主数据…")
            self.progress_changed.emit(40)
            svc = EnterpriseProfileIngestService(client)
            result = svc.ingest_files(self._excel_files)
            self.log_message.emit(
                f"工商入库完成：batch={result.import_batch_id}，写入行={result.rows_total}，"
                f"失败文件={result.failed_files}/{result.files_total}"
            )
            self.progress_changed.emit(100)
            self.status_message.emit("状态：工商导入完成")
            self.finished_ok.emit(result.import_batch_id)
        except Exception as err:
            self.failed.emit(str(err))


class _ExportBatchWorker(QObject):
    """Background worker: write merged xlsx for one batch."""

    log_message = Signal(str)
    progress_changed = Signal(int)
    status_message = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, import_batch_id: str, source_type: str, target_path: str) -> None:
        super().__init__()
        self._import_batch_id = import_batch_id
        self._source_type = source_type
        self._target_path = target_path

    def run(self) -> None:
        """Export batch to xlsx in worker thread."""
        try:
            self.status_message.emit("状态：正在导出 Excel...")
            self.progress_changed.emit(92)
            bundle = get_integration_bundle(self._source_type)
            service = bundle.export_cls()
            self.log_message.emit(service.export_basis_description())
            output = service.export_batch_to_xlsx(self._import_batch_id, self._target_path)
            self.progress_changed.emit(100)
            self.status_message.emit("状态：导出完成")
            self.finished_ok.emit(output)
        except Exception as err:
            self.failed.emit(str(err))


class UploadPage(QWidget):
    """Provide upload entry from files and folders."""

    back_home_requested = Signal()
    back_to_source_select_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build upload page UI."""
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._entry_name = "通用数据"
        self._last_batch_id = ""
        self._last_source_type = "other"
        self._pipeline_mode = "process_only"
        self._pipeline_thread: QThread | None = None
        self._pipeline_worker: _AutoPipelineWorker | None = None
        self._export_thread: QThread | None = None
        self._export_worker: _ExportBatchWorker | None = None
        self._enterprise_thread: QThread | None = None
        self._enterprise_worker: _EnterpriseImportWorker | None = None
        self._last_enterprise_batch_id = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel("文件上传")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self.entry_label = QLabel("当前入口：通用数据")
        self.entry_label.setObjectName("entryLabel")
        root.addWidget(self.entry_label)

        toolbar_card = QWidget()
        toolbar_card.setObjectName("uploadToolbar")
        toolbar_layout = QVBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(12, 12, 12, 12)
        toolbar_layout.setSpacing(10)

        self.back_button = QPushButton("返回")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.setVisible(False)
        self.back_button.clicked.connect(self.back_to_source_select_requested.emit)
        toolbar_layout.addWidget(self.back_button)

        button_row = QHBoxLayout()
        self.select_file_button = QPushButton("选择文件")
        self.select_folder_button = QPushButton("选择文件夹")
        self.clear_files_button = QPushButton("清空当前列表")
        self.clear_files_button.setObjectName("secondaryButton")
        self.process_button = QPushButton("处理当前数据")
        button_row.addWidget(self.select_file_button)
        button_row.addWidget(self.select_folder_button)
        button_row.addWidget(self.clear_files_button)
        button_row.addWidget(self.process_button)
        self.export_button = QPushButton("导出全字段合并")
        self.export_button.setToolTip(
            "导出 .xlsx：银行数据为多工作表（全字段合并、细则_双方往来、个人_银行明细、个人_银行统计）。"
            "商务网导出含「全字段合并」与「中标情况统计」；具体以导出日志说明为准。"
        )
        self.browse_db_button = QPushButton("查看数据")
        self.browse_db_button.setToolTip(
            "查看已入库数据的预览界面。"
        )
        self.import_enterprise_button = QPushButton("导入工商数据")
        self.import_enterprise_button.setToolTip("导入企查查等导出的企业工商信息 .xlsx/.xls（与商务网中标文件分开选择）。")
        self.import_enterprise_button.setVisible(False)
        self.risk_analysis_button = QPushButton("风险分析")
        self.risk_analysis_button.setToolTip("结合工商库与当前商务网批次进行风险规则分析。")
        self.risk_analysis_button.setVisible(False)
        button_row.addWidget(self.export_button)
        self.filter_button = QPushButton("筛选分析")
        self.filter_button.setObjectName("secondaryButton")
        self.filter_button.setToolTip("处理完成后打开银行筛选分析窗口。")
        button_row.addWidget(self.filter_button)
        button_row.addWidget(self.import_enterprise_button)
        button_row.addWidget(self.risk_analysis_button)
        button_row.addWidget(self.browse_db_button)
        button_row.addStretch(1)
        toolbar_layout.addLayout(button_row)
        root.addWidget(toolbar_card)

        self.file_list_widget = FileListWidget()
        self.file_list_widget.setPlaceholderText("支持拖入文件 / 文件夹到此区域。")
        root.addWidget(self.file_list_widget, 1)

        status_card = QWidget()
        status_card.setObjectName("uploadStatusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)

        self.batch_info_label = QLabel("最近处理批次：无")
        self.batch_info_label.setObjectName("hintLabel")
        status_layout.addWidget(self.batch_info_label)
        self.batch_list_label = QLabel("可用批次（点击后用于分析/导出）")
        self.batch_list_label.setObjectName("hintLabel")
        status_layout.addWidget(self.batch_list_label)
        self.batch_list = QListWidget()
        self.batch_list.setMinimumHeight(120)
        status_layout.addWidget(self.batch_list)

        self.hint_label = QLabel(
            "支持选择单个文件或整个文件夹（递归读取）。\n"
            "也支持直接拖入文件 / 文件夹到上方空白区域。\n"
            "银行流程：先点击「处理当前数据」完成入库和标准化，再从下方批次列表中选择批次，再点击「导出全字段合并」或「筛选分析」。"
            "商务网导出含「全字段合并」与「中标情况统计」；银行数据导出为多工作表（全字段合并、细则_双方往来、个人_银行明细、个人_银行统计）。\n"
            "筛选分析说明：仅银行数据可用，会弹出独立筛选窗口进行描述预览与筛选导出。\n"
            "商务网：先点击「处理当前数据」生成批次，再点击下方批次做导出或风险分析；可另选文件点击「导入工商数据」写入企业主数据。"
        )
        self.hint_label.setObjectName("hintLabel")
        self.hint_label.setWordWrap(True)
        status_layout.addWidget(self.hint_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("状态：等待导入")
        status_layout.addWidget(self.status_label)
        root.addWidget(status_card)

        self.log_widget = LogWidget()
        root.addWidget(self.log_widget, 1)

        self.select_file_button.clicked.connect(self.select_files)
        self.select_folder_button.clicked.connect(self.select_folder)
        self.clear_files_button.clicked.connect(self.clear_current_files)
        self.process_button.clicked.connect(self.process_current_data)
        self.export_button.clicked.connect(self.export_last_batch)
        self.filter_button.clicked.connect(self.open_bank_filter_dialog)
        self.import_enterprise_button.clicked.connect(self.import_enterprise_data)
        self.risk_analysis_button.clicked.connect(self.open_commercial_risk_dialog)
        self.batch_list.itemDoubleClicked.connect(self._open_analysis_by_batch_item)
        self.browse_db_button.clicked.connect(self.open_db_browser)
        self._refresh_entry_ui_by_source()
        self._refresh_recent_batches()

    def set_entry_name(self, entry_name: str) -> None:
        """Set active data-entry name shown in page header."""
        previous = self._entry_name
        self._entry_name = entry_name
        self.entry_label.setText(f"当前入口：{entry_name}")
        source_type = self._resolve_source_type()
        self.back_button.setVisible(source_type in {"commercial", "bank"})
        self._refresh_entry_ui_by_source()
        if previous != entry_name:
            had_files = self.file_list_widget.count() > 0
            if had_files:
                self.file_list_widget.clear()
                self.log_widget.append_log("入口已切换，已自动清空待处理文件列表，避免不同来源串用。")
            self._last_batch_id = ""
            self._last_enterprise_batch_id = ""
            self._last_source_type = source_type
            self.progress_bar.setValue(0)
            self.status_label.setText("状态：等待导入")
            self.batch_info_label.setText("最近处理批次：无")
            self._refresh_recent_batches()

    def select_files(self) -> None:
        """Open native file dialog and append selected files."""
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", "All Files (*.*)")
        if files:
            self.file_list_widget.add_files(files)
            self.log_widget.append_log(f"已添加 {len(files)} 个文件。")

    def select_folder(self) -> None:
        """Open native folder dialog and append all nested files."""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not folder:
            return
        files = self._collect_files(folder)
        self.file_list_widget.add_files(files)
        self.log_widget.append_log(f"目录扫描完成，新增 {len(files)} 个文件。")

    def clear_current_files(self) -> None:
        """Clear current selected files and reset status for next run."""
        count = self.file_list_widget.count()
        if count == 0:
            zh_information(self, "提示", "当前列表为空，无需清空。")
            return
        self.file_list_widget.clear()
        self._last_batch_id = ""
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：已清空，等待导入")
        self.batch_info_label.setText("最近处理批次：无")
        self.log_widget.append_log(f"已清空当前文件列表（{count} 条）。")

    def _collect_files(self, folder: str) -> Iterable[str]:
        """Collect all files recursively from folder."""
        root = Path(folder)
        return [str(path) for path in root.rglob("*") if path.is_file()]

    def bootstrap_database(self) -> None:
        """Initialize local SQLite tables."""
        self.status_label.setText("状态：正在初始化数据库...")
        try:
            client = SqliteClient()
            run_bootstrap(client)
            self.status_label.setText("状态：数据库初始化完成")
            self.log_widget.append_log("SQLite数据库初始化成功（meta/raw/std层表就绪）。")
        except Exception as err:
            self.status_label.setText("状态：数据库初始化失败")
            self.log_widget.append_log(f"数据库初始化失败：{err}")
            zh_critical(self, "数据库初始化失败", str(err))

    def ingest_bank_data(self) -> None:
        """Ingest selected excel files into local raw layer."""
        excel_files = self._collect_excel_files()
        if not excel_files:
            zh_information(self, "提示", "请先选择至少一个 .xlsx/.xls 文件。")
            return

        bank_name = self._resolve_bank_name()
        source_type = self._resolve_source_type()
        self.status_label.setText(f"状态：开始入库（{bank_name}）...")
        self.progress_bar.setValue(20)
        self.log_widget.append_log(f"开始数据整合入库，来源={source_type}，标记={bank_name}")
        self.log_widget.append_log(f"待处理文件数：{len(excel_files)}")
        try:
            bundle = get_integration_bundle(source_type)
            service = bundle.ingest_cls()
            result = service.ingest_files(excel_files, bank_name, source_type)
            self._last_batch_id = result.import_batch_id
            self.progress_bar.setValue(100)
            self.status_label.setText(
                f"状态：入库完成，成功文件 {result.files_total - result.failed_files}/{result.files_total}"
            )
            self.log_widget.append_log(
                f"批次完成 batch_id={result.import_batch_id}，sheet={result.sheets_total}，"
                f"行数={result.rows_total}，新模板={result.new_templates}，失败文件={result.failed_files}"
            )
        except Exception as err:
            self.progress_bar.setValue(0)
            self.status_label.setText("状态：入库失败")
            self.log_widget.append_log(f"入库失败：{err}")
            zh_critical(self, "入库失败", str(err))

    def _resolve_bank_name(self) -> str:
        """Map current entry text to bank name tag."""
        text = self._entry_name.lower()
        if "银行" in self._entry_name:
            return self._entry_name
        if "商务网" in self._entry_name or "商业网" in self._entry_name:
            return "商务网数据"
        if "其他" in self._entry_name:
            return "其他数据"
        if "bank" in text:
            return "银行数据"
        return "未分类银行数据"

    def _resolve_source_type(self) -> str:
        """Resolve source type key from current integration entry."""
        text = self._entry_name.lower()
        if "银行" in self._entry_name or "bank" in text:
            return "bank"
        if "商务网" in self._entry_name or "商业网" in self._entry_name or "commercial" in text:
            return "commercial"
        return "other"

    def _collect_excel_files(self) -> list[str]:
        """Collect selected excel files from list widget."""
        files: list[str] = []
        for index in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(index)
            if item is None:
                continue
            file_path = item.text()
            suffix = Path(file_path).suffix.lower()
            if suffix in {".xlsx", ".xls"}:
                files.append(file_path)
        return files

    def standardize_last_batch(self) -> None:
        """Standardize last import batch into std schema."""
        if not self._last_batch_id:
            zh_information(self, "提示", "请先执行整合入库，再进行标准化。")
            return
        try:
            bundle = get_integration_bundle(self._last_source_type)
            service = bundle.mapping_cls()
            count = service.standardize_batch(self._last_batch_id)
            self.log_widget.append_log(f"标准化完成：写入标准层 {count} 行。")
            self.status_label.setText("状态：标准化完成")
        except Exception as err:
            self.log_widget.append_log(f"标准化失败：{err}")
            self.status_label.setText("状态：标准化失败")
            zh_critical(self, "标准化失败", str(err))

    def open_db_browser(self) -> None:
        """Open data preview dialog."""
        dialog = DbBrowserDialog(self)
        dialog.exec()

    def _export_flow_busy(self) -> bool:
        """True if pipeline or export thread is running."""
        if self._pipeline_thread is not None and self._pipeline_thread.isRunning():
            return True
        if self._export_thread is not None and self._export_thread.isRunning():
            return True
        if self._enterprise_flow_busy():
            return True
        return False

    def process_current_data(self) -> None:
        """Process current source files (bank/commercial)."""
        if self._export_flow_busy():
            self.log_widget.append_log("已有任务在运行，请稍候。")
            return
        source_type = self._resolve_source_type()
        if source_type not in {"bank", "commercial"}:
            zh_information(self, "提示", "当前入口暂不支持处理。")
            return
        self._pipeline_mode = "process_only"
        self._start_pipeline(source_type)

    def export_last_batch(self) -> None:
        """Export using processed batch; commercial keeps old one-click behavior."""
        if self._export_flow_busy():
            self.log_widget.append_log("已有导出任务在运行，请稍候。")
            return
        source_type = self._resolve_source_type()
        if source_type == "other":
            zh_information(self, "提示", "其他数据入口暂未开放，暂不支持处理与导出。")
            return
        selected = self._selected_batch_for_source(source_type)
        batch_id = selected or self._last_batch_id
        if not batch_id:
            zh_information(self, "提示", "请先点击「处理当前数据」并在下方批次列表选择一个批次后再导出。")
            return
        self._start_export_for_batch(batch_id, source_type)

    def open_bank_filter_dialog(self) -> None:
        """Open standalone bank filter dialog after processing."""
        if self._resolve_source_type() != "bank":
            return
        batch_id = self._selected_batch_for_source("bank") or self._last_batch_id
        if not batch_id:
            zh_information(self, "提示", "请先点击「处理当前数据」，并在下方批次列表选择银行批次后再筛选分析。")
            return
        dialog = BankFilterDialog(batch_id, self)
        dialog.exec()

    def import_enterprise_data(self) -> None:
        """Import Qichacha enterprise profile workbooks (separate file picker)."""
        if self._resolve_source_type() != "commercial":
            return
        if self._export_flow_busy() or self._enterprise_flow_busy():
            self.log_widget.append_log("已有任务在运行，请稍候。")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择企查查/工商导出 Excel",
            "",
            "Excel 工作簿 (*.xlsx *.xls)",
        )
        if not files:
            return
        self.import_enterprise_button.setEnabled(False)
        self.risk_analysis_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.process_button.setEnabled(False)
        self.filter_button.setEnabled(False)
        self.progress_bar.setValue(5)
        self.status_label.setText("状态：导入工商数据…")
        self._enterprise_thread = QThread(self)
        self._enterprise_worker = _EnterpriseImportWorker(files)
        self._enterprise_worker.moveToThread(self._enterprise_thread)
        self._enterprise_thread.started.connect(self._enterprise_worker.run)
        self._enterprise_worker.log_message.connect(self.log_widget.append_log)
        self._enterprise_worker.progress_changed.connect(self.progress_bar.setValue)
        self._enterprise_worker.status_message.connect(self.status_label.setText)
        self._enterprise_worker.finished_ok.connect(self._on_enterprise_import_ok)
        self._enterprise_worker.failed.connect(self._on_enterprise_import_fail)
        self._enterprise_worker.finished_ok.connect(self._enterprise_thread.quit)
        self._enterprise_worker.failed.connect(self._enterprise_thread.quit)
        self._enterprise_thread.finished.connect(self._enterprise_worker.deleteLater)
        self._enterprise_thread.finished.connect(self._enterprise_thread.deleteLater)
        self._enterprise_thread.finished.connect(self._clear_enterprise_thread)
        self._enterprise_thread.start()

    def _clear_enterprise_thread(self) -> None:
        self._enterprise_thread = None
        self._enterprise_worker = None
        self.import_enterprise_button.setEnabled(True)
        self.risk_analysis_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.process_button.setEnabled(self._resolve_source_type() in {"bank", "commercial"})
        self.filter_button.setEnabled(self._resolve_source_type() == "bank")

    def _on_enterprise_import_ok(self, batch_id: str) -> None:
        self._last_enterprise_batch_id = batch_id
        self.log_widget.append_log(f"最近一次工商导入批次：{batch_id}")

    def _on_enterprise_import_fail(self, message: str) -> None:
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：工商导入失败")
        self.log_widget.append_log(f"工商导入失败：{message}")
        zh_critical(self, "工商导入失败", message)

    def open_commercial_risk_dialog(self) -> None:
        if self._resolve_source_type() != "commercial":
            return
        batch_id = self._selected_batch_for_source("commercial") or self._last_batch_id
        if not batch_id:
            zh_information(self, "提示", "请先点击「处理当前数据」，并在下方批次列表选择商务网批次后再分析。")
            return
        dialog = CommercialRiskDialog(
            batch_id,
            self,
            default_enterprise_batch_id=self._last_enterprise_batch_id,
        )
        dialog.exec()

    def _enterprise_flow_busy(self) -> bool:
        return self._enterprise_thread is not None and self._enterprise_thread.isRunning()

    def _start_pipeline(self, source_type: str) -> None:
        """Run ingest+standardize pipeline for selected files."""
        excel_files = self._collect_excel_files()
        if not excel_files:
            zh_information(self, "提示", "请先选择或拖入至少一个 .xlsx/.xls 文件。")
            return
        self._last_source_type = source_type
        self.progress_bar.setValue(10)
        self.status_label.setText("状态：自动处理中（初始化数据库）...")
        self.process_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.filter_button.setEnabled(False)
        self.import_enterprise_button.setEnabled(False)
        self.risk_analysis_button.setEnabled(False)

        bank_name = self._resolve_bank_name()
        self._pipeline_thread = QThread(self)
        self._pipeline_worker = _AutoPipelineWorker(excel_files, bank_name, source_type)
        self._pipeline_worker.moveToThread(self._pipeline_thread)

        self._pipeline_thread.started.connect(self._pipeline_worker.run)
        self._pipeline_worker.log_message.connect(self.log_widget.append_log)
        self._pipeline_worker.progress_changed.connect(self.progress_bar.setValue)
        self._pipeline_worker.status_message.connect(self.status_label.setText)
        self._pipeline_worker.finished_ok.connect(self._on_pipeline_finished_ok)
        self._pipeline_worker.failed.connect(self._on_pipeline_failed)
        self._pipeline_thread.finished.connect(self._pipeline_worker.deleteLater)
        self._pipeline_thread.finished.connect(self._pipeline_thread.deleteLater)
        self._pipeline_thread.finished.connect(self._clear_pipeline_thread)
        self._pipeline_thread.start()

    def _clear_pipeline_thread(self) -> None:
        """Drop pipeline thread references after it stops."""
        self._pipeline_thread = None
        self._pipeline_worker = None

    def _clear_export_thread(self) -> None:
        """Drop export thread references after it stops."""
        self._export_thread = None
        self._export_worker = None

    def _on_pipeline_finished_ok(self, batch_id: str, source_type: str) -> None:
        """Pipeline completed on main thread."""
        if self._pipeline_thread is not None:
            self._pipeline_thread.quit()
        self._last_batch_id = batch_id
        self._last_source_type = source_type
        self.batch_info_label.setText(f"最近处理批次：{batch_id}")
        self._refresh_recent_batches(selected_batch_id=batch_id)
        self.process_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.filter_button.setEnabled(True)
        self.import_enterprise_button.setEnabled(self._resolve_source_type() == "commercial")
        self.risk_analysis_button.setEnabled(self._resolve_source_type() == "commercial")
        if self._pipeline_mode == "process_only":
            self.progress_bar.setValue(100)
            self.status_label.setText("状态：处理完成，可导出/筛选分析")
            self.log_widget.append_log("处理完成：请在下方批次列表选择批次后进行导出或分析。")
            return
        self._start_export_for_batch(batch_id, source_type)

    def _on_pipeline_failed(self, message: str) -> None:
        """Pipeline error on main thread."""
        if self._pipeline_thread is not None:
            self._pipeline_thread.quit()
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：自动处理失败")
        self.log_widget.append_log(f"自动处理失败：{message}")
        self.process_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.filter_button.setEnabled(True)
        self.import_enterprise_button.setEnabled(self._resolve_source_type() == "commercial")
        self.risk_analysis_button.setEnabled(self._resolve_source_type() == "commercial")
        zh_critical(self, "自动处理失败", message)

    def _on_export_finished_ok(self, output: str) -> None:
        if self._export_thread is not None:
            self._export_thread.quit()
        self.log_widget.append_log(f"导出完成：{output}")
        self.process_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.filter_button.setEnabled(True)
        self.import_enterprise_button.setEnabled(self._resolve_source_type() == "commercial")
        self.risk_analysis_button.setEnabled(self._resolve_source_type() == "commercial")

    def _on_export_failed(self, message: str) -> None:
        if self._export_thread is not None:
            self._export_thread.quit()
        self.log_widget.append_log(f"导出失败：{message}")
        self.status_label.setText("状态：导出失败")
        self.process_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.filter_button.setEnabled(True)
        self.import_enterprise_button.setEnabled(self._resolve_source_type() == "commercial")
        self.risk_analysis_button.setEnabled(self._resolve_source_type() == "commercial")
        zh_critical(self, "导出失败", message)

    def _refresh_entry_ui_by_source(self) -> None:
        """Toggle bank-specific controls by current source."""
        is_bank = self._resolve_source_type() == "bank"
        is_commercial = self._resolve_source_type() == "commercial"
        self.process_button.setVisible(is_bank or is_commercial)
        self.filter_button.setVisible(is_bank)
        self.import_enterprise_button.setVisible(is_commercial)
        self.risk_analysis_button.setVisible(is_commercial)
        self._refresh_recent_batches()

    def _refresh_recent_batches(self, selected_batch_id: str = "") -> None:
        """Load recent processed batches for current source type."""
        source_type = self._resolve_source_type()
        self.batch_list.clear()
        if source_type not in {"bank", "commercial"}:
            return
        try:
            rows = SqliteClient().query_all(
                """
                SELECT import_batch_id, source_type, COUNT(*), MAX(imported_at)
                FROM meta_bank_files
                WHERE source_type=?
                GROUP BY import_batch_id, source_type
                ORDER BY MAX(imported_at) DESC
                LIMIT 80;
                """,
                (source_type,),
            )
        except Exception:
            return
        for row in rows:
            batch_id = str(row[0])
            count = int(row[2])
            ts = str(row[3] or "")
            item = QListWidgetItem(f"{batch_id[:8]}…  文件{count}个  时间:{ts}")
            item.setData(Qt.ItemDataRole.UserRole, (batch_id, source_type))
            self.batch_list.addItem(item)
            if selected_batch_id and batch_id == selected_batch_id:
                self.batch_list.setCurrentItem(item)

    def _selected_batch_for_source(self, source_type: str) -> str:
        item = self.batch_list.currentItem()
        if item is None:
            return ""
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload or len(payload) != 2:
            return ""
        batch_id, src = payload
        if src != source_type:
            return ""
        return str(batch_id)

    def _open_analysis_by_batch_item(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload or len(payload) != 2:
            return
        _batch_id, src = payload
        if src == "bank":
            self.open_bank_filter_dialog()
        elif src == "commercial":
            self.open_commercial_risk_dialog()

    def _start_export_for_batch(self, batch_id: str, source_type: str) -> None:
        """Prompt output path then start export worker."""
        batch_short = batch_id.split("-")[0]
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出全字段合并",
            f"标准导出_{batch_short}.xlsx",
            "Excel 工作簿 (*.xlsx)",
        )
        if not target_path:
            self.status_label.setText("状态：已取消保存")
            self.log_widget.append_log("已取消保存，未导出文件。")
            return
        self.process_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.filter_button.setEnabled(False)
        self.import_enterprise_button.setEnabled(False)
        self.risk_analysis_button.setEnabled(False)
        self._export_thread = QThread(self)
        self._export_worker = _ExportBatchWorker(batch_id, source_type, target_path)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.log_message.connect(self.log_widget.append_log)
        self._export_worker.progress_changed.connect(self.progress_bar.setValue)
        self._export_worker.status_message.connect(self.status_label.setText)
        self._export_worker.finished_ok.connect(self._on_export_finished_ok)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_thread.finished.connect(self._export_worker.deleteLater)
        self._export_thread.finished.connect(self._export_thread.deleteLater)
        self._export_thread.finished.connect(self._clear_export_thread)
        self._export_thread.start()

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        """Reserve drag-enter hook for future drop support."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        """Handle local file drop and append to list."""
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        dropped_files: list[str] = []
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if not local_path:
                continue
            path = Path(local_path)
            if path.is_file():
                dropped_files.append(str(path))
            elif path.is_dir():
                dropped_files.extend(self._collect_files(str(path)))
        self.file_list_widget.add_files(dropped_files)
        event.acceptProposedAction()
