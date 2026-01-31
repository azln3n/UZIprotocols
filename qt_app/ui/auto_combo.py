from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


_POPUP_ITEM_PADDING = "padding: 6px 12px;"
_DISPLAY_TEXT_PAD_X = 8
# Межстрочный интервал 85% (одинаково с полем шаблонного текста)
_LINE_HEIGHT_RATIO = 0.85


class WrapAnywhereDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawPrimitive(QtWidgets.QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)

        text_rect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        check_state = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
        if check_state is not None:
            check_rect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheck, opt, opt.widget)
            cb_opt = QtWidgets.QStyleOptionButton()
            cb_opt.rect = check_rect
            cb_opt.state = QtWidgets.QStyle.StateFlag.State_Enabled
            cb_opt.state |= (
                QtWidgets.QStyle.StateFlag.State_On
                if check_state == QtCore.Qt.CheckState.Checked
                else QtWidgets.QStyle.StateFlag.State_Off
            )
            style.drawControl(QtWidgets.QStyle.ControlElement.CE_CheckBox, cb_opt, painter, opt.widget)
            text_rect.setLeft(check_rect.right() + 6)
        painter.save()
        if opt.state & QtWidgets.QStyle.StateFlag.State_Selected:
            painter.setPen(opt.palette.color(QtGui.QPalette.ColorRole.HighlightedText))
        else:
            painter.setPen(opt.palette.color(QtGui.QPalette.ColorRole.Text))
        text_opt = QtGui.QTextOption()
        text_opt.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
        text_opt.setAlignment(QtCore.Qt.AlignmentFlag.AlignJustify)
        painter.drawText(QtCore.QRectF(text_rect), opt.text, text_opt)
        painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index) -> QtCore.QSize:
        try:
            opt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            width = int(opt.rect.width() or 0)
            if width <= 0 and isinstance(opt.widget, QtWidgets.QAbstractItemView):
                try:
                    width = int(opt.widget.viewport().width())
                except Exception:
                    width = 0
            check_state = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
            if check_state is not None:
                width -= 24
            width = max(120, width or 220)
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(opt.font)
            to = QtGui.QTextOption()
            to.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignJustify)
            doc.setDefaultTextOption(to)
            doc.setPlainText(opt.text)
            doc.setTextWidth(width)
            line_h = opt.fontMetrics().height()
            doc_h = int(doc.size().height())
            # Однострочный пункт — высота как у комбобокса (padding 6+6 из стиля), чтобы список не был выше поля
            if doc_h <= line_h * 1.3:
                height = line_h + 12
            else:
                height = doc_h + 6
            return QtCore.QSize(width, max(height, line_h + 12))
        except Exception:
            return QtCore.QSize(220, 30)


# Делегат только для полей «словарь» и «шаблон»: межстрочный интервал 85% и выравнивание по ширине (как в шаблонном тексте).
class DictTemplateLineHeightDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawPrimitive(QtWidgets.QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)

        text_rect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        check_state = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
        if check_state is not None:
            check_rect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheck, opt, opt.widget)
            cb_opt = QtWidgets.QStyleOptionButton()
            cb_opt.rect = check_rect
            cb_opt.state = QtWidgets.QStyle.StateFlag.State_Enabled
            cb_opt.state |= (
                QtWidgets.QStyle.StateFlag.State_On
                if check_state == QtCore.Qt.CheckState.Checked
                else QtWidgets.QStyle.StateFlag.State_Off
            )
            style.drawControl(QtWidgets.QStyle.ControlElement.CE_CheckBox, cb_opt, painter, opt.widget)
            text_rect.setLeft(check_rect.right() + 6)
        try:
            painter.save()
            color = (
                opt.palette.color(QtGui.QPalette.ColorRole.HighlightedText)
                if opt.state & QtWidgets.QStyle.StateFlag.State_Selected
                else opt.palette.color(QtGui.QPalette.ColorRole.Text)
            )
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(opt.font)
            to = QtGui.QTextOption()
            to.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignJustify)
            doc.setDefaultTextOption(to)
            doc.setPlainText(opt.text)
            bf = QtGui.QTextBlockFormat()
            bf.setLineHeight(_LINE_HEIGHT_RATIO, 1)  # 1 = ProportionalHeight
            cur = QtGui.QTextCursor(doc)
            cur.select(QtGui.QTextCursor.SelectionType.Document)
            cur.mergeBlockFormat(bf)
            doc.setTextWidth(max(1, text_rect.width()))
            cur = QtGui.QTextCursor(doc)
            cur.select(QtGui.QTextCursor.SelectionType.Document)
            cf = QtGui.QTextCharFormat()
            cf.setForeground(QtGui.QBrush(color))
            cur.mergeCharFormat(cf)
            painter.translate(text_rect.left(), text_rect.top())
            doc.drawContents(painter)
            painter.translate(-text_rect.left(), -text_rect.top())
        except Exception:
            painter.save()
            role = QtGui.QPalette.ColorRole.HighlightedText if (opt.state & QtWidgets.QStyle.StateFlag.State_Selected) else QtGui.QPalette.ColorRole.Text
            painter.setPen(opt.palette.color(role))
            painter.drawText(QtCore.QRectF(text_rect), opt.text, QtGui.QTextOption())
            painter.restore()
        painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index) -> QtCore.QSize:
        try:
            opt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            width = int(opt.rect.width() or 0)
            if width <= 0 and isinstance(opt.widget, QtWidgets.QAbstractItemView):
                try:
                    width = int(opt.widget.viewport().width())
                except Exception:
                    width = 0
            check_state = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
            if check_state is not None:
                width -= 24
            width = max(120, width or 220)
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(opt.font)
            to = QtGui.QTextOption()
            to.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignJustify)
            doc.setDefaultTextOption(to)
            doc.setPlainText(opt.text)
            bf = QtGui.QTextBlockFormat()
            bf.setLineHeight(_LINE_HEIGHT_RATIO, 1)  # 1 = ProportionalHeight
            cur = QtGui.QTextCursor(doc)
            cur.select(QtGui.QTextCursor.SelectionType.Document)
            cur.mergeBlockFormat(bf)
            doc.setTextWidth(width)
            height = int(doc.size().height()) + 6
            return QtCore.QSize(width, max(height, 22))
        except Exception:
            return QtCore.QSize(220, 30)


