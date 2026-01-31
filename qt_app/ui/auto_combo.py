from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


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
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            doc.setDefaultTextOption(to)
            doc.setPlainText(opt.text)
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
            role = (
                QtGui.QPalette.ColorRole.HighlightedText
                if (opt.state & QtWidgets.QStyle.StateFlag.State_Selected)
                else QtGui.QPalette.ColorRole.Text
            )
            painter.setPen(opt.palette.color(role))
            text_opt = QtGui.QTextOption()
            text_opt.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            text_opt.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            painter.drawText(QtCore.QRectF(text_rect), opt.text, text_opt)
            painter.restore()
        painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index) -> QtCore.QSize:
        try:
            opt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            width = int(opt.rect.width() or 0)
            if isinstance(opt.widget, QtWidgets.QTableView) and width <= 0:
                try:
                    width = int(opt.widget.columnWidth(index.column()))
                except Exception:
                    pass
            if isinstance(opt.widget, QtWidgets.QAbstractItemView) and width <= 0:
                try:
                    vw = int(opt.widget.viewport().width())
                    if vw > 0:
                        width = vw
                except Exception:
                    pass
            check_state = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
            if check_state is not None:
                width -= 24
            width = max(120, (width or 220))
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(opt.font)
            to = QtGui.QTextOption()
            to.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
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
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            doc.setDefaultTextOption(to)
            doc.setPlainText(opt.text)
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
            if isinstance(opt.widget, QtWidgets.QAbstractItemView):
                try:
                    vw = int(opt.widget.viewport().width())
                    if vw > 0:
                        width = vw
                except Exception:
                    pass
            check_state = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
            if check_state is not None:
                width -= 24
            width = max(120, (width or 220))
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(opt.font)
            to = QtGui.QTextOption()
            to.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
            to.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            doc.setDefaultTextOption(to)
            doc.setPlainText(opt.text)
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
        self._combo_kind = "normal"
        self._le_filter_installed = False
        self._combo_click_filter_installed = False
        self._allow_popup_next = False  # True только после клика по кнопке-стрелке
        # По умолчанию открытие только по стрелке (по требованию)
        self.setProperty("open_only_on_arrow", True)
        self.setProperty("combo_kind", self._combo_kind)
        try:
            view = self.view()
            if view is not None:
                view.setAlternatingRowColors(False)
                view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                # Явно наследуем шрифт (Arial 12 задаётся на QApplication, но на некоторых темах
                # попап может взять системный).
                view.setFont(self.font())
        except Exception:
            pass
        self._apply_view_config()
        self._ensure_lineedit_filter()
        self._ensure_combo_click_filter()

    def setEditable(self, editable: bool) -> None:  # noqa: N802 (Qt naming)
        # При переключении editable Qt может создать новый lineEdit().
        # Нам нужно сразу поставить фильтр, чтобы попап открывался кликом по полю с первого раза.
        super().setEditable(bool(editable))
        # lineEdit() появился/обновился -> ставим фильтр
        self._le_filter_installed = False
        self._combo_click_filter_installed = False
        self._ensure_lineedit_filter()
        self._ensure_combo_click_filter()

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
        else:
            if self.property("open_only_on_arrow") or self.isEditable():
                # Для editable-комбо перехватываем клик по полю, чтобы открывать список
                le.installEventFilter(self)
                if self.property("open_only_on_arrow"):
                    le.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._le_filter_installed = True

    def _ensure_combo_click_filter(self) -> None:
        """При open_only_on_arrow ставим фильтр на комбобокс, чтобы разрешать попап только после клика по стрелке."""
        if self._combo_click_filter_installed:
            return
        if not self.property("open_only_on_arrow"):
            return
        self.installEventFilter(self)
        self._combo_click_filter_installed = True

    def set_combo_kind(self, kind: str) -> None:
        kind = (kind or "normal").strip().lower()
        if kind not in ("normal", "dict", "template"):
            kind = "normal"
        self._combo_kind = kind
        self.setProperty("combo_kind", kind)
        self._apply_view_config()

    def _apply_view_config(self) -> None:
        view = self.view()
        if view is None:
            return
        if self._combo_kind not in ("dict", "template"):
            return
        try:
            view.setFont(self.font())
            view.setWordWrap(True)
            view.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
            view.setUniformItemSizes(False)
            view.setSpacing(2)
            view.setViewportMargins(6, 0, 6, 0)
            view.setItemDelegate(DictTemplateLineHeightDelegate(view))
        except Exception:
            pass

    def _is_click_on_arrow(self, pos: QtCore.QPoint | QtCore.QPointF) -> bool:
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        arrow_rect = self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox,
            opt,
            QtWidgets.QStyle.SubControl.SC_ComboBoxArrow,
            self,
        )
        if hasattr(pos, "toPoint"):
            pos = pos.toPoint()
        return arrow_rect.contains(QtCore.QPoint(int(pos.x()), int(pos.y())))

    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        # Клик по комбобоксу: разрешаем попап только если клик по кнопке-стрелке
        if obj is self and event.type() == QtCore.QEvent.Type.MouseButtonPress and isinstance(event, QtGui.QMouseEvent):
            if self.property("open_only_on_arrow"):
                pos = getattr(event, "position", lambda: event.pos())()
                if self._is_click_on_arrow(pos):
                    self._allow_popup_next = True
                    return False  # передать событие — комбо вызовет showPopup()
                self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                return True  # клик по полю — не открывать
        le = self.lineEdit()
        if le is None or obj is not le:
            return super().eventFilter(obj, event)
        et = event.type()
        if et == QtCore.QEvent.Type.MouseButtonPress:
            if self.property("open_only_on_arrow"):
                # Перехватываем клик по полю — попап только по кнопке справа
                try:
                    self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                except Exception:
                    pass
                return True
            try:
                self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            except Exception:
                pass
            self.showPopup()
            return True
        if et == QtCore.QEvent.Type.KeyPress and isinstance(event, QtGui.QKeyEvent):
            key = event.key()
            if key in (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Up) or key == QtCore.Qt.Key.Key_Space:
                if self.property("open_only_on_arrow"):
                    return True
                self.showPopup()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if self.property("open_only_on_arrow"):
            key = event.key()
            if key in (
                QtCore.Qt.Key.Key_Down,
                QtCore.Qt.Key.Key_Up,
                QtCore.Qt.Key.Key_Space,
                QtCore.Qt.Key.Key_Return,
                QtCore.Qt.Key.Key_Enter,
            ):
                return
        super().keyPressEvent(event)

    def _force_popup_below(self) -> None:
        view = self.view()
        if view is None:
            return
        popup = view.window()
        if not isinstance(popup, QtWidgets.QWidget):
            return
        try:
            below_y = self.mapToGlobal(QtCore.QPoint(0, self.height())).y()
            above_y = self.mapToGlobal(QtCore.QPoint(0, 0)).y()
            pg = popup.geometry()
            screen = QtGui.QGuiApplication.screenAt(self.mapToGlobal(QtCore.QPoint(0, 0)))
            if screen is None:
                screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()
            space_below = int(avail.bottom() - below_y - 6)
            space_above = int(above_y - avail.top() - 6)
            desired_h = int(pg.height())
            if space_below >= desired_h or space_below >= space_above:
                max_h = max(80, space_below)
                pg.setTop(below_y)
                pg.setHeight(min(desired_h, max_h))
            else:
                max_h = max(80, space_above)
                pg.setHeight(min(desired_h, max_h))
                pg.setTop(max(int(avail.top()), int(above_y - pg.height())))
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
        if self._combo_kind not in ("dict", "template"):
            super().showPopup()
            # Ensure normal combos open below the field (not inside)
            try:
                view = self.view()
                if view is not None:
                    try:
                        view.setFont(QtGui.QFont("Arial", 12))
                        view.setUniformItemSizes(False)
                        count = int(self.count() or 0)
                        if count > 0:
                            if self.property("popup_auto_height"):
                                self.setMaxVisibleItems(count)
                                view.setVerticalScrollBarPolicy(
                                    QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                                )
                                try:
                                    sb = view.verticalScrollBar()
                                    if sb is not None:
                                        sb.hide()
                                        sb.setDisabled(True)
                                        sb.setFixedWidth(0)
                                except Exception:
                                    pass
                                try:
                                    row_h = int(view.sizeHintForRow(0))
                                except Exception:
                                    row_h = max(22, self.fontMetrics().height() + 6)
                                total_h = row_h * count + (view.frameWidth() * 2) + 2
                                view.setMinimumHeight(total_h)
                                view.setMaximumHeight(total_h)
                            else:
                                visible = min(count, int(self._max_popup_items))
                                self.setMaxVisibleItems(visible)
                                view.setVerticalScrollBarPolicy(
                                    QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
                                )
                        if self.property("no_popup_margins"):
                            view.setViewportMargins(0, 0, 0, 0)
                        else:
                            view.setViewportMargins(6, 0, 6, 0)
                        view.setStyleSheet(
                            "QListView { background: #ffffff; border-top: 1px solid #bbbbbb; "
                            "border-bottom: 1px solid #bbbbbb; border-left: 0px; border-right: 0px; "
                            "border-radius: 0px; }"
                            "QListView::item { background: #ffffff; padding: 0px 0px; border-bottom: 1px solid #e0e0e0; }"
                            "QListView::item:selected { background: #007bff; color: #ffffff; border-radius: 0px; }"
                        )
                        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    except Exception:
                        pass
                    popup = view.window()
                    if isinstance(popup, QtWidgets.QWidget):
                        below_y = self.mapToGlobal(QtCore.QPoint(0, self.height())).y()
                        combo_w = int(self.width())
                        try:
                            view.setFixedWidth(combo_w)
                            popup.setFixedWidth(combo_w)
                        except Exception:
                            pass
                        popup.move(popup.x(), below_y)
            except Exception:
                pass
            return
        # Открывать только по нажатию на кнопку выпадающего списка, не по клику по полю
        if self.property("open_only_on_arrow"):
            if not self._allow_popup_next:
                # На случай другого порядка событий: разрешить только если курсор над стрелкой
                try:
                    pos_local = self.mapFromGlobal(QtGui.QCursor.pos())
                    if not self._is_click_on_arrow(pos_local):
                        return
                except Exception:
                    return
            self._allow_popup_next = False
        self._ensure_lineedit_filter()
        try:
            count = int(self.count() or 0)
            if count > 0:
                visible = min(count, max(1, self._max_popup_items))
                self.setMaxVisibleItems(visible)

                view = self.view()
                if view is not None:
                    self._apply_view_config()
                    try:
                        view.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
                    except Exception:
                        pass
                    view.setAutoFillBackground(True)
                    view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    if self._combo_kind in ("dict", "template"):
                        # Height: sum of row heights (variable row size)
                        try:
                            view.doItemsLayout()
                        except Exception:
                            pass
                        fallback_h = max(22, self.fontMetrics().height() + 10)
                        total_h = 0
                        for i in range(visible):
                            try:
                                h = int(view.sizeHintForRow(i))
                            except Exception:
                                h = 0
                            if h <= 0:
                                h = fallback_h
                            total_h += h
                        desired_h = total_h + (view.frameWidth() * 2) + 2
                        view.setMinimumHeight(int(desired_h))

                    # Во всех комбобоксах: ширина списка = ширина поля, элементы в размер с полем
                    combo_w = int(self.width())
                    view_w = max(combo_w - 12, 180)
                    view.setFixedWidth(view_w)
                    try:
                        view.doItemsLayout()
                    except Exception:
                        pass
                    view.updateGeometry()

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
        def _recalc_popup_geometry() -> None:
            v = self.view()
            if v is None:
                return
            try:
                if self._combo_kind in ("dict", "template"):
                    model = self.model()
                    delegate = v.itemDelegate()
                    if model is not None and delegate is not None:
                        opt = QtWidgets.QStyleOptionViewItem()
                        opt.initFrom(v)
                        opt.rect = QtCore.QRect(0, 0, v.viewport().width(), 0)
                        for row in range(model.rowCount()):
                            index = model.index(row, 0)
                            try:
                                sz = delegate.sizeHint(opt, index)
                                model.setData(index, sz, QtCore.Qt.ItemDataRole.SizeHintRole)
                            except Exception:
                                continue
                v.reset()
                v.doItemsLayout()
            except Exception:
                pass
            self._force_popup_below()

        QtCore.QTimer.singleShot(0, _recalc_popup_geometry)
        QtCore.QTimer.singleShot(50, _recalc_popup_geometry)

