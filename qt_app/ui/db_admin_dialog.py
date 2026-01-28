from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..db import connect
from ..paths import db_path, ultrasound_dir
from ..repo import delete_field, delete_group, delete_patient, delete_protocol, delete_tab
from .auto_combo import AutoComboBox


@dataclass(frozen=True)
class _TableInfo:
    name: str
    columns: list[str]
    pk_columns: list[str]
    has_rowid: bool


class DatabaseAdminDialog(QtWidgets.QDialog):
    """
    Администрирование SQLite БД:
    - импорт/экспорт файла БД (sqlite .db)
    - просмотр таблиц
    - безопасное редактирование (по умолчанию read-only, unlock по подтверждению)
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Настройки — база данных")
        self.resize(1100, 720)
        self.setModal(True)

        self._editing_unlocked = False
        self._db_replaced = False

        self._page_size = 250
        self._page = 0

        # current view metadata
        self._table: _TableInfo | None = None
        self._keys_by_row: dict[int, dict[str, object]] = {}
        self._dirty: dict[tuple[object, ...], dict[str, object]] = {}
        self._key_cols: list[str] = []
        self._visible_cols: list[str] = []

        self._build_ui()
        self._load_tables()
        self._refresh_state()

    # ---------------- UI ----------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- DB file panel
        file_box = QtWidgets.QGroupBox("Файл БД")
        fl = QtWidgets.QGridLayout(file_box)
        fl.setHorizontalSpacing(10)
        fl.setVerticalSpacing(8)

        fl.addWidget(QtWidgets.QLabel("Текущая БД:"), 0, 0)
        self.path_edit = QtWidgets.QLineEdit(str(db_path().resolve()))
        self.path_edit.setReadOnly(True)
        fl.addWidget(self.path_edit, 0, 1, 1, 4)

        self.backup_btn = QtWidgets.QPushButton("Сделать бэкап…")
        self.export_btn = QtWidgets.QPushButton("Экспортировать БД…")
        self.import_btn = QtWidgets.QPushButton("Импортировать БД…")

        self.backup_btn.clicked.connect(self._backup_db_interactive)
        self.export_btn.clicked.connect(self._export_db_interactive)
        self.import_btn.clicked.connect(self._import_db_interactive)

        fl.addWidget(self.backup_btn, 1, 1)
        fl.addWidget(self.export_btn, 1, 2)
        fl.addWidget(self.import_btn, 1, 3)

        root.addWidget(file_box)

        # ---- Table browser panel
        data_box = QtWidgets.QGroupBox("Таблицы")
        dl = QtWidgets.QVBoxLayout(data_box)
        dl.setContentsMargins(10, 10, 10, 10)
        dl.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(QtWidgets.QLabel("Таблица:"))
        self.table_combo = AutoComboBox(max_popup_items=30)
        self.table_combo.setMinimumWidth(240)
        self.table_combo.currentIndexChanged.connect(self._on_table_changed)
        top.addWidget(self.table_combo)

        top.addSpacing(12)

        top.addWidget(QtWidgets.QLabel("Поиск (на странице):"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("подстрока…")
        self.search_edit.textChanged.connect(self._apply_search_filter)
        top.addWidget(self.search_edit, 1)

        self.refresh_btn = QtWidgets.QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self._reload_page)
        top.addWidget(self.refresh_btn)
        dl.addLayout(top)

        nav = QtWidgets.QHBoxLayout()
        nav.setSpacing(10)
        self.prev_btn = QtWidgets.QPushButton("←")
        self.next_btn = QtWidgets.QPushButton("→")
        self.page_label = QtWidgets.QLabel("Страница: 1")
        self.page_label.setMinimumWidth(140)
        self.prev_btn.clicked.connect(lambda: self._move_page(-1))
        self.next_btn.clicked.connect(lambda: self._move_page(+1))
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.page_label)
        nav.addStretch(1)

        self.unlock_btn = QtWidgets.QPushButton("Разблокировать редактирование…")
        self.unlock_btn.clicked.connect(self._unlock_editing)
        nav.addWidget(self.unlock_btn)

        self.add_row_btn = QtWidgets.QPushButton("Добавить строку…")
        self.del_row_btn = QtWidgets.QPushButton("Удалить строку…")
        self.save_btn = QtWidgets.QPushButton("Сохранить изменения")
        self.add_row_btn.clicked.connect(self._add_row)
        self.del_row_btn.clicked.connect(self._delete_row)
        self.save_btn.clicked.connect(self._save_changes)

        nav.addWidget(self.add_row_btn)
        nav.addWidget(self.del_row_btn)
        nav.addWidget(self.save_btn)
        dl.addLayout(nav)

        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)
        dl.addWidget(self.table, 1)

        root.addWidget(data_box, 1)

        # ---- Footer
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._db_replaced:
            QtWidgets.QMessageBox.information(
                self,
                "Перезапуск",
                "База данных была заменена.\n\n"
                "Чтобы приложение корректно продолжило работу, перезапустите его.",
            )
        super().closeEvent(event)

    # ---------------- Data loading ----------------

    def _load_tables(self) -> None:
        self.table_combo.blockSignals(True)
        self.table_combo.clear()

        with connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            names = [str(r["name"]) for r in rows]

        for n in names:
            self.table_combo.addItem(n, n)

        self.table_combo.blockSignals(False)
        if self.table_combo.count() > 0:
            self.table_combo.setCurrentIndex(0)
            self._on_table_changed()

    def _describe_table(self, table_name: str) -> _TableInfo:
        with connect() as conn:
            cols_info = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            cols = [str(r["name"]) for r in cols_info]
            pk_cols = [str(r["name"]) for r in cols_info if int(r["pk"] or 0) > 0]

            # Some SQLite tables can be WITHOUT ROWID; detect via sqlite_master SQL
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).fetchone()
            sql = (str(row["sql"]) if row and row["sql"] else "").upper()
            has_rowid = "WITHOUT ROWID" not in sql

        return _TableInfo(name=table_name, columns=cols, pk_columns=pk_cols, has_rowid=has_rowid)

    @QtCore.Slot()
    def _on_table_changed(self) -> None:
        name = self.table_combo.currentData()
        if not name:
            return
        self._page = 0
        self._table = self._describe_table(str(name))
        self._dirty.clear()
        self._reload_page()

    def _reload_page(self) -> None:
        if not self._table:
            return

        self.table.blockSignals(True)
        try:
            self._dirty.clear()
            self._keys_by_row.clear()
            self.search_edit.blockSignals(True)
            try:
                self.search_edit.clear()
            finally:
                self.search_edit.blockSignals(False)

            t = self._table
            cols = list(t.columns)
            key_cols: list[str]
            select_cols: list[str]

            if t.pk_columns:
                key_cols = list(t.pk_columns)
                select_cols = cols
                sql = f"SELECT {', '.join(cols)} FROM {t.name} LIMIT ? OFFSET ?"
            else:
                # use rowid if available; otherwise we can only browse safely
                if t.has_rowid:
                    key_cols = ["rowid"]
                    select_cols = ["rowid"] + cols
                    sql = f"SELECT rowid, {', '.join(cols)} FROM {t.name} LIMIT ? OFFSET ?"
                else:
                    key_cols = []
                    select_cols = cols
                    sql = f"SELECT {', '.join(cols)} FROM {t.name} LIMIT ? OFFSET ?"

            self._key_cols = key_cols
            self._visible_cols = list(select_cols)

            with connect() as conn:
                rows = conn.execute(sql, (self._page_size, self._page * self._page_size)).fetchall()

            # setup table widget
            self.table.setRowCount(0)
            self.table.setColumnCount(len(select_cols))
            # Заголовки: делаем читаемыми + подсказки с оригинальными именами
            pretty = [c.replace("_", " ") for c in select_cols]
            self.table.setHorizontalHeaderLabels(pretty)
            header = self.table.horizontalHeader()
            header.setStretchLastSection(True)
            header.setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(90)

            for r in rows:
                row_idx = self.table.rowCount()
                self.table.insertRow(row_idx)

                # store key values for this row (for save/delete)
                key_vals: dict[str, object] = {}
                for kc in key_cols:
                    key_vals[kc] = r[kc]
                self._keys_by_row[row_idx] = key_vals

                for c, col_name in enumerate(select_cols):
                    val = r[col_name]
                    item = QtWidgets.QTableWidgetItem("" if val is None else str(val))
                    # stash original value for change detection
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, val)
                    self.table.setItem(row_idx, c, item)

            # resize columns after content is placed (so headers won't look cut off)
            self.table.resizeColumnsToContents()
            # tooltips: show real column name
            for i, real_name in enumerate(select_cols):
                hi = self.table.horizontalHeaderItem(i)
                if hi is not None:
                    hi.setToolTip(real_name)

            self._refresh_state()
        finally:
            self.table.blockSignals(False)

    def _apply_search_filter(self) -> None:
        q = (self.search_edit.text() or "").strip().casefold()
        for r in range(self.table.rowCount()):
            if not q:
                self.table.setRowHidden(r, False)
                continue
            matched = False
            for c in range(self.table.columnCount()):
                it = self.table.item(r, c)
                if it and q in (it.text() or "").casefold():
                    matched = True
                    break
            self.table.setRowHidden(r, not matched)

    def _move_page(self, delta: int) -> None:
        new_page = self._page + int(delta)
        if new_page < 0:
            return
        # If there are unsaved changes, block navigation
        if self._dirty:
            QtWidgets.QMessageBox.warning(
                self,
                "Есть несохранённые изменения",
                "Сначала сохраните изменения или обновите таблицу (изменения будут потеряны).",
            )
            return
        self._page = new_page
        self._reload_page()

    def _refresh_state(self) -> None:
        self.page_label.setText(f"Страница: {self._page + 1}")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(True)  # unknown total; allow, empty page will show no rows

        editable = bool(self._editing_unlocked and self._table and (self._table.pk_columns or self._table.has_rowid))
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.AllEditTriggers
            if editable
            else QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.add_row_btn.setEnabled(editable)
        self.del_row_btn.setEnabled(editable)
        self.save_btn.setEnabled(editable and bool(self._dirty))

    # ---------------- Editing ----------------

    def _unlock_editing(self) -> None:
        if self._editing_unlocked:
            return
        if (
            QtWidgets.QMessageBox.warning(
                self,
                "Внимание",
                "Редактирование базы данных может привести к ошибкам в приложении.\n\n"
                "Включить редактирование?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return
        self._editing_unlocked = True
        self.unlock_btn.setText("Редактирование разблокировано")
        self.unlock_btn.setEnabled(False)
        self._refresh_state()

    def _row_key_tuple(self, row: int) -> tuple[object, ...] | None:
        if row not in self._keys_by_row:
            return None
        kv = self._keys_by_row[row]
        if not self._key_cols:
            return None
        return tuple(kv.get(k) for k in self._key_cols)

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if not self._editing_unlocked or not self._table:
            return
        row = item.row()
        col = item.column()
        # Use real column name (not the display label)
        if col < 0 or col >= len(self._visible_cols):
            return
        col_name = self._visible_cols[col]

        # key columns should not be edited (pk/rowid)
        if col_name in set(self._key_cols):
            self.table.blockSignals(True)
            try:
                orig = item.data(QtCore.Qt.ItemDataRole.UserRole)
                item.setText("" if orig is None else str(orig))
            finally:
                self.table.blockSignals(False)
            return

        key = self._row_key_tuple(row)
        if key is None:
            return

        new_text = item.text()
        new_val: object = None if (new_text is None or str(new_text).strip() == "") else str(new_text)

        self._dirty.setdefault(key, {})[col_name] = new_val
        self._refresh_state()

    def _save_changes(self) -> None:
        if not self._table or not self._dirty:
            return

        t = self._table
        if not (t.pk_columns or t.has_rowid):
            QtWidgets.QMessageBox.warning(self, "Нельзя", "Таблица не поддерживает безопасное обновление (нет PK/rowid).")
            return

        try:
            with connect() as conn:
                cur = conn.cursor()
                cur.execute("BEGIN")
                for key_tuple, changes in self._dirty.items():
                    if not changes:
                        continue

                    set_parts: list[str] = []
                    params: list[object] = []
                    for col_name, val in changes.items():
                        set_parts.append(f"{col_name} = ?")
                        params.append(val)

                    where_parts: list[str] = []
                    where_params: list[object] = []
                    if t.pk_columns:
                        for i, pk in enumerate(t.pk_columns):
                            where_parts.append(f"{pk} = ?")
                            where_params.append(key_tuple[i])
                    else:
                        where_parts.append("rowid = ?")
                        where_params.append(key_tuple[0])

                    sql = f"UPDATE {t.name} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"
                    cur.execute(sql, params + where_params)

                conn.commit()
        except Exception as e:
            try:
                with connect() as conn:
                    conn.rollback()
            except Exception:
                pass
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить изменения:\n{e}")
            return

        QtWidgets.QMessageBox.information(self, "Успех", "Изменения сохранены.")
        self._dirty.clear()
        self._reload_page()

    def _add_row(self) -> None:
        if not self._table:
            return
        t = self._table

        # simple form with all columns (exclude rowid pseudo-column)
        cols = [c for c in t.columns]

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Добавить строку — {t.name}")
        dlg.resize(520, 200)
        layout = QtWidgets.QVBoxLayout(dlg)

        form = QtWidgets.QFormLayout()
        edits: dict[str, QtWidgets.QLineEdit] = {}
        for c in cols:
            le = QtWidgets.QLineEdit()
            edits[c] = le
            form.addRow(f"{c}:", le)
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
            return

        values: list[object] = []
        for c in cols:
            txt = edits[c].text()
            values.append(None if not txt.strip() else txt.strip())

        try:
            with connect() as conn:
                cur = conn.cursor()
                cur.execute("BEGIN")
                placeholders = ", ".join(["?"] * len(cols))
                cur.execute(
                    f"INSERT INTO {t.name} ({', '.join(cols)}) VALUES ({placeholders})",
                    values,
                )
                conn.commit()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось добавить строку:\n{e}")
            return

        self._reload_page()

    def _delete_row(self) -> None:
        if not self._table:
            return
        t = self._table
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Удаление", "Выберите строку.")
            return

        key = self._row_key_tuple(row)
        if key is None:
            QtWidgets.QMessageBox.warning(self, "Нельзя", "Не удалось определить ключ строки (PK/rowid).")
            return

        if (
            QtWidgets.QMessageBox.question(self, "Удалить", "Удалить выбранную строку?")
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return

        try:
            # Для ключевых таблиц используем "безопасные" операции репозитория,
            # чтобы соблюсти ограничения ТЗ (нельзя удалить родителя при наличии детей)
            # и/или выполнить каскад (например, протокол -> значения).
            if t.name in ("protocols", "patients", "tabs", "groups", "fields"):
                # поддерживаем только PK вида id (или rowid fallback)
                obj_id: int | None = None
                if t.pk_columns and len(t.pk_columns) == 1:
                    obj_id = int(key[0])
                elif not t.pk_columns and t.has_rowid:
                    obj_id = int(key[0])

                if obj_id is None:
                    QtWidgets.QMessageBox.warning(
                        self, "Нельзя", "Не удалось определить id строки (нет PK/rowid)."
                    )
                    return

                if t.name == "protocols":
                    delete_protocol(int(obj_id))
                elif t.name == "patients":
                    delete_patient(int(obj_id))
                elif t.name == "tabs":
                    delete_tab(int(obj_id))
                elif t.name == "groups":
                    delete_group(int(obj_id))
                elif t.name == "fields":
                    delete_field(int(obj_id))
                else:  # pragma: no cover
                    pass
            else:
                with connect() as conn:
                    cur = conn.cursor()
                    cur.execute("BEGIN")
                    if t.pk_columns:
                        where_parts = [f"{pk} = ?" for pk in t.pk_columns]
                        cur.execute(
                            f"DELETE FROM {t.name} WHERE {' AND '.join(where_parts)}",
                            list(key),
                        )
                    else:
                        cur.execute(f"DELETE FROM {t.name} WHERE rowid = ?", (key[0],))
                    conn.commit()
        except ValueError as e:
            # repo.delete_* uses ValueError for "нельзя удалить"
            QtWidgets.QMessageBox.warning(self, "Нельзя удалить", str(e))
            return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить:\n{e}")
            return

        self._reload_page()

    # ---------------- DB file operations ----------------

    def _default_backup_dir(self) -> Path:
        d = ultrasound_dir() / "db_backups"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _auto_backup(self) -> Path | None:
        src = db_path()
        if not src.exists():
            return None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = self._default_backup_dir() / f"uzi_protocols_{stamp}.db"
        shutil.copy2(src, dst)
        return dst

    def _backup_db_interactive(self) -> None:
        src = db_path()
        if not src.exists():
            QtWidgets.QMessageBox.warning(self, "Бэкап", "Файл БД не найден.")
            return
        default = self._default_backup_dir() / f"uzi_protocols_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        out, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Сохранить бэкап БД",
            str(default),
            "SQLite DB (*.db);;Все файлы (*.*)",
        )
        if not out:
            return
        dst = Path(out)
        if dst.suffix.lower() != ".db":
            dst = dst.with_suffix(".db")
        try:
            shutil.copy2(src, dst)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить бэкап:\n{e}")
            return
        QtWidgets.QMessageBox.information(self, "Бэкап", f"Бэкап сохранён:\n{dst}")

    def _export_db_interactive(self) -> None:
        # export is essentially Save As of current DB
        self._backup_db_interactive()

    def _import_db_interactive(self) -> None:
        src, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Импортировать БД (SQLite .db)",
            str(db_path().parent),
            "SQLite DB (*.db);;Все файлы (*.*)",
        )
        if not src:
            return
        srcp = Path(src)
        if not srcp.exists():
            return

        if (
            QtWidgets.QMessageBox.warning(
                self,
                "Внимание",
                "Импорт заменит текущий файл БД.\n"
                "Перед заменой будет создан автобэкап.\n\n"
                "Продолжить?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return

        try:
            backup = self._auto_backup()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сделать автобэкап:\n{e}")
            return

        try:
            shutil.copy2(srcp, db_path())
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                "Не удалось заменить файл БД.\n\n"
                f"{e}\n\n"
                "Возможно, файл занят приложением. Закройте приложение и повторите импорт.",
            )
            return

        self._db_replaced = True
        msg = "База данных импортирована."
        if backup:
            msg += f"\n\nАвтобэкап:\n{backup}"
        msg += "\n\nПерезапустите приложение."
        QtWidgets.QMessageBox.information(self, "Импорт", msg)

