from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..repo import (
    StudyTypeRow,
    TabRow,
    GroupRow,
    FieldRow,
    create_study_type,
    create_tab,
    create_group,
    create_field,
    delete_study_type,
    delete_tab,
    delete_group,
    delete_field,
    list_study_types_all,
    list_tabs,
    list_groups,
    list_fields,
    move_study_type,
    move_tab,
    move_group,
    move_field,
    update_study_type,
    update_tab,
    update_group,
    update_field,
)
from .dictionary_values_dialog import DictionaryValuesDialog


class SettingsStructureDialog(QtWidgets.QDialog):
    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Настройки — структура протокола")
        self.resize(980, 620)
        self.setModal(True)

        self._study_types: list[StudyTypeRow] = []
        self._tabs: list[TabRow] = []
        self._groups: list[GroupRow] = []
        self._fields: list[FieldRow] = []
        self._current_study_type_id: int | None = None
        self._current_tab_id: int | None = None
        self._current_group_id: int | None = None

        self._build_ui()
        self._reload_studies(select_first=True)

    def _build_ui(self) -> None:
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ===== Left: studies =====
        left = QtWidgets.QWidget()
        left.setMinimumWidth(320)
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)

        title = QtWidgets.QLabel("Типы исследований")
        f = title.font()
        f.setBold(True)
        f.setPointSize(12)
        title.setFont(f)
        ll.addWidget(title)

        # Buttons (2 rows): top = add/edit, bottom = delete + arrows
        btns = QtWidgets.QVBoxLayout()
        btns.setSpacing(6)
        self.add_study_btn = QtWidgets.QPushButton("Добавить")
        self.edit_study_btn = QtWidgets.QPushButton("Изменить")
        self.del_study_btn = QtWidgets.QPushButton("Удалить")
        self.up_study_btn = QtWidgets.QPushButton("↑")
        self.down_study_btn = QtWidgets.QPushButton("↓")

        self.add_study_btn.clicked.connect(self._add_study)
        self.edit_study_btn.clicked.connect(self._edit_study)
        self.del_study_btn.clicked.connect(self._delete_study)
        self.up_study_btn.clicked.connect(lambda: self._move_study(-1))
        self.down_study_btn.clicked.connect(lambda: self._move_study(+1))

        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self.add_study_btn)
        row1.addWidget(self.edit_study_btn)
        self._equalize_buttons([self.add_study_btn, self.edit_study_btn])
        row1.addStretch(1)

        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(self.del_study_btn)
        row2.addWidget(self.up_study_btn)
        row2.addWidget(self.down_study_btn)
        row2.addStretch(1)

        btns.addLayout(row1)
        btns.addLayout(row2)
        ll.addLayout(btns)

        self.study_list = QtWidgets.QListWidget()
        self.study_list.itemSelectionChanged.connect(self._on_study_selected)
        ll.addWidget(self.study_list, 1)

        root.addWidget(left, 0)

        # ===== Right: tabs for selected study =====
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        self.study_header = QtWidgets.QLabel("Вкладки")
        f2 = self.study_header.font()
        f2.setBold(True)
        f2.setPointSize(12)
        self.study_header.setFont(f2)
        rl.addWidget(self.study_header)

        tab_btns = QtWidgets.QHBoxLayout()
        tab_btns.setSpacing(10)
        self.add_tab_btn = QtWidgets.QPushButton("Добавить вкладку")
        self.edit_tab_btn = QtWidgets.QPushButton("Изменить")
        self.del_tab_btn = QtWidgets.QPushButton("Удалить")
        self.left_tab_btn = QtWidgets.QPushButton("←")
        self.right_tab_btn = QtWidgets.QPushButton("→")

        self.add_tab_btn.clicked.connect(self._add_tab)
        self.edit_tab_btn.clicked.connect(self._edit_tab)
        self.del_tab_btn.clicked.connect(self._delete_tab)
        self.left_tab_btn.clicked.connect(lambda: self._move_tab(-1))
        self.right_tab_btn.clicked.connect(lambda: self._move_tab(+1))

        tab_btns.addWidget(self.add_tab_btn)
        tab_btns.addWidget(self.edit_tab_btn)
        tab_btns.addWidget(self.del_tab_btn)
        self._equalize_buttons([self.add_tab_btn, self.edit_tab_btn, self.del_tab_btn])
        tab_btns.addStretch(1)
        tab_btns.addWidget(self.left_tab_btn)
        tab_btns.addWidget(self.right_tab_btn)
        rl.addLayout(tab_btns)

        self.tabs_table = QtWidgets.QTableWidget(0, 2)
        self.tabs_table.setHorizontalHeaderLabels(["Порядок", "Название"])
        self.tabs_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabs_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabs_table.horizontalHeader().setStretchLastSection(True)
        self.tabs_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tabs_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tabs_table.itemSelectionChanged.connect(self._on_tab_selected)

        groups_widget = QtWidgets.QWidget()
        gl = QtWidgets.QVBoxLayout(groups_widget)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)

        g_title = QtWidgets.QLabel("Группы (для выбранной вкладки)")
        g_title.setStyleSheet("font-weight: bold;")
        gl.addWidget(g_title)

        g_btns = QtWidgets.QHBoxLayout()
        g_btns.setSpacing(10)
        self.add_group_btn = QtWidgets.QPushButton("Добавить группу")
        self.edit_group_btn = QtWidgets.QPushButton("Изменить")
        self.del_group_btn = QtWidgets.QPushButton("Удалить")
        self.up_group_btn = QtWidgets.QPushButton("↑")
        self.down_group_btn = QtWidgets.QPushButton("↓")
        self.add_group_btn.clicked.connect(self._add_group)
        self.edit_group_btn.clicked.connect(self._edit_group)
        self.del_group_btn.clicked.connect(self._delete_group)
        self.up_group_btn.clicked.connect(lambda: self._move_group(-1))
        self.down_group_btn.clicked.connect(lambda: self._move_group(+1))
        g_btns.addWidget(self.add_group_btn)
        g_btns.addWidget(self.edit_group_btn)
        g_btns.addWidget(self.del_group_btn)
        self._equalize_buttons([self.add_group_btn, self.edit_group_btn, self.del_group_btn])
        g_btns.addStretch(1)
        g_btns.addWidget(self.up_group_btn)
        g_btns.addWidget(self.down_group_btn)
        gl.addLayout(g_btns)

        self.groups_table = QtWidgets.QTableWidget(0, 3)
        self.groups_table.setHorizontalHeaderLabels(["Порядок", "Название", "По умолч. раскрыта"])
        self.groups_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.groups_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.groups_table.horizontalHeader().setStretchLastSection(True)
        self.groups_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.groups_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.groups_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.groups_table.itemSelectionChanged.connect(self._on_group_selected)
        gl.addWidget(self.groups_table, 1)

        fields_widget = QtWidgets.QWidget()
        fl = QtWidgets.QVBoxLayout(fields_widget)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)

        f_title = QtWidgets.QLabel("Поля (для выбранной группы)")
        f_title.setStyleSheet("font-weight: bold;")
        fl.addWidget(f_title)

        f_btns = QtWidgets.QHBoxLayout()
        f_btns.setSpacing(10)
        self.add_field_btn = QtWidgets.QPushButton("Добавить поле")
        self.edit_field_btn = QtWidgets.QPushButton("Изменить")
        self.del_field_btn = QtWidgets.QPushButton("Удалить")
        self.values_btn = QtWidgets.QPushButton("Значения…")
        self.up_field_btn = QtWidgets.QPushButton("↑")
        self.down_field_btn = QtWidgets.QPushButton("↓")
        self.add_field_btn.clicked.connect(self._add_field)
        self.edit_field_btn.clicked.connect(self._edit_field)
        self.del_field_btn.clicked.connect(self._delete_field)
        self.values_btn.clicked.connect(self._edit_dictionary_values)
        self.up_field_btn.clicked.connect(lambda: self._move_field(-1))
        self.down_field_btn.clicked.connect(lambda: self._move_field(+1))
        f_btns.addWidget(self.add_field_btn)
        f_btns.addWidget(self.edit_field_btn)
        f_btns.addWidget(self.del_field_btn)
        f_btns.addWidget(self.values_btn)
        self._equalize_buttons([self.add_field_btn, self.edit_field_btn, self.del_field_btn, self.values_btn])
        f_btns.addStretch(1)
        f_btns.addWidget(self.up_field_btn)
        f_btns.addWidget(self.down_field_btn)
        fl.addLayout(f_btns)

        self.fields_table = QtWidgets.QTableWidget(0, 7)
        self.fields_table.setHorizontalHeaderLabels(["Кол", "Порядок", "Название", "Тег", "Тип", "Req", "Hidden"])
        self.fields_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.fields_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fields_table.horizontalHeader().setStretchLastSection(True)
        self.fields_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.fields_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.fields_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.fields_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.fields_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.fields_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.fields_table.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        fl.addWidget(self.fields_table, 1)
        # Важно: иначе кнопки "Изменить/Удалить/Значения" не активируются при выборе поля.
        self.fields_table.itemSelectionChanged.connect(self._on_field_selected)

        # Один общий вертикальный splitter.
        # По просьбе: поменять местами размеры секций "Вкладки" и "Группы".
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(self.tabs_table)
        main_splitter.addWidget(groups_widget)
        main_splitter.addWidget(fields_widget)
        # tabs smaller, groups larger, fields medium
        main_splitter.setSizes([180, 280, 220])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setStretchFactor(2, 1)
        rl.addWidget(main_splitter, 1)

        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.setStyleSheet(
            "QPushButton { background: #e9ecef; color: black; border: 2px solid #9aa0a6; border-radius: 6px; padding: 6px 18px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        rl.addLayout(footer)

        root.addWidget(right, 1)

        self._refresh_buttons()

    @QtCore.Slot()
    def _on_field_selected(self) -> None:
        self._refresh_buttons()

    def _equalize_buttons(self, btns: list[QtWidgets.QAbstractButton]) -> None:
        """
        Делает кнопки одинаковой ширины (по максимальному sizeHint),
        чтобы "Добавить/Изменить/Удалить" выглядели ровно.
        """
        if not btns:
            return
        maxw = max(b.sizeHint().width() for b in btns)
        for b in btns:
            b.setMinimumWidth(maxw)

    # ---------- Studies ----------
    def _reload_studies(self, *, select_first: bool = False, select_id: int | None = None) -> None:
        self._study_types = list_study_types_all()
        self.study_list.clear()
        for st in self._study_types:
            txt = st.name + ("" if st.is_active else " (неактивен)")
            it = QtWidgets.QListWidgetItem(txt)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, st.id)
            self.study_list.addItem(it)

        if select_id:
            for i in range(self.study_list.count()):
                if int(self.study_list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)) == int(select_id):
                    self.study_list.setCurrentRow(i)
                    return
        if select_first and self.study_list.count() > 0:
            self.study_list.setCurrentRow(0)

    def _current_study(self) -> StudyTypeRow | None:
        item = self.study_list.currentItem()
        if not item:
            return None
        sid = int(item.data(QtCore.Qt.ItemDataRole.UserRole))
        return next((s for s in self._study_types if s.id == sid), None)

    @QtCore.Slot()
    def _on_study_selected(self) -> None:
        st = self._current_study()
        self._current_study_type_id = st.id if st else None
        self._reload_tabs()
        self._current_tab_id = None
        self._current_group_id = None
        self._reload_groups()
        self._reload_fields()
        self._refresh_buttons()

    def _ask_study_dialog(self, *, title: str, default_name: str = "", default_active: bool = True) -> tuple[str, bool] | None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        layout = QtWidgets.QVBoxLayout(dlg)

        form = QtWidgets.QFormLayout()
        name = QtWidgets.QLineEdit(default_name)
        active = QtWidgets.QCheckBox("Активный")
        active.setChecked(default_active)
        form.addRow("Название:", name)
        form.addRow("", active)
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
        n = name.text().strip()
        if not n:
            return None
        return n, bool(active.isChecked())

    def _add_study(self) -> None:
        res = self._ask_study_dialog(title="Добавить тип исследования")
        if not res:
            return
        name, is_active = res
        try:
            new_id = create_study_type(name, is_active=is_active)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось создать: {e}")
            return
        self._reload_studies(select_id=new_id)
        self.changed.emit()

    def _edit_study(self) -> None:
        st = self._current_study()
        if not st:
            return
        res = self._ask_study_dialog(title="Изменить тип исследования", default_name=st.name, default_active=st.is_active)
        if not res:
            return
        name, is_active = res
        try:
            update_study_type(st.id, name=name, is_active=is_active)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось обновить: {e}")
            return
        self._reload_studies(select_id=st.id)
        self.changed.emit()

    def _delete_study(self) -> None:
        st = self._current_study()
        if not st:
            return
        if QtWidgets.QMessageBox.question(self, "Удалить", f"Удалить тип исследования '{st.name}'?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            delete_study_type(st.id)
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Нельзя удалить", str(e))
            return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            return
        self._reload_studies(select_first=True)
        self.changed.emit()

    def _move_study(self, direction: int) -> None:
        st = self._current_study()
        if not st:
            return
        move_study_type(st.id, direction)
        self._reload_studies(select_id=st.id)
        self.changed.emit()

    # ---------- Tabs ----------
    def _reload_tabs(self) -> None:
        self.tabs_table.setRowCount(0)
        st_id = self._current_study_type_id
        if not st_id:
            self.study_header.setText("Вкладки")
            self._tabs = []
            return
        st = self._current_study()
        self.study_header.setText(f"Вкладки — {st.name}" if st else "Вкладки")
        self._tabs = list_tabs(st_id)
        for t in self._tabs:
            row = self.tabs_table.rowCount()
            self.tabs_table.insertRow(row)
            self.tabs_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(t.display_order)))
            it = QtWidgets.QTableWidgetItem(t.name)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, t.id)
            self.tabs_table.setItem(row, 1, it)

    @QtCore.Slot()
    def _on_tab_selected(self) -> None:
        self._current_tab_id = self._current_tab_id_from_table()
        self._current_group_id = None
        self._reload_groups()
        self._reload_fields()
        self._refresh_buttons()

    def _current_tab_id_from_table(self) -> int | None:
        row = self.tabs_table.currentRow()
        if row < 0:
            return None
        item = self.tabs_table.item(row, 1)
        if not item:
            return None
        return int(item.data(QtCore.Qt.ItemDataRole.UserRole))

    def _ask_tab_name(self, *, title: str, default: str = "") -> str | None:
        text, ok = QtWidgets.QInputDialog.getText(self, title, "Название вкладки:", text=default)
        if not ok:
            return None
        name = str(text).strip()
        return name or None

    def _add_tab(self) -> None:
        st_id = self._current_study_type_id
        if not st_id:
            return
        name = self._ask_tab_name(title="Добавить вкладку")
        if not name:
            return
        try:
            create_tab(st_id, name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось создать вкладку: {e}")
            return
        self._reload_tabs()
        self.changed.emit()

    def _edit_tab(self) -> None:
        tab_id = self._current_tab_id_from_table()
        if not tab_id:
            return
        tab = next((t for t in self._tabs if t.id == tab_id), None)
        if not tab:
            return
        name = self._ask_tab_name(title="Изменить вкладку", default=tab.name)
        if not name:
            return
        try:
            update_tab(tab_id, name=name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось обновить: {e}")
            return
        self._reload_tabs()
        self.changed.emit()

    def _delete_tab(self) -> None:
        tab_id = self._current_tab_id_from_table()
        if not tab_id:
            return
        tab = next((t for t in self._tabs if t.id == tab_id), None)
        if not tab:
            return
        if QtWidgets.QMessageBox.question(self, "Удалить", f"Удалить вкладку '{tab.name}'?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            delete_tab(tab_id)
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Нельзя удалить", str(e))
            return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            return
        self._reload_tabs()
        self.changed.emit()

    def _move_tab(self, direction: int) -> None:
        tab_id = self._current_tab_id_from_table()
        if not tab_id:
            return
        move_tab(tab_id, direction)
        self._reload_tabs()
        self.changed.emit()

    def _refresh_buttons(self) -> None:
        has_study = self._current_study() is not None
        self.edit_study_btn.setEnabled(has_study)
        self.del_study_btn.setEnabled(has_study)
        self.up_study_btn.setEnabled(has_study)
        self.down_study_btn.setEnabled(has_study)

        has_tab = self._current_tab_id_from_table() is not None
        self.add_tab_btn.setEnabled(has_study)
        self.edit_tab_btn.setEnabled(has_tab)
        self.del_tab_btn.setEnabled(has_tab)
        self.left_tab_btn.setEnabled(has_tab)
        self.right_tab_btn.setEnabled(has_tab)

        has_group = self._current_group_id is not None
        self.add_group_btn.setEnabled(has_tab)
        self.edit_group_btn.setEnabled(has_group)
        self.del_group_btn.setEnabled(has_group)
        self.up_group_btn.setEnabled(has_group)
        self.down_group_btn.setEnabled(has_group)

        has_field = self._current_field() is not None
        self.add_field_btn.setEnabled(has_group)
        self.edit_field_btn.setEnabled(has_field)
        self.del_field_btn.setEnabled(has_field)
        self.up_field_btn.setEnabled(has_field)
        self.down_field_btn.setEnabled(has_field)
        # значения доступны для словарь/шаблон
        f = self._current_field()
        self.values_btn.setEnabled(bool(f and f.field_type in ("словарь", "шаблон")))

    # ---------- Groups ----------
    def _reload_groups(self) -> None:
        self.groups_table.setRowCount(0)
        self._groups = []
        if not self._current_tab_id:
            return
        self._groups = list_groups(self._current_tab_id)
        for g in self._groups:
            r = self.groups_table.rowCount()
            self.groups_table.insertRow(r)
            self.groups_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(g.display_order)))
            it = QtWidgets.QTableWidgetItem(g.name)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, g.id)
            self.groups_table.setItem(r, 1, it)
            self.groups_table.setItem(r, 2, QtWidgets.QTableWidgetItem("Да" if g.is_expanded_by_default else "Нет"))

    def _current_group(self) -> GroupRow | None:
        if not self._current_group_id:
            return None
        return next((g for g in self._groups if g.id == self._current_group_id), None)

    @QtCore.Slot()
    def _on_group_selected(self) -> None:
        row = self.groups_table.currentRow()
        if row < 0:
            self._current_group_id = None
        else:
            it = self.groups_table.item(row, 1)
            self._current_group_id = int(it.data(QtCore.Qt.ItemDataRole.UserRole)) if it else None
        self._reload_fields()
        self._refresh_buttons()

    def _ask_group(self, *, title: str, default_name: str = "", default_expanded: bool = False) -> tuple[str, bool] | None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        layout = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        name = QtWidgets.QLineEdit(default_name)
        expanded = QtWidgets.QCheckBox("Раскрыта по умолчанию")
        expanded.setChecked(default_expanded)
        form.addRow("Название:", name)
        form.addRow("", expanded)
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
        n = name.text().strip()
        if not n:
            return None
        return n, bool(expanded.isChecked())

    def _add_group(self) -> None:
        if not self._current_tab_id:
            return
        res = self._ask_group(title="Добавить группу")
        if not res:
            return
        name, expanded = res
        try:
            gid = create_group(self._current_tab_id, name, is_expanded_by_default=expanded)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось создать группу: {e}")
            return
        self._reload_groups()
        self._current_group_id = gid
        self._reload_fields()
        self.changed.emit()

    def _edit_group(self) -> None:
        g = self._current_group()
        if not g:
            return
        res = self._ask_group(title="Изменить группу", default_name=g.name, default_expanded=g.is_expanded_by_default)
        if not res:
            return
        name, expanded = res
        try:
            update_group(g.id, name=name, is_expanded_by_default=expanded)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось обновить: {e}")
            return
        self._reload_groups()
        self.changed.emit()

    def _delete_group(self) -> None:
        g = self._current_group()
        if not g:
            return
        if QtWidgets.QMessageBox.question(self, "Удалить", f"Удалить группу '{g.name}'?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            delete_group(g.id)
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Нельзя удалить", str(e))
            return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            return
        self._current_group_id = None
        self._reload_groups()
        self._reload_fields()
        self.changed.emit()

    def _move_group(self, direction: int) -> None:
        g = self._current_group()
        if not g:
            return
        move_group(g.id, direction)
        self._reload_groups()
        self.changed.emit()

    # ---------- Fields ----------
    def _reload_fields(self) -> None:
        self.fields_table.setRowCount(0)
        self._fields = []
        if not self._current_group_id:
            return
        self._fields = list_fields(self._current_group_id)
        for f in self._fields:
            r = self.fields_table.rowCount()
            self.fields_table.insertRow(r)
            self.fields_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(f.column_num)))
            self.fields_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(f.display_order)))
            it = QtWidgets.QTableWidgetItem(f.name)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, f.id)
            self.fields_table.setItem(r, 2, it)
            self.fields_table.setItem(r, 3, QtWidgets.QTableWidgetItem(f.template_tag or ""))
            self.fields_table.setItem(r, 4, QtWidgets.QTableWidgetItem(f.field_type))
            self.fields_table.setItem(r, 5, QtWidgets.QTableWidgetItem("Да" if f.is_required else "Нет"))
            self.fields_table.setItem(r, 6, QtWidgets.QTableWidgetItem("Да" if f.is_hidden else "Нет"))

    def _current_field(self) -> FieldRow | None:
        row = self.fields_table.currentRow()
        if row < 0:
            return None
        it = self.fields_table.item(row, 2)
        if not it:
            return None
        fid = int(it.data(QtCore.Qt.ItemDataRole.UserRole))
        return next((x for x in self._fields if x.id == fid), None)

    def _ask_field(self, *, title: str, existing: FieldRow | None = None) -> dict | None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(520, 520)
        layout = QtWidgets.QVBoxLayout(dlg)

        form = QtWidgets.QFormLayout()
        name = QtWidgets.QLineEdit(existing.name if existing else "")
        template_tag = QtWidgets.QLineEdit((existing.template_tag or "") if existing else "")
        template_tag.setPlaceholderText("например: MZhPd__mm_lz (без @)")
        ftype = QtWidgets.QComboBox()
        ftype.addItems(["строка", "текст", "число", "дата", "время", "словарь", "шаблон", "скрытое", "формула"])
        if existing:
            idx = ftype.findText(existing.field_type)
            if idx >= 0:
                ftype.setCurrentIndex(idx)
        col = QtWidgets.QSpinBox()
        col.setRange(1, 3)
        col.setValue(existing.column_num if existing else 1)
        precision = QtWidgets.QSpinBox()
        precision.setRange(0, 6)
        precision.setValue(existing.precision if (existing and existing.precision is not None) else 0)
        precision.setEnabled(bool(existing and existing.field_type in ("число", "формула")) or False)
        required = QtWidgets.QCheckBox()
        required.setChecked(existing.is_required if existing else False)
        height = QtWidgets.QSpinBox()
        height.setRange(1, 10)
        height.setValue(existing.height if existing else 1)
        width = QtWidgets.QSpinBox()
        width.setRange(10, 200)
        width.setValue(existing.width if existing else 20)

        formula = QtWidgets.QPlainTextEdit(existing.formula or "" if existing else "")
        formula.setMinimumHeight(70)

        # refs
        def _dbl(val: float | None) -> str:
            return "" if val is None else str(val).replace(".", ",")

        rm_min = QtWidgets.QLineEdit(_dbl(existing.reference_male_min) if existing else "")
        rm_max = QtWidgets.QLineEdit(_dbl(existing.reference_male_max) if existing else "")
        rf_min = QtWidgets.QLineEdit(_dbl(existing.reference_female_min) if existing else "")
        rf_max = QtWidgets.QLineEdit(_dbl(existing.reference_female_max) if existing else "")

        hidden = QtWidgets.QCheckBox()
        hidden.setChecked(existing.is_hidden if existing else False)

        # trigger field: only dictionary fields in this group
        trigger_field = QtWidgets.QComboBox()
        trigger_field.addItem("—", None)
        for f in self._fields:
            if f.field_type == "словарь":
                trigger_field.addItem(f.name, f.id)
        if existing and existing.hidden_trigger_field_id:
            idx = trigger_field.findData(existing.hidden_trigger_field_id)
            if idx >= 0:
                trigger_field.setCurrentIndex(idx)
        trigger_value = QtWidgets.QLineEdit(existing.hidden_trigger_value or "" if existing else "")

        form.addRow("Название:", name)
        form.addRow("Тег для шаблона (@...):", template_tag)
        form.addRow("Тип:", ftype)
        form.addRow("Колонка:", col)
        form.addRow("Обязательное:", required)
        form.addRow("Точность (число/формула):", precision)
        form.addRow("Высота:", height)
        form.addRow("Ширина:", width)
        form.addRow("Формула:", formula)
        form.addRow("Ref муж min/max:", self._hpair(rm_min, rm_max))
        form.addRow("Ref жен min/max:", self._hpair(rf_min, rf_max))
        form.addRow("Скрытое:", hidden)
        form.addRow("Триггер поле:", trigger_field)
        form.addRow("Триггер значение:", trigger_value)
        layout.addLayout(form)

        def on_type_changed():
            t = ftype.currentText()
            precision.setEnabled(t in ("число", "формула"))
            formula.setEnabled(t == "формула")
            # По просьбе: "тег" нужен именно когда выбирают тип "шаблон"
            template_tag.setEnabled(t == "шаблон")
        ftype.currentIndexChanged.connect(on_type_changed)
        on_type_changed()

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
        n = name.text().strip()
        if not n:
            return None

        # tag: allow empty; if user typed '@' -> strip; validate only for 'шаблон'
        t = ftype.currentText()
        tag = template_tag.text().strip()
        if tag.startswith("@"):
            tag = tag[1:].strip()
        if t == "шаблон":
            if not tag:
                QtWidgets.QMessageBox.warning(dlg, "Внимание", "Для типа «шаблон» нужно указать тег (например: MZhPd__mm_lz).")
                return None
            # \w in Qt = [A-Za-z0-9_] (+ unicode letters). Нам нужно минимум: буквы/цифры/_.
            if not QtCore.QRegularExpression(r"^\w+$").match(tag).hasMatch():
                QtWidgets.QMessageBox.warning(dlg, "Внимание", "Тег может содержать только буквы/цифры и знак подчёркивания (_).")
                return None

        def _parse_float(s: str) -> float | None:
            s = s.strip().replace(",", ".")
            if not s:
                return None
            try:
                return float(s)
            except ValueError:
                return None

        return {
            "name": n,
            "template_tag": tag or None,
            "field_type": t,
            "column_num": int(col.value()),
            "precision": int(precision.value()) if t in ("число", "формула") else None,
            "reference_male_min": _parse_float(rm_min.text()),
            "reference_male_max": _parse_float(rm_max.text()),
            "reference_female_min": _parse_float(rf_min.text()),
            "reference_female_max": _parse_float(rf_max.text()),
            "formula": formula.toPlainText().strip() if t == "формула" else None,
            "is_required": bool(required.isChecked()),
            "height": int(height.value()),
            "width": int(width.value()),
            "is_hidden": bool(hidden.isChecked()),
            "hidden_trigger_field_id": trigger_field.currentData(),
            "hidden_trigger_value": trigger_value.text().strip() or None,
        }

    def _hpair(self, a: QtWidgets.QWidget, b: QtWidgets.QWidget) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        l = QtWidgets.QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)
        l.addWidget(a)
        l.addWidget(b)
        return w

    def _add_field(self) -> None:
        if not self._current_group_id:
            return
        data = self._ask_field(title="Добавить поле")
        if not data:
            return
        try:
            create_field(group_id=self._current_group_id, **data)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось создать поле: {e}")
            return
        self._reload_fields()
        self.changed.emit()

    def _edit_field(self) -> None:
        cur = self._current_field()
        if not cur:
            return
        data = self._ask_field(title="Изменить поле", existing=cur)
        if not data:
            return
        try:
            update_field(cur.id, **data)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось обновить: {e}")
            return
        self._reload_fields()
        self.changed.emit()

    def _delete_field(self) -> None:
        cur = self._current_field()
        if not cur:
            return
        if QtWidgets.QMessageBox.question(self, "Удалить", f"Удалить поле '{cur.name}'?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            delete_field(cur.id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            return
        self._reload_fields()
        self.changed.emit()

    def _move_field(self, direction: int) -> None:
        cur = self._current_field()
        if not cur:
            return
        move_field(cur.id, direction)
        self._reload_fields()
        self.changed.emit()

    def _edit_dictionary_values(self) -> None:
        cur = self._current_field()
        if not cur or cur.field_type not in ("словарь", "шаблон"):
            return
        dlg = DictionaryValuesDialog(field_id=cur.id, field_name=cur.name, parent=self)
        dlg.changed.connect(self.changed.emit)
        dlg.exec()
