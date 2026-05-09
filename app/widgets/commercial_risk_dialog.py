"""商务网：工商匹配 + 风险分析预览与导出."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.services.integration.commercial.risk_export_service import CommercialRiskExportService
from app.services.integration.commercial.risk_rule_service import CommercialRiskAnalysisService
from app.services.shared.db.sqlite_client import SqliteClient
from app.widgets.zh_message_box import zh_critical, zh_information


class _RiskRunWorker(QObject):
    finished_ok = Signal(int, int)
    failed = Signal(str)

    def __init__(self, commercial_batch_id: str, enterprise_batch_id: str | None) -> None:
        super().__init__()
        self._commercial_batch_id = commercial_batch_id
        self._enterprise_batch_id = enterprise_batch_id or None

    def run(self) -> None:
        try:
            svc = CommercialRiskAnalysisService()
            ev, sm = svc.run_full(self._commercial_batch_id, self._enterprise_batch_id)
            self.finished_ok.emit(ev, sm)
        except Exception as err:
            self.failed.emit(str(err))


class CommercialRiskDialog(QDialog):
    """展示风险事件/汇总并支持导出."""

    def __init__(
        self,
        commercial_batch_id: str,
        parent=None,
        *,
        default_enterprise_batch_id: str = "",
    ) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _RiskRunWorker | None = None

        self.setWindowTitle("商务网 · 风险分析")
        self.resize(1100, 720)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("风险分析：可单独使用商务网批次，也可叠加工商批次联合分析"))

        row = QHBoxLayout()
        row.addWidget(QLabel("商务网批次"))
        self._commercial_combo = QComboBox()
        self._commercial_combo.setMinimumWidth(360)
        self._load_commercial_batches(commercial_batch_id)
        row.addWidget(self._commercial_combo, 1)
        row.addWidget(QLabel("工商数据批次（空=使用全部已导入工商库）"))
        self._enterprise_combo = QComboBox()
        self._enterprise_combo.setMinimumWidth(300)
        self._load_enterprise_batches(default_enterprise_batch_id)
        row.addWidget(self._enterprise_combo, 1)
        self._run_btn = QPushButton("运行分析")
        self._export_btn = QPushButton("导出风险报告")
        row.addWidget(self._run_btn)
        row.addWidget(self._export_btn)
        root.addLayout(row)

        split = QSplitter()
        self._event_table = QTableWidget(0, 6)
        self._event_table.setHorizontalHeaderLabels(
            ["规则", "名称", "等级", "分数", "企业", "询价单号"]
        )
        self._summary_table = QTableWidget(0, 7)
        self._summary_table.setHorizontalHeaderLabels(
            ["企业", "参标次数", "中标次数", "中标金额", "总分", "命中数", "等级"]
        )
        split.addWidget(self._event_table)
        split.addWidget(self._summary_table)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        root.addWidget(split, 1)

        self._run_btn.clicked.connect(self._run_analysis)
        self._export_btn.clicked.connect(self._export_report)
        self._commercial_combo.currentIndexChanged.connect(lambda _i: self._refresh_tables())
        self._refresh_tables()

    def _load_commercial_batches(self, default_id: str) -> None:
        self._commercial_combo.clear()
        rows = SqliteClient().query_all(
            """
            SELECT import_batch_id, COUNT(*), MAX(imported_at)
            FROM meta_bank_files
            WHERE source_type='commercial'
            GROUP BY import_batch_id
            ORDER BY MAX(imported_at) DESC
            LIMIT 80;
            """
        )
        select_idx = 0
        for idx, row in enumerate(rows):
            bid = str(row[0])
            cnt = int(row[1])
            ts = str(row[2] or "")
            self._commercial_combo.addItem(f"{bid[:8]}… ({cnt} 文件, {ts})", bid)
            if default_id and bid == default_id:
                select_idx = idx
        if self._commercial_combo.count() > 0:
            self._commercial_combo.setCurrentIndex(select_idx)

    def _selected_commercial_batch(self) -> str:
        data = self._commercial_combo.currentData()
        return str(data or "")

    def _load_enterprise_batches(self, default_id: str) -> None:
        self._enterprise_combo.clear()
        self._enterprise_combo.addItem("(全部工商库)", "")
        client = SqliteClient()
        rows = client.query_all(
            """
            SELECT import_batch_id, COUNT(*), MAX(imported_at)
            FROM std_enterprise_profile
            GROUP BY import_batch_id
            ORDER BY MAX(imported_at) DESC
            LIMIT 40;
            """
        )
        select_idx = 0
        for idx, row in enumerate(rows, start=1):
            bid = str(row[0])
            cnt = int(row[1])
            label = f"{bid[:8]}… ({cnt} 条)"
            self._enterprise_combo.addItem(label, bid)
            if default_id and bid == default_id:
                select_idx = idx
        self._enterprise_combo.setCurrentIndex(select_idx)

    def _selected_enterprise_batch(self) -> str | None:
        data = self._enterprise_combo.currentData()
        if not data:
            return None
        return str(data)

    def _run_analysis(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        bid = self._selected_commercial_batch()
        if not bid:
            zh_information(self, "提示", "未找到可用商务网批次，请先处理商务网数据。")
            return
        eb = self._selected_enterprise_batch()
        self._run_btn.setEnabled(False)
        self._thread = QThread(self)
        self._worker = _RiskRunWorker(bid, eb)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished_ok.connect(self._on_run_ok)
        self._worker.failed.connect(self._on_run_fail)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_thread)
        self._thread.start()

    def _clear_thread(self) -> None:
        self._thread = None
        self._worker = None
        self._run_btn.setEnabled(True)

    def _on_run_ok(self, ev: int, sm: int) -> None:
        zh_information(self, "分析完成", f"风险事件 {ev} 条，企业汇总 {sm} 条。")
        self._refresh_tables()

    def _on_run_fail(self, msg: str) -> None:
        zh_critical(self, "分析失败", msg)

    def _refresh_tables(self) -> None:
        bid = self._selected_commercial_batch()
        if not bid:
            self._event_table.setRowCount(0)
            self._summary_table.setRowCount(0)
            return
        client = SqliteClient()
        ev = client.query_all(
            """
            SELECT rule_code, rule_name, risk_level, risk_score, enterprise_name, inquiry_no
            FROM ana_risk_event
            WHERE import_batch_id=?
            ORDER BY event_id DESC
            LIMIT 500;
            """,
            (bid,),
        )
        self._event_table.setRowCount(len(ev))
        for r, row in enumerate(ev):
            for c, val in enumerate(row):
                self._event_table.setItem(r, c, QTableWidgetItem(str(val)))
        sm = client.query_all(
            """
            SELECT enterprise_name, total_score, hit_count, risk_level, detail_json
            FROM ana_risk_summary
            WHERE import_batch_id=?
            ORDER BY total_score DESC
            LIMIT 200;
            """,
            (bid,),
        )
        self._summary_table.setRowCount(len(sm))
        for r, row in enumerate(sm):
            detail = {}
            try:
                import json

                detail = json.loads(str(row[4] or "{}"))
            except Exception:
                detail = {}
            data = [
                row[0],
                detail.get("participation_count", 0),
                detail.get("win_count", 0),
                detail.get("win_amount", 0),
                row[1],
                row[2],
                row[3],
            ]
            for c, val in enumerate(data):
                self._summary_table.setItem(r, c, QTableWidgetItem(str(val)))

    def _export_report(self) -> None:
        bid = self._selected_commercial_batch()
        if not bid:
            zh_information(self, "提示", "请先选择商务网批次。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出风险报告",
            f"风险报告_{bid.split('-')[0]}.xlsx",
            "Excel 工作簿 (*.xlsx)",
        )
        if not path:
            return
        out = CommercialRiskExportService().export_risk_report(bid, path)
        zh_information(self, "导出完成", out)


__all__ = ["CommercialRiskDialog"]
