from __future__ import annotations

import sys

from PySide6 import QtWidgets

from qt_app.db import ensure_db_initialized
from qt_app.ui.app_style import apply_app_style
from qt_app.ui.login_dialog import LoginDialog
from qt_app.ui.main_window import MainWindow, Session


def main() -> int:
    ensure_db_initialized()

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("УЗИ-протоколирование")
    apply_app_style(app)

    while True:
        login = LoginDialog()
        if login.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return 0

        inst_id = int(login.institution_combo.currentData())
        doc_id = int(login.doctor_combo.currentData())

        window = MainWindow(Session(inst_id, doc_id))
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

