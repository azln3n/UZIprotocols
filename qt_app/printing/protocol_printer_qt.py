from __future__ import annotations

import calendar
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..db import connect
from ..paths import protocols_dir, protocols_templates_dir
from ..repo import get_study_template_variant, upsert_study_template_variant
from ..ui.protocol_builder_qt import ProtocolBuilderQt


@dataclass(frozen=True)
class TemplateChoice:
    # None => DB template
    file_path: str | None


class ProtocolPrinterQt:
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        self.parent = parent

    def print_current(
        self,
        *,
        patient_id: int,
        study_type_id: int,
        doctor_id: int,
        device_id: int,
        builder: ProtocolBuilderQt,
        study_name: str | None = None,
        protocol_id: int | None = None,
    ) -> bool:
        variant = self._ask_print_options()
        if not variant:
            return False

        choice = self._choose_template(study_type_id, variant)
        if choice is None:
            return False

        template_content = self._resolve_template(study_type_id, variant, choice)
        if not template_content:
            return False

        data = self._prepare_replacement_data_for_current(
            patient_id=patient_id,
            study_type_id=study_type_id,
            doctor_id=doctor_id,
            device_id=device_id,
            builder=builder,
            study_name=study_name,
        )
        # future: variant-specific replacements
        data["@PrintVariant"] = variant

        html = self._replace_template_variables(template_content, data)
        return self._save_and_open_for_print(html, patient_id=patient_id, protocol_id=protocol_id)

    def print_saved(self, *, protocol_id: int) -> bool:
        variant = self._ask_print_options()
        if not variant:
            return False

        meta = self._get_protocol_data_by_id(protocol_id)
        if not meta:
            QtWidgets.QMessageBox.critical(self.parent, "Ошибка", "Протокол не найден.")
            return False

        patient_id = int(meta["patient_id"])
        study_type_id = int(meta["study_type_id"])

        choice = self._choose_template(study_type_id, variant)
        if choice is None:
            return False

        template_content = self._resolve_template(study_type_id, variant, choice)
        if not template_content:
            return False

        data = self._prepare_replacement_data_for_saved_protocol(protocol_id)
        data["@PrintVariant"] = variant
        html = self._replace_template_variables(template_content, data)
        return self._save_and_open_for_print(html, patient_id=patient_id, protocol_id=protocol_id)

    # -------------------- Template selection --------------------

    def _choose_template(self, study_type_id: int, variant: str) -> TemplateChoice | None:
        # If DB has template => use it by default
        if self._has_db_template(study_type_id, variant):
            return TemplateChoice(file_path=None)

        msg = QtWidgets.QMessageBox(self.parent)
        msg.setWindowTitle("Шаблон печати")
        msg.setText("Шаблон для этого исследования не найден в базе.\nВыберите HTML файл шаблона.")
        msg.setIcon(QtWidgets.QMessageBox.Icon.Information)

        pick = msg.addButton("Выбрать файл...", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        cancel = msg.addButton("Отмена", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(pick)
        msg.exec()
        if msg.clickedButton() == cancel:
            return None

        # По просьбе: templates/ и фото лежат в /protocols/templates
        initial_dir = protocols_templates_dir()
        initial_dir.mkdir(parents=True, exist_ok=True)

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.parent,
            "Выберите HTML шаблон для печати",
            str(initial_dir),
            "HTML файлы (*.htm *.html);;Все файлы (*.*)",
        )
        if not file_path:
            return None
        return TemplateChoice(file_path=file_path)

    def _has_db_template(self, study_type_id: int, variant: str) -> bool:
        # New variants table first
        content = get_study_template_variant(study_type_id, variant)
        if content:
            return True
        # Backward-compat: legacy single template is treated as unsigned
        if variant == "unsigned":
            with connect() as conn:
                row = conn.execute(
                    "SELECT template_content FROM study_templates WHERE study_type_id = ?",
                    (study_type_id,),
                ).fetchone()
            return bool(row and row["template_content"])
        return False

    def _get_template_from_db(self, study_type_id: int, variant: str) -> str | None:
        content = get_study_template_variant(study_type_id, variant)
        if content:
            return content
        if variant == "unsigned":
            with connect() as conn:
                row = conn.execute(
                    "SELECT template_content FROM study_templates WHERE study_type_id = ?",
                    (study_type_id,),
                ).fetchone()
            if row and row["template_content"]:
                return str(row["template_content"])
        return None

    def _resolve_template(self, study_type_id: int, variant: str, choice: TemplateChoice) -> str | None:
        if choice.file_path is None:
            content = self._get_template_from_db(study_type_id, variant)
            if not content:
                QtWidgets.QMessageBox.warning(
                    self.parent,
                    "Внимание",
                    "Шаблон для этого исследования не найден в базе данных.\n"
                    "Выберите HTML файл шаблона.",
                )
                return None
            return content

        content = Path(choice.file_path).read_text(encoding="utf-8", errors="replace")

        # Offer to persist into DB to satisfy TЗ (both variants stored)
        reply = QtWidgets.QMessageBox.question(
            self.parent,
            "Сохранить шаблон?",
            f"Сохранить выбранный шаблон в БД для варианта '{variant}'?\n"
            "Так приложение будет работать без отдельных HTML-файлов.",
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            upsert_study_template_variant(
                study_type_id=study_type_id,
                variant=variant,
                template_name=Path(choice.file_path).name,
                template_content=content,
            )
        return content

    # -------------------- Data preparation --------------------

    def _prepare_replacement_data_for_current(
        self,
        *,
        patient_id: int,
        study_type_id: int,
        doctor_id: int,
        device_id: int,
        builder: ProtocolBuilderQt,
        study_name: str | None,
    ) -> dict[str, str]:
        data: dict[str, str] = {}

        with connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT p.full_name, p.iin, p.birth_date, p.gender,
                       i.name as institution, d.full_name as doctor, dev.name as device
                FROM patients p
                LEFT JOIN institutions i ON p.institution_id = i.id
                LEFT JOIN doctors d ON d.id = ?
                LEFT JOIN devices dev ON dev.id = ?
                WHERE p.id = ?
                """,
                (doctor_id, device_id, patient_id),
            )
            row = cur.fetchone()

            if row:
                data["@FIO"] = row["full_name"] or ""
                data["@PoliceNumber"] = row["iin"] or ""
                data["@Birthday"] = row["birth_date"] or ""
                data["@ProtocolPol"] = row["gender"] or ""
                data["@UZ_skaner"] = row["device"] or ""
                data["@Datchik"] = row["device"] or ""

                # Age calc (same idea as Tkinter printer)
                if row["birth_date"]:
                    birth_date = datetime.strptime(str(row["birth_date"]), "%Y-%m-%d")
                    now = datetime.now()
                    years, months, days = self._age_parts(birth_date, now)
                    data["@Vozrast"] = str(years)
                    data["@Months"] = str(months)
                    data["@Days"] = str(days)
                    data["@AgeWord"] = self._decline_years(years)
                else:
                    data["@Vozrast"] = ""
                    data["@Months"] = ""
                    data["@Days"] = ""
                    data["@AgeWord"] = ""

            # Field mapping for this study
            cur.execute(
                """
                SELECT f.id, f.name, f.template_tag
                FROM fields f
                JOIN groups g ON f.group_id = g.id
                JOIN tabs t ON g.tab_id = t.id
                WHERE t.study_type_id = ?
                """,
                (study_type_id,),
            )
            field_mapping = [
                (int(r["id"]), str(r["name"]), str(r["template_tag"]) if r["template_tag"] is not None else None)
                for r in cur.fetchall()
            ]

            values = builder.collect_values()
            for field_id, value in values.items():
                # поддерживаем:
                # - @<НазваниеПоля> (как сейчас)
                # - @<ID> (надёжно, если в названии есть пробелы/знаки)
                # - @<Название_с_подчёркиваниями> (на всякий случай)
                for fid, field_name, template_tag in field_mapping:
                    if int(field_id) != int(fid):
                        continue
                    s = value or ""
                    data[f"@{fid}"] = s
                    data[f"@{field_name}"] = s
                    slug = re.sub(r"\\W+", "_", field_name, flags=re.UNICODE).strip("_")
                    if slug:
                        data[f"@{slug}"] = s
                    if template_tag:
                        data[f"@{template_tag}"] = s
                    break

            now = datetime.now()
            data["@ProtocolDate"] = now.strftime("%d.%m.%Y")
            data["@ProtocolTime"] = now.strftime("%H:%M")

            cur.execute("SELECT full_name FROM doctors WHERE id = ?", (doctor_id,))
            doc_row = cur.fetchone()
            data["@DoctorName"] = (doc_row["full_name"] if doc_row else "") or ""

            if study_name:
                data["@StudyType"] = study_name
            else:
                cur.execute("SELECT name FROM study_types WHERE id = ?", (study_type_id,))
                st_row = cur.fetchone()
                data["@StudyType"] = (st_row["name"] if st_row else "") or ""

        return data

    def _prepare_replacement_data_for_saved_protocol(self, protocol_id: int) -> dict[str, str]:
        with connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    p.full_name, p.iin, p.birth_date, p.gender,
                    i.name as institution, d.full_name as doctor,
                    dev.name as device, st.name as study_type,
                    pr.created_at, pr.finished_at,
                    p.id as patient_id, pr.study_type_id
                FROM protocols pr
                JOIN patients p ON pr.patient_id = p.id
                JOIN institutions i ON pr.institution_id = i.id
                LEFT JOIN doctors d ON pr.doctor_id = d.id
                LEFT JOIN devices dev ON pr.device_id = dev.id
                JOIN study_types st ON pr.study_type_id = st.id
                WHERE pr.id = ?
                """,
                (protocol_id,),
            )
            pr = cur.fetchone()
            if not pr:
                return {}

            data: dict[str, str] = {}
            data["@FIO"] = pr["full_name"] or ""
            data["@PoliceNumber"] = pr["iin"] or ""
            data["@Birthday"] = pr["birth_date"] or ""
            data["@ProtocolPol"] = pr["gender"] or ""
            data["@UZ_skaner"] = pr["device"] or ""
            data["@Datchik"] = pr["device"] or ""
            data["@StudyType"] = pr["study_type"] or ""
            data["@DoctorName"] = pr["doctor"] or ""

            if pr["birth_date"]:
                birth_date = datetime.strptime(str(pr["birth_date"]), "%Y-%m-%d")
                now = datetime.now()
                years, months, days = self._age_parts(birth_date, now)
                data["@Vozrast"] = str(years)
                data["@Months"] = str(months)
                data["@Days"] = str(days)
                data["@AgeWord"] = self._decline_years(years)
            else:
                data["@Vozrast"] = ""
                data["@Months"] = ""
                data["@Days"] = ""
                data["@AgeWord"] = ""

            # Protocol date/time from created_at if possible
            created_at = pr["created_at"]
            if created_at:
                dt = self._parse_sqlite_datetime(str(created_at))
                data["@ProtocolDate"] = dt.strftime("%d.%m.%Y")
                data["@ProtocolTime"] = dt.strftime("%H:%M")
            else:
                now = datetime.now()
                data["@ProtocolDate"] = now.strftime("%d.%m.%Y")
                data["@ProtocolTime"] = now.strftime("%H:%M")

            # field values (поддерживаем name / id / slug / template_tag)
            cur.execute(
                """
                SELECT f.id, f.name, f.template_tag, pv.value
                FROM protocol_values pv
                JOIN fields f ON pv.field_id = f.id
                WHERE pv.protocol_id = ?
                """,
                (protocol_id,),
            )
            for r in cur.fetchall():
                fid = int(r["id"])
                name = str(r["name"] or "").strip()
                tag = str(r["template_tag"]).strip() if r["template_tag"] is not None else ""
                val = r["value"] or ""

                data[f"@{fid}"] = val
                if name:
                    data[f"@{name}"] = val
                    slug = re.sub(r"\\W+", "_", name, flags=re.UNICODE).strip("_")
                    if slug:
                        data[f"@{slug}"] = val
                if tag:
                    data[f"@{tag}"] = val

            return data

    # -------------------- Replace + open --------------------

    def _replace_template_variables(self, template_content: str, replacement_data: dict[str, str]) -> str:
        # По ТЗ: если поле не заполнено — переменная не отображается.
        variable_pattern = r"@(\w+)"

        def repl(m: re.Match) -> str:
            key = m.group(0)
            return replacement_data.get(key, "")

        return re.sub(variable_pattern, repl, template_content)

    def _save_and_open_for_print(self, html_content: str, *, patient_id: int, protocol_id: int | None) -> bool:
        patient_name = self._get_patient_name(patient_id)
        safe_name = re.sub(r'[<>:"/\\\\|?*]', "_", patient_name or "Неизвестный")
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"Протокол_{protocol_id}_{safe_name}_{date_str}" if protocol_id else f"Протокол_{safe_name}_{date_str}"
        root = protocols_dir()
        day_dir = root / datetime.now().strftime("%Y-%m-%d")
        (root / "templates").mkdir(parents=True, exist_ok=True)
        day_dir.mkdir(parents=True, exist_ok=True)
        out_file = day_dir / f"{base}.html"

        html_with_meta = self._normalize_html_for_local_assets(html_content)

        out_file.write_text(html_with_meta, encoding="utf-8")
        webbrowser.open(out_file.as_uri())

        QtWidgets.QMessageBox.information(
            self.parent,
            "Печать",
            "Протокол открыт в браузере.\n\n"
            "Для печати:\n"
            "1) Нажмите Ctrl+P\n"
            "2) Выберите принтер\n"
            "3) Нажмите «Печать»\n\n"
            "Файл сохранён:\n"
            f"{out_file}\n\n"
            "Шаблоны/фото держите в папке:\n"
            f"{(protocols_dir() / 'templates')}",
        )
        return True

    def _normalize_html_for_local_assets(self, html_content: str) -> str:
        """
        Гарантируем:
        - meta charset
        - base href на папку /protocols/templates/, чтобы относительные ссылки на фото/стили
          (например `header.jpg`) работали даже если сам HTML лежит в /protocols/<date>/...
        """
        html = html_content
        lower = html.lower()

        if "<meta charset" not in lower:
            html = html.replace(
                "<head>",
                "<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
            )
            lower = html.lower()

        if "<base " not in lower:
            # По просьбе: фото/шаблоны лежат в /protocols/templates
            href = protocols_templates_dir().resolve().as_uri()
            if not href.endswith("/"):
                href += "/"
            html = html.replace("<head>", f"<head>\n    <base href=\"{href}\">", 1)

        # Пользователь может писать в шаблоне и так:
        #   <img src="header.jpg">
        # и так:
        #   <img src="templates/header.jpg">
        # При base=/protocols/templates второй вариант станет /protocols/templates/templates/...
        # Исправляем наиболее частые случаи.
        html = re.sub(r'(\b(?:src|href)\s*=\s*["\'])(?:\./)?templates/', r"\1", html, flags=re.IGNORECASE)

        return html

    def _ask_print_options(self) -> str | None:
        dlg = QtWidgets.QDialog(self.parent)
        dlg.setWindowTitle("Печать протокола")
        dlg.setModal(True)

        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(QtWidgets.QLabel("Выберите вариант:"))

        variant_group = QtWidgets.QGroupBox("Вариант")
        vg = QtWidgets.QVBoxLayout(variant_group)
        rb_signed = QtWidgets.QRadioButton("С подписью")
        rb_unsigned = QtWidgets.QRadioButton("Без подписи")
        rb_unsigned.setChecked(True)
        vg.addWidget(rb_unsigned)
        vg.addWidget(rb_signed)
        layout.addWidget(variant_group)

        note = QtWidgets.QLabel("Формат: HTML (откроется в браузере). Печать: Ctrl+P.")
        note.setStyleSheet("color: #333;")
        layout.addWidget(note)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        ok = QtWidgets.QPushButton("OK")
        cancel = QtWidgets.QPushButton("Отмена")
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None

        return "signed" if rb_signed.isChecked() else "unsigned"

    # -------------------- Helpers --------------------

    def _get_patient_name(self, patient_id: int) -> str:
        with connect() as conn:
            row = conn.execute("SELECT full_name FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return str(row["full_name"]) if row and row["full_name"] else "Неизвестный"

    def _get_protocol_data_by_id(self, protocol_id: int) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT p.id as patient_id, pr.study_type_id
                FROM protocols pr
                JOIN patients p ON pr.patient_id = p.id
                WHERE pr.id = ?
                """,
                (protocol_id,),
            ).fetchone()
        if not row:
            return None
        return {"patient_id": int(row["patient_id"]), "study_type_id": int(row["study_type_id"])}

    def _parse_sqlite_datetime(self, s: str) -> datetime:
        s = s.strip()
        if "." in s:
            s = s.split(".", 1)[0]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return datetime.now()

    def _age_parts(self, birth_date: datetime, now: datetime) -> tuple[int, int, int]:
        years = now.year - birth_date.year
        months = now.month - birth_date.month
        days = now.day - birth_date.day

        if days < 0:
            months -= 1
            if now.month == 1:
                prev_month = 12
                prev_year = now.year - 1
            else:
                prev_month = now.month - 1
                prev_year = now.year
            days_in_prev_month = calendar.monthrange(prev_year, prev_month)[1]
            days = days_in_prev_month + days

        if months < 0:
            years -= 1
            months = 12 + months
        return years, months, days

    def _decline_years(self, years: int) -> str:
        if years % 10 == 1 and years % 100 != 11:
            return "год"
        if 2 <= years % 10 <= 4 and (years % 100 < 10 or years % 100 >= 20):
            return "года"
        return "лет"

