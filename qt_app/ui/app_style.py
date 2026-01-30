from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


def apply_app_style(app: QtWidgets.QApplication) -> None:
    """
    Стиль по ТЗ/HTML-примерам:
    - Arial 12
    - фон окон aliceblue
    - синяя рамка при фокусе на любых полях
    """
    app.setFont(QtGui.QFont("Arial", 12))

    # Причина "точек" в QTimeEdit/QDateEdit/QSpinBox — системный стиль Windows.
    # Самый стабильный способ получить нормальные стрелки на всех темах/масштабах — стиль Qt "Fusion".
    # Он хорошо сочетается с нашим palette + stylesheet.
    try:
        fusion = QtWidgets.QStyleFactory.create("Fusion")
        if fusion is not None:
            app.setStyle(fusion)
    except Exception:
        pass

    pal = app.palette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#f0f8ff"))  # aliceblue
    pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#ffffff"))  # input bg
    pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#f1f1f1"))
    pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#e9ecef"))
    pal.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#000000"))
    pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#000000"))
    pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#000000"))
    pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#007bff"))
    pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(pal)

    # Focus blue border: keep layout stable by compensating padding.
    app.setStyleSheet(
        """
        /* Buttons: ensure disabled looks disabled even if per-button stylesheet exists */
        QPushButton, QToolButton {
          padding: 6px 12px;
          border: 2px solid transparent; /* без серой рамки по умолчанию */
          border-radius: 6px;
          background: #e9ecef; /* единый серый фон */
          color: black;
        }
        QPushButton:hover, QToolButton:hover {
          border-color: #007bff; /* синяя рамка именно при наведении */
        }
        QPushButton:disabled {
          background: #d0d0d0;
          color: #666666;
        }

        /* Inputs */
        QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {
          background: white;
          color: #000000;
          border: 1px solid #bbbbbb;
          border-radius: 4px;
          padding: 6px 8px;
        }
        QLineEdit:hover, QComboBox:hover, QTextEdit:hover, QPlainTextEdit:hover {
          border: 2px solid #007bff;
          padding: 5px 7px;
        }
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
          border: 2px solid #007bff;
          padding: 5px 7px;
        }

        /* QComboBox can paint "current item" using HighlightedText on some themes.
           If background is forced to white by QSS, text can become white-on-white.
           Force readable text + selection colors for both non-editable and editable combos. */
        QComboBox {
          color: #000000;
          selection-background-color: #007bff;
          selection-color: #ffffff;
        }
        QComboBox:on {
          /* popup opened */
          color: #000000;
        }
        QComboBox QLineEdit {
          background: #ffffff;
          color: #000000;
          selection-background-color: #007bff;
          selection-color: #ffffff;
        }

        /* NOTE: We do NOT style QDateEdit/QTimeEdit themselves via QSS (arrows would disappear).
           Only the inner QLineEdit gets padding so the text has 6px horizontal indent. */
        QDateEdit QLineEdit, QTimeEdit QLineEdit {
          padding: 4px 6px;
        }

        /* ComboBox popup list must stay readable on any OS theme */
        QComboBox QAbstractItemView {
          background: #ffffff;
          color: #000000;
          selection-background-color: #007bff;
          selection-color: #ffffff;
          outline: 0;
        }
        QComboBox QAbstractItemView::item {
          padding: 6px 12px;
        }
        QComboBox QAbstractItemView::item:hover {
          background: #eef5ff; /* подсветка при наведении */
          color: #000000;
        }
        QComboBox QAbstractItemView::item:selected {
          background: #007bff;
          color: #ffffff;
        }

        /* Optional: add comfortable padding inside popup items for specific comboboxes */
        QComboBox[padded_popup="true"] QAbstractItemView::item {
          padding: 6px 12px;
        }

        /* Lists / tables also get focus border per "любой поле" wording */
        QListWidget, QTableWidget, QTreeWidget, QTableView, QTreeView {
          border: 1px solid #bbbbbb;
          border-radius: 4px;
        }
        QListWidget:focus, QTableWidget:focus, QTreeWidget:focus, QTableView:focus, QTreeView:focus {
          border: 2px solid #007bff;
        }
        QTableWidget::item:selected, QTreeWidget::item:selected {
          background: #007bff;
          color: #ffffff;
        }
        QTableWidget::item:selected:!active, QTreeWidget::item:selected:!active {
          background: #007bff;
          color: #ffffff;
        }

        /* Tabs: active pink, inactive blue */
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

        /* Calendar popup (QDateEdit): fix "black on black" on some Windows themes */
        QCalendarWidget QWidget {
          background: #ffffff;
          color: #000000;
        }
        QCalendarWidget QToolButton {
          background: #e9ecef;
          color: #000000;
          border: 1px solid #bbbbbb;
          border-radius: 4px;
          padding: 4px 8px;
        }
        QCalendarWidget QToolButton:hover {
          border-color: #007bff;
        }
        QCalendarWidget QMenu {
          background: #ffffff;
          color: #000000;
        }
        QCalendarWidget QMenu::item:selected {
          background: #007bff;
          color: #ffffff;
        }
        QCalendarWidget QAbstractItemView {
          background: #ffffff;
          color: #000000;
          selection-background-color: #007bff;
          selection-color: #ffffff;
          outline: 0;
        }

        /* Скроллбар как в окне протокола: узкий, светло-зелёный */
        QScrollBar:vertical {
          width: 12px;
          background: #CCE6D4;
          border: none;
          margin: 0;
        }
        QScrollBar::handle:vertical {
          background: #9fccb0;
          min-height: 20px;
          border-radius: 6px;
          margin: 2px;
        }
        QScrollBar::handle:vertical:hover {
          background: #7fb89a;
        }
        QScrollBar::handle:vertical:pressed {
          background: #6ba888;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
          height: 0px;
          background: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
          background: none;
        }
        """
    )

    # Автоподбор минимальной ширины кнопок под их текст (чтобы "Добавить/Изменить/Удалить" не обрезались).
    # Делается глобально, чтобы не править каждое окно вручную.
    if not hasattr(app, "_btn_autosize_filter"):
        flt = _ButtonAutoSizeFilter()
        app._btn_autosize_filter = flt  # keep alive
        app.installEventFilter(flt)

    if not hasattr(app, "_date_select_filter"):
        dflt = _DateEditSelectDayFilter()
        app._date_select_filter = dflt
        app.installEventFilter(dflt)


