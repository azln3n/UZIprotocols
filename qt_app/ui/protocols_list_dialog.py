from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..repo import ProtocolListItem, list_protocols_for_patient
from .protocol_view_dialog import ProtocolViewDialog


class ProtocolsListDialog(QtWidgets.QDialog):
    def __init__(self, *, patient_id: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.patient_id = patient_id
        self.setWindowTitle("Протоколы пациента")
        self.resize(720, 420)
        self.setModal(True)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Дата/время", "Исследование", "Подписан"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)
        self.table.cellDoubleClicked.connect(self._open_selected)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.setStyleSheet(
            "QPushButton { background: #e9ecef; color: black; border: 2px solid #9aa0a6; border-radius: 6px; padding: 6px 18px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        root.addLayout(btns)

        self._load()

    def _load(self) -> None:
        items = list_protocols_for_patient(self.patient_id)
        self.table.setRowCount(0)
        for it in items:
            self._add_row(it)

    def _add_row(self, it: ProtocolListItem) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(it.id)))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(it.finished_at or it.created_at))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(it.study_name))
        self.table.setItem(row, 3, QtWidgets.QTableWidgetItem("Да" if it.is_signed else "Нет"))

    @QtCore.Slot(int, int)
    def _open_selected(self, _row: int, _col: int) -> None:
        item = self.table.item(self.table.currentRow(), 0)
        if not item:
            return
        try:
            protocol_id = int(item.text())
        except ValueError:
            return
        ProtocolViewDialog(protocol_id=protocol_id, parent=self).exec()
