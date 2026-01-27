from __future__ import annotations

import csv
import html
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..db import connect
from ..paths import protocols_dir
from .auto_combo import AutoComboBox


MONTHS = [
    ("Все", None),
    ("Январь", 1),
    ("Февраль", 2),
    ("Март", 3),
    ("Апрель", 4),
    ("Май", 5),
    ("Июнь", 6),
    ("Июль", 7),
    ("Август", 8),
    ("Сентябрь", 9),
    ("Октябрь", 10),
    ("Ноябрь", 11),
    ("Декабрь", 12),
]


@dataclass(frozen=True)
class ReportParams:
    year: str | None  # YYYY or None (all)
    month: int | None  # 1..12 or None (all)
    study_type_name: str | None
    channel_name: str | None


class ReportDialog(QtWidgets.QDialog):
    def __init__(self, *, institution_id: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.institution_id = institution_id
        self.setWindowTitle("Формирование отчёта")
        self.resize(920, 720)
        self.setModal(True)

        self._build_ui()
        self._load_filters()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        params_box = QtWidgets.QGroupBox("Параметры отчёта")
        pf = QtWidgets.QGridLayout(params_box)
        pf.setHorizontalSpacing(10)
        pf.setVerticalSpacing(10)

        pf.addWidget(QtWidgets.QLabel("Год:"), 0, 0)
        self.year_combo = AutoComboBox(max_popup_items=30)
        pf.addWidget(self.year_combo, 0, 1)

        pf.addWidget(QtWidgets.QLabel("Месяц:"), 0, 2)
        self.month_combo = AutoComboBox(max_popup_items=30)
        for name, num in MONTHS:
            self.month_combo.addItem(name, num)
        pf.addWidget(self.month_combo, 0, 3)

        pf.addWidget(QtWidgets.QLabel("Тип исследования:"), 1, 0)
        self.study_combo = AutoComboBox(max_popup_items=30)
        pf.addWidget(self.study_combo, 1, 1)

        pf.addWidget(QtWidgets.QLabel("Канал поступления:"), 1, 2)
        self.channel_combo = AutoComboBox(max_popup_items=30)
        pf.addWidget(self.channel_combo, 1, 3)

        btn_row = QtWidgets.QHBoxLayout()
        build_btn = QtWidgets.QPushButton("Сформировать отчёт")
        build_btn.setStyleSheet(
            "QPushButton { background: #4CAF50; color: white; font-weight: bold; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        build_btn.clicked.connect(self._generate)
        clear_btn = QtWidgets.QPushButton("Очистить")
        clear_btn.setStyleSheet(
            "QPushButton { background: #FF9800; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(build_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        pf.addLayout(btn_row, 2, 0, 1, 4)

        root.addWidget(params_box)

        result_box = QtWidgets.QGroupBox("Результаты отчёта")
        rl = QtWidgets.QVBoxLayout(result_box)
        self.total_label = QtWidgets.QLabel("Общее количество исследований: 0")
        self.total_label.setStyleSheet("font-weight: bold;")
        rl.addWidget(self.total_label)

        self.stats_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.stats_split.setChildrenCollapsible(False)

        # stats tables (по ТЗ: "общее число и число каждого в виде таблицы")
        stats_top = QtWidgets.QWidget()
        stl = QtWidgets.QHBoxLayout(stats_top)
        stl.setContentsMargins(0, 0, 0, 0)
        stl.setSpacing(12)

        self.study_stats = QtWidgets.QTableWidget(0, 3)
        self.study_stats.setHorizontalHeaderLabels(["Тип исследования", "Кол-во", "%"])
        self.study_stats.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.study_stats.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.study_stats.horizontalHeader().setStretchLastSection(True)
        self.study_stats.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.study_stats.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.study_stats.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.channel_stats = QtWidgets.QTableWidget(0, 3)
        self.channel_stats.setHorizontalHeaderLabels(["Канал поступления", "Кол-во", "%"])
        self.channel_stats.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.channel_stats.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.channel_stats.horizontalHeader().setStretchLastSection(True)
        self.channel_stats.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.channel_stats.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.channel_stats.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        stl.addWidget(self.study_stats, 1)
        stl.addWidget(self.channel_stats, 1)

        # details table
        self.details = QtWidgets.QTableWidget(0, 7)
        self.details.setHorizontalHeaderLabels(
            ["ID", "ФИО", "ИИН", "Тип исследования", "Канал", "Дата/время", "Врач"]
        )
        self.details.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.details.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.details.horizontalHeader().setStretchLastSection(True)
        self.details.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.details.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.details.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.details.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.details.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.details.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.details.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.stats_split.addWidget(stats_top)
        self.stats_split.addWidget(self.details)
        self.stats_split.setSizes([220, 420])

        rl.addWidget(self.stats_split, 1)
        root.addWidget(result_box, 1)

        footer = QtWidgets.QHBoxLayout()
        self.print_btn = QtWidgets.QPushButton("Печать отчёта")
        self.print_btn.setStyleSheet(
            "QPushButton { background: #795548; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        self.print_btn.clicked.connect(self._print)
        export_btn = QtWidgets.QPushButton("Экспорт в файл")
        export_btn.setStyleSheet(
            "QPushButton { background: #2196F3; color: white; padding: 6px 10px; border: 2px solid #9aa0a6; border-radius: 6px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        export_btn.clicked.connect(self._export_txt)
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.setStyleSheet(
            "QPushButton { background: #e9ecef; color: black; border: 2px solid #9aa0a6; border-radius: 6px; padding: 6px 18px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #007bff; }"
        )
        close_btn.clicked.connect(self.accept)

        footer.addWidget(self.print_btn)
        footer.addWidget(export_btn)
        footer.addStretch(1)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _load_filters(self) -> None:
        with connect() as conn:
            years = conn.execute(
                "SELECT DISTINCT strftime('%Y', created_at) as year FROM protocols ORDER BY year DESC"
            ).fetchall()
            year_vals = ["Все"] + [str(r["year"]) for r in years if r["year"]]

            studies = conn.execute(
                "SELECT name FROM study_types WHERE is_active = 1 ORDER BY name"
            ).fetchall()
            study_vals = ["Все"] + [str(r["name"]) for r in studies]

            channels = conn.execute(
                "SELECT name FROM admission_channels WHERE is_active = 1 ORDER BY name"
            ).fetchall()
            channel_vals = ["Все"] + [str(r["name"]) for r in channels]

        self.year_combo.clear()
        self.year_combo.addItems(year_vals)
        # default current year if present else "Все"
        cur_year = str(datetime.now().year)
        idx = self.year_combo.findText(cur_year)
        self.year_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.study_combo.clear()
        self.study_combo.addItems(study_vals)
        self.channel_combo.clear()
        self.channel_combo.addItems(channel_vals)

        self.month_combo.setCurrentIndex(0)

    def _params(self) -> ReportParams:
        year = self.year_combo.currentText()
        month_num = self.month_combo.currentData()
        study = self.study_combo.currentText()
        channel = self.channel_combo.currentText()
        return ReportParams(
            year=None if year == "Все" else year,
            month=None if month_num is None else int(month_num),
            study_type_name=None if study == "Все" else study,
            channel_name=None if channel == "Все" else channel,
        )

    def _clear(self) -> None:
        cur_year = str(datetime.now().year)
        idx = self.year_combo.findText(cur_year)
        self.year_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.month_combo.setCurrentIndex(0)
        self.study_combo.setCurrentIndex(0)
        self.channel_combo.setCurrentIndex(0)
        self.total_label.setText("Общее количество исследований: 0")
        self.study_stats.setRowCount(0)
        self.channel_stats.setRowCount(0)
        self.details.setRowCount(0)

    def _generate(self) -> None:
        p = self._params()
        self.total_label.setText("Общее количество исследований: 0")
        self.study_stats.setRowCount(0)
        self.channel_stats.setRowCount(0)
        self.details.setRowCount(0)

        params: list[object] = []
        conditions = ["p.institution_id = ?"]
        params.append(int(self.institution_id))

        if p.year:
            conditions.append("strftime('%Y', pr.created_at) = ?")
            params.append(p.year)
        if p.month:
            conditions.append("strftime('%m', pr.created_at) = ?")
            params.append(f"{p.month:02d}")
        if p.study_type_name:
            conditions.append("st.name = ?")
            params.append(p.study_type_name)
        if p.channel_name:
            conditions.append("ac.name = ?")
            params.append(p.channel_name)

        where = " AND ".join(conditions)

        with connect() as conn:
            cur = conn.cursor()
            total_count = cur.execute(
                f"""
                SELECT COUNT(*)
                FROM protocols pr
                JOIN patients p ON pr.patient_id = p.id
                JOIN study_types st ON pr.study_type_id = st.id
                LEFT JOIN admission_channels ac ON p.admission_channel_id = ac.id
                WHERE {where}
                """,
                params,
            ).fetchone()[0]

            study_rows = cur.execute(
                f"""
                SELECT st.name as study_type, COUNT(*) as cnt
                FROM protocols pr
                JOIN patients p ON pr.patient_id = p.id
                JOIN study_types st ON pr.study_type_id = st.id
                LEFT JOIN admission_channels ac ON p.admission_channel_id = ac.id
                WHERE {where}
                GROUP BY st.name
                ORDER BY st.name
                """,
                params,
            ).fetchall()

            channel_rows = cur.execute(
                f"""
                SELECT COALESCE(ac.name, 'Не указан') as channel, COUNT(*) as cnt
                FROM protocols pr
                JOIN patients p ON pr.patient_id = p.id
                JOIN study_types st ON pr.study_type_id = st.id
                LEFT JOIN admission_channels ac ON p.admission_channel_id = ac.id
                WHERE {where}
                GROUP BY ac.name
                ORDER BY channel
                """,
                params,
            ).fetchall()

            details = cur.execute(
                f"""
                SELECT
                  pr.id,
                  p.full_name,
                  p.iin,
                  st.name as study_type,
                  ac.name as channel,
                  pr.created_at,
                  d.full_name as doctor_name
                FROM protocols pr
                JOIN patients p ON pr.patient_id = p.id
                JOIN study_types st ON pr.study_type_id = st.id
                LEFT JOIN admission_channels ac ON p.admission_channel_id = ac.id
                LEFT JOIN doctors d ON pr.doctor_id = d.id
                WHERE {where}
                ORDER BY pr.created_at DESC
                LIMIT 100
                """,
                params,
            ).fetchall()

        if not total_count:
            self.total_label.setText("Общее количество исследований: 0")
            return

        self.total_label.setText(f"Общее количество исследований: {int(total_count)}")

        # fill study stats table
        self.study_stats.setRowCount(0)
        for r in study_rows:
            st = str(r["study_type"])
            cnt = int(r["cnt"])
            pct = (cnt / total_count * 100.0) if total_count else 0.0
            row = self.study_stats.rowCount()
            self.study_stats.insertRow(row)
            self.study_stats.setItem(row, 0, QtWidgets.QTableWidgetItem(st))
            self.study_stats.setItem(row, 1, QtWidgets.QTableWidgetItem(str(cnt)))
            self.study_stats.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{pct:.1f}%"))

        # fill channel stats table
        self.channel_stats.setRowCount(0)
        for r in channel_rows:
            ch = str(r["channel"] or "Не указан")
            cnt = int(r["cnt"])
            pct = (cnt / total_count * 100.0) if total_count else 0.0
            row = self.channel_stats.rowCount()
            self.channel_stats.insertRow(row)
            self.channel_stats.setItem(row, 0, QtWidgets.QTableWidgetItem(ch))
            self.channel_stats.setItem(row, 1, QtWidgets.QTableWidgetItem(str(cnt)))
            self.channel_stats.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{pct:.1f}%"))

        # fill details
        self.details.setRowCount(0)
        for d in details:
            row = self.details.rowCount()
            self.details.insertRow(row)
            dt = str(d["created_at"] or "")
            if "." in dt:
                dt = dt.split(".", 1)[0]
            self.details.setItem(row, 0, QtWidgets.QTableWidgetItem(str(d["id"])))
            self.details.setItem(row, 1, QtWidgets.QTableWidgetItem(str(d["full_name"] or "")))
            self.details.setItem(row, 2, QtWidgets.QTableWidgetItem(str(d["iin"] or "")))
            self.details.setItem(row, 3, QtWidgets.QTableWidgetItem(str(d["study_type"] or "")))
            self.details.setItem(row, 4, QtWidgets.QTableWidgetItem(str(d["channel"] or "Не указан")))
            self.details.setItem(row, 5, QtWidgets.QTableWidgetItem(dt))
            self.details.setItem(row, 6, QtWidgets.QTableWidgetItem(str(d["doctor_name"] or "")))

    def _print(self) -> None:
        if self.details.rowCount() == 0 and self.study_stats.rowCount() == 0 and self.channel_stats.rowCount() == 0:
            QtWidgets.QMessageBox.warning(self, "Внимание", "Сначала сформируйте отчёт.")
            return

        def _table_html(table: QtWidgets.QTableWidget) -> str:
            headers = [html.escape(table.horizontalHeaderItem(i).text()) for i in range(table.columnCount())]
            rows: list[str] = []
            for r in range(table.rowCount()):
                tds = []
                for c in range(table.columnCount()):
                    it = table.item(r, c)
                    tds.append(f"<td>{html.escape(it.text() if it else '')}</td>")
                rows.append("<tr>" + "".join(tds) + "</tr>")
            return (
                "<table>"
                "<thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead>"
                "<tbody>" + "".join(rows) + "</tbody>"
                "</table>"
            )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <title>Отчёт по УЗИ</title>
          <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; font-size: 12px; }}
            h1 {{ text-align: center; color: #333; }}
            table {{ width: 100%; border-collapse: collapse; margin: 8px 0 18px 0; }}
            th, td {{ border: 1px solid #999; padding: 6px 8px; text-align: left; }}
            th {{ background: #eef5ff; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
            .no-print {{ margin-top: 20px; text-align: center; }}
            @media print {{ .no-print {{ display: none; }} }}
          </style>
        </head>
        <body>
          <h1>ОТЧЕТ ПО УЗИ-ИССЛЕДОВАНИЯМ</h1>
          <div><p>Дата формирования: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p></div>
          <p><b>{html.escape(self.total_label.text())}</b></p>
          <div class="grid">
            <div>
              <h3>Статистика по типам</h3>
              {_table_html(self.study_stats)}
            </div>
            <div>
              <h3>Статистика по каналам</h3>
              {_table_html(self.channel_stats)}
            </div>
          </div>
          <h3>Детализация (последние 100)</h3>
          {_table_html(self.details)}
          <div class="no-print">
            <button onclick="window.print()">Печать</button>
          </div>
        </body>
        </html>
        """

        day_dir = protocols_dir() / "reports" / datetime.now().strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        out = day_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        out.write_text(html_content, encoding="utf-8")
        webbrowser.open(out.as_uri())
        QtWidgets.QMessageBox.information(self, "Печать", "Отчёт открыт в браузере. Нажмите Ctrl+P для печати.")

    def _export_txt(self) -> None:
        if self.details.rowCount() == 0 and self.study_stats.rowCount() == 0 and self.channel_stats.rowCount() == 0:
            QtWidgets.QMessageBox.warning(self, "Внимание", "Сначала сформируйте отчёт.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Сохранить отчёт",
            str(Path.home() / f"Отчет_УЗИ_{datetime.now().strftime('%Y%m%d')}.csv"),
            "CSV файлы (*.csv);;Все файлы (*.*)",
        )
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() != ".csv":
            p = p.with_suffix(".csv")

        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([self.total_label.text()])
            w.writerow([])
            w.writerow(["СТАТИСТИКА ПО ТИПАМ"])
            w.writerow(["Тип исследования", "Кол-во", "%"])
            for r in range(self.study_stats.rowCount()):
                w.writerow([self.study_stats.item(r, 0).text(), self.study_stats.item(r, 1).text(), self.study_stats.item(r, 2).text()])
            w.writerow([])
            w.writerow(["СТАТИСТИКА ПО КАНАЛАМ"])
            w.writerow(["Канал", "Кол-во", "%"])
            for r in range(self.channel_stats.rowCount()):
                w.writerow([self.channel_stats.item(r, 0).text(), self.channel_stats.item(r, 1).text(), self.channel_stats.item(r, 2).text()])
            w.writerow([])
            w.writerow(["ДЕТАЛИЗАЦИЯ (последние 100)"])
            w.writerow(["ID", "ФИО", "ИИН", "Тип исследования", "Канал", "Дата/время", "Врач"])
            for r in range(self.details.rowCount()):
                w.writerow([self.details.item(r, c).text() for c in range(self.details.columnCount())])

        QtWidgets.QMessageBox.information(self, "Успех", f"Отчёт сохранён:\n{p}")

