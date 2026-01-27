from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..utils.app_settings import ExternalFilesSettings, load_external_files_settings, save_external_files_settings


class FilePathsDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Настройки — пути к файлам")
        self.resize(760, 260)
        self.setModal(True)

        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        info = QtWidgets.QLabel(
            "Здесь можно указать пути к файлам для кнопок:\n"
            "«Справка» (exe), «Сервис» (html), «О программе» (exe).\n"
            "Если путь не задан — приложение попробует найти файлы рядом с приложением (как раньше)."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.help_edit = QtWidgets.QLineEdit()
        self.service_edit = QtWidgets.QLineEdit()
        self.about_edit = QtWidgets.QLineEdit()

        form.addRow("Справка (exe):", self._row(self.help_edit, self._pick_help))
        form.addRow("Сервис (html):", self._row(self.service_edit, self._pick_service))
        form.addRow("О программе (exe):", self._row(self.about_edit, self._pick_about))
        root.addLayout(form)

        footer = QtWidgets.QHBoxLayout()
        self.reset_btn = QtWidgets.QPushButton("Сбросить")
        self.reset_btn.clicked.connect(self._reset)
        footer.addWidget(self.reset_btn)
        footer.addStretch(1)
        ok = QtWidgets.QPushButton("OK")
        cancel = QtWidgets.QPushButton("Отмена")
        ok.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        footer.addWidget(ok)
        footer.addWidget(cancel)
        root.addLayout(footer)

    def _row(self, edit: QtWidgets.QLineEdit, browse_cb) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        l = QtWidgets.QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)
        l.addWidget(edit, 1)
        b = QtWidgets.QPushButton("…")
        b.setFixedWidth(40)
        b.clicked.connect(browse_cb)
        l.addWidget(b)
        return w

    def _load(self) -> None:
        s = load_external_files_settings()
        self.help_edit.setText(s.help_path or "")
        self.service_edit.setText(s.service_path or "")
        self.about_edit.setText(s.about_path or "")

    def _reset(self) -> None:
        self.help_edit.clear()
        self.service_edit.clear()
        self.about_edit.clear()

    def _pick_help(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите файл справки", "", "EXE (*.exe);;Все файлы (*.*)")
        if path:
            self.help_edit.setText(path)

    def _pick_service(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите файл сервиса", "", "HTML (*.htm *.html);;Все файлы (*.*)")
        if path:
            self.service_edit.setText(path)

    def _pick_about(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите файл «О программе»", "", "EXE (*.exe);;Все файлы (*.*)")
        if path:
            self.about_edit.setText(path)

    @QtCore.Slot()
    def _save(self) -> None:
        def _norm(p: str) -> str | None:
            p = (p or "").strip()
            if not p:
                return None
            return str(Path(p))

        s = ExternalFilesSettings(
            help_path=_norm(self.help_edit.text()),
            service_path=_norm(self.service_edit.text()),
            about_path=_norm(self.about_edit.text()),
        )
        save_external_files_settings(s)
        self.accept()

