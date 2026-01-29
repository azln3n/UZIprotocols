from __future__ import annotations

import calendar
import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from PySide6 import QtCore, QtGui, QtWidgets

from ..repo import ComboItem, get_patient, list_admission_channels, upsert_patient
from .admission_channels_dialog import AdmissionChannelsDialog
from .auto_combo import AutoComboBox


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
        # По замечанию: окно должно быть компактнее, как в примере
        self.resize(620, 360)
        self.setMinimumWidth(620)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        self.error_label = QtWidgets.QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b00020;")

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(
            "Редактирование пациента" if self.patient_id else "Добавление нового пациента"
        )
        f = title.font()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        header.addWidget(title)
        header.addStretch(1)

        self.channel_settings_btn = QtWidgets.QToolButton()
        self.channel_settings_btn.setText("⚙")
        self.channel_settings_btn.setToolTip("Настройки каналов поступления")
        self.channel_settings_btn.clicked.connect(self._open_channel_settings)
        self.channel_settings_btn.setFixedWidth(48)
        self.channel_settings_btn.setMinimumHeight(32)
        header.addWidget(self.channel_settings_btn)
        root.addLayout(header)

        form = QtWidgets.QFormLayout()
        # Выравнивание/ровность: фиксируем правила для всех строк формы
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        labels: list[QtWidgets.QLabel] = []

        def _form_label(text: str) -> QtWidgets.QLabel:
            lbl = self._bold_label(text)
            labels.append(lbl)
            return lbl

        # Date / time (UX only)
        input_h = 30
        self.exam_date = QtWidgets.QDateEdit()
        self.exam_date.setCalendarPopup(True)
        self.exam_date.setDisplayFormat("dd.MM.yyyy")
        self.exam_time = QtWidgets.QTimeEdit()
        self.exam_time.setDisplayFormat("HH:mm")
        now = QtCore.QDateTime.currentDateTime()
        self.exam_date.setDate(now.date())
        self.exam_time.setTime(now.time())

        dt_row = QtWidgets.QHBoxLayout()
        dt_row.setContentsMargins(0, 0, 0, 0)
        dt_row.setSpacing(12)
        self.exam_date.setMinimumWidth(180)
        self.exam_time.setMinimumWidth(110)
        self.exam_date.setMinimumHeight(input_h)
        self.exam_time.setMinimumHeight(input_h)
        dt_row.addWidget(self.exam_date, 1)
        dt_row.addWidget(self.exam_time, 0)
        dt_container = QtWidgets.QWidget()
        dt_container.setLayout(dt_row)
        form.addRow(_form_label("Дата и время:"), dt_container)

        # FIO
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Введите Ф.И.О. пациента")
        self.name_edit.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.name_edit.setMinimumHeight(input_h)
        self.name_edit.textChanged.connect(self._refresh_save_state)
        form.addRow(_form_label("Ф.И.О. пациента:"), self.name_edit)

        # IIN
        self.iin_edit = QtWidgets.QLineEdit()
        self.iin_edit.setPlaceholderText("12 цифр")
        self.iin_edit.setMaxLength(12)
        # Важно: НЕ используем inputMask — на Windows он даёт "квадратик" каретки и
        # иногда сбрасывает позицию ввода в начало. Валидатор оставляет обычную каретку "|"
        # и позволяет начинать ввод с места клика.
        rx = QtCore.QRegularExpression(r"^\d{0,12}$")
        self.iin_edit.setValidator(QtGui.QRegularExpressionValidator(rx, self.iin_edit))
        self.iin_edit.setInputMethodHints(QtCore.Qt.InputMethodHint.ImhDigitsOnly)
        self.iin_edit.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.iin_edit.setMinimumHeight(input_h)
        self.iin_edit.textChanged.connect(self._refresh_save_state)
        form.addRow(_form_label("ИИН:"), self.iin_edit)

        # Birth date
        self.birth_date = QtWidgets.QDateEdit()
        self.birth_date.setCalendarPopup(True)
        self.birth_date.setDisplayFormat("dd.MM.yyyy")
        # По просьбе: дата рождения + возраст в одной строке, поля компактнее
        self.birth_date.setMinimumWidth(130)
        self.birth_date.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.birth_date.setMinimumHeight(input_h)
        self._birth_min_date = QtCore.QDate(1900, 1, 1)
        self.birth_date.setMinimumDate(self._birth_min_date)
        self.birth_date.setMaximumDate(QtCore.QDate.currentDate())
        # self.birth_date.setSpecialValueText("ДД.ММ.ГГГГ")
        self.birth_date.setDate(self._birth_min_date)
        # True: возраст пересчитывается сразу при изменении даты (без Tab/клика).
        self.birth_date.setKeyboardTracking(True)
        self.birth_date.dateChanged.connect(lambda _d: (self._refresh_age(), self._refresh_save_state()))
        # Не трогаем lineEdit() валидатором: у QDateEdit есть свой встроенный валидатор/парсер.
        # Подмена валидатора ломает ввод и может приводить к значениям вида -2147483648.
        if self.birth_date.lineEdit():
            self.birth_date.lineEdit().setPlaceholderText("ДД.ММ.ГГГГ")

        self.age_edit = QtWidgets.QLineEdit()
        self.age_edit.setReadOnly(True)
        # компактнее и не шире остальных полей
        self.age_edit.setMinimumWidth(0)
        self.age_edit.setMinimumHeight(input_h)
        self.age_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        birth_age_row = QtWidgets.QWidget()
        bl = QtWidgets.QHBoxLayout(birth_age_row)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)
        age_lbl = self._bold_label("Возраст:")
        age_lbl.setMinimumWidth(age_lbl.sizeHint().width())
        bl.addWidget(self.birth_date, 0)
        bl.addWidget(age_lbl, 0)
        bl.addWidget(self.age_edit, 1)
        form.addRow(_form_label("Дата рождения:"), birth_age_row)

        # Gender
        self.gender_combo = AutoComboBox(max_popup_items=30)
        self.gender_combo.addItem("муж.", "муж")
        self.gender_combo.addItem("жен.", "жен")
        self.gender_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.gender_combo.setMinimumHeight(input_h)
        self.gender_combo.currentIndexChanged.connect(self._refresh_save_state)
        self._setup_combo_placeholder(self.gender_combo)
        form.addRow(_form_label("Пол:"), self.gender_combo)

        # Admission channel
        self.channel_combo = AutoComboBox(max_popup_items=30)
        self.channel_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.channel_combo.setMinimumHeight(input_h)
        self.channel_combo.currentIndexChanged.connect(self._refresh_save_state)
        self._setup_combo_placeholder(self.channel_combo)
        form.addRow(_form_label("Канал поступления:"), self.channel_combo)

        root.addLayout(form)
        if labels:
            max_w = max(lbl.sizeHint().width() for lbl in labels)
            for lbl in labels:
                lbl.setMinimumWidth(max_w)

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
        for item in self._channel_items:
            self.channel_combo.addItem(item.name, item.id)
        self.channel_combo.setCurrentIndex(-1)

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
        else:
            self.birth_date.setDate(self._birth_min_date)

        gender = data.get("gender")
        if gender in ("муж", "жен"):
            idx = self.gender_combo.findData(gender)
            if idx >= 0:
                self.gender_combo.setCurrentIndex(idx)
        if gender not in ("муж", "жен"):
            self.gender_combo.setCurrentIndex(-1)

        ac_id = data.get("admission_channel_id")
        if ac_id:
            idx = self.channel_combo.findData(int(ac_id))
            if idx >= 0:
                self.channel_combo.setCurrentIndex(idx)
        if not ac_id:
            self.channel_combo.setCurrentIndex(-1)

        # Set current datetime (UX)
        now = QtCore.QDateTime.currentDateTime()
        self.exam_date.setDate(now.date())
        self.exam_time.setTime(now.time())

    def _birth_date_is_set(self) -> bool:
        qd = self.birth_date.date()
        return bool(qd and qd > self._birth_min_date)

    def _refresh_age(self) -> None:
        if not self._birth_date_is_set():
            self.age_edit.setText("")
            return
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
        self.birth_date.setDate(self._birth_min_date)
        self.gender_combo.setCurrentIndex(-1)
        self.channel_combo.setCurrentIndex(-1)

        now = QtCore.QDateTime.currentDateTime()
        self.exam_date.setDate(now.date())
        self.exam_time.setTime(now.time())

        self._refresh_age()
        self._refresh_save_state()

    def _refresh_save_state(self) -> None:
        if not hasattr(self, "save_btn"):
            return
        self.error_label.setText("")
        can = True

        name = self.name_edit.text().strip()
        if not name:
            can = False

        gender = self.gender_combo.currentData()
        if gender not in ("муж", "жен"):
            can = False

        if not self._birth_date_is_set():
            can = False
        age = self.age_edit.text().strip()
        if age in ("Дата в будущем", "Некорректная дата"):
            can = False

        # IIN: по ТЗ строго 12 цифр (обязательное поле)
        iin_raw = self.iin_edit.text()
        iin_digits = re.sub(r"\D", "", iin_raw)
        if len(iin_digits) != 12:
            can = False

        self.save_btn.setEnabled(can)

    def _setup_combo_placeholder(self, combo: QtWidgets.QComboBox) -> None:
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setPlaceholderText("Выберите")
        pal = combo.palette()
        pal.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor("#9aa0a6"))
        combo.setPalette(pal)
        combo.setCurrentIndex(-1)

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

        if not self._birth_date_is_set():
            self.error_label.setText("Укажите дату рождения пациента.")
            self.birth_date.setFocus()
            return

        iin_digits = re.sub(r"\D", "", self.iin_edit.text())
        iin: str | None
        if len(iin_digits) != 12:
            self.error_label.setText("ИИН должен содержать ровно 12 цифр.")
            self.iin_edit.setFocus()
            return
        iin = iin_digits

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
