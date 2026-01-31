from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtWidgets

from ..repo import ComboItem, list_doctors, list_institutions
from .settings_system_dialog import SettingsSystemDialog
from .auto_combo import AutoComboBox


@dataclass(frozen=True)
class LoginResult:
    institution_id: int
    doctor_id: int


class LoginDialog(QtWidgets.QDialog):
    logged_in = QtCore.Signal(LoginResult)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("УЗИ-протоколирование — Вход")
        self.setModal(True)
        # По замечанию заказчика: сделать окно чуть шире/длиннее под длинные надписи и значения
        self.setMinimumWidth(420)

        self._institution_items: list[ComboItem] = []
        self._doctor_items: list[ComboItem] = []

        self._build_ui()
        self._load_institutions()
        QtCore.QTimer.singleShot(0, self._adjust_to_contents)

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Вход в систему")
        title_font = title.font()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch(1)

        self.settings_btn = QtWidgets.QToolButton()
        # Ближе к скрину: шестерёнка в правом верхнем углу
        self.settings_btn.setText("⚙")
        self.settings_btn.setToolTip("Настройки")
        header.addWidget(self.settings_btn)
        root.addLayout(header)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.institution_combo = AutoComboBox(max_popup_items=30)
        self.doctor_combo = AutoComboBox(max_popup_items=30)
        self.institution_combo.setEditable(False)
        self.doctor_combo.setEditable(False)
        # По ТЗ: окно входа небольшое, но текст в комбобоксах не должен обрезаться
        for cb in (self.institution_combo, self.doctor_combo):
            cb.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
            cb.currentTextChanged.connect(lambda _t=None: self._adjust_to_contents())
            # Match standard field styling (like Пол/Канал)
            cb.setStyleSheet(
                "QComboBox { border: 1px solid #bbbbbb; border-radius: 4px; padding: 6px 8px; } "
                "QComboBox:focus, QComboBox:on { border: 2px solid #007bff; padding: 5px 7px; }"
            )

        self.institution_combo.currentIndexChanged.connect(self._on_institution_changed)

        form.addRow(self._bold_label("Учреждение:"), self.institution_combo)
        form.addRow(self._bold_label("Врач:"), self.doctor_combo)
        root.addLayout(form)

        self.error_label = QtWidgets.QLabel("")
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.login_btn = QtWidgets.QPushButton("Вход")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self._login)
        self.login_btn.setMinimumWidth(140)
        self.login_btn.setStyleSheet(
            "QPushButton { background: #2196F3; color: white; padding: 8px 18px; border-radius: 6px; border: 2px solid #9aa0a6; }"
            "QPushButton:hover { background: #1976D2; border-color: #007bff; }"
            "QPushButton:focus { border-color: #007bff; }"
        )
        btn_row.addWidget(self.login_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.settings_btn.clicked.connect(self._open_settings)

    def _adjust_to_contents(self) -> None:
        # Подгоняем диалог под текущие значения комбобоксов (и их sizeHint).
        try:
            min_w = max(
                int(self.institution_combo.sizeHint().width()),
                int(self.doctor_combo.sizeHint().width()),
                260,
            )
            self.institution_combo.setMinimumWidth(min_w)
            self.doctor_combo.setMinimumWidth(min_w)
        except Exception:
            pass
        self.adjustSize()

    def _bold_label(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    def _load_institutions(self) -> None:
        self._institution_items = list_institutions()
        self.institution_combo.clear()
        for item in self._institution_items:
            self.institution_combo.addItem(item.name, item.id)

        if self._institution_items:
            self.institution_combo.setCurrentIndex(0)
            self._on_institution_changed(0)
        self._adjust_to_contents()

    @QtCore.Slot(int)
    def _on_institution_changed(self, index: int) -> None:
        self.error_label.setText("")
        if index < 0 or index >= len(self._institution_items):
            self._doctor_items = []
            self.doctor_combo.clear()
            return

        inst_id = self._institution_items[index].id
        self._doctor_items = list_doctors(inst_id)

        self.doctor_combo.clear()
        for item in self._doctor_items:
            self.doctor_combo.addItem(item.name, item.id)

        if self._doctor_items:
            self.doctor_combo.setCurrentIndex(0)
        self._adjust_to_contents()

    def _current_ids(self) -> tuple[int | None, int | None, int | None]:
        inst_id = self.institution_combo.currentData()
        doc_id = self.doctor_combo.currentData()
        return inst_id, doc_id, None

    @QtCore.Slot()
    def _login(self) -> None:
        inst_id, doc_id, _ = self._current_ids()
        if not inst_id or not doc_id:
            self.error_label.setText("Заполните все поля (учреждение, врач).")
            return

        result = LoginResult(int(inst_id), int(doc_id))
        self.logged_in.emit(result)
        self.accept()

    @QtCore.Slot()
    def _open_settings(self) -> None:
        dlg = SettingsSystemDialog(parent=self)
        dlg.exec()
        # После изменений перезагружаем список учреждений/врачей/аппаратов
        self._load_institutions()

