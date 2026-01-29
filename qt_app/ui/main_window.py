from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .patient_dialog import PatientDialog
from .protocols_list_dialog import ProtocolsListDialog
from ..repo import list_protocols_for_patient
from .protocol_view_dialog import ProtocolViewDialog
from .protocol_area import ProtocolArea
from .search_dialog import SearchDialog
from ..repo import PatientListItem, delete_patient, delete_protocol, list_patients_for_institution
from ..paths import app_base_dir
from ..utils.open_external import open_in_os
from ..utils.app_settings import load_external_files_settings
from .report_dialog import ReportDialog


@dataclass(frozen=True)
class Session:
    institution_id: int
    doctor_id: int


ROLE_KIND = int(QtCore.Qt.ItemDataRole.UserRole)
ROLE_PROTOCOL_SELECTED = int(QtCore.Qt.ItemDataRole.UserRole) + 10
ROLE_PATIENT_SELECTED = int(QtCore.Qt.ItemDataRole.UserRole) + 11


class _PatientProtocolDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index) -> None:
        # Важно: option.font не всегда учитывает шрифт/размер, заданный в QTreeWidgetItem.
        # Берём "правильные" значения через initStyleOption().
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        kind = index.data(ROLE_KIND)
        is_patient = bool(kind and isinstance(kind, (list, tuple)) and kind[0] == "patient")
        is_protocol = bool(kind and isinstance(kind, (list, tuple)) and kind[0] == "protocol")

        # Рисуем фон сами (иначе QSS/QStyle затирает заливку).
        if is_patient or is_protocol:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            rect = option.rect.adjusted(1, 1, -1, -1)

            if is_patient:
                bg = QtGui.QColor("#FF95A8") if bool(index.data(ROLE_PATIENT_SELECTED)) else QtGui.QColor("#c6dbff")
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(rect, 6, 6)
                text_rect = rect.adjusted(10, 0, -10, 0)
            else:
                # Протоколы: фон не на всю строку — начинаем там, где "плашка" (отступ как в примере).
                left_pad = 22
                box = rect.adjusted(left_pad, 0, 0, 0)
                bg = QtGui.QColor("#c6dbff") if bool(index.data(ROLE_PROTOCOL_SELECTED)) else QtGui.QColor("#ffffff")
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(box, 6, 6)
                text_rect = box.adjusted(8, 0, -8, 0)

            # Текст
            font = QtGui.QFont(opt.font)
            if is_patient:
                # По ТЗ/скрину: выбранный пациент — жирным
                font.setBold(bool(index.data(ROLE_PATIENT_SELECTED)))
            painter.setFont(font)
            painter.setPen(opt.palette.color(QtGui.QPalette.ColorRole.Text))
            text = str(opt.text or "")
            painter.drawText(
                text_rect,
                int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
                text,
            )
            painter.restore()
            return

        super().paint(painter, option, index)


class _GripSplitterHandle(QtWidgets.QSplitterHandle):
    """
    Визуально показывает маленькую "ручку" (грип) по центру, вместо полосы на всю высоту.
    Сам handle остаётся функциональным для перетаскивания.
    """

    def __init__(self, orientation: QtCore.Qt.Orientation, parent: QtWidgets.QSplitter):
        super().__init__(orientation, parent)
        self._hover = False
        self.setMouseTracking(True)

    def enterEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802 (Qt naming)
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802 (Qt naming)
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        # Прозрачный фон
        painter.fillRect(self.rect(), QtCore.Qt.GlobalColor.transparent)

        # Вертикальная линия
        r = self.rect()
        cx = r.center().x()
        line_color = QtGui.QColor("#666")
        painter.setPen(QtGui.QPen(line_color, 2))
        painter.drawLine(int(cx), r.top(), int(cx), r.bottom())


class _GripSplitter(QtWidgets.QSplitter):
    def createHandle(self) -> QtWidgets.QSplitterHandle:  # noqa: N802 (Qt naming)
        return _GripSplitterHandle(self.orientation(), self)


