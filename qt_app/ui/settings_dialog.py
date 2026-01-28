from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .db_admin_dialog import DatabaseAdminDialog
from .file_paths_dialog import FilePathsDialog
from .settings_structure_dialog import SettingsStructureDialog


class SettingsDialog(QtWidgets.QDialog):
    """
    Единая точка входа в настройки.

    По плану:
    - настройки структуры исследований (как сейчас)
    - администрирование БД (просмотр/редактирование + импорт/экспорт)
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.resize(520, 220)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        title = QtWidgets.QLabel("Выберите раздел настроек")
        f = title.font()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        btns = QtWidgets.QHBoxLayout()
        btns.setSpacing(12)

        self.structure_btn = QtWidgets.QPushButton("Структура исследований")
        self.structure_btn.setMinimumHeight(64)
        self.structure_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.structure_btn.clicked.connect(self._open_structure)
        btns.addWidget(self.structure_btn, 1)

        self.db_btn = QtWidgets.QPushButton("База данных")
        self.db_btn.setMinimumHeight(64)
        self.db_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.db_btn.clicked.connect(self._open_db_admin)
        btns.addWidget(self.db_btn, 1)

        self.paths_btn = QtWidgets.QPushButton("Пути к файлам")
        self.paths_btn.setMinimumHeight(64)
        self.paths_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.paths_btn.clicked.connect(self._open_paths)
        btns.addWidget(self.paths_btn, 1)

        root.addLayout(btns)

        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    @QtCore.Slot()
    def _open_structure(self) -> None:
        dlg = SettingsStructureDialog(parent=self)
        dlg.exec()

    @QtCore.Slot()
    def _open_db_admin(self) -> None:
        dlg = DatabaseAdminDialog(parent=self)
        dlg.exec()

    @QtCore.Slot()
    def _open_paths(self) -> None:
        dlg = FilePathsDialog(parent=self)
        dlg.exec()

