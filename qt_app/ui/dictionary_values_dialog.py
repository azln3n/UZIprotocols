from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..repo import (
    DictionaryValueRow,
    create_dictionary_value,
    delete_dictionary_value,
    list_dictionary_values,
    move_dictionary_value,
    update_dictionary_value,
)
from .auto_combo import WrapAnywhereDelegate


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
        self.table.setItemDelegate(WrapAnywhereDelegate(self.table))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(28)
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
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(v.display_order)))
            it = QtWidgets.QTableWidgetItem(v.value)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, v.id)
            self.table.setItem(r, 1, it)
        self.table.resizeRowsToContents()

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

