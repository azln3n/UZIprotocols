from __future__ import annotations

import math
import re
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from ..db import connect
from ..repo import get_protocol_draft_id, load_protocol_values

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


class CollapsibleGroupBox(QtWidgets.QWidget):
    def __init__(self, title: str, *, expanded: bool = False, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.toggle_btn = QtWidgets.QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow
        )
        self.toggle_btn.clicked.connect(self._on_toggled)
        self.toggle_btn.setStyleSheet(
            """
            QToolButton {
              background: #C8E6C9; /* светло-зелёный */
              font-weight: bold;
              font-size: 13pt;
              padding: 10px;
              border-radius: 4px;
              text-align: left;
            }
            """
        )
        layout.addWidget(self.toggle_btn)

        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 6, 12, 6)
        self.content_layout.setSpacing(8)
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
        self.tab_widget.setDocumentMode(True)

        self.fields: dict[int, FieldBinding] = {}
        self.field_meta: dict[int, FieldMeta] = {}
        self.hidden_by_trigger: dict[int, list[int]] = {}

        self._protocol_id: int | None = None
        self._loading = False
        self._tab_ids: list[int] = []

    def build(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
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

                tab_root = QtWidgets.QWidget()
                tab_layout = QtWidgets.QVBoxLayout(tab_root)
                tab_layout.setContentsMargins(0, 0, 0, 0)
                tab_layout.setSpacing(8)

                scroll = QtWidgets.QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

                scroll_body = QtWidgets.QWidget()
                scroll_layout = QtWidgets.QVBoxLayout(scroll_body)
                scroll_layout.setContentsMargins(8, 8, 8, 8)
                scroll_layout.setSpacing(10)
                scroll_layout.addStretch(1)
                scroll.setWidget(scroll_body)
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
                    expanded = True if group_count == 1 else bool(group["is_expanded_by_default"])

                    group_box = CollapsibleGroupBox(group_name, expanded=expanded)
                    scroll_layout.addWidget(group_box)

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

                    # layout by columns
                    col_layout = QtWidgets.QHBoxLayout()
                    col_layout.setContentsMargins(0, 0, 0, 0)
                    col_layout.setSpacing(16)

                    columns: dict[int, QtWidgets.QGridLayout] = {}
                    column_widgets: dict[int, QtWidgets.QWidget] = {}
                    row_index: dict[int, int] = {}

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

                        cnum = meta.column_num or 1
                        if cnum not in columns:
                            colw = QtWidgets.QWidget()
                            grid = QtWidgets.QGridLayout(colw)
                            grid.setContentsMargins(0, 0, 0, 0)
                            grid.setHorizontalSpacing(10)
                            grid.setVerticalSpacing(8)
                            grid.setColumnStretch(1, 1)
                            columns[cnum] = grid
                            column_widgets[cnum] = colw
                            row_index[cnum] = 0
                            col_layout.addWidget(colw, 1)

                        grid = columns[cnum]
                        r = row_index[cnum]
                        row_index[cnum] = r + 1

                        binding = self._create_field_widget(conn, meta)
                        self.fields[field_id] = binding

                        if meta.required:
                            binding.label.setText(binding.label.text() + " *")

                        # hidden triggers mapping
                        if meta.is_hidden and meta.trigger_field_id:
                            self.hidden_by_trigger.setdefault(meta.trigger_field_id, []).append(field_id)
                            binding.container.setVisible(False)

                        grid.addWidget(binding.label, r, 0, 1, 1)
                        grid.addWidget(binding.container, r, 1, 1, 1)

                    group_box.content_layout.addLayout(col_layout)

                if stretch_item is not None:
                    scroll_layout.addItem(stretch_item)
                else:
                    scroll_layout.addStretch(1)
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
              padding: 6px 14px;
              margin-right: 4px;
              border-top-left-radius: 6px;
              border-top-right-radius: 6px;
            }
            QTabBar::tab:selected { background: #FF95A8; }
            """
        )

    def _create_field_widget(self, conn, meta: FieldMeta) -> FieldBinding:
        label = QtWidgets.QLabel(meta.name + ":")
        label.setStyleSheet("font-weight: bold;")

        container = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        w: QtWidgets.QWidget
        t = meta.field_type

        if t == "текст":
            te = QtWidgets.QPlainTextEdit()
            te.setMinimumHeight(max(1, meta.height) * 26)
            if self._read_only:
                te.setReadOnly(True)
            w = te
        elif t == "словарь":
            cb = QtWidgets.QComboBox()
            vals = conn.execute(
                "SELECT value FROM dictionary_values WHERE field_id = ? ORDER BY display_order",
                (meta.id,),
            ).fetchall()
            for v in vals:
                cb.addItem(str(v["value"]))
            if self._read_only:
                cb.setEnabled(False)
            w = cb
        elif t == "шаблон":
            cb = QtWidgets.QComboBox()
            cb.setProperty("template_multi", True)
            cb.setEditable(True)
            if cb.lineEdit():
                cb.lineEdit().setReadOnly(True)
            cb.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
            model = QtGui.QStandardItemModel(cb)
            vals = conn.execute(
                "SELECT value FROM dictionary_values WHERE field_id = ? ORDER BY display_order",
                (meta.id,),
            ).fetchall()
            for v in vals:
                item = QtGui.QStandardItem(str(v["value"]))
                item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(QtCore.Qt.CheckState.Unchecked, QtCore.Qt.ItemDataRole.CheckStateRole)
                model.appendRow(item)
            cb.setModel(model)

            def _toggle_item(idx: QtCore.QModelIndex) -> None:
                item = model.itemFromIndex(idx)
                if not item:
                    return
                state = item.checkState()
                item.setCheckState(
                    QtCore.Qt.CheckState.Unchecked
                    if state == QtCore.Qt.CheckState.Checked
                    else QtCore.Qt.CheckState.Checked
                )
                values = [
                    model.item(i).text()
                    for i in range(model.rowCount())
                    if model.item(i).checkState() == QtCore.Qt.CheckState.Checked
                ]
                cb.setEditText(" ".join(values))

            cb.view().pressed.connect(_toggle_item)
            if self._read_only:
                cb.setEnabled(False)
            w = cb
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

        # width hint
        w.setMinimumWidth(max(120, meta.width * 8))
        hl.addWidget(w, 1)

        binding = FieldBinding(meta=meta, widget=w, label=label, container=container)

        return binding

    def _connect_value_change(self, field_id: int, handler) -> None:
        w = self.fields[field_id].widget
        if isinstance(w, QtWidgets.QLineEdit):
            w.textChanged.connect(handler)
        elif isinstance(w, QtWidgets.QPlainTextEdit):
            w.textChanged.connect(handler)
        elif isinstance(w, QtWidgets.QComboBox):
            w.currentTextChanged.connect(handler)
        elif isinstance(w, QtWidgets.QDateEdit):
            w.dateChanged.connect(handler)
        elif isinstance(w, QtWidgets.QTimeEdit):
            w.timeChanged.connect(handler)

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
        if color is None:
            w.setStyleSheet("")
            return
        w.setStyleSheet(f"background: {color.name()};")

    def _update_hidden(self, trigger_field_id: int) -> None:
        if trigger_field_id not in self.hidden_by_trigger:
            return
        trigger_val = self.fields[trigger_field_id].get_str()
        for hid in self.hidden_by_trigger[trigger_field_id]:
            meta = self.field_meta[hid]
            show = bool(meta.trigger_value) and trigger_val == meta.trigger_value
            self.fields[hid].container.setVisible(show)
            self.fields[hid].label.setVisible(show)

    def _recalculate_formulas(self) -> None:
        if self._loading:
            return
        if self._has_missing_required_fields():
            self._clear_formula_fields()
            return
        for fid, binding in self.fields.items():
            if binding.meta.field_type != "формула":
                continue
            formula = binding.meta.formula
            if not formula:
                continue
            result = self._evaluate_formula(formula)
            if result is None:
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

    def _has_missing_required_fields(self) -> bool:
        for b in self.fields.values():
            if not b.meta.required:
                continue
            if b.meta.is_hidden and not b.container.isVisible():
                continue
            v = b.get_str()
            if not v or not v.strip():
                return True
        return False

    def _clear_formula_fields(self) -> None:
        self._loading = True
        try:
            for fid, binding in self.fields.items():
                if binding.meta.field_type == "формула":
                    binding.set_str("")
                    self._set_widget_bg(binding.widget, None)
        finally:
            self._loading = False
    def _evaluate_formula(self, formula: str) -> float | None:
        # same approach as Tkinter: references like "Вкладка.Группа.Поле"
        try:
            pattern = r"([\w\s]+)\.([\w\s]+)\.([\w\s]+)"
            field_refs = re.findall(pattern, formula)
            values: dict[str, str] = {}

            for tab_name, group_name, field_name in field_refs:
                key = f"{tab_name.strip()}.{group_name.strip()}.{field_name.strip()}"
                # Tkinter only matches by field name; keep parity
                v = "0"
                for fid, meta in self.field_meta.items():
                    if meta.name.strip() == field_name.strip() and fid in self.fields:
                        raw = self.fields[fid].get_str()
                        v = raw.replace(",", ".") if raw else "0"
                        break
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
