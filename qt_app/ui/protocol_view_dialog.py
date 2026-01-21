from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..repo import get_patient_brief, get_protocol_meta
from ..printing.protocol_printer_qt import ProtocolPrinterQt
from .protocol_builder_qt import ProtocolBuilderQt


class ProtocolViewDialog(QtWidgets.QDialog):
    def __init__(self, *, protocol_id: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.protocol_id = protocol_id
        self.setWindowTitle(f"Просмотр протокола #{protocol_id}")
        self.resize(980, 720)
        self.setModal(True)

        meta = get_protocol_meta(protocol_id)
        if not meta:
            layout = QtWidgets.QVBoxLayout(self)
            layout.addWidget(QtWidgets.QLabel("Протокол не найден.", alignment=QtCore.Qt.AlignmentFlag.AlignCenter))
            return

        patient_id = int(meta["patient_id"])
        study_type_id = int(meta["study_type_id"])
        brief = get_patient_brief(patient_id)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        if not brief:
            layout.addWidget(QtWidgets.QLabel("Пациент не найден.", alignment=QtCore.Qt.AlignmentFlag.AlignCenter))
            return

        header = QtWidgets.QLabel(
            f"Пациент: {brief[0]} ({brief[1]}) | created_at={meta['created_at']} | finished_at={meta['finished_at']}",
        )
        header.setStyleSheet("color: #444;")
        header.setWordWrap(True)
        layout.addWidget(header)

        builder = ProtocolBuilderQt(
            parent=self,
            patient_id=patient_id,
            patient_gender=str(brief[1]),
            study_type_id=study_type_id,
            protocol_id=protocol_id,
            read_only=True,
        )
        built = builder.build()
        layout.addWidget(built, 1)

        btns = QtWidgets.QHBoxLayout()
        print_btn = QtWidgets.QPushButton("Печать")
        print_btn.setStyleSheet(
            "QPushButton { background: #795548; color: white; font-weight: bold; padding: 6px 12px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        print_btn.clicked.connect(
            lambda: ProtocolPrinterQt(parent=self).print_saved(protocol_id=int(protocol_id))
        )
        btns.addWidget(print_btn)
        btns.addStretch(1)
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.setStyleSheet(
            "QPushButton { background: #e9ecef; color: black; border: 2px solid #9aa0a6; border-radius: 6px; padding: 6px 18px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

