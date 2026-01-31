from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..repo import (
    DictionaryValueRow,
    create_dictionary_value,
    delete_dictionary_value,
    list_dictionary_values,
    move_dictionary_value,
    update_dictionary_value,
)
from .auto_combo import WrapAnywhereDelegate


class _TableWrapDelegate(WrapAnywhereDelegate):
    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index) -> QtCore.QSize:
        try:
            opt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            view = opt.widget
            if isinstance(view, QtWidgets.QTableView):
                try:
                    width = int(view.columnWidth(index.column()))
                except Exception:
                    width = int(opt.rect.width() or 0)
            else:
                width = int(opt.rect.width() or 0)
            width = max(60, width)
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(opt.font)
            to = QtGui.QTextOption()
            to.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            doc.setDefaultTextOption(to)
            doc.setPlainText(opt.text)
            doc.setTextWidth(width)
            height = int(doc.size().height()) + 6
            line_h = opt.fontMetrics().height()
            return QtCore.QSize(width, max(height, line_h + 6))
        except Exception:
            return super().sizeHint(option, index)


class DictionaryValuesDialog(QtWidgets.QDialog):
    changed = QtCore.Signal()

    def __init__(self, *, field_id: int, field_name: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.field_id = field_id
        self.setWindowTitle(f"Значения — {field_name}")
        self.resize(560, 420)
        self.setModal(True)

        self._values: list[DictionaryValueRow] = []

        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Добавить")
        edit_btn = QtWidgets.QPushButton("Изменить")
        del_btn = QtWidgets.QPushButton("Удалить")
        up_btn = QtWidgets.QPushButton("↑")
        down_btn = QtWidgets.QPushButton("↓")

        add_btn.clicked.connect(self._add)
        edit_btn.clicked.connect(self._edit)
        del_btn.clicked.connect(self._delete)
        up_btn.clicked.connect(lambda: self._move(-1))
        down_btn.clicked.connect(lambda: self._move(+1))

        btns.addWidget(add_btn)
        btns.addWidget(edit_btn)
        btns.addWidget(del_btn)
        btns.addStretch(1)
        btns.addWidget(up_btn)
        btns.addWidget(down_btn)
        root.addLayout(btns)

        self.table = QtWidgets.QTableWidget(0, 2)
        table_font = self.table.font()
        table_font.setPointSize(11)
        self.table.setFont(table_font)
        self.table.setHorizontalHeaderLabels(["Порядок", "Значение"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        self.table.setItemDelegateForColumn(1, _TableWrapDelegate(self.table))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        try:
            self.table.horizontalHeader().sectionResized.connect(
                lambda *_: QtCore.QTimer.singleShot(0, self._refresh_row_heights)
            )
        except Exception:
            pass
        if self.table.viewport() is not None:
            self.table.viewport().installEventFilter(self)
        root.addWidget(self.table, 1)

        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        close = QtWidgets.QPushButton("Закрыть")
        close.setStyleSheet(
            "QPushButton { background: #e9ecef; color: black; border: 2px solid #9aa0a6; border-radius: 6px; padding: 6px 18px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

    def _reload(self) -> None:
        self._values = list_dictionary_values(self.field_id)
        self.table.setRowCount(0)
        for v in self._values:
            r = self.table.rowCount()
            self.table.insertRow(r)
            it_order = QtWidgets.QTableWidgetItem(str(v.display_order))
            it_order.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
            self.table.setItem(r, 0, it_order)
            it = QtWidgets.QTableWidgetItem(v.value)
            it.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, v.id)
            self.table.setItem(r, 1, it)
        self._refresh_row_heights()


    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        if obj is self.table.viewport() and event.type() == QtCore.QEvent.Type.Resize:
            QtCore.QTimer.singleShot(0, self._refresh_row_heights)
        return super().eventFilter(obj, event)

    def _refresh_row_heights(self) -> None:
        try:
            col_w = int(self.table.columnWidth(1) or 0)
            col_w = max(60, col_w)
            fm = self.table.fontMetrics()
            min_h = fm.height() + 6
            for row in range(self.table.rowCount()):
                it = self.table.item(row, 1)
                if it is None:
                    continue
                h = self._row_height_for_text(it.text(), col_w)
                self.table.setRowHeight(row, max(min_h, h))
        except Exception:
            pass

    def _row_height_for_text(self, text: str, width: int) -> int:
        try:
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(self.table.font())
            to = QtGui.QTextOption()
            to.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            doc.setDefaultTextOption(to)
            doc.setPlainText(text or "")
            doc.setTextWidth(max(1, int(width) - 6))
            return int(doc.size().height()) + 6
        except Exception:
            return 24

    def _current_value(self) -> DictionaryValueRow | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        it = self.table.item(row, 1)
        if not it:
            return None
        vid = int(it.data(QtCore.Qt.ItemDataRole.UserRole))
        return next((x for x in self._values if x.id == vid), None)

    def _ask_value(self, *, title: str, default: str = "") -> str | None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(520)
        dlg.setMinimumHeight(220)
        layout = QtWidgets.QVBoxLayout(dlg)

        form = QtWidgets.QFormLayout()
        edit = QtWidgets.QPlainTextEdit()
        edit.setPlainText(default)
        edit.setMinimumHeight(90)
        form.addRow("Значение:", edit)
        layout.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        ok = QtWidgets.QPushButton("OK")
        cancel = QtWidgets.QPushButton("Отмена")
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return edit.toPlainText().strip() or None

    def _add(self) -> None:
        val = self._ask_value(title="Добавить значение")
        if not val:
            return
        create_dictionary_value(self.field_id, val)
        self._reload()
        self.changed.emit()

    def _edit(self) -> None:
        cur = self._current_value()
        if not cur:
            return
        val = self._ask_value(title="Изменить значение", default=cur.value)
        if not val:
            return
        update_dictionary_value(cur.id, val)
        self._reload()
        self.changed.emit()

    def _delete(self) -> None:
        cur = self._current_value()
        if not cur:
            return
        if QtWidgets.QMessageBox.question(self, "Удалить", f"Удалить значение '{cur.value}'?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        delete_dictionary_value(cur.id)
        self._reload()
        self.changed.emit()

    def _move(self, direction: int) -> None:
        cur = self._current_value()
        if not cur:
            return
        move_dictionary_value(cur.id, direction)
        self._reload()
        self.changed.emit()

