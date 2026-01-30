from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6 import QtCore, QtGui, QtWidgets

from ..repo import list_study_types, search_protocol_patient_ids, search_patient_ids_by_fields
from .auto_combo import AutoComboBox


@dataclass(frozen=True)
class SearchResult:
    patient_ids: list[int]


class SearchDialog(QtWidgets.QDialog):
    def __init__(self, *, institution_id: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.institution_id = institution_id
        self.setWindowTitle("Поиск")
        self.resize(520, 280)
        self.setMinimumHeight(260)
        self.setModal(True)

        self.result: SearchResult | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        box = QtWidgets.QGroupBox("Параметры поиска")
        box.setMinimumHeight(200)
        grid = QtWidgets.QGridLayout(box)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        _row_h = 32
        grid.addWidget(QtWidgets.QLabel("ФИО пациента:"), 0, 0)
        self.fio = QtWidgets.QLineEdit()
        self.fio.setMinimumHeight(_row_h)
        grid.addWidget(self.fio, 0, 1)

        grid.addWidget(QtWidgets.QLabel("ИИН:"), 0, 2)
        self.iin = QtWidgets.QLineEdit()
        self.iin.setMinimumHeight(_row_h)
        self.iin.setMaxLength(12)
        rx = QtCore.QRegularExpression(r"^\d{0,12}$")
        self.iin.setValidator(QtGui.QRegularExpressionValidator(rx, self.iin))
        self.iin.setInputMethodHints(QtCore.Qt.InputMethodHint.ImhDigitsOnly)
        grid.addWidget(self.iin, 0, 3)

        # "Период" показываем один раз (без дубляжа)
        self.use_period = QtWidgets.QCheckBox("Период с:")
        self.use_period.setChecked(False)
        grid.addWidget(self.use_period, 1, 0, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        def _dt_line_edit_padding(dt_widget):
            le = dt_widget.lineEdit()
            if le is not None:
                le.setStyleSheet("padding: 4px 6px;")
        self.date_from = QtWidgets.QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setDate(QtCore.QDate.currentDate())
        self.date_from.setMinimumWidth(140)
        self.date_from.setMinimumHeight(_row_h)
        _dt_line_edit_padding(self.date_from)
        grid.addWidget(self.date_from, 1, 1)

        grid.addWidget(QtWidgets.QLabel("по:"), 1, 2)
        self.date_to = QtWidgets.QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setDate(QtCore.QDate.currentDate())
        self.date_to.setMinimumWidth(140)
        self.date_to.setMinimumHeight(_row_h)
        _dt_line_edit_padding(self.date_to)
        grid.addWidget(self.date_to, 1, 3)

        grid.addWidget(QtWidgets.QLabel("Тип исследования:"), 2, 0)
        self.study = AutoComboBox(max_popup_items=30)
        self.study.setMinimumWidth(260)
        self.study.setMinimumHeight(_row_h)
        self.study.addItem("Все", None)
        for it in list_study_types():
            self.study.addItem(it.name, it.id)
        grid.addWidget(self.study, 2, 1, 1, 2)

        # give date columns some room
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.find_btn = QtWidgets.QPushButton("Найти")
        self.find_btn.setStyleSheet(
            "QPushButton { background: #4CAF50; color: white; font-weight: bold; padding: 6px 14px; }"
        )
        self.find_btn.clicked.connect(self._search)
        grid.addWidget(self.find_btn, 2, 3)

        self.clear_btn = QtWidgets.QPushButton("Очистить")
        self.clear_btn.setStyleSheet(
            "QPushButton { background: #FF9800; color: white; font-weight: bold; padding: 6px 14px; }"
        )
        self.clear_btn.clicked.connect(self._clear_form)
        grid.addWidget(self.clear_btn, 2, 4)

        root.addWidget(box)

        self.info = QtWidgets.QLabel("")
        self.info.setStyleSheet("color: #666;")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel = QtWidgets.QPushButton("Закрыть")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        root.addLayout(btns)

        def _refresh_period_enabled() -> None:
            enabled = bool(self.use_period.isChecked())
            self.date_from.setEnabled(enabled)
            self.date_to.setEnabled(enabled)

        self.use_period.toggled.connect(_refresh_period_enabled)
        _refresh_period_enabled()

    @QtCore.Slot()
    def _clear(self) -> None:
        self.result = SearchResult(patient_ids=[])
        self.accept()

    @QtCore.Slot()
    def _search(self) -> None:
        fio = self.fio.text().strip()
        iin = self.iin.text().strip()
        st_id = self.study.currentData()

        if not fio and not iin and not st_id and not self.use_period.isChecked():
            self.info.setText("Введите ФИО (можно только фамилию) или ИИН.")
            return

        df: date | None = None
        dt: date | None = None
        if self.use_period.isChecked():
            df = self.date_from.date().toPython()
            dt = self.date_to.date().toPython()
            if isinstance(df, date) and isinstance(dt, date) and df > dt:
                self.info.setText("Период: дата 'с' не может быть больше даты 'по'.")
                return

        # По требованию: искать и по пациентам без протоколов.
        # - Если задан период или тип исследования — это фильтр по протоколам.
        # - Иначе ищем по таблице пациентов.
        if df or dt or st_id:
            ids = search_protocol_patient_ids(
                institution_id=self.institution_id,
                fio=fio,
                iin=iin,
                date_from=df.isoformat() if df else None,
                date_to=dt.isoformat() if dt else None,
                study_type_id=int(st_id) if st_id else None,
            )
        else:
            ids = search_patient_ids_by_fields(institution_id=self.institution_id, fio=fio, iin=iin)
        self.result = SearchResult(patient_ids=ids)
        self.accept()

    @QtCore.Slot()
    def _clear_form(self) -> None:
        self.fio.clear()
        self.iin.clear()
        self.study.setCurrentIndex(0)
        self.use_period.setChecked(False)
        self.info.setText("")