class AutoComboBox(QtWidgets.QComboBox):
    """
    Надёжный автоподбор размера выпадающего списка для Windows.

    Qt на некоторых темах/стилях открывает попап слишком маленьким (появляется прокрутка даже
    при 2-3 пунктах). В showPopup() принудительно подгоняем:
    - количество видимых строк (maxVisibleItems)
    - минимальную высоту/ширину view()
    """

    def __init__(self, *args, max_popup_items: int = 30, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_popup_items = int(max_popup_items)
        self._le_filter_installed = False
        try:
            view = self.view()
            if view is not None:
                view.setWordWrap(True)
                view.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
                view.setUniformItemSizes(False)
                view.setAlternatingRowColors(False)
                view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                # Явно наследуем шрифт (Arial 12 задаётся на QApplication, но на некоторых темах
                # попап может взять системный).
                view.setFont(self.font())
                _pad = self.property("popup_item_padding")
                _item_pad = (_pad if isinstance(_pad, str) and _pad.strip() else _POPUP_ITEM_PADDING)
                view.setStyleSheet(
                    "QListView { background: #ffffff; }"
                    f"QListView::item {{ {_item_pad} background: #ffffff; color: #000000; border-bottom: 1px solid #e0e0e0; font-size: 12pt; }}"
                    "QListView::item:hover { background: #e6f0ff; }"
                    "QListView::item:selected { background: #1e88e5; color: #ffffff; }"
                )
                view.setItemDelegate(WrapAnywhereDelegate(view))
        except Exception:
            pass
        self._ensure_lineedit_filter()

    def setEditable(self, editable: bool) -> None:  # noqa: N802 (Qt naming)
        # При переключении editable Qt может создать новый lineEdit().
        # Нам нужно сразу поставить фильтр, чтобы попап открывался кликом по полю с первого раза.
        super().setEditable(bool(editable))
        # lineEdit() появился/обновился -> ставим фильтр
        self._le_filter_installed = False
        self._ensure_lineedit_filter()

    def _ensure_lineedit_filter(self) -> None:
        if self._le_filter_installed:
            return
        le = self.lineEdit()
        if le is None:
            return
        # В режиме multiline_display текст рисуем в paintEvent; lineEdit не умеет переносить строк,
        # поэтому скрываем его, иначе перекрывает обёрнутый текст.
        if self._multiline_enabled():
            le.hide()
        # Словари и шаблоны: не трогаем lineEdit (нет фильтра, нет "руки") — тогда курсор
        # ставится в место клика и текст можно редактировать с любой позиции, а не только с конца.
        elif not self.property("open_only_on_arrow"):
            le.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            le.installEventFilter(self)
        self._le_filter_installed = True

    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        # Для словарей и шаблонов (open_only_on_arrow) попап только по стрелке; для остальных — по клику и клавишам.
        if self.property("open_only_on_arrow"):
            return super().eventFilter(obj, event)
        le = self.lineEdit()
        if le is not None and obj is le:
            et = event.type()
            if et == QtCore.QEvent.Type.MouseButtonPress:
                try:
                    self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                except Exception:
                    pass
                self.showPopup()
                return True
            if et == QtCore.QEvent.Type.KeyPress and isinstance(event, QtGui.QKeyEvent):
                key = event.key()
                if key in (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Up) or (
                    key == QtCore.Qt.Key.Key_Space
                ):
                    self.showPopup()
                    return True
        return super().eventFilter(obj, event)

    def _force_popup_below(self) -> None:
        view = self.view()
        if view is None:
            return
        popup = view.window()
        if not isinstance(popup, QtWidgets.QWidget):
            return
        try:
            below_y = self.mapToGlobal(QtCore.QPoint(0, self.height())).y()
            pg = popup.geometry()
            screen = QtGui.QGuiApplication.screenAt(self.mapToGlobal(QtCore.QPoint(0, 0)))
            if screen is None:
                screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()
            max_h = max(80, int(avail.bottom() - below_y - 6))
            pg.setTop(below_y)
            pg.setHeight(min(int(pg.height()), max_h))
            popup.setGeometry(pg)
        except Exception:
            return

    def _multiline_enabled(self) -> bool:
        return bool(self.property("multiline_display"))

    def _max_display_height(self) -> int | None:
        try:
            v = self.property("max_display_height")
            if v is None:
                return None
            iv = int(v)
            return iv if iv > 0 else None
        except Exception:
            return None

    def sizeHint(self) -> QtCore.QSize:
        sh = super().sizeHint()
        if not self._multiline_enabled():
            return sh
        text = self.currentText() or ""
        if not text.strip():
            return sh
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        edit_rect = self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox,
            opt,
            QtWidgets.QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        width = max(80, int(edit_rect.width()) - 4)
        doc = QtGui.QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setPlainText(text)
        doc.setTextWidth(width)
        height = int(doc.size().height()) + 8
        h = max(sh.height(), height)
        cap = self._max_display_height()
        if cap is not None:
            h = min(h, int(cap))
        return QtCore.QSize(sh.width(), int(h))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if not self._multiline_enabled():
            super().paintEvent(event)
            return
        painter = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        painter.drawComplexControl(QtWidgets.QStyle.ComplexControl.CC_ComboBox, opt)
        edit_rect = self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox,
            opt,
            QtWidgets.QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        # Левый отступ для текста (иначе "прилипает" к краю в multiline режиме)
        edit_rect = edit_rect.adjusted(_DISPLAY_TEXT_PAD_X, 0, -2, 0)
        text = self.currentText() or ""
        if not text.strip():
            # По просьбе: для некоторых полей placeholder может быть пустым (тогда просто не рисуем текст)
            text = str(self.property("placeholder_text") or "")
            painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.PlaceholderText))
        else:
            painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.Text))
        text_opt = QtGui.QTextOption()
        text_opt.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
        text_opt.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        painter.drawText(QtCore.QRectF(edit_rect), text, text_opt)

    def adjust_multiline_height(self) -> None:
        if not self._multiline_enabled():
            return
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        edit_rect = self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox,
            opt,
            QtWidgets.QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        text = self.currentText() or ""
        base_h = super().sizeHint().height()
        if not text.strip():
            self.setFixedHeight(base_h)
            le = self.lineEdit()
            if le is not None:
                le.setFixedHeight(max(20, base_h - 2))
            return
        width = max(80, int(edit_rect.width()) - 4)
        doc = QtGui.QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setPlainText(text)
        doc.setTextWidth(width)
        height = int(doc.size().height()) + 8
        h = max(base_h, height)
        cap = self._max_display_height()
        if cap is not None:
            h = min(h, int(cap))
        self.setFixedHeight(h)
        le = self.lineEdit()
        if le is not None:
            le.setFixedHeight(max(20, h - 2))
        self.updateGeometry()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._multiline_enabled():
            self.adjust_multiline_height()

    def showPopup(self) -> None:  # noqa: N802 (Qt naming)
        self._ensure_lineedit_filter()
        try:
            count = int(self.count() or 0)
            if count > 0:
                visible = min(count, max(1, self._max_popup_items))
                self.setMaxVisibleItems(visible)

                view = self.view()
                if view is not None:
                    view.setFont(self.font())
                    view.setWordWrap(True)
                    view.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
                    view.setUniformItemSizes(False)
                    try:
                        view.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
                    except Exception:
                        pass
                    view.setAutoFillBackground(True)
                    view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    _pad = self.property("popup_item_padding")
                    item_padding = (_pad if isinstance(_pad, str) and _pad.strip() else _POPUP_ITEM_PADDING)
                    view.setStyleSheet(
                        "QListView { background: #ffffff; }"
                        f"QListView::item {{ {item_padding} background: #ffffff; color: #000000; border-bottom: 1px solid #e0e0e0; font-size: 12pt; }}"
                        "QListView::item:hover { background: #e6f0ff; }"
                        "QListView::item:selected { background: #1e88e5; color: #ffffff; }"
                    )
                    view.setItemDelegate(WrapAnywhereDelegate(view))
                    # Height: enough rows to avoid scrolling for small lists
                    try:
                        row_h = int(view.sizeHintForRow(0))
                    except Exception:
                        row_h = 0
                    if row_h <= 0:
                        row_h = max(22, self.fontMetrics().height() + 10)

                    desired_h = visible * row_h + (view.frameWidth() * 2) + 2
                    view.setMinimumHeight(int(desired_h))

                    # Во всех комбобоксах: ширина списка = ширина поля, элементы в размер с полем
                    combo_w = int(self.width())
                    view_w = max(combo_w - 12, 180)
                    view.setFixedWidth(view_w)

                    # Hide scrollbar when everything fits
                    if count <= visible:
                        view.setVerticalScrollBarPolicy(
                            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        )
                    else:
                        view.setVerticalScrollBarPolicy(
                            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
                        )
        except Exception:
            pass

        super().showPopup()
        QtCore.QTimer.singleShot(0, self._force_popup_below)

