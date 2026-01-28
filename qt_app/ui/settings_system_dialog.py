from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..db import connect
from .auto_combo import AutoComboBox


class SettingsSystemDialog(QtWidgets.QDialog):
    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Настройки системы")
        self.resize(920, 560)
        self.setModal(True)

        self._build_ui()
        self._load_all()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)

        # Institutions
        self.inst_page = QtWidgets.QWidget()
        self.tabs.addTab(self.inst_page, "Учреждения")
        self._build_institutions_tab()

        # Doctors
        self.doc_page = QtWidgets.QWidget()
        self.tabs.addTab(self.doc_page, "Врачи")
        self._build_doctors_tab()

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

    # ---------- Institutions ----------
    def _build_institutions_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.inst_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        btns = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("Добавить")
        edit = QtWidgets.QPushButton("Изменить")
        delete = QtWidgets.QPushButton("Удалить")
        add.clicked.connect(self._add_institution)
        edit.clicked.connect(self._edit_institution)
        delete.clicked.connect(self._delete_institution)
        btns.addWidget(add)
        btns.addWidget(edit)
        btns.addWidget(delete)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.inst_table = QtWidgets.QTableWidget(0, 3)
        self.inst_table.setHorizontalHeaderLabels(["ID", "Название", "Активен"])
        self.inst_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.inst_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inst_table.horizontalHeader().setStretchLastSection(True)
        self.inst_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.inst_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.inst_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.inst_table, 1)

    def _load_institutions(self) -> None:
        with connect() as conn:
            rows = conn.execute("SELECT id, name, is_active FROM institutions ORDER BY name").fetchall()
        self.inst_table.setRowCount(0)
        for r in rows:
            row = self.inst_table.rowCount()
            self.inst_table.insertRow(row)
            self.inst_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
            self.inst_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(r["name"])))
            self.inst_table.setItem(row, 2, QtWidgets.QTableWidgetItem("Да" if r["is_active"] else "Нет"))

    def _selected_id(self, table: QtWidgets.QTableWidget) -> int | None:
        row = table.currentRow()
        if row < 0:
            return None
        it = table.item(row, 0)
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

    def _add_institution(self) -> None:
        res = self._ask_name_active(title="Добавить учреждение")
        if not res:
            return
        name, active = res
        with connect() as conn:
            try:
                conn.execute("INSERT INTO institutions (name, is_active) VALUES (?, ?)", (name, 1 if active else 0))
                conn.commit()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось добавить: {e}")
                return
        self._load_all()

    def _edit_institution(self) -> None:
        inst_id = self._selected_id(self.inst_table)
        if not inst_id:
            return
        with connect() as conn:
            row = conn.execute("SELECT name, is_active FROM institutions WHERE id = ?", (inst_id,)).fetchone()
        if not row:
            return
        res = self._ask_name_active(title="Изменить учреждение", name=str(row["name"]), active=bool(row["is_active"]))
        if not res:
            return
        name, active = res
        with connect() as conn:
            conn.execute("UPDATE institutions SET name = ?, is_active = ? WHERE id = ?", (name, 1 if active else 0, inst_id))
            conn.commit()
        self._load_all()

    def _delete_institution(self) -> None:
        inst_id = self._selected_id(self.inst_table)
        if not inst_id:
            return
        if QtWidgets.QMessageBox.question(self, "Удалить", "Удалить выбранное учреждение?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        with connect() as conn:
            try:
                conn.execute("DELETE FROM institutions WHERE id = ?", (inst_id,))
                conn.commit()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                return
        self._load_all()

    # ---------- Doctors ----------
    def _build_doctors_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.doc_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Учреждение:"))
        self.doc_inst_filter = AutoComboBox(max_popup_items=30)
        self.doc_inst_filter.currentIndexChanged.connect(self._load_doctors)
        top.addWidget(self.doc_inst_filter, 1)
        layout.addLayout(top)

        btns = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("Добавить")
        edit = QtWidgets.QPushButton("Изменить")
        delete = QtWidgets.QPushButton("Удалить")
        add.clicked.connect(self._add_doctor)
        edit.clicked.connect(self._edit_doctor)
        delete.clicked.connect(self._delete_doctor)
        btns.addWidget(add)
        btns.addWidget(edit)
        btns.addWidget(delete)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.doc_table = QtWidgets.QTableWidget(0, 4)
        self.doc_table.setHorizontalHeaderLabels(["ID", "ФИО", "Учреждение", "Активен"])
        self.doc_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.doc_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.doc_table.horizontalHeader().setStretchLastSection(True)
        self.doc_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.doc_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.doc_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.doc_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.doc_table, 1)

    def _load_institution_combo(self, combo: QtWidgets.QComboBox) -> None:
        combo.blockSignals(True)
        combo.clear()
        with connect() as conn:
            rows = conn.execute("SELECT id, name FROM institutions ORDER BY name").fetchall()
        for r in rows:
            combo.addItem(str(r["name"]), int(r["id"]))
        combo.blockSignals(False)

    def _load_doctors(self) -> None:
        inst_id = self.doc_inst_filter.currentData()
        if not inst_id:
            self.doc_table.setRowCount(0)
            return
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.full_name, i.name AS inst_name, d.is_active
                FROM doctors d
                LEFT JOIN institutions i ON i.id = d.institution_id
                WHERE d.institution_id = ?
                ORDER BY d.full_name
                """,
                (int(inst_id),),
            ).fetchall()
        self.doc_table.setRowCount(0)
        for r in rows:
            row = self.doc_table.rowCount()
            self.doc_table.insertRow(row)
            self.doc_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
            self.doc_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(r["full_name"])))
            self.doc_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(r["inst_name"] or "")))
            self.doc_table.setItem(row, 3, QtWidgets.QTableWidgetItem("Да" if r["is_active"] else "Нет"))

    def _ask_doctor(self, *, title: str, name: str = "", active: bool = True) -> tuple[str, bool] | None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        # По замечанию: сделать окно шире, чтобы подписи/значения помещались
        dlg.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        name_edit = QtWidgets.QLineEdit(name)
        active_cb = QtWidgets.QCheckBox("Активный")
        active_cb.setChecked(active)
        form.addRow("ФИО:", name_edit)
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

    def _add_doctor(self) -> None:
        inst_id = self.doc_inst_filter.currentData()
        if not inst_id:
            return
        res = self._ask_doctor(title="Добавить врача")
        if not res:
            return
        name, active = res
        with connect() as conn:
            conn.execute(
                "INSERT INTO doctors (full_name, institution_id, is_active) VALUES (?, ?, ?)",
                (name, int(inst_id), 1 if active else 0),
            )
            conn.commit()
        self._load_all()

    def _edit_doctor(self) -> None:
        doc_id = self._selected_id(self.doc_table)
        if not doc_id:
            return
        with connect() as conn:
            row = conn.execute("SELECT full_name, is_active FROM doctors WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            return
        res = self._ask_doctor(title="Изменить врача", name=str(row["full_name"]), active=bool(row["is_active"]))
        if not res:
            return
        name, active = res
        with connect() as conn:
            conn.execute("UPDATE doctors SET full_name = ?, is_active = ? WHERE id = ?", (name, 1 if active else 0, doc_id))
            conn.commit()
        self._load_all()

    def _delete_doctor(self) -> None:
        doc_id = self._selected_id(self.doc_table)
        if not doc_id:
            return
        if QtWidgets.QMessageBox.question(self, "Удалить", "Удалить выбранного врача?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        with connect() as conn:
            conn.execute("DELETE FROM doctors WHERE id = ?", (doc_id,))
            conn.commit()
        self._load_all()

    # ---------- All ----------
    def _load_all(self) -> None:
        self._load_institutions()
        self._load_institution_combo(self.doc_inst_filter)
        self._load_doctors()
        self.changed.emit()