class MainWindow(QtWidgets.QMainWindow):
    logout_requested = QtCore.Signal()

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.setWindowTitle("УЗИ-протоколирование")
        self.resize(1200, 720)

        self._patients: list[PatientListItem] = []
        self._selected_patient_id: int | None = None
        self._selected_protocol_item: QtWidgets.QTreeWidgetItem | None = None
        self._search_highlight_ids: set[int] = set()

        splitter = _GripSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

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
        # Чуть больше внутренние отступы, чтобы рамки кнопок (border) не "упирались" в рамку группы.
        header_layout.setContentsMargins(12, 12, 12, 12)
        header_layout.setSpacing(8)

        title = QtWidgets.QLabel("Список пациентов")
        f = title.font()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("background: transparent; border: 0; padding: 0;")
        header_layout.addWidget(title)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 0, 0, 0)
        # Центрируем блок кнопок, но сами кнопки не растягиваем
        btn_row.addStretch(1)
        self.add_patient_btn = QtWidgets.QPushButton("Добавить")
        self.add_patient_btn.setStyleSheet(
            "QPushButton { background: #4CAF50; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        # При расширении левой панели кнопки не должны растягиваться
        self.add_patient_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.add_patient_btn.clicked.connect(self._add_patient)
        btn_row.addWidget(self.add_patient_btn)

        self.edit_patient_btn = QtWidgets.QPushButton("Изменить")
        self.edit_patient_btn.setStyleSheet(
            "QPushButton { background: #FF9800; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        self.edit_patient_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.edit_patient_btn.clicked.connect(self._edit_patient)
        btn_row.addWidget(self.edit_patient_btn)

        self.delete_patient_btn = QtWidgets.QPushButton("Удалить")
        self.delete_patient_btn.setStyleSheet(
            "QPushButton { background: #F44336; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        self.delete_patient_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.delete_patient_btn.clicked.connect(self._delete_patient)
        btn_row.addWidget(self.delete_patient_btn)
        btn_row.addStretch(1)
        header_layout.addLayout(btn_row)

        left_layout.addWidget(header)

        # Patient list with expandable protocols (по просьбе: клик по ФИО раскрывает протоколы снизу)
        patients_frame = QtWidgets.QFrame()
        # Фон контейнера списка пациентов — как у плашки с кнопками в окне протокола
        patients_frame.setStyleSheet("QFrame { background: #f1f1f1; border: 1px solid #ddd; border-radius: 6px; }")
        patients_layout = QtWidgets.QVBoxLayout(patients_frame)
        patients_layout.setContentsMargins(6, 6, 6, 6)
        patients_layout.setSpacing(0)

        self.patient_tree = QtWidgets.QTreeWidget()
        self.patient_tree.setHeaderHidden(True)
        self.patient_tree.setItemsExpandable(True)
        # По ТЗ: перед ФИО должен быть "+" / "-" (а не стандартная стрелка дерева)
        self.patient_tree.setRootIsDecorated(False)
        self.patient_tree.setIndentation(0)
        self.patient_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        # Чтобы Qt не рисовал рамку фокуса вокруг текста item'а (после закрытия просмотра протокола)
        self.patient_tree.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.patient_tree.itemClicked.connect(self._on_patient_tree_clicked)
        self.patient_tree.itemDoubleClicked.connect(self._on_patient_tree_double_clicked)
        self.patient_tree.itemExpanded.connect(self._on_patient_tree_expanded)
        self.patient_tree.itemCollapsed.connect(self._on_patient_tree_collapsed)
        self.patient_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.patient_tree.customContextMenuRequested.connect(self._on_patient_tree_context_menu)
        # По просьбе: клик по пустому месту в списке пациентов должен "снимать" пациента справа.
        self.patient_tree.viewport().installEventFilter(self)
        self.patient_tree.setStyleSheet(
            """
            /* Прозрачный фон, чтобы был виден фон контейнера patients_frame */
            QTreeWidget { background: transparent; border: 0px; }
            QTreeWidget::viewport { background: transparent; }
            /* Hide default expand/collapse indicator (some themes show it as black squares) */
            QTreeView::branch {
              background: transparent;
              border-image: none;
              image: none;
              width: 0px;
              height: 0px;
            }
            QTreeView::branch:open,
            QTreeView::branch:closed,
            QTreeView::branch:has-children,
            QTreeView::branch:has-children:open,
            QTreeView::branch:has-children:closed,
            QTreeView::branch:has-siblings:open,
            QTreeView::branch:has-siblings:closed,
            QTreeView::branch:has-siblings:has-children:open,
            QTreeView::branch:has-siblings:has-children:closed {
              background: transparent;
              border-image: none;
              image: none;
            }
            /* disable "text focus rectangle" */
            QTreeWidget::item:focus { outline: 0; }
            QTreeWidget::item:selected { outline: 0; }
            QTreeWidget::item { outline: 0; }
            /* patients (top-level, has children indicator) */
            QTreeWidget::item:has-children {
              border: 0px;
              padding: 10px;
              margin-bottom: 2px;
            }
            QTreeWidget::item:has-children:hover {
              /* фон рисуется делегатом; hover оставляем пустым */
            }
            /* protocols (children) look like "button", highlight only on hover */
            QTreeWidget::item:!has-children {
              border: 0px;
              padding: 4px 8px;
              margin-left: 22px;
              margin-top: 2px;
              margin-bottom: 2px;
            }
            QTreeWidget::item:!has-children:hover {
              /* фон рисуется делегатом; hover оставляем пустым */
            }
            """
        )
        self.patient_tree.setItemDelegate(_PatientProtocolDelegate(self.patient_tree))
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

        # Внешний отступ от границ окна до всего контента (чтобы правый блок не упирался в край).
        central = QtWidgets.QWidget()
        outer = QtWidgets.QHBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)
        outer.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self._reload_patients()
        self._refresh_buttons()

    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        # Click on empty area in the patient list -> clear selection and right pane.
        try:
            if (
                obj is self.patient_tree.viewport()
                and event.type() == QtCore.QEvent.Type.MouseButtonPress
                and isinstance(event, QtGui.QMouseEvent)
            ):
                pos = event.position().toPoint()
                it = self.patient_tree.itemAt(pos)
                if it is None:
                    self.patient_tree.clearSelection()
                    self.patient_tree.setCurrentItem(None)
                    self._selected_patient_id = None
                    self._clear_protocol_selected()
                    self.protocol_area.set_patient(None)
                    self._apply_patient_item_styles()
                    self._refresh_buttons()
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

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
        self._selected_protocol_item = None

        last_added_id: int | None = None
        if select_last_added and self._patients:
            last_added_id = self._patients[0].id

        if select_patient_id:
            self._selected_patient_id = int(select_patient_id)

        for p in self._patients:
            it = QtWidgets.QTreeWidgetItem([f"+ {p.full_name}"])
            it.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("patient", p.id))
            # Должно быть раскрываемо (протоколы подгружаем по клику). Сам индикатор ветки скрываем стилем.
            it.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            it.setTextAlignment(0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            f = it.font(0)
            f.setPointSize(13)
            it.setFont(0, f)

            self.patient_tree.addTopLevelItem(it)

        # selection
        if select_patient_id:
            self._select_patient_by_id(select_patient_id)
        elif select_last_added and self._patients:
            # list is ordered by created_at desc, so [0] is most recent
            self._select_patient_by_id(self._patients[0].id)
        self._apply_patient_item_styles(last_added_id=last_added_id)
        self._refresh_buttons()

    def _apply_patient_item_styles(self, *, last_added_id: int | None = None) -> None:
        """
        Единая логика оформления списка пациентов.

        Требование: выбранный пациент отображается жирным.
        Поиск/последний добавленный могут подсвечиваться фоном, но жирность остаётся только у выбранного.
        """
        search_bg = QtGui.QColor("#c6dbff")
        search_fg = QtGui.QColor("#000000")

        for i in range(self.patient_tree.topLevelItemCount()):
            it = self.patient_tree.topLevelItem(i)
            tag = it.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not tag or tag[0] != "patient":
                continue
            pid = int(tag[1])

            # base font (not bold)
            f = it.font(0)
            f.setBold(False)
            it.setFont(0, f)
            it.setBackground(0, QtGui.QBrush())
            it.setForeground(0, QtGui.QBrush())
            it.setData(0, ROLE_PATIENT_SELECTED, False)

            if self._selected_patient_id is not None and pid == int(self._selected_patient_id):
                f2 = it.font(0)
                f2.setBold(True)
                it.setFont(0, f2)
                it.setData(0, ROLE_PATIENT_SELECTED, True)
                continue

            if pid in self._search_highlight_ids or (last_added_id is not None and pid == int(last_added_id)):
                it.setBackground(0, search_bg)
                it.setForeground(0, search_fg)
        try:
            self.patient_tree.viewport().update()
        except Exception:
            pass

    def _clear_protocol_selected(self) -> None:
        if self._selected_protocol_item is None:
            return
        try:
            self._selected_protocol_item.setData(0, ROLE_PROTOCOL_SELECTED, False)
        except Exception:
            pass
        self._selected_protocol_item = None

    def _set_protocol_selected(self, item: QtWidgets.QTreeWidgetItem) -> None:
        self._clear_protocol_selected()
        self._selected_protocol_item = item
        item.setData(0, ROLE_PROTOCOL_SELECTED, True)
        try:
            self.patient_tree.viewport().update()
        except Exception:
            pass

    def _select_patient_by_id(self, patient_id: int) -> QtWidgets.QTreeWidgetItem | None:
        for i in range(self.patient_tree.topLevelItemCount()):
            it = self.patient_tree.topLevelItem(i)
            tag = it.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if tag and tag[0] == "patient" and int(tag[1]) == int(patient_id):
                self.patient_tree.setCurrentItem(it)
                return it
        return None

    @QtCore.Slot(QtWidgets.QTreeWidgetItem, int)
    def _on_patient_tree_clicked(self, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
        tag = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not tag:
            return
        kind, idv = tag
        if kind == "patient":
            pid = int(idv)
            self._selected_patient_id = pid
            self._clear_protocol_selected()
            self.protocol_area.set_patient(pid)
            self._apply_patient_item_styles()
            self._refresh_buttons()
            # По ТЗ: клик раскрывает/сворачивает протоколы (как "+" / "-")
            self._toggle_protocol_children(item, pid)
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
                self._clear_protocol_selected()
                self.protocol_area.set_patient(pid)
                self._refresh_buttons()
            else:
                st_id = int(item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1) or 0)
                self._selected_patient_id = pid
                self.protocol_area.set_patient(pid)
                self._refresh_buttons()
                self.protocol_area.open_saved_protocol(protocol_id=proto_id, study_type_id=st_id)

            if proto_id > 0:
                self._set_protocol_selected(item)
            self._apply_patient_item_styles()
            self.patient_tree.setCurrentItem(item)
            self.patient_tree.clearFocus()
            self.protocol_area.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            return

    @QtCore.Slot(QtCore.QPoint)
    def _on_patient_tree_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.patient_tree.itemAt(pos)
        if not item:
            return
        tag = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not tag:
            return
        kind, idv = tag
        if kind != "protocol":
            return
        proto_id = int(idv)
        if proto_id <= 0:
            return

        parent = item.parent()
        if not parent:
            return
        pid = int(parent.data(0, QtCore.Qt.ItemDataRole.UserRole)[1])

        menu = QtWidgets.QMenu(self)
        act_del = menu.addAction("Удалить протокол…")
        chosen = menu.exec(self.patient_tree.viewport().mapToGlobal(pos))
        if chosen != act_del:
            return

        if (
            QtWidgets.QMessageBox.question(
                self,
                "Удаление протокола",
                "Вы точно хотите удалить выбранный протокол?\n"
                "Данные протокола будут стерты.",
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return

        try:
            delete_protocol(proto_id)
        except Exception as e:  # pragma: no cover
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось удалить протокол: {e}")
            return

        # обновляем список
        self._reload_patients(select_patient_id=pid)
        pit = self._select_patient_by_id(pid)
        if pit:
            self._toggle_protocol_children(pit, pid)

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
            self._set_patient_prefix(patient_item)
            return

        # Populate children
        patient_item.takeChildren()
        protocols = list_protocols_for_patient(patient_id)
        if not protocols:
            ch = QtWidgets.QTreeWidgetItem(["Нет протокола"])
            ch.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("protocol", 0))
            ch.setTextAlignment(0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            f = ch.font(0)
            f.setPointSize(10)
            ch.setFont(0, f)
            patient_item.addChild(ch)
        else:
            for pr in protocols:
                title = f"{pr.study_name} {pr.created_at}"
                ch = QtWidgets.QTreeWidgetItem([title])
                ch.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("protocol", pr.id))
                ch.setData(0, QtCore.Qt.ItemDataRole.UserRole + 1, int(pr.study_type_id))
                ch.setTextAlignment(0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                f = ch.font(0)
                f.setPointSize(10)
                ch.setFont(0, f)
                patient_item.addChild(ch)
        patient_item.setExpanded(True)
        self._set_patient_prefix(patient_item)

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
        self._set_patient_prefix(item)

    @QtCore.Slot(QtWidgets.QTreeWidgetItem)
    def _on_patient_tree_collapsed(self, item: QtWidgets.QTreeWidgetItem) -> None:
        tag = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not tag:
            return
        kind, _idv = tag
        if kind != "patient":
            return
        self._set_patient_prefix(item)

    def _set_patient_prefix(self, item: QtWidgets.QTreeWidgetItem) -> None:
        tag = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not tag or tag[0] != "patient":
            return
        name = str(item.text(0) or "")
        # strip existing prefix if any
        for pref in ("+ ", "- ", "− "):
            if name.startswith(pref):
                name = name[len(pref) :]
                break
        prefix = "- " if item.isExpanded() else "+ "
        item.setText(0, prefix + name)

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
        if dlg.result.patient_ids:
            pid = int(dlg.result.patient_ids[0])
            self._selected_patient_id = pid
            self._reload_patients(select_patient_id=pid)
            self.protocol_area.set_patient(pid)
        else:
            self._reload_patients()

    @QtCore.Slot()
    def _back_to_login(self) -> None:
        # main_qt.py will handle showing login again
        self.logout_requested.emit()
        self.close()

    def _open_help(self) -> None:
        s = load_external_files_settings()
        if s.help_path and Path(s.help_path).exists():
            open_in_os(Path(s.help_path))
            return
        self._open_side_file(preferred_names=["help.exe", "Справка.exe"])

    def _open_service(self) -> None:
        s = load_external_files_settings()
        if s.service_path and Path(s.service_path).exists():
            open_in_os(Path(s.service_path))
            return
        self._open_side_file(preferred_names=["service.html", "service.htm", "Сервис.html", "Сервис.htm"])

    def _open_about(self) -> None:
        s = load_external_files_settings()
        if s.about_path and Path(s.about_path).exists():
            open_in_os(Path(s.about_path))
            return
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
