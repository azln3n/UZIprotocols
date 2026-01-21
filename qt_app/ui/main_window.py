from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from .patient_dialog import PatientDialog
from .protocols_list_dialog import ProtocolsListDialog
from ..repo import list_protocols_for_patient
from .protocol_view_dialog import ProtocolViewDialog
from .protocol_area import ProtocolArea
from .search_dialog import SearchDialog
from ..repo import PatientListItem, delete_patient, list_patients_for_institution
from ..paths import app_base_dir
from ..utils.open_external import open_in_os
from .report_dialog import ReportDialog


@dataclass(frozen=True)
class Session:
    institution_id: int
    doctor_id: int
    device_id: int


class MainWindow(QtWidgets.QMainWindow):
    logout_requested = QtCore.Signal()

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.setWindowTitle("УЗИ-протоколирование")
        self.resize(1200, 720)

        self._patients: list[PatientListItem] = []
        self._selected_patient_id: int | None = None
        self._search_highlight_ids: set[int] = set()

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ===== Left: patients list =====
        left = QtWidgets.QWidget()
        # По ТЗ/скрину: левая часть чуть шире, чтобы кнопки не налезали
        left.setMinimumWidth(420)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)

        # Header plaque: title + buttons in one block (как на скрине)
        header = QtWidgets.QFrame()
        header.setStyleSheet("QFrame { background: #f1f1f1; border: 1px solid #ddd; border-radius: 6px; }")
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(8)

        title = QtWidgets.QLabel("Список пациентов")
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("background: transparent; border: 0; padding: 0;")
        header_layout.addWidget(title)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 0, 0, 0)
        self.add_patient_btn = QtWidgets.QPushButton("Добавить")
        self.add_patient_btn.setStyleSheet(
            "QPushButton { background: #4CAF50; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        self.add_patient_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.add_patient_btn.clicked.connect(self._add_patient)
        btn_row.addWidget(self.add_patient_btn)

        self.edit_patient_btn = QtWidgets.QPushButton("Изменить")
        self.edit_patient_btn.setStyleSheet(
            "QPushButton { background: #FF9800; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        self.edit_patient_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.edit_patient_btn.clicked.connect(self._edit_patient)
        btn_row.addWidget(self.edit_patient_btn)

        self.delete_patient_btn = QtWidgets.QPushButton("Удалить")
        self.delete_patient_btn.setStyleSheet(
            "QPushButton { background: #F44336; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        self.delete_patient_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.delete_patient_btn.clicked.connect(self._delete_patient)
        btn_row.addWidget(self.delete_patient_btn)
        header_layout.addLayout(btn_row)

        left_layout.addWidget(header)

        # Patient list with expandable protocols (по просьбе: клик по ФИО раскрывает протоколы снизу)
        patients_frame = QtWidgets.QFrame()
        patients_frame.setStyleSheet("QFrame { background: #ffffff; border: 1px solid #ddd; border-radius: 6px; }")
        patients_layout = QtWidgets.QVBoxLayout(patients_frame)
        patients_layout.setContentsMargins(6, 6, 6, 6)
        patients_layout.setSpacing(0)

        self.patient_tree = QtWidgets.QTreeWidget()
        self.patient_tree.setHeaderHidden(True)
        self.patient_tree.setItemsExpandable(True)
        self.patient_tree.setRootIsDecorated(True)
        self.patient_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        # Чтобы Qt не рисовал рамку фокуса вокруг текста item'а (после закрытия просмотра протокола)
        self.patient_tree.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.patient_tree.itemClicked.connect(self._on_patient_tree_clicked)
        self.patient_tree.itemDoubleClicked.connect(self._on_patient_tree_double_clicked)
        self.patient_tree.itemExpanded.connect(self._on_patient_tree_expanded)
        self.patient_tree.setStyleSheet(
            """
            QTreeWidget { background: #ffffff; border: 0px; }
            /* disable "text focus rectangle" */
            QTreeWidget::item:focus { outline: 0; }
            QTreeWidget::item:selected { outline: 0; }
            QTreeWidget::item { outline: 0; }
            /* patients (top-level, has children indicator) */
            QTreeWidget::item:has-children {
              background: #c6dbff;
              border: 1px solid #7dafff;
              border-radius: 6px;
              padding: 10px;
              margin-bottom: 2px;
            }
            QTreeWidget::item:has-children:hover { background: #eef5ff; }
            QTreeWidget::item:has-children:selected {
              background: #FF95A8;
              border: 1px solid transparent; /* без рамки вокруг текста */
            }
            /* protocols (children) look like "button", highlight only on hover */
            QTreeWidget::item:!has-children {
              background: transparent;
              border: 0px;
              border-radius: 6px;
              padding: 8px;
              margin-left: 22px;
            }
            QTreeWidget::item:!has-children:hover { background: transparent; }
            QTreeWidget::item:!has-children:selected { background: transparent; color: black; }
            """
        )
        patients_layout.addWidget(self.patient_tree, 1)
        left_layout.addWidget(patients_frame, 1)

        splitter.addWidget(left)

        # ===== Right: placeholder for protocol area =====
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)

        self.protocol_area = ProtocolArea(
            institution_id=self.session.institution_id,
            doctor_id=self.session.doctor_id,
            device_id=self.session.device_id,
            parent=right,
        )
        # Верхние кнопки (как на скрине) живут внутри ProtocolArea, а MainWindow только реагирует.
        self.protocol_area.back_requested.connect(self._back_to_login)
        self.protocol_area.search_requested.connect(self._open_search)
        self.protocol_area.help_requested.connect(self._open_help)
        self.protocol_area.service_requested.connect(self._open_service)
        self.protocol_area.about_requested.connect(self._open_about)
        self.protocol_area.report_requested.connect(self._open_report)
        self.protocol_area.protocol_saved.connect(self._on_protocol_saved)
        right_layout.addWidget(self.protocol_area, 1)

        splitter.addWidget(right)
        splitter.setSizes([420, 780])

        self.setCentralWidget(splitter)

        self._reload_patients()
        self._refresh_buttons()
        self._fixed_after_maximize = False

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        # По просьбе: главное окно открывается на весь экран и его нельзя уменьшить.
        if not getattr(self, "_fixed_after_maximize", False):
            self._fixed_after_maximize = True
            self.showMaximized()
            QtCore.QTimer.singleShot(0, lambda: self.setFixedSize(self.size()))

    @QtCore.Slot()
    def _add_patient(self) -> None:
        dlg = PatientDialog(institution_id=self.session.institution_id, parent=self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._reload_patients(select_last_added=True)

    @QtCore.Slot()
    def _edit_patient(self) -> None:
        if not self._selected_patient_id:
            QtWidgets.QMessageBox.warning(self, "Внимание", "Выберите пациента для редактирования.")
            return
        dlg = PatientDialog(
            institution_id=self.session.institution_id,
            patient_id=self._selected_patient_id,
            parent=self,
        )
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._reload_patients(select_patient_id=self._selected_patient_id)

    @QtCore.Slot()
    def _delete_patient(self) -> None:
        if not self._selected_patient_id:
            QtWidgets.QMessageBox.warning(self, "Внимание", "Выберите пациента для удаления.")
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Подтверждение удаления",
            "Вы точно хотите удалить выбранного пациента?\n"
            "Если у пациента есть протоколы, удаление невозможно.",
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        try:
            delete_patient(self._selected_patient_id)
        except ValueError as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", str(e))
            return
        except Exception as e:  # pragma: no cover
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить пациента: {e}")
            return

        self._selected_patient_id = None
        self._reload_patients()

    def _reload_patients(
        self,
        *,
        select_patient_id: int | None = None,
        select_last_added: bool = False,
    ) -> None:
        self._patients = list_patients_for_institution(self.session.institution_id, limit=50)
        self.patient_tree.clear()

        highlight_bg = QtGui.QColor("#FF95A8")
        highlight_fg = QtGui.QColor("#000000")

        last_added_id: int | None = None
        if select_last_added and self._patients:
            last_added_id = self._patients[0].id

        if select_patient_id:
            self._selected_patient_id = int(select_patient_id)

        for p in self._patients:
            it = QtWidgets.QTreeWidgetItem([p.full_name])
            it.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("patient", p.id))
            it.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            it.setTextAlignment(0, QtCore.Qt.AlignmentFlag.AlignCenter)

            # placeholder child so the arrow is shown; we load real protocols on expand/click
            ph = QtWidgets.QTreeWidgetItem([""])
            ph.setTextAlignment(0, QtCore.Qt.AlignmentFlag.AlignCenter)
            it.addChild(ph)

            if (
                p.id in self._search_highlight_ids
                or p.id == self._selected_patient_id
                or (last_added_id is not None and p.id == last_added_id)
            ):
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
                it.setBackground(0, highlight_bg)
                it.setForeground(0, highlight_fg)

            self.patient_tree.addTopLevelItem(it)

        # selection
        if select_patient_id:
            self._select_patient_by_id(select_patient_id)
        elif select_last_added and self._patients:
            # list is ordered by created_at desc, so [0] is most recent
            self._select_patient_by_id(self._patients[0].id)
        else:
            self._refresh_buttons()

    def _select_patient_by_id(self, patient_id: int) -> None:
        for i in range(self.patient_tree.topLevelItemCount()):
            it = self.patient_tree.topLevelItem(i)
            tag = it.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if tag and tag[0] == "patient" and int(tag[1]) == int(patient_id):
                self.patient_tree.setCurrentItem(it)
                return

    @QtCore.Slot(QtWidgets.QTreeWidgetItem, int)
    def _on_patient_tree_clicked(self, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
        tag = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not tag:
            return
        kind, idv = tag
        if kind == "patient":
            pid = int(idv)
            self._selected_patient_id = pid
            self.protocol_area.set_patient(pid)
            self._refresh_buttons()
            # Раскрытие протоколов — только по стрелочке (itemExpanded)
        elif kind == "protocol":
            # Clicking protocol opens it in the right pane (ProtocolArea) instead of a separate window.
            parent = item.parent()
            if not parent:
                return
            pid = int(parent.data(0, QtCore.Qt.ItemDataRole.UserRole)[1])
            proto_id = int(idv)
            if proto_id <= 0:
                QtWidgets.QMessageBox.information(self, "Протоколы", "Нет протокола")
                # keep patient selected
                self._selected_patient_id = pid
                self.protocol_area.set_patient(pid)
                self._refresh_buttons()
            else:
                st_id = int(item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1) or 0)
                self._selected_patient_id = pid
                self.protocol_area.set_patient(pid)
                self._refresh_buttons()
                self.protocol_area.open_saved_protocol(protocol_id=proto_id, study_type_id=st_id)

            self.patient_tree.setCurrentItem(parent)
            self.patient_tree.clearFocus()
            self.protocol_area.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            return

    @QtCore.Slot(QtWidgets.QTreeWidgetItem, int)
    def _on_patient_tree_double_clicked(self, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
        tag = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not tag:
            return
        kind, idv = tag
        if kind == "patient":
            # double click on patient edits
            pid = int(idv)
            self._selected_patient_id = pid
            self._edit_patient()

    def _toggle_protocol_children(self, patient_item: QtWidgets.QTreeWidgetItem, patient_id: int) -> None:
        # If already populated, just toggle expanded
        if patient_item.childCount() > 0 and patient_item.child(0).data(0, QtCore.Qt.ItemDataRole.UserRole):
            patient_item.setExpanded(not patient_item.isExpanded())
            return

        # Populate children
        patient_item.takeChildren()
        protocols = list_protocols_for_patient(patient_id)
        if not protocols:
            ch = QtWidgets.QTreeWidgetItem(["Нет протокола"])
            ch.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("protocol", 0))
            ch.setTextAlignment(0, QtCore.Qt.AlignmentFlag.AlignCenter)
            patient_item.addChild(ch)
        else:
            for pr in protocols:
                title = f"{pr.study_name} {pr.created_at}"
                ch = QtWidgets.QTreeWidgetItem([title])
                ch.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("protocol", pr.id))
                ch.setData(0, QtCore.Qt.ItemDataRole.UserRole + 1, int(pr.study_type_id))
                ch.setTextAlignment(0, QtCore.Qt.AlignmentFlag.AlignCenter)
                patient_item.addChild(ch)
        patient_item.setExpanded(True)

    @QtCore.Slot(QtWidgets.QTreeWidgetItem)
    def _on_patient_tree_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        # Пользователь может нажать на стрелочку раскрытия, не кликая по ФИО.
        # В этом случае тоже подгружаем протоколы.
        tag = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not tag:
            return
        kind, idv = tag
        if kind != "patient":
            return
        pid = int(idv)
        # If placeholder or empty, populate
        if item.childCount() == 0 or (item.childCount() == 1 and not item.child(0).data(0, QtCore.Qt.ItemDataRole.UserRole)):
            self._toggle_protocol_children(item, pid)

    def _refresh_buttons(self) -> None:
        enabled = self._selected_patient_id is not None
        self.edit_patient_btn.setEnabled(enabled)
        self.delete_patient_btn.setEnabled(enabled)

    @QtCore.Slot(int)
    def _on_protocol_saved(self, patient_id: int) -> None:
        # после сохранения протокола в БД у пациента появится [+]
        self._reload_patients(select_patient_id=patient_id)

    @QtCore.Slot()
    def _open_search(self) -> None:
        dlg = SearchDialog(institution_id=self.session.institution_id, parent=self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or dlg.result is None:
            return
        self._search_highlight_ids = set(dlg.result.patient_ids)
        # reload list to apply highlight, and select first match if present
        self._reload_patients()
        if dlg.result.patient_ids:
            self._select_patient_by_id(dlg.result.patient_ids[0])

    @QtCore.Slot()
    def _back_to_login(self) -> None:
        # main_qt.py will handle showing login again
        self.logout_requested.emit()
        self.close()

    def _open_help(self) -> None:
        self._open_side_file(preferred_names=["help.exe", "Справка.exe"])

    def _open_service(self) -> None:
        self._open_side_file(preferred_names=["service.html", "service.htm", "Сервис.html", "Сервис.htm"])

    def _open_about(self) -> None:
        self._open_side_file(preferred_names=["about.exe", "О программе.exe"])

    def _open_report(self) -> None:
        dlg = ReportDialog(institution_id=self.session.institution_id, parent=self)
        dlg.exec()

    def _open_side_file(self, preferred_names: list[str]) -> None:
        base = app_base_dir()
        for name in preferred_names:
            p = base / name
            if p.exists():
                open_in_os(p)
                return

        QtWidgets.QMessageBox.information(
            self,
            "Файл не найден",
            "По ТЗ файлы для кнопок «Справка/Сервис/О программе» должны лежать\n"
            f"рядом с приложением.\n\nПапка: {base}\n\n"
            f"Ожидались имена:\n- " + "\n- ".join(preferred_names),
        )


# (old QListWidget implementation removed; we now use QTreeWidget with expandable rows)
