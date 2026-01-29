from __future__ import annotations

import math
import re
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from ..db import connect
from ..repo import get_protocol_draft_id, load_protocol_values
from .auto_combo import AutoComboBox

TEMPLATE_MULTI_DELIM = " | "


@dataclass(frozen=True)
class FieldMeta:
    id: int
    group_id: int
    tab_id: int
    name: str
    field_type: str
    column_num: int
    display_order: int
    precision: int | None
    ref_male_min: float | None
    ref_male_max: float | None
    ref_female_min: float | None
    ref_female_max: float | None
    formula: str | None
    required: bool
    height: int
    width: int
    is_hidden: bool
    trigger_field_id: int | None
    trigger_value: str | None


@dataclass
class FieldBinding:
    meta: FieldMeta
    widget: QtWidgets.QWidget
    label: QtWidgets.QLabel
    container: QtWidgets.QWidget

    def get_str(self) -> str:
        w = self.widget
        if isinstance(w, QtWidgets.QLineEdit):
            return w.text()
        if isinstance(w, QtWidgets.QPlainTextEdit):
            return w.toPlainText()
        if isinstance(w, QtWidgets.QComboBox):
            tpl_text = w.property("template_text_widget")
            if isinstance(tpl_text, QtWidgets.QPlainTextEdit):
                return tpl_text.toPlainText()
            if w.property("template_multi"):
                model = w.model()
                values = [
                    model.item(i).text()
                    for i in range(model.rowCount())
                    if model.item(i).checkState() == QtCore.Qt.CheckState.Checked
                ]
                return TEMPLATE_MULTI_DELIM.join(values)
            return w.currentText()
        if isinstance(w, QtWidgets.QDateEdit):
            return w.date().toString("dd.MM.yyyy")
        if isinstance(w, QtWidgets.QTimeEdit):
            return w.time().toString("HH:mm")
        return ""

    def set_str(self, value: str) -> None:
        w = self.widget
        if isinstance(w, QtWidgets.QLineEdit):
            w.setText(value)
        elif isinstance(w, QtWidgets.QPlainTextEdit):
            w.setPlainText(value)
        elif isinstance(w, QtWidgets.QComboBox):
            tpl_text = w.property("template_text_widget")
            if isinstance(tpl_text, QtWidgets.QPlainTextEdit):
                tpl_text.setPlainText(value)
                return
            if w.property("template_multi"):
                model = w.model()
                if value:
                    if TEMPLATE_MULTI_DELIM in value:
                        parts = [p.strip() for p in value.split(TEMPLATE_MULTI_DELIM) if p.strip()]
                    else:
                        parts = [value.strip()]
                else:
                    parts = []
                for i in range(model.rowCount()):
                    item = model.item(i)
                    item.setCheckState(
                        QtCore.Qt.CheckState.Checked if item.text() in parts else QtCore.Qt.CheckState.Unchecked
                    )
                w.setEditText(" ".join(parts))
            else:
                idx = w.findText(value)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                else:
                    # fallback: allow user value
                    w.setCurrentText(value)
        elif isinstance(w, QtWidgets.QDateEdit):
            qd = QtCore.QDate.fromString(value, "dd.MM.yyyy")
            if qd.isValid():
                w.setDate(qd)
        elif isinstance(w, QtWidgets.QTimeEdit):
            qt = QtCore.QTime.fromString(value, "HH:mm")
            if qt.isValid():
                w.setTime(qt)


class _ResizeFilter(QtCore.QObject):
    """Вызывает callback при Resize виджета (для подгонки ширины шаблонного поля под viewport)."""

    def __init__(self, parent: QtCore.QObject, callback):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.Resize:
            try:
                self._callback()
            except Exception:
                pass
        return super().eventFilter(obj, event)


class CollapsibleGroupBox(QtWidgets.QWidget):
    def __init__(self, title: str, *, expanded: bool = False, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.toggle_btn = QtWidgets.QToolButton()
        # По требованию: НЕ добавляем двоеточие автоматически
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # По ТЗ: группы выглядят как "длинные кнопки" на всю ширину
        self.toggle_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.toggle_btn.setMinimumHeight(34)
        self.toggle_btn.setMaximumHeight(34)
        self.toggle_btn.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow
        )
        self.toggle_btn.clicked.connect(self._on_toggled)
        self.toggle_btn.setStyleSheet(
            """
            QToolButton {
              background: #C8E6C9; /* светло-зелёный */
              font-weight: bold;
              font-size: 12pt;
              padding: 8px 10px;
              /* Чтобы "шапка" группы заканчивалась там же, где и поля (с небольшим отступом) */
              margin-left: 6px;
              margin-right: 6px;
              border: 1px solid #bbbbbb;
              border-radius: 4px;
              text-align: left;
            }
            """
        )
        layout.addWidget(self.toggle_btn)

        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        # По скринам: элементы внутри группы должны быть "на одном уровне" с заголовком/табом,
        # без лишнего сдвига вправо.
        # Чуть ближе к заголовку группы
        self.content_layout.setContentsMargins(0, 4, 0, 4)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)
        layout.addWidget(self.content)

    @QtCore.Slot()
    def _on_toggled(self) -> None:
        expanded = self.toggle_btn.isChecked()
        self.toggle_btn.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow
        )
        self.content.setVisible(expanded)


