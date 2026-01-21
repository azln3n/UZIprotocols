from __future__ import annotations

import traceback

from PySide6 import QtCore, QtGui, QtWidgets

from ..printing.protocol_printer_qt import ProtocolPrinterQt
from ..repo import finalize_open_protocols, get_patient_brief, list_study_types, save_protocol
from .protocol_builder_qt import ProtocolBuilderQt
from .settings_structure_dialog import SettingsStructureDialog


class ProtocolArea(QtWidgets.QWidget):
    protocol_saved = QtCore.Signal(int)  # patient_id
    back_requested = QtCore.Signal()
    search_requested = QtCore.Signal()
    help_requested = QtCore.Signal()
    service_requested = QtCore.Signal()
    about_requested = QtCore.Signal()
    report_requested = QtCore.Signal()

    def __init__(
        self,
        *,
        institution_id: int,
        doctor_id: int,
        device_id: int,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.institution_id = institution_id
        self.doctor_id = doctor_id
        self.device_id = device_id

        self.patient_id: int | None = None
        self.patient_gender: str | None = None
        self._builder: ProtocolBuilderQt | None = None
        self._builder_read_only: bool = False

        self._build_ui()
        self._load_studies()
        self._sync_state()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1) Плашка "Окно протокола"
        title_frame = QtWidgets.QFrame()
        title_frame.setStyleSheet("QFrame { background: #f1f1f1; border: 1px solid #ddd; border-radius: 6px; }")
        title_layout = QtWidgets.QHBoxLayout(title_frame)
        title_layout.setContentsMargins(10, 8, 10, 8)
        title_layout.setSpacing(0)

        title = QtWidgets.QLabel("Окно протокола")
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title, 1)
        layout.addWidget(title_frame)

        # 2) Кнопки (одним рядом)
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(6)

        back_btn = QtWidgets.QPushButton("Назад")
        back_btn.clicked.connect(self.back_requested.emit)
        toolbar.addWidget(back_btn)

        search_btn = QtWidgets.QPushButton("Поиск")
        search_btn.clicked.connect(self.search_requested.emit)
        toolbar.addWidget(search_btn)

        help_btn = QtWidgets.QPushButton("Справка")
        help_btn.clicked.connect(self.help_requested.emit)
        toolbar.addWidget(help_btn)

        service_btn = QtWidgets.QPushButton("Сервис")
        service_btn.clicked.connect(self.service_requested.emit)
        toolbar.addWidget(service_btn)

        about_btn = QtWidgets.QPushButton("О программе")
        about_btn.clicked.connect(self.about_requested.emit)
        toolbar.addWidget(about_btn)

        self.start_btn = QtWidgets.QPushButton("Начать")
        self.start_btn.clicked.connect(self._start)
        toolbar.addWidget(self.start_btn)

        self.save_btn = QtWidgets.QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._save)
        toolbar.addWidget(self.save_btn)

        self.print_btn = QtWidgets.QPushButton("Печать")
        self.print_btn.clicked.connect(self._print)
        toolbar.addWidget(self.print_btn)

        self.settings_btn = QtWidgets.QPushButton("Настройки")
        self.settings_btn.clicked.connect(self._open_settings)
        toolbar.addWidget(self.settings_btn)

        report_btn = QtWidgets.QPushButton("Отчёт")
        report_btn.clicked.connect(self.report_requested.emit)
        toolbar.addWidget(report_btn)

        self.clear_btn = QtWidgets.QPushButton("Очистить")
        # Делам явно красной (как на скрине), при наведении рамка станет синей глобальным стилем
        self.clear_btn.setStyleSheet(
            "QPushButton { background: #F44336; color: white; font-weight: bold; }"
            # По просьбе: остаётся красной даже когда недоступна
            "QPushButton:disabled { background: #F44336; color: white; }"
        )
        self.clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(self.clear_btn)

        layout.addLayout(toolbar)

        # 3) Синяя плашка: слева "Исследование", справа выбор (как в ТЗ)
        study_frame = QtWidgets.QFrame()
        study_frame.setStyleSheet("QFrame { background: #007bff; border-radius: 6px; }")
        study_layout = QtWidgets.QHBoxLayout(study_frame)
        study_layout.setContentsMargins(10, 6, 10, 6)
        study_layout.setSpacing(10)

        study_lbl = QtWidgets.QLabel("Исследование")
        study_lbl.setStyleSheet("color: white; font-weight: bold;")
        study_layout.addWidget(study_lbl)

        self.study_combo = QtWidgets.QComboBox()
        self.study_combo.setMinimumWidth(280)
        study_layout.addWidget(self.study_combo, 1)

        layout.addWidget(study_frame)

        # Инфо о пациенте (аккуратно, без "отладки")
        self._patient_label_full_text = "Выберите пациента слева"
        self.patient_label = QtWidgets.QLabel(self._patient_label_full_text)
        self.patient_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        self.patient_label.setMinimumWidth(0)
        self.patient_label.setStyleSheet("color: #333;")
        layout.addWidget(self.patient_label)

        self.error = QtWidgets.QLabel("")
        self.error.setStyleSheet("color: #b00020;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        self.body_stack = QtWidgets.QStackedWidget()
        self.placeholder = QtWidgets.QLabel(
            "Область протокола.\nВыберите пациента и тип исследования, затем нажмите «Начать».",
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        self.placeholder.setStyleSheet("color: #666; border: 1px dashed #bbb; padding: 20px;")
        self.body_stack.addWidget(self.placeholder)
        layout.addWidget(self.body_stack, 1)

    def _load_studies(self) -> None:
        self.study_combo.clear()
        items = list_study_types()
        for it in items:
            self.study_combo.addItem(it.name, it.id)

    def set_patient(self, patient_id: int | None) -> None:
        self.patient_id = patient_id
        self.patient_gender = None
        self._builder = None
        self._builder_read_only = False
        self.body_stack.setCurrentWidget(self.placeholder)

        if not patient_id:
            self._patient_label_full_text = "Выберите пациента слева"
            self.patient_label.setStyleSheet("color: #333;")
        else:
            brief = get_patient_brief(patient_id)
            if brief:
                name, gender = brief
                self.patient_gender = gender
                self._patient_label_full_text = f"Пациент: {name} ({gender})"
                self.patient_label.setStyleSheet("color: #333;")
                self.patient_label.setToolTip(self._patient_label_full_text)
            else:
                self._patient_label_full_text = "Пациент не найден"
                self.patient_label.setStyleSheet("color: #b00020;")

        self._update_patient_label_elide()
        self._sync_state()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_patient_label_elide()

    def _update_patient_label_elide(self) -> None:
        full = getattr(self, "_patient_label_full_text", "") or ""
        if not full:
            return
        fm = self.patient_label.fontMetrics()
        self.patient_label.setText(
            fm.elidedText(full, QtCore.Qt.TextElideMode.ElideRight, max(10, self.patient_label.width()))
        )

    def _sync_state(self) -> None:
        has_patient = self.patient_id is not None and self.patient_gender in ("муж", "жен")
        self.start_btn.setEnabled(has_patient)
        self.save_btn.setEnabled(has_patient and self._builder is not None and not self._builder_read_only)
        self.print_btn.setEnabled(has_patient and self._builder is not None)
        self.clear_btn.setEnabled(has_patient and self._builder is not None and not self._builder_read_only)

    @QtCore.Slot()
    def _start(self) -> None:
        self.error.setText("")
        if not self.patient_id or self.patient_gender not in ("муж", "жен"):
            self.error.setText("Выберите пациента.")
            return
        study_id = self.study_combo.currentData()
        if not study_id:
            self.error.setText("Выберите тип исследования.")
            return

        # По просьбе: просто создаём НОВЫЙ протокол всегда.
        # Чтобы старые черновики не мешали, тихо закрываем их (если были).
        finalize_open_protocols(patient_id=int(self.patient_id), study_type_id=int(study_id))
        forced_protocol_id = save_protocol(
            protocol_id=None,
            patient_id=int(self.patient_id),
            study_type_id=int(study_id),
            doctor_id=int(self.doctor_id),
            device_id=int(self.device_id),
            institution_id=int(self.institution_id),
            values={},
            finalize=False,
        )
        # обновим список протоколов слева (чтобы новый сразу появился)
        self.protocol_saved.emit(int(self.patient_id))

        self._builder = ProtocolBuilderQt(
            parent=self,
            patient_id=int(self.patient_id),
            patient_gender=str(self.patient_gender),
            study_type_id=int(study_id),
            protocol_id=int(forced_protocol_id) if forced_protocol_id else None,
            read_only=False,
        )
        self._builder_read_only = False
        try:
            widget = self._builder.build()
        except Exception as e:  # pragma: no cover
            tb = traceback.format_exc()
            self.error.setText(f"Ошибка при построении протокола: {e}\nСм. qt_error.log")
            try:
                with open("qt_error.log", "a", encoding="utf-8") as f:
                    f.write("\n--- Protocol build error ---\n")
                    f.write(tb)
            except Exception:
                pass
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Ошибка при построении протокола:\n{e}")
            self._builder = None
            self._sync_state()
            return
        if self.body_stack.count() == 1:
            self.body_stack.addWidget(widget)
        else:
            old = self.body_stack.widget(1)
            self.body_stack.removeWidget(old)
            old.deleteLater()
            self.body_stack.addWidget(widget)
        self.body_stack.setCurrentIndex(1)
        self._sync_state()

    def open_saved_protocol(self, *, protocol_id: int, study_type_id: int) -> None:
        """
        Открыть сохранённый протокол в правом блоке (по ТЗ: при выборе в списке слева).
        Режим просмотра: изменения запрещены.
        """
        self.error.setText("")
        if not self.patient_id or self.patient_gender not in ("муж", "жен"):
            self.error.setText("Выберите пациента.")
            return
        if not protocol_id or protocol_id <= 0:
            return

        if study_type_id:
            idx = self.study_combo.findData(int(study_type_id))
            if idx >= 0:
                self.study_combo.setCurrentIndex(idx)

        self._builder = ProtocolBuilderQt(
            parent=self,
            patient_id=int(self.patient_id),
            patient_gender=str(self.patient_gender),
            study_type_id=int(study_type_id) if study_type_id else int(self.study_combo.currentData() or 0),
            protocol_id=int(protocol_id),
            read_only=True,
        )
        self._builder_read_only = True

        try:
            widget = self._builder.build()
        except Exception as e:  # pragma: no cover
            tb = traceback.format_exc()
            self.error.setText(f"Ошибка при открытии протокола: {e}\nСм. qt_error.log")
            try:
                with open("qt_error.log", "a", encoding="utf-8") as f:
                    f.write("\n--- Protocol open error ---\n")
                    f.write(tb)
            except Exception:
                pass
            self._builder = None
            self._builder_read_only = False
            self._sync_state()
            return

        if self.body_stack.count() == 1:
            self.body_stack.addWidget(widget)
        else:
            old = self.body_stack.widget(1)
            self.body_stack.removeWidget(old)
            old.deleteLater()
            self.body_stack.addWidget(widget)
        self.body_stack.setCurrentIndex(1)
        self._sync_state()

    @QtCore.Slot()
    def _clear(self) -> None:
        self.error.setText("")
        if self._builder:
            self._builder.clear_current_tab()

    @QtCore.Slot()
    def _save(self) -> None:
        self.error.setText("")
        if not self.patient_id or not self._builder:
            self.error.setText("Сначала начните исследование.")
            return

        # required fields validation (visible only, like Tkinter)
        missing: list[str] = []
        for fid, b in self._builder.fields.items():
            if b.meta.required:
                if b.meta.is_hidden and not b.container.isVisible():
                    continue
                v = b.get_str()
                if not v or not v.strip():
                    missing.append(b.meta.name)
        if missing:
            self.error.setText("Заполните обязательные поля:\n" + "\n".join(f"- {m}" for m in missing))
            return

        values = self._builder.collect_values()
        pid = save_protocol(
            protocol_id=self._builder.protocol_id(),
            patient_id=int(self.patient_id),
            study_type_id=int(self._builder.study_type_id),
            doctor_id=int(self.doctor_id),
            device_id=int(self.device_id),
            institution_id=int(self.institution_id),
            values=values,
            finalize=False,
        )
        self._builder.set_protocol_id(pid)
        QtWidgets.QMessageBox.information(self, "Успех", f"Протокол сохранён (ID: {pid}).")
        self.protocol_saved.emit(int(self.patient_id))

    @QtCore.Slot()
    def _print(self) -> None:
        self.error.setText("")
        if not self.patient_id or not self._builder:
            self.error.setText("Сначала начните исследование.")
            return

        # Если открыт сохранённый протокол (read-only), печатаем именно его (без автосохранения).
        if self._builder_read_only and self._builder.protocol_id():
            ProtocolPrinterQt(parent=self).print_saved(protocol_id=int(self._builder.protocol_id()))
            return

        # По просьбе: печать завершает протокол, чтобы следующий запуск создавал новый и
        # не появлялось "есть незавершённый" после уже распечатанного протокола.
        values = self._builder.collect_values()
        pid = save_protocol(
            protocol_id=self._builder.protocol_id(),
            patient_id=int(self.patient_id),
            study_type_id=int(self._builder.study_type_id),
            doctor_id=int(self.doctor_id),
            device_id=int(self.device_id),
            institution_id=int(self.institution_id),
            values=values,
            finalize=True,
        )
        self._builder.set_protocol_id(pid)
        self.protocol_saved.emit(int(self.patient_id))

        printer = ProtocolPrinterQt(parent=self)
        ok = printer.print_current(
            patient_id=int(self.patient_id),
            study_type_id=int(self._builder.study_type_id),
            doctor_id=int(self.doctor_id),
            device_id=int(self.device_id),
            builder=self._builder,
            study_name=self.study_combo.currentText(),
            protocol_id=pid,
        )
        if ok:
            # после печати делаем режим просмотра, чтобы нельзя было случайно перезаписать завершённый протокол
            self.open_saved_protocol(protocol_id=int(pid), study_type_id=int(self._builder.study_type_id))

    @QtCore.Slot()
    def _open_settings(self) -> None:
        dlg = SettingsStructureDialog(parent=self)
        dlg.changed.connect(self._load_studies)
        dlg.exec()
