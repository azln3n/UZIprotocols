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
          border: 2px solid #9aa0a6; /* серая рамка по умолчанию */
          border-radius: 6px;
        }
        QPushButton:hover, QToolButton:hover {
          border-color: #007bff; /* синяя рамка именно при наведении */
        }
        QPushButton:disabled {
          background: #d0d0d0;
          color: #666666;
        }

        /* Inputs */
        QLineEdit, QComboBox, QDateEdit, QTimeEdit, QTextEdit, QPlainTextEdit {
          background: white;
          border: 1px solid #bbbbbb;
          border-radius: 4px;
          padding: 6px 8px;
        }
        QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTimeEdit:hover,
        QTextEdit:hover, QPlainTextEdit:hover {
          border: 2px solid #007bff;
          padding: 5px 7px;
        }
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
        QTextEdit:focus, QPlainTextEdit:focus {
          border: 2px solid #007bff;
          padding: 5px 7px;
        }

        /* SpinBox: keep native up/down buttons readable (no "точки") */
        QSpinBox, QDoubleSpinBox {
          background: white;
          border: 1px solid #bbbbbb;
          border-radius: 4px;
          padding: 6px 8px;
          padding-right: 26px; /* place for arrows */
        }
        QSpinBox:hover, QDoubleSpinBox:hover,
        QSpinBox:focus, QDoubleSpinBox:focus {
          border: 2px solid #007bff;
          padding: 5px 7px;
          padding-right: 25px;
        }
        QSpinBox::up-button, QDoubleSpinBox::up-button {
          subcontrol-origin: border;
          subcontrol-position: top right;
          width: 20px;
          border-left: 1px solid #bbbbbb;
          border-top-right-radius: 4px;
        }
        QSpinBox::down-button, QDoubleSpinBox::down-button {
          subcontrol-origin: border;
          subcontrol-position: bottom right;
          width: 20px;
          border-left: 1px solid #bbbbbb;
          border-bottom-right-radius: 4px;
        }
        /* Draw arrows ourselves (black), so they are always visible */
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
          image: none;
          width: 0px;
          height: 0px;
          border-left: 5px solid transparent;
          border-right: 5px solid transparent;
          border-bottom: 7px solid #000000;
          margin: 3px;
        }
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
          image: none;
          width: 0px;
          height: 0px;
          border-left: 5px solid transparent;
          border-right: 5px solid transparent;
          border-top: 7px solid #000000;
          margin: 3px;
        }

        /* ComboBox popup list must stay readable on any OS theme */
        QComboBox QAbstractItemView {
          background: #ffffff;
          color: #000000;
          selection-background-color: #007bff;
          selection-color: #ffffff;
          outline: 0;
        }
        QComboBox QAbstractItemView::item:hover {
          background: #eef5ff; /* подсветка при наведении */
          color: #000000;
        }
        QComboBox QAbstractItemView::item:selected {
          background: #007bff;
          color: #ffffff;
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
          padding: 6px 14px;
          margin-right: 4px;
          border-top-left-radius: 6px;
          border-top-right-radius: 6px;
        }
        QTabBar::tab:selected { background: #FF95A8; }
        """
    )

    # Автоподбор минимальной ширины кнопок под их текст (чтобы "Добавить/Изменить/Удалить" не обрезались).
    # Делается глобально, чтобы не править каждое окно вручную.
    if not hasattr(app, "_btn_autosize_filter"):
        flt = _ButtonAutoSizeFilter()
        app._btn_autosize_filter = flt  # keep alive
        app.installEventFilter(flt)


class _ButtonAutoSizeFilter(QtCore.QObject):
    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        et = event.type()
        if et in (QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Polish):
            if isinstance(obj, QtWidgets.QWidget):
                # Do minimal work; only adjust buttons in this widget subtree.
                for btn in obj.findChildren(QtWidgets.QAbstractButton):
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