class ProtocolBuilderQt(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(
        self,
        *,
        parent: QtWidgets.QWidget,
        patient_id: int,
        patient_gender: str,
        study_type_id: int,
        protocol_id: int | None = None,
        read_only: bool = False,
    ):
        super().__init__(parent)
        self.parent = parent
        self.patient_id = patient_id
        self.patient_gender = patient_gender  # 'муж'|'жен'
        self.study_type_id = study_type_id
        self._forced_protocol_id = protocol_id
        self._read_only = read_only

        self.tab_widget = QtWidgets.QTabWidget()
        # DocumentMode иногда рисует лишнюю "полосу/линию" вверху на Windows;
        # по скринам нужна более "плоская" панель без разделителей.
        self.tab_widget.setDocumentMode(False)

        self.fields: dict[int, FieldBinding] = {}
        self.field_meta: dict[int, FieldMeta] = {}
        self.hidden_by_trigger: dict[int, list[int]] = {}
        # For TЗ formula syntax "Вкладка.Группа.Поле"
        self._tab_name_by_id: dict[int, str] = {}
        self._group_name_by_id: dict[int, str] = {}
        self._field_id_by_path: dict[str, int] = {}
        self._scroll_body_by_viewport: dict[QtCore.QObject, QtWidgets.QWidget] = {}

        self._protocol_id: int | None = None
        self._loading = False
        self._tab_ids: list[int] = []

    def build(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tab_widget, 1)

        self._load_structure()
        self._load_existing_protocol()
        self._recalculate_formulas()
        self._apply_tab_styles()
        return container

    def _load_structure(self) -> None:
        self.tab_widget.clear()
        self.fields.clear()
        self.field_meta.clear()
        self.hidden_by_trigger.clear()
        self._tab_ids.clear()
        self._tab_name_by_id.clear()
        self._group_name_by_id.clear()
        self._field_id_by_path.clear()

        with connect() as conn:
            tabs = conn.execute(
                """
                SELECT id, name, display_order
                FROM tabs
                WHERE study_type_id = ?
                ORDER BY display_order
                """,
                (self.study_type_id,),
            ).fetchall()

            if not tabs:
                lbl = QtWidgets.QLabel(
                    "Для типа исследования не создана структура.\n"
                    "Откройте настройки и создайте вкладки, группы и поля.",
                    alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
                )
                lbl.setStyleSheet("color: #b00020;")
                self.tab_widget.addTab(lbl, "Нет структуры")
                return

            for tab in tabs:
                tab_id = int(tab["id"])
                tab_name = str(tab["name"])
                self._tab_ids.append(tab_id)
                self._tab_name_by_id[tab_id] = tab_name

                tab_root = QtWidgets.QWidget()
                tab_layout = QtWidgets.QVBoxLayout(tab_root)
                tab_layout.setContentsMargins(0, 0, 0, 0)
                tab_layout.setSpacing(8)

                scroll = QtWidgets.QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
                scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

                scroll_body = QtWidgets.QWidget()
                scroll_body.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum
                )
                scroll_layout = QtWidgets.QVBoxLayout(scroll_body)
                # Небольшой отступ справа от края окна (и симметрично слева)
                scroll_layout.setContentsMargins(0, 8, 10, 8)
                scroll_layout.setSpacing(10)
                scroll_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
                scroll_layout.addStretch(1)
                scroll.setWidget(scroll_body)
                vp = scroll.viewport()
                self._scroll_body_by_viewport[vp] = scroll_body
                vp.installEventFilter(self)
                tab_layout.addWidget(scroll, 1)

                groups = conn.execute(
                    """
                    SELECT id, name, display_order, is_expanded_by_default
                    FROM groups
                    WHERE tab_id = ?
                    ORDER BY display_order
                    """,
                    (tab_id,),
                ).fetchall()
                group_count = len(groups)

                # remove last stretch so we can insert before it (guard for empty layouts)
                stretch_item = None
                if scroll_layout.count() > 0:
                    stretch_item = scroll_layout.takeAt(scroll_layout.count() - 1)

                for group in groups:
                    group_id = int(group["id"])
                    group_name = str(group["name"])
                    self._group_name_by_id[group_id] = group_name
                    expanded = True if group_count == 1 else bool(group["is_expanded_by_default"])

                    group_box = CollapsibleGroupBox(group_name, expanded=expanded)
                    scroll_layout.addWidget(group_box)
                    group_box.toggle_btn.clicked.connect(
                        lambda _=None, sb=scroll_body: sb.setMinimumHeight(sb.sizeHint().height())
                    )

                    fields_rows = conn.execute(
                        """
                        SELECT
                          id, name, field_type, column_num, display_order,
                          precision, reference_male_min, reference_male_max,
                          reference_female_min, reference_female_max, formula,
                          is_required, height, width, is_hidden,
                          hidden_trigger_field_id, hidden_trigger_value
                        FROM fields
                        WHERE group_id = ?
                        ORDER BY column_num, display_order
                        """,
                        (group_id,),
                    ).fetchall()

                    # layout by columns:
                    # - "сплошная" (1) на всю ширину
                    # - "левая" (2) и "правая" (3) в две колонки
                    full_widget = QtWidgets.QWidget()
                    # Сплошная колонка должна растягиваться на всю доступную ширину
                    full_widget.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Preferred,
                    )
                    full_grid = QtWidgets.QGridLayout(full_widget)
                    full_grid.setContentsMargins(6, 0, 6, 0)
                    full_grid.setHorizontalSpacing(6)
                    full_grid.setVerticalSpacing(8)
                    full_grid.setColumnStretch(1, 1)

                    left_widget = QtWidgets.QWidget()
                    left_grid = QtWidgets.QGridLayout(left_widget)
                    left_grid.setContentsMargins(6, 0, 6, 0)
                    left_grid.setHorizontalSpacing(6)
                    left_grid.setVerticalSpacing(8)
                    left_grid.setColumnStretch(1, 1)

                    right_widget = QtWidgets.QWidget()
                    right_grid = QtWidgets.QGridLayout(right_widget)
                    right_grid.setContentsMargins(6, 0, 6, 0)
                    right_grid.setHorizontalSpacing(6)
                    right_grid.setVerticalSpacing(8)
                    right_grid.setColumnStretch(1, 1)

                    row_index = {"full": 0, "left": 0, "right": 0}
                    label_widths = {"full": 0, "left": 0, "right": 0}
                    max_label_width = 0
                    counts = {"full": 0, "left": 0, "right": 0}

                    for fr in fields_rows:
                        field_id = int(fr["id"])
                        meta = FieldMeta(
                            id=field_id,
                            group_id=group_id,
                            tab_id=tab_id,
                            name=str(fr["name"]),
                            field_type=str(fr["field_type"]),
                            column_num=int(fr["column_num"] or 1),
                            display_order=int(fr["display_order"] or 0),
                            precision=int(fr["precision"]) if fr["precision"] is not None else None,
                            ref_male_min=float(fr["reference_male_min"]) if fr["reference_male_min"] is not None else None,
                            ref_male_max=float(fr["reference_male_max"]) if fr["reference_male_max"] is not None else None,
                            ref_female_min=float(fr["reference_female_min"]) if fr["reference_female_min"] is not None else None,
                            ref_female_max=float(fr["reference_female_max"]) if fr["reference_female_max"] is not None else None,
                            formula=str(fr["formula"]) if fr["formula"] is not None else None,
                            required=bool(fr["is_required"]),
                            height=int(fr["height"] or 1),
                            width=int(fr["width"] or 20),
                            is_hidden=bool(fr["is_hidden"]),
                            trigger_field_id=int(fr["hidden_trigger_field_id"]) if fr["hidden_trigger_field_id"] is not None else None,
                            trigger_value=str(fr["hidden_trigger_value"]) if fr["hidden_trigger_value"] is not None else None,
                        )
                        self.field_meta[field_id] = meta
                        # "Вкладка.Группа.Поле" for formulas; keep a normalized key.
                        # If duplicates exist, later one will overwrite; that's OK because we use full path.
                        key = f"{tab_name.strip()}.{group_name.strip()}.{meta.name.strip()}"
                        self._field_id_by_path[key] = field_id

                        cnum = meta.column_num or 1
                        if cnum == 1:
                            grid = full_grid
                            key = "full"
                        elif cnum == 2:
                            grid = left_grid
                            key = "left"
                        else:
                            grid = right_grid
                            key = "right"

                        r = row_index[key]
                        row_index[key] = r + 1

                        binding = self._create_field_widget(conn, meta)
                        self.fields[field_id] = binding

                        if meta.required:
                            binding.label.setText(binding.label.text() + " *")
                        # Выравнивание подписей:
                        # - слева/сплошная: по левому краю (по самой длинной подписи слева)
                        # - справа: по правому краю (по самой длинной подписи справа)
                        h_align = (
                            QtCore.Qt.AlignmentFlag.AlignRight
                            if key == "right"
                            else QtCore.Qt.AlignmentFlag.AlignLeft
                        )
                        v_align = (
                            QtCore.Qt.AlignmentFlag.AlignTop
                            if meta.field_type == "шаблон"
                            else QtCore.Qt.AlignmentFlag.AlignVCenter
                        )
                        binding.label.setAlignment(h_align | v_align)
                        try:
                            lw = binding.label.sizeHint().width()
                            label_widths[key] = max(label_widths.get(key, 0), lw)
                            max_label_width = max(max_label_width, lw)
                        except Exception:
                            pass
                        counts[key] += 1

                        # hidden triggers mapping
                        if meta.is_hidden and meta.trigger_field_id:
                            self.hidden_by_trigger.setdefault(meta.trigger_field_id, []).append(field_id)
                            binding.container.setVisible(False)

                        grid.addWidget(binding.label, r, 0, 1, 1)
                        if meta.field_type == "шаблон":
                            # Важно: шаблонный блок выше строки (комбо + текст ниже).
                            # При изменении высоты текстового поля без AlignTop Qt может центрировать
                            # контейнер по вертикали внутри строки, и комбобокс "уезжает" вниз.
                            grid.addWidget(
                                binding.container,
                                r,
                                1,
                                1,
                                1,
                                QtCore.Qt.AlignmentFlag.AlignTop,
                            )
                        else:
                            grid.addWidget(binding.container, r, 1, 1, 1)

                    if counts["full"] > 0:
                        group_box.content_layout.addWidget(full_widget)

                    if counts["left"] > 0 or counts["right"] > 0:
                        lr_layout = QtWidgets.QHBoxLayout()
                        lr_layout.setContentsMargins(0, 0, 0, 0)
                        lr_layout.setSpacing(16)
                        # Важно: даже если одна из колонок пуста, добавляем оба widget и НЕ скрываем их,
                        # иначе оставшаяся колонка растянется "сплошняком" на всю ширину.
                        # Пустая колонка должна просто занимать своё место (половину ширины).
                        lr_layout.addWidget(left_widget, 1)
                        lr_layout.addWidget(right_widget, 1)
                        # Чтобы правая колонка не "висела" по центру между строками левой —
                        # прижимаем оба блока к верху.
                        lr_layout.setAlignment(left_widget, QtCore.Qt.AlignmentFlag.AlignTop)
                        lr_layout.setAlignment(right_widget, QtCore.Qt.AlignmentFlag.AlignTop)
                        group_box.content_layout.addLayout(lr_layout)

                    # Ширина колонки подписей:
                    # - full и left должны стартовать одинаково (от самой длинной подписи слева)
                    # - right отдельно (и подписи там AlignRight)
                    mw_left = int(label_widths.get("left", 0) or 0)
                    mw_full = int(label_widths.get("full", 0) or 0)
                    mw_right = int(label_widths.get("right", 0) or 0)
                    mw_lf = max(mw_left, mw_full)
                    if mw_lf > 0:
                        full_grid.setColumnMinimumWidth(0, mw_lf)
                        left_grid.setColumnMinimumWidth(0, mw_lf)
                    if mw_right > 0:
                        right_grid.setColumnMinimumWidth(0, mw_right)

                if stretch_item is not None:
                    scroll_layout.addItem(stretch_item)
                else:
                    scroll_layout.addStretch(1)
                scroll_body.adjustSize()
                try:
                    scroll_body.setMinimumHeight(scroll_body.sizeHint().height())
                except Exception:
                    pass
                try:
                    scroll_body.setMinimumWidth(scroll.viewport().width())
                except Exception:
                    pass
                self.tab_widget.addTab(tab_root, tab_name)
                self.tab_widget.tabBar().setTabData(self.tab_widget.count() - 1, tab_id)

        # connect triggers after build
        for trigger_id in self.hidden_by_trigger.keys():
            if trigger_id in self.fields:
                self._connect_value_change(trigger_id, lambda _=None, fid=trigger_id: self._update_hidden(fid))

        # connect formula recalculation
        for field_id, binding in self.fields.items():
            if binding.meta.field_type in ("число", "строка", "словарь"):
                self._connect_value_change(field_id, lambda _=None: self._recalculate_formulas())

        # connect reference checks (after self.fields is populated)
        for field_id, binding in self.fields.items():
            if binding.meta.field_type in ("число", "формула"):
                self._connect_value_change(field_id, lambda _=None, fid=field_id: self._check_reference(fid))

    def _apply_tab_styles(self) -> None:
        # По ТЗ: активная вкладка — розовая, неактивная — синяя.
        self.tab_widget.setStyleSheet(
            """
            QTabWidget::pane { border: 0px; }
            QTabBar::tab {
              background: #9ec9f5;
              color: black;
              font: bold 12pt "Arial";
              padding: 10px 18px;
              margin-right: 4px;
              border-top-left-radius: 6px;
              border-top-right-radius: 6px;
              border: 1px solid #bbbbbb;
            }
            QTabBar::tab:selected { background: #FF95A8; }
            """
        )

    def _create_field_widget(self, conn, meta: FieldMeta) -> FieldBinding:
        label = QtWidgets.QLabel(meta.name)
        # Чуть меньше расстояние между подписью и полем
        label.setStyleSheet("font-weight: bold; padding: 4px 4px;")

        container = QtWidgets.QWidget()
        container.setStyleSheet("border: 0px;")
        hl = QtWidgets.QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        w: QtWidgets.QWidget
        t = meta.field_type

        apply_border = True
        grow_height = False
        binding_widget: QtWidgets.QWidget | None = None
        display_widget: QtWidgets.QWidget | None = None
        if t == "текст":
            te = QtWidgets.QPlainTextEdit()
            te.setMinimumHeight(70)
            if self._read_only:
                te.setReadOnly(True)
            w = te
        elif t == "словарь":
            cb = AutoComboBox(max_popup_items=30)
            cb.setFont(QtGui.QFont("Arial", 12))
            # Словарь: обычный комбобокс, но значение можно отредактировать (ввод своего значения).
            cb.setEditable(True)
            if cb.lineEdit():
                cb.lineEdit().setReadOnly(False)
            cb.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
            cb.setSizeAdjustPolicy(
                QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            cb.setMinimumContentsLength(16)
            vals = conn.execute(
                "SELECT value FROM dictionary_values WHERE field_id = ? ORDER BY display_order",
                (meta.id,),
            ).fetchall()
            for v in vals:
                cb.addItem(str(v["value"]))
            cb.setCurrentIndex(-1)
            # Пусто, когда ничего не выбрано
            cb.setCurrentText("")
            if self._read_only:
                cb.setEnabled(False)
            # Ползунок в выпадающем списке при большом числе значений
            _view = cb.view()
            if _view is not None:
                _view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                _view.setFont(QtGui.QFont("Arial", 12))
            # Серая рамка, синяя при фокусе и при открытом списке (:on)
            cb.setStyleSheet(
                "QComboBox { border: 1px solid #bbbbbb; border-radius: 4px; padding: 4px 6px; } "
                "QComboBox:focus, QComboBox:on { border: 2px solid #007bff; padding: 3px 5px; }"
            )
            w = cb
            grow_height = False
            apply_border = False  # стиль уже задан выше, не перезаписывать
        elif t == "шаблон":
            cb = AutoComboBox(max_popup_items=30)
            cb.setFont(QtGui.QFont("Arial", 12))
            cb.setEditable(True)
            if cb.lineEdit():
                cb.lineEdit().setReadOnly(True)
            cb.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
            cb.setSizeAdjustPolicy(
                QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            cb.setMinimumContentsLength(16)
            vals = conn.execute(
                "SELECT value FROM dictionary_values WHERE field_id = ? ORDER BY display_order",
                (meta.id,),
            ).fetchall()
            for v in vals:
                cb.addItem(str(v["value"]))
            cb.setCurrentIndex(-1)
            cb.setEditText("")
            # По просьбе: пусто, без "Выберите"
            self._setup_combo_placeholder(cb, "")
            if self._read_only:
                cb.setEnabled(False)
            _tpl_view = cb.view()
            if _tpl_view is not None:
                _tpl_view.setFont(QtGui.QFont("Arial", 12))

            ta = QtWidgets.QPlainTextEdit()
            ta.setFont(QtGui.QFont("Arial", 12))
            ta.setPlaceholderText("")
            if self._read_only:
                ta.setReadOnly(True)
            # Скролл — через QScrollArea (как в окне протокола), чтобы была каретка
            ta.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            ta.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            ta.setStyleSheet(
                "QPlainTextEdit { border: 1px solid #bbbbbb; border-radius: 4px; padding: 4px 6px; } "
                "QPlainTextEdit:focus { border: 2px solid #007bff; padding: 3px 5px; }"
            )
            ta.setMinimumHeight(80)

            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll_area.setFixedHeight(200)  # поле всегда одной высоты, скроллбар при переполнении
            scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll_area.setWidget(ta)
            scroll_area.setStyleSheet("QScrollArea { border: 0; background: transparent; }")
            # Виджет внутри не растягиваем — высота по контенту, чтобы скроллбар появился
            scroll_area.setWidgetResizable(False)

            # Фиксированная высота области (как у окна протокола) — поле не меняет размер
            _template_area_height = 200

            def _update_template_scroll_height() -> None:
                # Внутренний виджет не меньше высоты области; растёт только при переполнении
                line_count = max(1, ta.document().lineCount())
                line_h = ta.fontMetrics().height()
                doc_h = line_count * line_h + 8
                ta.setMinimumHeight(max(_template_area_height, min(2000, doc_h)))
                ta.setFixedHeight(ta.minimumHeight())

            def _update_template_ta_width() -> None:
                vp = scroll_area.viewport()
                if vp is not None and vp.width() > 0:
                    ta.setMinimumWidth(vp.width())
                    ta.setFixedWidth(vp.width())

            ta.setMinimumHeight(_template_area_height)
            ta.setFixedHeight(_template_area_height)
            ta.document().contentsChanged.connect(_update_template_scroll_height)
            scroll_area.viewport().installEventFilter(
                _ResizeFilter(scroll_area.viewport(), _update_template_ta_width)
            )
            QtCore.QTimer.singleShot(50, _update_template_ta_width)

            # Серая рамка, синяя при фокусе и при открытом списке (:on)
            cb.setStyleSheet(
                "QComboBox { border: 1px solid #bbbbbb; border-radius: 4px; padding: 4px 6px; } "
                "QComboBox:focus, QComboBox:on { border: 2px solid #007bff; padding: 3px 5px; }"
            )

            def _append_value(text: str) -> None:
                if not text or not text.strip():
                    return
                cur = ta.toPlainText().strip()
                if not cur:
                    ta.setPlainText(text)
                else:
                    ta.setPlainText(cur + "\n" + text)
                ta.moveCursor(QtGui.QTextCursor.MoveOperation.End)
                cb.setCurrentIndex(-1)

            cb.activated.connect(lambda _idx, c=cb: _append_value(c.currentText()))
            cb.setProperty("template_text_widget", ta)

            # Layout: комбобокс справа от названия, область прокрутки с текстом ниже
            inner = QtWidgets.QWidget()
            vlayout = QtWidgets.QVBoxLayout(inner)
            vlayout.setContentsMargins(0, 0, 0, 0)
            vlayout.setSpacing(6)
            vlayout.addWidget(cb, 0)
            vlayout.addWidget(scroll_area, 0)
            w = inner
            apply_border = False
            grow_height = True
            binding_widget = cb
            display_widget = inner
        elif t == "дата":
            de = QtWidgets.QDateEdit()
            de.setCalendarPopup(True)
            de.setDisplayFormat("dd.MM.yyyy")
            if self._read_only:
                de.setEnabled(False)
            w = de
        elif t == "время":
            te = QtWidgets.QTimeEdit()
            te.setDisplayFormat("HH:mm")
            if self._read_only:
                te.setEnabled(False)
            w = te
        else:
            le = QtWidgets.QLineEdit()
            if t in ("число", "формула"):
                le.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            if t == "число":
                # По ТЗ: "число" — ввод только числа, с поддержкой запятой и точности.
                decimals = int(meta.precision) if meta.precision is not None else 6
                v = QtGui.QDoubleValidator(le)
                v.setNotation(QtGui.QDoubleValidator.Notation.StandardNotation)
                v.setDecimals(max(0, min(10, decimals)))
                # allow comma as decimal separator (RU locale)
                try:
                    v.setLocale(QtCore.QLocale(QtCore.QLocale.Language.Russian, QtCore.QLocale.Country.Russia))
                except Exception:
                    v.setLocale(QtCore.QLocale())
                # allow wide range, incl. negatives (референсы могут быть отрицательные)
                v.setBottom(-1e12)
                v.setTop(1e12)
                le.setValidator(v)

                def _normalize_number() -> None:
                    if self._loading:
                        return
                    raw = le.text().strip()
                    if not raw:
                        return
                    try:
                        val = float(raw.replace(",", "."))
                    except ValueError:
                        return
                    if meta.precision is not None:
                        val = round(val, int(meta.precision))
                        s = f"{val:.{int(meta.precision)}f}"
                    else:
                        s = str(val)
                    le.setText(s.replace(".", ","))

                le.editingFinished.connect(_normalize_number)
            if t == "формула" or self._read_only:
                le.setReadOnly(True)
            w = le

        if display_widget is None:
            display_widget = w
        if binding_widget is None:
            binding_widget = w

        display_widget.setMinimumWidth(200)
        if not grow_height:
            display_widget.setMinimumHeight(30)
        if apply_border:
            # Рамка серая, при фокусе — синяя
            _field_normal = "border: 1px solid #bbbbbb; border-radius: 4px; padding: 4px 6px;"
            _field_focus = "border: 2px solid #007bff; padding: 3px 5px;"
            _full = (
                "QLineEdit, QPlainTextEdit, QDateEdit, QTimeEdit { " + _field_normal + " } "
                "QLineEdit:focus, QPlainTextEdit:focus, QDateEdit:focus, QTimeEdit:focus { " + _field_focus + " }"
            )
            display_widget.setProperty("base_border_style", _full)
            display_widget.setStyleSheet(_full)
        display_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred if grow_height else QtWidgets.QSizePolicy.Policy.Fixed,
        )
        if meta.field_type == "шаблон":
            # Шаблонный блок не должен растягиваться по вертикали; пусть будет фиксированный
            # (комбобокс + поле высотой 40), но занимает всю ширину.
            display_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
            )
        hl.addWidget(display_widget, 1)

        binding = FieldBinding(meta=meta, widget=binding_widget, label=label, container=container)

        return binding

    def _connect_value_change(self, field_id: int, handler) -> None:
        w = self.fields[field_id].widget
        if isinstance(w, QtWidgets.QLineEdit):
            w.textChanged.connect(handler)
        elif isinstance(w, QtWidgets.QPlainTextEdit):
            w.textChanged.connect(handler)
        elif isinstance(w, QtWidgets.QComboBox):
            w.currentTextChanged.connect(handler)
            tpl_text = w.property("template_text_widget")
            if isinstance(tpl_text, QtWidgets.QPlainTextEdit):
                tpl_text.textChanged.connect(handler)
        elif isinstance(w, QtWidgets.QDateEdit):
            w.dateChanged.connect(handler)
        elif isinstance(w, QtWidgets.QTimeEdit):
            w.timeChanged.connect(handler)

    def _setup_combo_placeholder(self, combo: QtWidgets.QComboBox, text: str) -> None:
        if not combo.isEditable():
            combo.setEditable(True)
        le = combo.lineEdit()
        if le is None:
            return
        le.setPlaceholderText(text)
        pal = combo.palette()
        pal.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor("#9aa0a6"))
        combo.setPalette(pal)

    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.Resize and obj in self._scroll_body_by_viewport:
            try:
                body = self._scroll_body_by_viewport[obj]
                if isinstance(body, QtWidgets.QWidget) and isinstance(obj, QtWidgets.QWidget):
                    body.setMinimumWidth(obj.width())
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _current_ref_range(self, meta: FieldMeta) -> tuple[float | None, float | None]:
        if self.patient_gender == "жен":
            return meta.ref_female_min, meta.ref_female_max
        return meta.ref_male_min, meta.ref_male_max

    def _check_reference(self, field_id: int) -> None:
        if self._loading:
            return
        b = self.fields.get(field_id)
        if not b:
            return
        if b.meta.field_type not in ("число", "формула"):
            return
        txt = b.get_str().strip()
        if not txt:
            self._set_widget_bg(b.widget, None)
            return
        try:
            val = float(txt.replace(",", "."))
        except ValueError:
            return
        if b.meta.precision is not None:
            val = round(val, b.meta.precision)
            # keep comma like Tkinter
            if isinstance(b.widget, QtWidgets.QLineEdit):
                self._loading = True
                try:
                    b.widget.setText(f"{val:.{b.meta.precision}f}".replace(".", ","))
                finally:
                    self._loading = False
        rmin, rmax = self._current_ref_range(b.meta)
        if rmin is not None and rmax is not None:
            self._set_widget_bg(b.widget, QtGui.QColor("#FF95A8") if not (rmin <= val <= rmax) else None)

    def _set_widget_bg(self, w: QtWidgets.QWidget, color: QtGui.QColor | None) -> None:
        base = w.property("base_border_style")
        base_style = str(base) if isinstance(base, str) else ""
        if color is None:
            if base_style:
                w.setStyleSheet(base_style)
            else:
                w.setStyleSheet("")
            return
        # Добавляем фон отдельным правилом, не трогая :focus
        if base_style:
            w.setStyleSheet(
                base_style
                + " QLineEdit, QPlainTextEdit, QDateEdit, QTimeEdit { background: "
                + color.name()
                + "; }"
            )
        else:
            w.setStyleSheet(f"background: {color.name()};")

    def _update_hidden(self, trigger_field_id: int) -> None:
        if trigger_field_id not in self.hidden_by_trigger:
            return
        trigger_val = (self.fields[trigger_field_id].get_str() or "").strip()
        trigger_widget = self.fields[trigger_field_id].widget

        def _first_choice_text() -> str | None:
            if not isinstance(trigger_widget, QtWidgets.QComboBox):
                return None
            # template_multi uses model items (checkable)
            if trigger_widget.property("template_multi"):
                try:
                    m = trigger_widget.model()
                    if m is None or m.rowCount() <= 0:
                        return None
                    it = m.item(0)
                    return (it.text() if it else "").strip()
                except Exception:
                    return None
            if trigger_widget.count() <= 0:
                return None
            return (trigger_widget.itemText(0) or "").strip()

        first_txt = _first_choice_text()
        for hid in self.hidden_by_trigger[trigger_field_id]:
            meta = self.field_meta[hid]
            # По ТЗ:
            # - если выбрано первое значение — поле скрыто
            # - любое другое значение — поле показывается
            if isinstance(trigger_widget, QtWidgets.QComboBox) and first_txt is not None:
                if not trigger_val:
                    show = False
                elif trigger_widget.property("template_multi"):
                    parts = [p.strip() for p in trigger_val.split(TEMPLATE_MULTI_DELIM) if p.strip()]
                    # Если выбрано только первое значение — скрываем, иначе показываем
                    show = not (len(parts) == 1 and parts[0] == first_txt)
                else:
                    show = trigger_val != first_txt
            else:
                # fallback for legacy behavior
                show = bool(meta.trigger_value) and trigger_val == str(meta.trigger_value).strip()
            self.fields[hid].container.setVisible(show)
            self.fields[hid].label.setVisible(show)

    def _recalculate_formulas(self) -> None:
        if self._loading:
            return
        for fid, binding in self.fields.items():
            if binding.meta.field_type != "формула":
                continue
            formula = binding.meta.formula
            if not formula:
                continue
            result = self._evaluate_formula(formula)
            if result is None:
                self._loading = True
                try:
                    binding.set_str("")
                    self._set_widget_bg(binding.widget, None)
                finally:
                    self._loading = False
                continue
            if binding.meta.precision is not None:
                result = round(result, binding.meta.precision)
                s = f"{result:.{binding.meta.precision}f}"
            else:
                s = str(result)
            s = s.replace(".", ",")
            self._loading = True
            try:
                binding.set_str(s)
            finally:
                self._loading = False
            self._check_reference(fid)

    def _evaluate_formula(self, formula: str) -> float | None:
        # same approach as Tkinter: references like "Вкладка.Группа.Поле"
        try:
            pattern = r"([\w\s]+)\.([\w\s]+)\.([\w\s]+)"
            field_refs = re.findall(pattern, formula)
            values: dict[str, str] = {}

            for tab_name, group_name, field_name in field_refs:
                key = f"{tab_name.strip()}.{group_name.strip()}.{field_name.strip()}"
                # По ТЗ: матчим именно по полному пути "Вкладка.Группа.Поле".
                v = "0"
                fid = self._field_id_by_path.get(key)
                if fid is not None and fid in self.fields:
                    raw = self.fields[fid].get_str()
                    if not raw or not raw.strip():
                        return None
                    v = raw.replace(",", ".")
                else:
                    # Fallback для старых формул: если путь не найден, пробуем как раньше — по имени поля.
                    found = False
                    for fid2, meta in self.field_meta.items():
                        if meta.name.strip() == field_name.strip() and fid2 in self.fields:
                            raw = self.fields[fid2].get_str()
                            if not raw or not raw.strip():
                                return None
                            v = raw.replace(",", ".")
                            found = True
                            break
                    if not found:
                        return None
                values[key] = v

            expression = formula
            for ref, v in values.items():
                expression = expression.replace(ref, v)

            expression = re.sub(r"\\s*([\\+\\-\\*/])\\s*", r" \\1 ", expression)
            expression = expression.replace(",", ".")

            allowed_chars = set("0123456789.+-*/() ")
            if not all(c in allowed_chars for c in expression):
                return None

            allowed_names = {
                "sqrt": math.sqrt,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "pi": math.pi,
                "e": math.e,
            }
            return float(eval(expression, {"__builtins__": {}}, allowed_names))
        except Exception:
            return None

    def _load_existing_protocol(self) -> None:
        if self._forced_protocol_id:
            self._protocol_id = int(self._forced_protocol_id)
        else:
            self._protocol_id = get_protocol_draft_id(self.patient_id, self.study_type_id)
        if not self._protocol_id:
            return
        values = load_protocol_values(self._protocol_id)
        self._loading = True
        try:
            for fid, v in values.items():
                if fid in self.fields and v:
                    self.fields[fid].set_str(v)
        finally:
            self._loading = False

        # sync hidden fields based on triggers
        for trigger_id in list(self.hidden_by_trigger.keys()):
            if trigger_id in self.fields:
                self._update_hidden(trigger_id)

    def collect_values(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for fid, binding in self.fields.items():
            # if hidden and not visible, skip
            if binding.meta.is_hidden and not binding.container.isVisible():
                continue
            v = binding.get_str()
            out[fid] = v
        return out

    def protocol_id(self) -> int | None:
        return self._protocol_id

    def set_protocol_id(self, protocol_id: int) -> None:
        self._protocol_id = int(protocol_id)

    def clear(self) -> None:
        self.clear_current_tab()

    def clear_current_tab(self) -> None:
        """По ТЗ: очищает все поля текущей вкладки."""
        idx = self.tab_widget.currentIndex()
        if idx < 0:
            return
        tab_id = self.tab_widget.tabBar().tabData(idx)
        if tab_id is None:
            return

        self._loading = True
        try:
            for fid, b in self.fields.items():
                if b.meta.tab_id != int(tab_id):
                    continue
                b.set_str("")
        finally:
            self._loading = False

        for trigger_id in list(self.hidden_by_trigger.keys()):
            if trigger_id in self.fields and self.field_meta[trigger_id].tab_id == int(tab_id):
                self._update_hidden(trigger_id)
        self._recalculate_formulas()
