from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..db import connect


class AdmissionChannelsDialog(QtWidgets.QDialog):
    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Каналы поступления")
        self.resize(680, 420)
        self.setModal(True)

        self._build_ui()
        self._load_channels()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        btns = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("Добавить")
        edit = QtWidgets.QPushButton("Изменить")
        delete = QtWidgets.QPushButton("Удалить")
        add.clicked.connect(self._add_channel)
        edit.clicked.connect(self._edit_channel)
        delete.clicked.connect(self._delete_channel)
        btns.addWidget(add)
        btns.addWidget(edit)
        btns.addWidget(delete)
        btns.addStretch(1)
        root.addLayout(btns)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Название", "Активен"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)

        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.setStyleSheet(
            "QPushButton { background: #e9ecef; color: black; border: 2px solid #9aa0a6; border-radius: 6px; padding: 6px 18px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _load_channels(self) -> None:
        with connect() as conn:
            rows = conn.execute("SELECT id, name, is_active FROM admission_channels ORDER BY name").fetchall()
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(r["name"])))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem("Да" if r["is_active"] else "Нет"))

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        it = self.table.item(row, 0)
        if not it:
            return None
        try:
            return int(it.text())
        except ValueError:
            return None

    def _ask_name_active(self, *, title: str, name: str = "", active: bool = True) -> tuple[str, bool] | None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        # По замечанию: сделать окно шире, чтобы подписи/значения помещались
        dlg.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        name_edit = QtWidgets.QLineEdit(name)
        active_cb = QtWidgets.QCheckBox("Активный")
        active_cb.setChecked(active)
        form.addRow("Название:", name_edit)
        form.addRow("", active_cb)
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
        n = name_edit.text().strip()
        if not n:
            return None
        return n, bool(active_cb.isChecked())

    def _add_channel(self) -> None:
        res = self._ask_name_active(title="Добавить канал поступления")
        if not res:
            return
        name, active = res
        with connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO admission_channels (name, is_active) VALUES (?, ?)",
                    (name, 1 if active else 0),
                )
                conn.commit()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось добавить: {e}")
                return
        self._load_channels()
        self.changed.emit()

    def _edit_channel(self) -> None:
        ch_id = self._selected_id()
        if not ch_id:
            return
        with connect() as conn:
            row = conn.execute(
                "SELECT name, is_active FROM admission_channels WHERE id = ?",
                (ch_id,),
            ).fetchone()
        if not row:
            return
        res = self._ask_name_active(
            title="Изменить канал поступления",
            name=str(row["name"]),
            active=bool(row["is_active"]),
        )
        if not res:
            return
        name, active = res
        with connect() as conn:
            conn.execute(
                "UPDATE admission_channels SET name = ?, is_active = ? WHERE id = ?",
                (name, 1 if active else 0, ch_id),
            )
            conn.commit()
        self._load_channels()
        self.changed.emit()

    def _delete_channel(self) -> None:
        ch_id = self._selected_id()
        if not ch_id:
            return
        if (
            QtWidgets.QMessageBox.question(self, "Удалить", "Удалить выбранный канал поступления?")
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return
        with connect() as conn:
            try:
                conn.execute("DELETE FROM admission_channels WHERE id = ?", (ch_id,))
                conn.commit()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                return
        self._load_channels()
        self.changed.emit()
