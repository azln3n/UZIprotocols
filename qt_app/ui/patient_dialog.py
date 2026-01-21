from __future__ import annotations

import calendar
import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from PySide6 import QtCore, QtWidgets

from ..repo import ComboItem, get_patient, list_admission_channels, upsert_patient
from .admission_channels_dialog import AdmissionChannelsDialog


@dataclass(frozen=True)
class PatientDialogResult:
    patient_id: int


def _calc_age_parts(birth: date, today: date) -> tuple[int, int, int]:
    if birth > today:
        return -1, -1, -1

    years = today.year - birth.year
    months = today.month - birth.month
    days = today.day - birth.day

    if days < 0:
        months -= 1
        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1
        last_day_prev_month = calendar.monthrange(prev_year, prev_month)[1]
        days += last_day_prev_month

    if months < 0:
        years -= 1
        months += 12

    return years, months, days


def _year_word_ru(years: int) -> str:
    if years % 10 == 1 and years % 100 != 11:
        return "год"
    if years % 10 in (2, 3, 4) and years % 100 not in (12, 13, 14):
        return "года"
    return "лет"


class PatientDialog(QtWidgets.QDialog):
    saved = QtCore.Signal(PatientDialogResult)

    def __init__(
        self,
        *,
        institution_id: int,
        patient_id: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.institution_id = institution_id
        self.patient_id = patient_id
        self.setModal(True)

        self._channel_items: list[ComboItem] = []

        self._build_ui()
        self._load_channels()
        self._load_patient_if_needed()
        self._refresh_age()
        self._refresh_save_state()

    def _build_ui(self) -> None:
        self.setWindowTitle("Данные пациента")
        self.resize(640, 520)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QtWidgets.QLabel(
            "Редактирование пациента" if self.patient_id else "Добавление нового пациента"
        )
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        # Date / time (UX only)
        self.exam_date = QtWidgets.QDateEdit()
        self.exam_date.setCalendarPopup(True)
        self.exam_date.setDisplayFormat("dd.MM.yyyy")
        self.exam_time = QtWidgets.QTimeEdit()
        self.exam_time.setDisplayFormat("HH:mm")
        now = QtCore.QDateTime.currentDateTime()
        self.exam_date.setDate(now.date())
        self.exam_time.setTime(now.time())

        dt_row = QtWidgets.QHBoxLayout()
        dt_row.addWidget(self.exam_date)
        dt_row.addWidget(self.exam_time)
        dt_container = QtWidgets.QWidget()
        dt_container.setLayout(dt_row)
        form.addRow(self._bold_label("Дата и время:"), dt_container)

        # FIO
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Введите Ф.И.О. пациента")
        self.name_edit.textChanged.connect(self._refresh_save_state)
        form.addRow(self._bold_label("Ф.И.О. пациента:"), self.name_edit)

        # IIN
        self.iin_edit = QtWidgets.QLineEdit()
        self.iin_edit.setPlaceholderText("12 цифр")
        self.iin_edit.setMaxLength(12)
        self.iin_edit.setInputMask("999999999999;_")
        self.iin_edit.textChanged.connect(self._refresh_save_state)
        form.addRow(self._bold_label("ИИН:"), self.iin_edit)

        # Birth date + age
        self.birth_date = QtWidgets.QDateEdit()
        self.birth_date.setCalendarPopup(True)
        self.birth_date.setDisplayFormat("dd.MM.yyyy")
        self.birth_date.setMinimumWidth(220)
        self.birth_date.setDate(QtCore.QDate(1990, 1, 1))
        self.birth_date.dateChanged.connect(lambda _d: (self._refresh_age(), self._refresh_save_state()))

        self.age_edit = QtWidgets.QLineEdit()
        self.age_edit.setReadOnly(True)
        # чтобы текст "36 лет, 0 мес, 16 дн" и т.п. не обрезался
        self.age_edit.setMinimumWidth(260)
        self.age_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )

        bd_row = QtWidgets.QHBoxLayout()
        bd_row.addWidget(self.birth_date, 1)
        bd_row.addSpacing(12)
        bd_row.addWidget(self._bold_label("Возраст:"))
        bd_row.addWidget(self.age_edit, 2)
        bd_container = QtWidgets.QWidget()
        bd_container.setLayout(bd_row)
        form.addRow(self._bold_label("Дата рождения:"), bd_container)

        # Gender
        self.gender_combo = QtWidgets.QComboBox()
        self.gender_combo.addItem("Выберите", "")
        self.gender_combo.addItem("Мужской", "муж")
        self.gender_combo.addItem("Женский", "жен")
        self.gender_combo.currentIndexChanged.connect(self._refresh_save_state)
        form.addRow(self._bold_label("Пол:"), self.gender_combo)

        # Admission channel
        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.currentIndexChanged.connect(self._refresh_save_state)
        self.channel_settings_btn = QtWidgets.QToolButton()
        self.channel_settings_btn.setText("⚙")
        self.channel_settings_btn.setToolTip("Настройки каналов поступления")
        self.channel_settings_btn.clicked.connect(self._open_channel_settings)
        channel_row = QtWidgets.QHBoxLayout()
        channel_row.addWidget(self.channel_combo, 1)
        channel_row.addWidget(self.channel_settings_btn)
        channel_container = QtWidgets.QWidget()
        channel_container.setLayout(channel_row)
        form.addRow(self._bold_label("Канал поступления:"), channel_container)

        root.addLayout(form)

        self.error_label = QtWidgets.QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b00020;")
        root.addWidget(self.error_label)

        btn_row = QtWidgets.QHBoxLayout()
        self.clear_btn = QtWidgets.QPushButton("Очистить")
        self.clear_btn.setStyleSheet(
            "QPushButton { background: #F44336; color: white; padding: 8px 18px; border-radius: 6px; border: 2px solid #9aa0a6; }"
            "QPushButton:hover { background: #d32f2f; border-color: #007bff; }"
            "QPushButton:focus { border-color: #007bff; }"
        )
        self.clear_btn.clicked.connect(self._clear)

        self.save_btn = QtWidgets.QPushButton("Изменить" if self.patient_id else "Добавить")
        self.save_btn.setEnabled(False)
        self.save_btn.setDefault(True)
        self.save_btn.setStyleSheet(
            "QPushButton { background: #2196F3; color: white; padding: 8px 18px; border-radius: 6px; border: 2px solid #9aa0a6; }"
            "QPushButton:hover { background: #1976D2; border-color: #007bff; }"
            "QPushButton:focus { border-color: #007bff; }"
            "QPushButton:disabled { background: #9ec9f5; color: #f7fbff; }"
        )
        self.save_btn.clicked.connect(self._save)

        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

    def _bold_label(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    def _load_channels(self) -> None:
        self._channel_items = list_admission_channels()
        self.channel_combo.clear()
        self.channel_combo.addItem("Выберите", None)
        for item in self._channel_items:
            self.channel_combo.addItem(item.name, item.id)

    @QtCore.Slot()
    def _open_channel_settings(self) -> None:
        dlg = AdmissionChannelsDialog(parent=self)
        dlg.exec()
        self._load_channels()

    def _load_patient_if_needed(self) -> None:
        if not self.patient_id:
            return
        data = get_patient(self.patient_id)
        if not data:
            self.error_label.setText("Пациент не найден (возможно, удалён).")
            return

        self.name_edit.setText(str(data.get("full_name") or ""))

        iin = data.get("iin")
        if iin:
            self.iin_edit.setText(str(iin))
        else:
            self.iin_edit.clear()

        birth_iso = data.get("birth_date")
        if birth_iso:
            try:
                y, m, d = map(int, str(birth_iso).split("-"))
                self.birth_date.setDate(QtCore.QDate(y, m, d))
            except Exception:
                pass

        gender = data.get("gender")
        if gender in ("муж", "жен"):
            idx = self.gender_combo.findData(gender)
            if idx >= 0:
                self.gender_combo.setCurrentIndex(idx)

        ac_id = data.get("admission_channel_id")
        if ac_id:
            idx = self.channel_combo.findData(int(ac_id))
            if idx >= 0:
                self.channel_combo.setCurrentIndex(idx)

        # Set current datetime (UX)
        now = QtCore.QDateTime.currentDateTime()
        self.exam_date.setDate(now.date())
        self.exam_time.setTime(now.time())

    def _refresh_age(self) -> None:
        qd = self.birth_date.date()
        birth = date(qd.year(), qd.month(), qd.day())
        today = date.today()

        years, months, days = _calc_age_parts(birth, today)
        if years < 0:
            self.age_edit.setText("Дата в будущем")
            return
        if years > 120:
            self.age_edit.setText("Некорректная дата")
            return
        self.age_edit.setText(f"{years} {_year_word_ru(years)}, {months} мес, {days} дн")

    def _clear(self) -> None:
        self.error_label.setText("")
        self.name_edit.clear()
        self.iin_edit.clear()
        self.birth_date.setDate(QtCore.QDate(1990, 1, 1))
        self.gender_combo.setCurrentIndex(0)
        self.channel_combo.setCurrentIndex(0)

        now = QtCore.QDateTime.currentDateTime()
        self.exam_date.setDate(now.date())
        self.exam_time.setTime(now.time())

        self._refresh_age()
        self._refresh_save_state()

    def _refresh_save_state(self) -> None:
        self.error_label.setText("")
        can = True

        name = self.name_edit.text().strip()
        if not name:
            can = False

        gender = self.gender_combo.currentData()
        if gender not in ("муж", "жен"):
            can = False

        # Age must not be empty and must not be error text
        age = self.age_edit.text().strip()
        if not age or age in ("Дата в будущем", "Некорректная дата"):
            can = False

        # IIN: allow empty, else 12 digits
        iin_raw = self.iin_edit.text()
        iin_digits = re.sub(r"\D", "", iin_raw)
        if iin_digits and len(iin_digits) != 12:
            can = False

        self.save_btn.setEnabled(can)

    @QtCore.Slot()
    def _save(self) -> None:
        self.error_label.setText("")

        full_name = self.name_edit.text().strip()
        if not full_name:
            self.error_label.setText("Введите Ф.И.О. пациента.")
            self.name_edit.setFocus()
            return

        gender = self.gender_combo.currentData()
        if gender not in ("муж", "жен"):
            self.error_label.setText("Выберите пол пациента.")
            self.gender_combo.setFocus()
            return

        iin_digits = re.sub(r"\D", "", self.iin_edit.text())
        iin: str | None
        if iin_digits:
            if len(iin_digits) != 12:
                self.error_label.setText("ИИН должен содержать ровно 12 цифр.")
                self.iin_edit.setFocus()
                return
            iin = iin_digits
        else:
            iin = None

        qd = self.birth_date.date()
        birth = date(qd.year(), qd.month(), qd.day())
        if birth > date.today():
            self.error_label.setText("Дата рождения не может быть в будущем.")
            return
        birth_iso = f"{birth.year:04d}-{birth.month:02d}-{birth.day:02d}"

        ch_id = self.channel_combo.currentData()
        admission_channel_id = int(ch_id) if ch_id else None

        try:
            new_id = upsert_patient(
                patient_id=self.patient_id,
                institution_id=self.institution_id,
                full_name=full_name,
                iin=iin,
                birth_date_iso=birth_iso,
                gender=str(gender),
                admission_channel_id=admission_channel_id,
            )
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                self.error_label.setText("Пациент с таким ИИН уже существует.")
                self.iin_edit.setFocus()
                return
            self.error_label.setText(f"Ошибка базы данных: {e}")
            return
        except Exception as e:  # pragma: no cover
            self.error_label.setText(f"Ошибка: {e}")
            return

        self.saved.emit(PatientDialogResult(new_id))
        self.accept()
