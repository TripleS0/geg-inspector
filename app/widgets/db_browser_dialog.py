"""本地库表浏览：逐表预览、勾选删行、删表结构；消息框为中文按钮。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.shared.db.sqlite_client import SqliteClient
from app.widgets.zh_message_box import (
    zh_critical,
    zh_information,
    zh_question_yes_no,
    zh_warning,
)


def _display_field_name(sql_column: str) -> str:
    """预览表头：与导入 Excel 列名一致（去掉存储层 src_ 前缀）。"""
    if sql_column.startswith("src_"):
        return sql_column[4:]
    return sql_column


def _display_table_name(table_name: str) -> str:
    """左侧列表展示名：隐藏技术前缀 raw_，并把下划线替换为空格。"""
    text = table_name
    if text.startswith("raw_"):
        text = text[4:]
    return text.replace("_", " ")


class DbBrowserDialog(QDialog):
    """仅展示用户导入产生的数据表；左侧预览，右侧勾选删行；可删整张用户表并同步清理登记信息。"""

    def __init__(self, parent=None, client: SqliteClient | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("我的数据表")
        self.setMinimumSize(960, 560)
        self._client = client or SqliteClient()
        self._preview_rowids: list[int] = []
        self._current_table = ""

        root = QVBoxLayout(self)
        self._path_label = QLabel()
        self._path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._path_label)

        hint = QLabel(
            "说明：此处只列出您导入 Excel 后生成的数据表（一般形如「原文件名_工作表名」）。"
            "系统内部的 meta 登记表、标准层汇总表等不会出现在列表中。"
            "预览仅显示您表格里的业务列（与 Excel 列名一致），不包含流水号、批次号、整行 JSON 等系统字段。"
            "预览为抽样行数，非全表。删除行请勾选行首方框后点「删除勾选行」。"
            "「删除表结构」将删除整张用户表并清除与之关联的模板登记（标准层历史行仍保留，如需一并清理请另行处理）。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        root.addWidget(hint)

        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("刷新表列表")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        toolbar.addWidget(refresh_btn)

        toolbar.addWidget(QLabel("预览行数："))
        self._limit_spin = QSpinBox()
        self._limit_spin.setRange(50, 2000)
        self._limit_spin.setSingleStep(50)
        self._limit_spin.setValue(200)
        self._limit_spin.valueChanged.connect(self._on_limit_changed)
        toolbar.addWidget(self._limit_spin)

        self._reload_preview_btn = QPushButton("刷新当前预览")
        self._reload_preview_btn.setToolTip("重新加载当前已选表的预览数据。")
        self._reload_preview_btn.clicked.connect(self._reload_preview_clicked)
        toolbar.addWidget(self._reload_preview_btn)

        self._check_all_btn = QPushButton("本页全选")
        self._check_all_btn.setObjectName("secondaryButton")
        self._check_all_btn.clicked.connect(self._check_all_visible)
        toolbar.addWidget(self._check_all_btn)

        self._uncheck_all_btn = QPushButton("本页取消勾选")
        self._uncheck_all_btn.setObjectName("secondaryButton")
        self._uncheck_all_btn.clicked.connect(self._uncheck_all_visible)
        toolbar.addWidget(self._uncheck_all_btn)

        self._delete_btn = QPushButton("删除勾选行")
        self._delete_btn.setToolTip("删除当前预览中已勾选方框的行（删除前确认）。")
        self._delete_btn.clicked.connect(self._delete_selected_rows)
        toolbar.addWidget(self._delete_btn)

        self._drop_table_btn = QPushButton("删除表结构")
        self._drop_table_btn.setToolTip(
            "对当前正在预览的表执行删表（DROP TABLE），表结构与全部数据永久删除；需两次确认。"
        )
        self._drop_table_btn.clicked.connect(self._drop_table_structure)
        toolbar.addWidget(self._drop_table_btn)

        self._count_label = QLabel("点击左侧某表的「预览」查看数据。")
        toolbar.addWidget(self._count_label, 1)
        root.addLayout(toolbar)

        body = QHBoxLayout()
        body.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumWidth(300)
        scroll.setMinimumWidth(240)

        self._tables_host = QWidget()
        self._tables_layout = QVBoxLayout(self._tables_host)
        self._tables_layout.setContentsMargins(8, 8, 8, 8)
        self._tables_layout.setSpacing(6)
        self._tables_layout.addStretch(1)
        scroll.setWidget(self._tables_host)
        body.addWidget(scroll)

        right = QVBoxLayout()
        self._grid = QTableWidget()
        self._grid.setAlternatingRowColors(True)
        self._grid.setEditTriggers(self._grid.EditTrigger.NoEditTriggers)
        self._grid.setSelectionMode(self._grid.SelectionMode.NoSelection)
        right.addWidget(self._grid, 1)
        body.addLayout(right, 1)

        root.addLayout(body, 1)

        buttons = QDialogButtonBox()
        close_btn = buttons.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole)
        close_btn.clicked.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_table_list()

    def _on_limit_changed(self) -> None:
        if self._current_table:
            self._load_current_table()

    def _reload_preview_clicked(self) -> None:
        if not self._current_table:
            zh_information(self, "提示", "请先在左侧点击某个表的「预览」。")
            return
        self._load_current_table()

    def _on_refresh_clicked(self) -> None:
        self._refresh_table_list()

    def _clear_tables_layout(self) -> None:
        while self._tables_layout.count() > 1:
            item = self._tables_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_table_rows(self, tables: list[str]) -> None:
        self._clear_tables_layout()
        for name in tables:
            row = QWidget()
            row.setProperty("tableName", name)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 4, 6, 4)
            row_layout.setSpacing(8)

            name_label = QLabel(_display_table_name(name))
            name_label.setWordWrap(True)
            name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(name_label, 1)

            preview_btn = QPushButton("预览")
            preview_btn.setFixedWidth(64)
            preview_btn.clicked.connect(lambda _=False, t=name: self._on_preview_table(t))
            row_layout.addWidget(preview_btn)

            self._tables_layout.insertWidget(self._tables_layout.count() - 1, row)

    def _highlight_active_row(self) -> None:
        for i in range(self._tables_layout.count() - 1):
            item = self._tables_layout.itemAt(i)
            widget = item.widget()
            if widget is None:
                continue
            t = widget.property("tableName")
            if t == self._current_table:
                widget.setStyleSheet(
                    "QWidget { background-color: rgba(0, 90, 200, 0.10); border-radius: 6px; }"
                )
            else:
                widget.setStyleSheet("")

    def _on_preview_table(self, table_name: str) -> None:
        self._current_table = table_name
        self._highlight_active_row()
        self._load_current_table()

    def _refresh_table_list(self) -> None:
        self._path_label.setText(f"数据文件位置：{self._client.db_path}")
        previous = self._current_table
        try:
            tables = self._client.list_user_upload_tables()
        except Exception as err:
            zh_warning(self, "读取失败", str(err))
            tables = []

        self._rebuild_table_rows(tables)

        if not tables:
            self._current_table = ""
            self._preview_rowids = []
            self._grid.clear()
            self._grid.setRowCount(0)
            self._grid.setColumnCount(0)
            self._count_label.setText("（暂无已登记的用户数据表，请先「初始化数据库」并导入 Excel）")
            return

        if previous in tables:
            self._current_table = previous
            self._highlight_active_row()
            self._load_current_table()
        else:
            self._current_table = tables[0]
            self._highlight_active_row()
            self._load_current_table()

    def _load_current_table(self) -> None:
        table = self._current_table.strip()
        if not table:
            return
        limit = self._limit_spin.value()
        try:
            total = self._client.count_table_rows(table)
            cols, rowids, rows = self._client.fetch_table_preview_with_rowids(
                table, limit=limit, offset=0, source_columns_only=True
            )
        except Exception as err:
            zh_warning(self, "加载失败", str(err))
            return

        self._preview_rowids = rowids
        shown = min(limit, total)
        self._count_label.setText(
            f"当前表：{_display_table_name(table)} ｜ 总行数：{total} ｜ 预览前 {shown} 行（可调预览行数后自动刷新）"
        )

        headers = [""] + [_display_field_name(c) for c in cols]
        self._grid.clear()
        self._grid.setColumnCount(len(headers))
        self._grid.setHorizontalHeaderLabels(headers)
        self._grid.setRowCount(len(rows))

        header = self._grid.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._grid.setColumnWidth(0, 44)

        base_flags = (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
        )
        for r, tup in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(base_flags)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self._grid.setItem(r, 0, chk)
            for c, value in enumerate(tup):
                text = "" if value is None else str(value)
                cell = QTableWidgetItem(text)
                cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                cell.setToolTip(text if len(text) > 200 else "")
                self._grid.setItem(r, c + 1, cell)
        self._grid.resizeColumnsToContents()
        self._grid.setColumnWidth(0, 44)

    def _check_all_visible(self) -> None:
        for r in range(self._grid.rowCount()):
            item = self._grid.item(r, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)

    def _uncheck_all_visible(self) -> None:
        for r in range(self._grid.rowCount()):
            item = self._grid.item(r, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)

    def _delete_selected_rows(self) -> None:
        table = self._current_table.strip()
        if not table:
            zh_information(self, "提示", "请先点击左侧某表的「预览」加载数据。")
            return

        rowids: list[int] = []
        for r in range(self._grid.rowCount()):
            item = self._grid.item(r, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            if 0 <= r < len(self._preview_rowids):
                rowids.append(self._preview_rowids[r])

        if not rowids:
            zh_information(self, "提示", "请先勾选要删除的行（行首小方框）。")
            return

        if not zh_question_yes_no(
            self,
            "确认删除",
            f"确定从表「{table}」删除已勾选的 {len(rowids)} 行吗？\n此操作不可撤销。",
        ):
            return

        try:
            deleted = self._client.delete_rows_by_rowid(table, rowids)
        except Exception as err:
            zh_critical(self, "删除失败", str(err))
            return

        zh_information(self, "删除完成", f"已删除 {deleted} 行。")
        self._load_current_table()

    def _drop_table_structure(self) -> None:
        """DROP TABLE for current preview table; two Chinese confirmations."""
        table = self._current_table.strip()
        if not table:
            zh_information(self, "提示", "请先在左侧点击某个表的「预览」，以指定要删除结构的表。")
            return

        if not zh_question_yes_no(
            self,
            "确认删表",
            f"将对表「{table}」执行删表（DROP TABLE）。\n"
            "该表中的全部数据以及表结构都会被永久删除，且不可恢复。\n\n是否继续？",
        ):
            return

        if not zh_question_yes_no(
            self,
            "再次确认",
            f"最后确认：是否删除表「{table}」及其登记信息？\n删除后需重新导入相同 Excel 才会再次生成该版式数据表。",
        ):
            return

        try:
            self._client.drop_user_upload_table(table)
        except Exception as err:
            zh_critical(self, "删表失败", str(err))
            return

        zh_information(self, "已完成", f"表「{table}」已从数据库中删除。")
        self._current_table = ""
        self._preview_rowids = []
        self._refresh_table_list()
