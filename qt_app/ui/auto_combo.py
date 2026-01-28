from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


_POPUP_ITEM_PADDING = "padding: 6px 12px;"
_DISPLAY_TEXT_PAD_X = 8


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
        text_opt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAnywhere)
        text_opt.setAlignment(opt.displayAlignment)
        painter.drawText(QtCore.QRectF(text_rect), opt.text, text_opt)
        painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index) -> QtCore.QSize:
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
        doc.setPlainText(opt.text)
        doc.setTextWidth(width)
        height = int(doc.size().height()) + 6
        return QtCore.QSize(width, max(height, 22))


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
        self._last_popup_width: int | None = None
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
                view.setStyleSheet(
                    "QListView { background: #ffffff; }"
                    f"QListView::item {{ {_POPUP_ITEM_PADDING} background: #ffffff; color: #000000; border-bottom: 1px solid #e0e0e0; }}"
                    "QListView::item:hover { background: #e6f0ff; }"
                    "QListView::item:selected { background: #1e88e5; color: #ffffff; }"
                )
                view.setItemDelegate(WrapAnywhereDelegate(view))
        except Exception:
            pass

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
                    view.setStyleSheet(
                        "QListView { background: #ffffff; }"
                        f"QListView::item {{ {_POPUP_ITEM_PADDING} background: #ffffff; color: #000000; border-bottom: 1px solid #e0e0e0; }}"
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

                    # Width: keep close to combo width to allow wrapping
                    desired_w = max(int(self.width()), 180)
                    # Не используем fixedWidth (и не трогаем окно попапа после открытия) —
                    # на некоторых Windows-сборках это вызывает "мерцание" и неправильную позицию попапа
                    # при первом открытии/клике.
                    view.setMinimumWidth(int(desired_w))

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

