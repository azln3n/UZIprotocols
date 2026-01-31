from __future__ import annotations

import sys
import traceback

from PySide6 import QtWidgets

from qt_app.db import ensure_db_initialized
from qt_app.ui.app_style import apply_app_style
from qt_app.ui.login_dialog import LoginDialog
from qt_app.ui.main_window import MainWindow, Session


def main() -> int:
    ensure_db_initialized()

    # Чтобы при падении в слотах/делегатах Qt в терминале был виден traceback
    def _excepthook(etype, value, tb):
        traceback.print_exception(etype, value, tb)

    sys.excepthook = _excepthook

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("УЗИ-протоколирование")
    apply_app_style(app)

    while True:
        login = LoginDialog()
        if login.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return 0

        inst_id = login.institution_combo.currentData()
        doc_id = login.doctor_combo.currentData()
        if inst_id is None or doc_id is None:
            continue

        try:
            window = MainWindow(Session(int(inst_id), int(doc_id)))
        except Exception:
            traceback.print_exc()
            return 1

        logout = {"flag": False}

        def _on_logout():
            logout["flag"] = True

        window.logout_requested.connect(_on_logout)
        window.show()

        window.destroyed.connect(lambda: app.quit() if not logout["flag"] else None)
        app.exec()

        if logout["flag"]:
            continue
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

