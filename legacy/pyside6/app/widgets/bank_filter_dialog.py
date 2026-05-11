"""Dialog for bank filter analysis, fixed modules, and optional export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSignalBlocker, QThread, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.integration.bank.analysis_modules import (
    AnalysisModuleId,
    ModuleParams,
    ModuleResult,
    run_module,
)
from app.services.integration.bank.export_service import BankExportService
from app.services.integration.bank.query_service import BankQueryFilters, BankQueryService
from app.widgets.zh_message_box import zh_critical, zh_information


class _ModuleAnalysisWorker(QObject):
    """Run fixed analysis module in a background thread."""

    finished_ok = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(int, str)

    def __init__(self, batch_id: str, module_id: str, params: ModuleParams) -> None:
        super().__init__()
        self._batch_id = batch_id
        self._module_id = module_id
        self._params = params

    def run(self) -> None:
        try:
            self.progress_changed.emit(20, "正在加载并分析…")
            result = run_module(self._batch_id, self._module_id, self._params)
            self.progress_changed.emit(100, "分析完成")
            self.finished_ok.emit(result)
        except Exception as err:
            self.failed.emit(str(err))


class BankFilterDialog(QDialog):
    """Bank-only analysis dialog: fixed modules + custom filters."""

    def __init__(self, import_batch_id: str, parent=None) -> None:
        super().__init__(parent)
        self._batch_id = import_batch_id
        self._query_service = BankQueryService()
        self._last_module_id: str = ""
        self._last_module_result: ModuleResult | None = None
        self._module_thread: QThread | None = None
        self._module_worker: _ModuleAnalysisWorker | None = None
        self._HIT_TABLE_HEADERS = (
            "数据来源",
            "银行类别",
            "姓名",
            "卡号",
            "时间戳",
            "收支标志",
            "币种",
            "金额",
            "余额",
            "对手名",
            "对手卡号",
            "交易描述",
            "备注",
        )
        self._HIT_TABLE_KEYS = (
            "data_source",
            "bank_type",
            "person_name",
            "acct_no",
            "txn_time",
            "txn_direction",
            "currency",
            "amount",
            "balance",
            "counterparty_name",
            "counterparty_account",
            "txn_desc",
            "remark",
        )

        self.setWindowTitle("银行筛选分析")
        self.resize(1460, 880)
        self.setMinimumSize(1280, 760)
        self.setSizeGripEnabled(True)
        self.setModal(True)
        self.setObjectName("bankFilterDialog")

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        fixed_panel = self._build_fixed_analysis_tab()
        custom_panel = self._build_custom_filter_tab()
        self._tabs.addTab(fixed_panel, "固定分析")
        self._tabs.addTab(custom_panel, "自定义筛选")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        btn_row = QHBoxLayout()
        self.preview_btn = QPushButton("生成描述")
        self.export_btn = QPushButton("导出筛选结果")
        self.close_btn = QPushButton("关闭")
        self.close_btn.setObjectName("secondaryButton")
        self.export_hits_btn = QPushButton("导出命中明细")
        self.export_hits_btn.setToolTip("仅导出当前表格中的命中流水，作为文字描述的佐证。")
        btn_row.addWidget(self.preview_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.export_hits_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        action_group = QGroupBox("操作")
        action_group.setObjectName("bankFilterAction")
        action_group.setLayout(btn_row)
        root.addWidget(action_group)

        root.addWidget(QLabel("描述预览（详版）"))
        self.desc_view = QPlainTextEdit()
        self.desc_view.setObjectName("bankDescView")
        self.desc_view.setReadOnly(True)
        self.desc_view.setPlaceholderText(
            "固定分析：点击模块后，此处为文字摘要，下方表格为命中明细预览；"
            "自定义筛选：设置条件后点击「生成描述」（仅文字摘要，无表格预览）。"
        )
        self.desc_view.setMinimumHeight(200)
        self.desc_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.desc_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.desc_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(self.desc_view, 2)

        self._hits_preview_container = QWidget()
        hits_layout = QVBoxLayout(self._hits_preview_container)
        hits_layout.setContentsMargins(0, 0, 0, 0)
        hits_layout.setSpacing(6)
        self._hits_preview_label = QLabel("命中明细预览（固定分析，与「导出命中明细」一致）")
        hits_layout.addWidget(self._hits_preview_label)
        self._hits_table = QTableWidget(0, len(self._HIT_TABLE_HEADERS))
        self._hits_table.setHorizontalHeaderLabels(list(self._HIT_TABLE_HEADERS))
        self._hits_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._hits_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._hits_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._hits_table.setAlternatingRowColors(True)
        self._hits_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._hits_table.horizontalHeader().setStretchLastSection(True)
        self._hits_table.setMinimumHeight(260)
        hits_layout.addWidget(self._hits_table, 1)
        root.addWidget(self._hits_preview_container, 3)

        self.preview_btn.clicked.connect(self.preview_description)
        self.export_btn.clicked.connect(self._export_clicked)
        self.export_hits_btn.clicked.connect(self.export_module_hits_only)
        self.close_btn.clicked.connect(self.accept)
        self._load_filter_options()
        self._on_tab_changed(self._tabs.currentIndex())

    def _build_fixed_analysis_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        param_row = QHBoxLayout()
        param_row.addWidget(QLabel("大额阈值（单笔绝对金额 ≥）"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1e12)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(100_000.0)
        self.threshold_spin.setSingleStep(10_000.0)
        param_row.addWidget(self.threshold_spin)

        param_row.addWidget(QLabel("资金流向 Top N（仅描述摘要）"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(15)
        param_row.addWidget(self.top_n_spin)

        param_row.addWidget(QLabel("重复金额最少次数"))
        self.repeat_min_spin = QSpinBox()
        self.repeat_min_spin.setRange(2, 50)
        self.repeat_min_spin.setValue(3)
        param_row.addWidget(self.repeat_min_spin)
        param_row.addStretch(1)
        layout.addLayout(param_row)

        btn_grid = QGridLayout()
        self.btn_large_inout = QPushButton("大额进出分析")
        self.btn_large_flow = QPushButton("大额资金流向")
        self.btn_special_amt = QPushButton("特殊金额分析")
        self.btn_special_time = QPushButton("特殊时间分析")
        for i, btn in enumerate(
            (self.btn_large_inout, self.btn_large_flow, self.btn_special_amt, self.btn_special_time)
        ):
            btn.setMinimumHeight(40)
            btn_grid.addWidget(btn, 0, i)
        layout.addLayout(btn_grid)

        self.btn_large_inout.clicked.connect(
            lambda: self._start_module_analysis(AnalysisModuleId.LARGE_INOUT)
        )
        self.btn_large_flow.clicked.connect(lambda: self._start_module_analysis(AnalysisModuleId.LARGE_FLOW))
        self.btn_special_amt.clicked.connect(
            lambda: self._start_module_analysis(AnalysisModuleId.SPECIAL_AMOUNT)
        )
        self.btn_special_time.clicked.connect(
            lambda: self._start_module_analysis(AnalysisModuleId.SPECIAL_TIME)
        )

        self.module_progress = QProgressBar()
        self.module_progress.setRange(0, 100)
        self.module_progress.setValue(0)
        layout.addWidget(self.module_progress)
        self.module_status = QLabel("就绪")
        layout.addWidget(self.module_status)
        layout.addStretch(1)
        return w

    def _build_custom_filter_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        filter_group = QGroupBox("筛选条件")
        filter_group.setObjectName("bankFilterGroup")
        outer.addWidget(filter_group)

        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(10, 10, 10, 10)
        filter_layout.setSpacing(10)

        self.bank_type_input = self._create_filter_combo()
        self.person_name_input = self._create_filter_combo()
        self.acct_no_input = self._create_filter_combo()
        self.counterparty_name_input = self._create_filter_combo()
        self.counterparty_account_input = self._create_filter_combo()
        self.amount_min_input = self._create_line_edit()
        self.amount_max_input = self._create_line_edit()
        self.use_time_filter_check = QCheckBox("启用时间段筛选")
        self.start_time_input = QDateTimeEdit()
        self.end_time_input = QDateTimeEdit()
        for dt in (self.start_time_input, self.end_time_input):
            dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            dt.setCalendarPopup(True)
            dt.setEnabled(False)
        self.use_time_filter_check.toggled.connect(self.start_time_input.setEnabled)
        self.use_time_filter_check.toggled.connect(self.end_time_input.setEnabled)

        self.use_day_time_check = QCheckBox("启用日内特殊时段筛选")
        self.day_time_preset = QComboBox()
        self.day_time_preset.addItems(
            [
                "手动选择",
                "凌晨时段 00:00:00-06:00:00",
                "上午时段 06:00:00-12:00:00",
                "下午时段 12:00:00-18:00:00",
                "晚间时段 18:00:00-23:59:59",
                "夜间跨日 22:00:00-02:00:00",
            ]
        )
        self.day_time_start = QTimeEdit()
        self.day_time_end = QTimeEdit()
        self.day_time_start.setDisplayFormat("HH:mm:ss")
        self.day_time_end.setDisplayFormat("HH:mm:ss")
        self.day_time_start.setEnabled(False)
        self.day_time_end.setEnabled(False)
        self.day_time_preset.setEnabled(False)
        self.use_day_time_check.toggled.connect(self.day_time_preset.setEnabled)
        self.use_day_time_check.toggled.connect(self.day_time_start.setEnabled)
        self.use_day_time_check.toggled.connect(self.day_time_end.setEnabled)
        self.day_time_preset.currentTextChanged.connect(self._apply_day_time_preset)

        self.bank_type_input.setPlaceholderText("例如：工商银行")
        self.person_name_input.setPlaceholderText("例如：张三")
        self.acct_no_input.setPlaceholderText("例如：6222****")
        self.counterparty_name_input.setPlaceholderText("例如：李四公司")
        self.counterparty_account_input.setPlaceholderText("例如：95588****")
        self.amount_min_input.setPlaceholderText("例如：1000")
        self.amount_max_input.setPlaceholderText("例如：50000")
        all_fields = (
            self.bank_type_input,
            self.person_name_input,
            self.acct_no_input,
            self.counterparty_name_input,
            self.counterparty_account_input,
            self.amount_min_input,
            self.amount_max_input,
            self.start_time_input,
            self.end_time_input,
            self.day_time_preset,
            self.day_time_start,
            self.day_time_end,
        )
        for field in all_fields:
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            field.setMinimumHeight(30)
            field.setMaximumHeight(34)

        basic_group = QGroupBox("基础条件")
        basic_group.setObjectName("bankFilterSubGroup")
        basic_layout = QGridLayout(basic_group)
        basic_layout.setContentsMargins(12, 14, 12, 12)
        basic_layout.setHorizontalSpacing(16)
        basic_layout.setVerticalSpacing(12)

        basic_layout.addWidget(self._make_label("姓名"), 0, 0)
        basic_layout.addWidget(self.person_name_input, 0, 1)
        basic_layout.addWidget(self._make_label("银行类型"), 1, 0)
        basic_layout.addWidget(self.bank_type_input, 1, 1)
        basic_layout.addWidget(self._make_label("卡号"), 2, 0)
        basic_layout.addWidget(self.acct_no_input, 2, 1)

        basic_layout.addWidget(self._make_label("对手名"), 0, 2)
        basic_layout.addWidget(self.counterparty_name_input, 0, 3)
        basic_layout.addWidget(self._make_label("对手卡号"), 1, 2)
        basic_layout.addWidget(self.counterparty_account_input, 1, 3)
        basic_layout.addWidget(self._make_label("金额下限"), 2, 2)
        basic_layout.addWidget(self.amount_min_input, 2, 3)
        basic_layout.addWidget(self._make_label("金额上限"), 3, 2)
        basic_layout.addWidget(self.amount_max_input, 3, 3)

        basic_layout.setColumnStretch(0, 0)
        basic_layout.setColumnStretch(1, 1)
        basic_layout.setColumnStretch(2, 0)
        basic_layout.setColumnStretch(3, 1)
        basic_layout.setRowStretch(4, 1)

        time_group = QGroupBox("时间段筛选")
        time_group.setObjectName("bankFilterSubGroup")
        time_layout = QGridLayout(time_group)
        time_layout.setContentsMargins(12, 14, 12, 12)
        time_layout.setHorizontalSpacing(16)
        time_layout.setVerticalSpacing(12)
        time_layout.addWidget(self.use_time_filter_check, 0, 0, 1, 2)
        time_layout.addWidget(self._make_label("开始时间"), 1, 0)
        time_layout.addWidget(self.start_time_input, 1, 1)
        time_layout.addWidget(self._make_label("结束时间"), 2, 0)
        time_layout.addWidget(self.end_time_input, 2, 1)
        time_layout.setColumnStretch(0, 0)
        time_layout.setColumnStretch(1, 1)
        time_layout.setRowStretch(3, 1)

        day_group = QGroupBox("日内特殊时段筛选")
        day_group.setObjectName("bankFilterSubGroup")
        day_layout = QGridLayout(day_group)
        day_layout.setContentsMargins(12, 14, 12, 12)
        day_layout.setHorizontalSpacing(16)
        day_layout.setVerticalSpacing(12)
        day_layout.addWidget(self.use_day_time_check, 0, 0, 1, 2)
        day_layout.addWidget(self._make_label("时段预设"), 1, 0)
        day_layout.addWidget(self.day_time_preset, 1, 1)
        day_layout.addWidget(self._make_label("日内开始"), 2, 0)
        day_layout.addWidget(self.day_time_start, 2, 1)
        day_layout.addWidget(self._make_label("日内结束"), 3, 0)
        day_layout.addWidget(self.day_time_end, 3, 1)
        day_layout.setColumnStretch(0, 0)
        day_layout.setColumnStretch(1, 1)
        day_layout.setRowStretch(4, 1)

        bottom_row = QWidget()
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        bottom_layout.addWidget(time_group, 1)
        bottom_layout.addWidget(day_group, 1)

        filter_layout.addWidget(basic_group)
        filter_layout.addWidget(bottom_row)
        filter_layout.addStretch(1)
        return w

    def _build_module_params(self) -> ModuleParams:
        return ModuleParams(
            large_amount_threshold=float(self.threshold_spin.value()),
            top_n=int(self.top_n_spin.value()),
            repeat_amount_min_count=int(self.repeat_min_spin.value()),
        )

    def _on_tab_changed(self, idx: int) -> None:
        if idx == 0:
            self.preview_btn.setVisible(False)
            self.export_btn.setText("导出模块结果")
            self.export_hits_btn.setVisible(True)
            self._hits_preview_container.setVisible(True)
            self._refresh_export_hits_enabled()
        else:
            self.preview_btn.setVisible(True)
            self.export_btn.setText("导出筛选结果")
            self.export_hits_btn.setVisible(False)
            self._hits_preview_container.setVisible(False)

    def _export_clicked(self) -> None:
        if self._tabs.currentIndex() == 0:
            self.export_module_result()
        else:
            self.export_filtered_result()

    def _set_module_buttons_enabled(self, enabled: bool) -> None:
        for b in (
            self.btn_large_inout,
            self.btn_large_flow,
            self.btn_special_amt,
            self.btn_special_time,
        ):
            b.setEnabled(enabled)

    def _start_module_analysis(self, module_id: str) -> None:
        if self._module_thread is not None and self._module_thread.isRunning():
            zh_information(self, "提示", "已有分析任务在执行，请稍候。")
            return
        params = self._build_module_params()
        self._set_module_buttons_enabled(False)
        self.module_progress.setValue(10)
        self.module_status.setText("状态：分析中…")
        self.desc_view.setPlainText("正在分析，请稍候…")
        self._last_module_result = None
        self._fill_hits_table([])
        self._refresh_export_hits_enabled()

        self._module_thread = QThread(self)
        self._module_worker = _ModuleAnalysisWorker(self._batch_id, module_id, params)
        self._module_worker.moveToThread(self._module_thread)

        self._module_thread.started.connect(self._module_worker.run)
        self._module_worker.progress_changed.connect(self._on_module_progress)
        self._module_worker.finished_ok.connect(self._on_module_finished)
        self._module_worker.failed.connect(self._on_module_failed)
        self._module_worker.finished_ok.connect(self._module_thread.quit)
        self._module_worker.failed.connect(self._module_thread.quit)
        self._module_thread.finished.connect(self._module_worker.deleteLater)
        self._module_thread.finished.connect(self._module_thread.deleteLater)
        self._module_thread.finished.connect(self._clear_module_thread)
        self._module_thread.start()

    def _on_module_progress(self, value: int, message: str) -> None:
        self.module_progress.setValue(value)
        self.module_status.setText(f"状态：{message}")

    def _on_module_finished(self, result: ModuleResult) -> None:
        self._last_module_id = result.module_id
        self._last_module_result = result
        self.desc_view.setPlainText(result.description)
        self._fill_hits_table(result.hit_records)
        self.module_status.setText("状态：就绪")
        self._set_module_buttons_enabled(True)
        self._refresh_export_hits_enabled()

    def _on_module_failed(self, message: str) -> None:
        self.module_progress.setValue(0)
        self.module_status.setText("状态：分析失败")
        self._set_module_buttons_enabled(True)
        self._refresh_export_hits_enabled()
        zh_critical(self, "分析失败", message)

    def _clear_module_thread(self) -> None:
        self._module_thread = None
        self._module_worker = None

    def _fill_hits_table(self, records: list[dict[str, str]]) -> None:
        table = self._hits_table
        table.setSortingEnabled(False)
        table.setRowCount(len(records))
        keys = self._HIT_TABLE_KEYS
        for r, row in enumerate(records):
            for c, key in enumerate(keys):
                text = row.get(key, "")
                if text is None:
                    text = ""
                item = QTableWidgetItem(str(text))
                item.setToolTip(str(text))
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        self._hits_preview_label.setText(
            f"命中明细预览（共 {len(records)} 笔，与「导出命中明细」一致）"
        )

    def _refresh_export_hits_enabled(self) -> None:
        ok = bool(
            self._tabs.currentIndex() == 0
            and self._last_module_result
            and self._last_module_result.hit_records
        )
        self.export_hits_btn.setEnabled(ok)

    def export_module_hits_only(self) -> None:
        if self._tabs.currentIndex() != 0:
            return
        if not self._last_module_result or not self._last_module_result.hit_records:
            zh_information(self, "提示", "请先在「固定分析」中运行模块，且存在命中流水后再导出。")
            return
        batch_short = self._batch_id.split("-")[0]
        labels = {
            AnalysisModuleId.LARGE_INOUT: "大额进出",
            AnalysisModuleId.LARGE_FLOW: "大额资金流向",
            AnalysisModuleId.SPECIAL_AMOUNT: "特殊金额",
            AnalysisModuleId.SPECIAL_TIME: "特殊时间",
        }
        mid = self._last_module_result.module_id
        prefix = labels.get(mid, "命中明细")
        output, _ = QFileDialog.getSaveFileName(
            self,
            "导出命中明细",
            f"命中明细_{prefix}_{batch_short}.xlsx",
            "Excel 工作簿 (*.xlsx)",
        )
        if not output:
            return
        service = BankExportService()
        out_path = service.export_unified_record_table(
            output, self._last_module_result.hit_records, sheet_name="命中明细"
        )
        zh_information(self, "导出完成", f"已导出：{Path(out_path)}")

    def export_module_result(self) -> None:
        if not self._last_module_id:
            zh_information(self, "提示", "请先在「固定分析」中点击任一分析模块生成结果。")
            return
        batch_short = self._batch_id.split("-")[0]
        labels = {
            AnalysisModuleId.LARGE_INOUT: "大额进出",
            AnalysisModuleId.LARGE_FLOW: "大额资金流向",
            AnalysisModuleId.SPECIAL_AMOUNT: "特殊金额",
            AnalysisModuleId.SPECIAL_TIME: "特殊时间",
        }
        prefix = labels.get(self._last_module_id, "模块分析")
        output, _ = QFileDialog.getSaveFileName(
            self,
            "导出模块结果",
            f"{prefix}_{batch_short}.xlsx",
            "Excel 工作簿 (*.xlsx)",
        )
        if not output:
            return
        service = BankExportService()
        out_path = service.export_module_report(
            self._batch_id, output, self._last_module_id, self._build_module_params()
        )
        zh_information(self, "导出完成", f"已导出：{Path(out_path)}")

    def _build_filters(self) -> BankQueryFilters | None:
        amount_min: float | None = None
        amount_max: float | None = None
        text_min = self.amount_min_input.text().strip()
        text_max = self.amount_max_input.text().strip()
        try:
            if text_min:
                amount_min = float(text_min)
            if text_max:
                amount_max = float(text_max)
        except ValueError:
            zh_information(self, "提示", "金额请输入数字格式。")
            return None
        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            zh_information(self, "提示", "金额下限不能大于金额上限。")
            return None

        start_time = ""
        end_time = ""
        if self.use_time_filter_check.isChecked():
            start_time = self.start_time_input.dateTime().toString("yyyy-MM-dd HH:mm:ss")
            end_time = self.end_time_input.dateTime().toString("yyyy-MM-dd HH:mm:ss")
            if start_time > end_time:
                zh_information(self, "提示", "开始时间不能晚于结束时间。")
                return None

        day_time_start = ""
        day_time_end = ""
        if self.use_day_time_check.isChecked():
            day_time_start = self.day_time_start.time().toString("HH:mm:ss")
            day_time_end = self.day_time_end.time().toString("HH:mm:ss")

        return BankQueryFilters(
            bank_type=self.bank_type_input.currentText().strip(),
            person_name=self.person_name_input.currentText().strip(),
            acct_no=self.acct_no_input.currentText().strip(),
            counterparty_name=self.counterparty_name_input.currentText().strip(),
            counterparty_account=self.counterparty_account_input.currentText().strip(),
            amount_min=amount_min,
            amount_max=amount_max,
            start_time=start_time,
            end_time=end_time,
            day_time_start=day_time_start,
            day_time_end=day_time_end,
        )

    def preview_description(self) -> None:
        if self._tabs.currentIndex() == 0:
            return
        filters = self._build_filters()
        if filters is None:
            return
        records = self._query_service.query_unified_records(self._batch_id, filters)
        summary = self._query_service.summarize(records)
        text = self._query_service.render_description(filters, summary)
        self.desc_view.setPlainText(text)

    def export_filtered_result(self) -> None:
        filters = self._build_filters()
        if filters is None:
            return
        batch_short = self._batch_id.split("-")[0]
        output, _ = QFileDialog.getSaveFileName(
            self,
            "导出筛选结果",
            f"筛选导出_{batch_short}.xlsx",
            "Excel 工作簿 (*.xlsx)",
        )
        if not output:
            return
        service = BankExportService()
        out_path = service.export_filtered_summary(self._batch_id, output, filters)
        zh_information(self, "导出完成", f"已导出：{Path(out_path)}")

    def _apply_day_time_preset(self, text: str) -> None:
        preset = {
            "凌晨时段 00:00:00-06:00:00": ("00:00:00", "06:00:00"),
            "上午时段 06:00:00-12:00:00": ("06:00:00", "12:00:00"),
            "下午时段 12:00:00-18:00:00": ("12:00:00", "18:00:00"),
            "晚间时段 18:00:00-23:59:59": ("18:00:00", "23:59:59"),
            "夜间跨日 22:00:00-02:00:00": ("22:00:00", "02:00:00"),
        }
        if text not in preset:
            return
        s, e = preset[text]
        self.day_time_start.setTime(QTime.fromString(s, "HH:mm:ss"))
        self.day_time_end.setTime(QTime.fromString(e, "HH:mm:ss"))

    def _create_filter_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        combo.setPlaceholderText("可输入或下拉选择")
        return combo

    def _make_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setMinimumWidth(72)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _create_line_edit(self) -> QLineEdit:
        return QLineEdit()

    def _load_filter_options(self) -> None:
        options = self._query_service.get_filter_options(self._batch_id)
        mapping = {
            self.bank_type_input: options.get("bank_type", []),
            self.person_name_input: options.get("person_name", []),
            self.acct_no_input: options.get("acct_no", []),
            self.counterparty_name_input: options.get("counterparty_name", []),
            self.counterparty_account_input: options.get("counterparty_account", []),
        }
        for combo, values in mapping.items():
            blocker = QSignalBlocker(combo)
            combo.clear()
            combo.addItem("")
            combo.addItems(values)
            del blocker
            combo.currentTextChanged.connect(combo.setToolTip)