class _ButtonAutoSizeFilter(QtCore.QObject):
    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        et = event.type()
        if et in (QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Polish):
            if isinstance(obj, QtWidgets.QWidget):
                # Do minimal work; only adjust buttons in this widget subtree.
                for btn in obj.findChildren(QtWidgets.QAbstractButton):
                    # allow opting out for constrained layouts
                    if bool(btn.property("no_autosize")):
                        continue
                    # icon-only buttons can stay small
                    txt = (btn.text() or "").strip()
                    if not txt or txt in ("↑", "↓", "←", "→", "+", "−"):
                        continue
                    hint = btn.sizeHint().width()
                    if hint > btn.minimumWidth():
                        btn.setMinimumWidth(hint)

                # Enable hover highlighting in combobox popup lists (по просьбе: подсветка при наведении).
                for cb in obj.findChildren(QtWidgets.QComboBox):
                    try:
                        v = cb.view()
                        v.setMouseTracking(True)
                        if v.viewport() is not None:
                            v.viewport().setMouseTracking(True)
                        # По ТЗ: длинные значения в выпадающих списках должны переноситься.
                        if isinstance(v, QtWidgets.QListView):
                            v.setWordWrap(True)
                            v.setUniformItemSizes(False)
                            v.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)

                    except Exception:
                        pass

                # Ensure editors have enough width to show their text (даты/значения не обрезаются)
                for w in obj.findChildren(QtWidgets.QWidget):
                    if isinstance(w, (QtWidgets.QComboBox, QtWidgets.QDateEdit, QtWidgets.QTimeEdit)):
                        try:
                            hint = w.sizeHint().width()
                            if hint > w.minimumWidth():
                                w.setMinimumWidth(hint)
                        except Exception:
                            continue

        return super().eventFilter(obj, event)


class _DateEditSelectDayFilter(QtCore.QObject):
    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        try:
            if isinstance(obj, QtWidgets.QDateEdit) and event.type() in (
                QtCore.QEvent.Type.FocusIn,
                QtCore.QEvent.Type.MouseButtonPress,
            ):
                obj.setCurrentSection(QtWidgets.QDateTimeEdit.Section.DaySection)
                obj.setSelectedSection(QtWidgets.QDateTimeEdit.Section.DaySection)
        except Exception:
            pass
        return super().eventFilter(obj, event)


