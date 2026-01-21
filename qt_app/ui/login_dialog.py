from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtWidgets

from ..repo import ComboItem, list_devices, list_doctors, list_institutions
from .settings_system_dialog import SettingsSystemDialog


@dataclass(frozen=True)
class LoginResult:
    institution_id: int
    doctor_id: int
    device_id: int


class LoginDialog(QtWidgets.QDialog):
    logged_in = QtCore.Signal(LoginResult)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("УЗИ-протоколирование — Вход")
        self.setModal(True)

        self._institution_items: list[ComboItem] = []
        self._doctor_items: list[ComboItem] = []
        self._device_items: list[ComboItem] = []

        self._build_ui()
        self._load_institutions()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Вход в систему")
        title_font = title.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch(1)

        self.settings_btn = QtWidgets.QToolButton()
        self.settings_btn.setText("⚙")
        self.settings_btn.setToolTip("Настройки")
        header.addWidget(self.settings_btn)
        root.addLayout(header)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.institution_combo = QtWidgets.QComboBox()
        self.doctor_combo = QtWidgets.QComboBox()
        self.device_combo = QtWidgets.QComboBox()

        self.institution_combo.currentIndexChanged.connect(self._on_institution_changed)

        form.addRow(self._bold_label("Учреждение:"), self.institution_combo)
        form.addRow(self._bold_label("Врач:"), self.doctor_combo)
        form.addRow(self._bold_label("Аппарат:"), self.device_combo)
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

    @QtCore.Slot(int)
    def _on_institution_changed(self, index: int) -> None:
        self.error_label.setText("")
        if index < 0 or index >= len(self._institution_items):
            self._doctor_items = []
            self._device_items = []
            self.doctor_combo.clear()
            self.device_combo.clear()
            return

        inst_id = self._institution_items[index].id
        self._doctor_items = list_doctors(inst_id)
        self._device_items = list_devices(inst_id)

        self.doctor_combo.clear()
        for item in self._doctor_items:
            self.doctor_combo.addItem(item.name, item.id)

        self.device_combo.clear()
        for item in self._device_items:
            self.device_combo.addItem(item.name, item.id)

        if self._doctor_items:
            self.doctor_combo.setCurrentIndex(0)
        if self._device_items:
            self.device_combo.setCurrentIndex(0)

    def _current_ids(self) -> tuple[int | None, int | None, int | None]:
        inst_id = self.institution_combo.currentData()
        doc_id = self.doctor_combo.currentData()
        dev_id = self.device_combo.currentData()
        return inst_id, doc_id, dev_id

    @QtCore.Slot()
    def _login(self) -> None:
        inst_id, doc_id, dev_id = self._current_ids()
        if not inst_id or not doc_id or not dev_id:
            self.error_label.setText("Заполните все поля (учреждение, врач, аппарат).")
            return

        result = LoginResult(int(inst_id), int(doc_id), int(dev_id))
        self.logged_in.emit(result)
        self.accept()

    @QtCore.Slot()
    def _open_settings(self) -> None:
        dlg = SettingsSystemDialog(parent=self)
        dlg.exec()
        # После изменений перезагружаем список учреждений/врачей/аппаратов
        self._load_institutions()

