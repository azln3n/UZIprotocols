from __future__ import annotations

from dataclasses import dataclass
import re

from .db import connect


@dataclass(frozen=True)
class ComboItem:
    id: int
    name: str


@dataclass(frozen=True)
class PatientListItem:
    id: int
    full_name: str
    iin: str | None
    has_protocols: bool


@dataclass(frozen=True)
class ProtocolListItem:
    id: int
    created_at: str
    finished_at: str | None
    study_name: str
    study_type_id: int
    is_signed: bool


def list_institutions() -> list[ComboItem]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name FROM institutions WHERE is_active = 1 ORDER BY name"
        ).fetchall()
    return [ComboItem(int(r["id"]), str(r["name"])) for r in rows]


def list_doctors(institution_id: int) -> list[ComboItem]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, full_name AS name
            FROM doctors
            WHERE institution_id = ? AND is_active = 1
            ORDER BY full_name
            """,
            (institution_id,),
        ).fetchall()
    return [ComboItem(int(r["id"]), str(r["name"])) for r in rows]


def list_devices(institution_id: int) -> list[ComboItem]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name
            FROM devices
            WHERE institution_id = ? AND is_active = 1
            ORDER BY name
            """,
            (institution_id,),
        ).fetchall()
    return [ComboItem(int(r["id"]), str(r["name"])) for r in rows]


def list_admission_channels() -> list[ComboItem]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name FROM admission_channels WHERE is_active = 1 ORDER BY name"
        ).fetchall()
    return [ComboItem(int(r["id"]), str(r["name"])) for r in rows]


def get_patient(patient_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              id, full_name, iin, birth_date, gender, admission_channel_id, institution_id
            FROM patients
            WHERE id = ?
            """,
            (patient_id,),
        ).fetchone()
    if not row:
        return None
    return {k: row[k] for k in row.keys()}


def upsert_patient(
    *,
    patient_id: int | None,
    institution_id: int,
    full_name: str,
    iin: str | None,
    birth_date_iso: str,
    gender: str,
    admission_channel_id: int | None,
) -> int:
    """
    gender: 'муж' | 'жен'
    birth_date_iso: YYYY-MM-DD
    """
    with connect() as conn:
        cur = conn.cursor()
        if patient_id:
            cur.execute(
                """
                UPDATE patients SET
                  full_name = ?,
                  iin = ?,
                  birth_date = ?,
                  gender = ?,
                  admission_channel_id = ?,
                  institution_id = ?
                WHERE id = ?
                """,
                (
                    full_name,
                    iin,
                    birth_date_iso,
                    gender,
                    admission_channel_id,
                    institution_id,
                    patient_id,
                ),
            )
            conn.commit()
            return int(patient_id)

        cur.execute(
            """
            INSERT INTO patients
              (full_name, iin, birth_date, gender, admission_channel_id, institution_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                full_name,
                iin,
                birth_date_iso,
                gender,
                admission_channel_id,
                institution_id,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_patients_for_institution(institution_id: int, limit: int = 50) -> list[PatientListItem]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              p.id,
              p.full_name,
              p.iin,
              CASE WHEN COUNT(pr.id) > 0 THEN 1 ELSE 0 END AS has_protocols
            FROM patients p
            LEFT JOIN protocols pr ON p.id = pr.patient_id
            WHERE p.institution_id = ?
            GROUP BY p.id
            ORDER BY p.created_at DESC
            LIMIT ?
            """,
            (institution_id, limit),
        ).fetchall()
    return [
        PatientListItem(
            id=int(r["id"]),
            full_name=str(r["full_name"]),
            iin=str(r["iin"]) if r["iin"] is not None else None,
            has_protocols=bool(r["has_protocols"]),
        )
        for r in rows
    ]


def search_patient_ids(institution_id: int, query: str) -> list[int]:
    """
    Поиск по ФИО/ИИН без зависимости от регистра (по ТЗ).
    SQLite NOCASE плохо работает с кириллицей, поэтому делаем casefold в Python.
    """
    q = (query or "").strip()
    if not q:
        return []
    q = q.casefold()
    # for search we scan more than 50
    items = list_patients_for_institution(institution_id, limit=5000)
    out: list[int] = []
    for p in items:
        if q in (p.full_name or "").casefold():
            out.append(p.id)
            continue
        if p.iin and q in p.iin.casefold():
            out.append(p.id)
            continue
    return out


def search_patient_ids_by_fields(*, institution_id: int, fio: str = "", iin: str = "") -> list[int]:
    """
    Поиск по всем пациентам (включая тех, у кого нет протоколов).
    Если заполнены оба поля (ФИО и ИИН) — применяем оба фильтра (AND).
    """
    fio_q = (fio or "").strip().casefold()
    iin_q = re.sub(r"\D", "", (iin or "").strip())

    if not fio_q and not iin_q:
        return []

    items = list_patients_for_institution(int(institution_id), limit=5000)
    out: list[int] = []
    for p in items:
        name_ok = True
        iin_ok = True
        if fio_q:
            name_ok = fio_q in (p.full_name or "").casefold()
        if iin_q:
            iin_ok = bool(p.iin) and iin_q in str(p.iin)
        if name_ok and iin_ok:
            out.append(int(p.id))
    return out


def search_protocol_patient_ids(
    *,
    institution_id: int,
    fio: str = "",
    iin: str = "",
    date_from: str | None = None,  # YYYY-MM-DD
    date_to: str | None = None,  # YYYY-MM-DD
    study_type_id: int | None = None,
) -> list[int]:
    """
    Поиск по протоколам (по ТЗ для окна "Поиск"): ФИО/ИИН + период + тип исследования.
    Возвращает список patient_id, удовлетворяющих фильтрам.
    """
    fio = (fio or "").strip()
    iin = (iin or "").strip()
    if not fio and not iin and not date_from and not date_to and not study_type_id:
        return []

    params: list[object] = [int(institution_id)]
    conditions = ["p.institution_id = ?"]

    if fio:
        # case-insensitive for кириллицы — сделаем фильтр в Python после SQL
        pass
    if iin:
        conditions.append("p.iin LIKE ?")
        params.append(f"%{iin}%")
    if study_type_id:
        conditions.append("pr.study_type_id = ?")
        params.append(int(study_type_id))
    if date_from:
        conditions.append("date(pr.created_at) >= date(?)")
        params.append(date_from)
    if date_to:
        conditions.append("date(pr.created_at) <= date(?)")
        params.append(date_to)

    where = " AND ".join(conditions)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT p.id, p.full_name
            FROM protocols pr
            JOIN patients p ON pr.patient_id = p.id
            WHERE {where}
            ORDER BY p.created_at DESC
            """,
            params,
        ).fetchall()

    if not fio:
        return [int(r["id"]) for r in rows]
    q = fio.casefold()
    out: list[int] = []
    for r in rows:
        if q in (str(r["full_name"] or "")).casefold():
            out.append(int(r["id"]))
    return out


def list_protocols_for_patient(patient_id: int) -> list[ProtocolListItem]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              pr.id,
              pr.created_at,
              pr.finished_at,
              st.name AS study_name,
              pr.study_type_id,
              pr.is_signed
            FROM protocols pr
            JOIN study_types st ON st.id = pr.study_type_id
            WHERE pr.patient_id = ?
            ORDER BY pr.created_at DESC
            """,
            (patient_id,),
        ).fetchall()
    return [
        ProtocolListItem(
            id=int(r["id"]),
            created_at=str(r["created_at"]),
            finished_at=str(r["finished_at"]) if r["finished_at"] is not None else None,
            study_name=str(r["study_name"]),
            study_type_id=int(r["study_type_id"]),
            is_signed=bool(r["is_signed"]),
        )
        for r in rows
    ]


def delete_protocol(protocol_id: int) -> None:
    """
    Каскадное удаление протокола: сначала значения, затем сам протокол.
    """
    with connect() as conn:
        cur = conn.cursor()
        pid = int(protocol_id)
        cur.execute("DELETE FROM protocol_values WHERE protocol_id = ?", (pid,))
        cur.execute("DELETE FROM protocols WHERE id = ?", (pid,))
        conn.commit()


def get_protocol_meta(protocol_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              pr.id,
              pr.patient_id,
              pr.study_type_id,
              pr.created_at,
              pr.finished_at,
              pr.is_signed
            FROM protocols pr
            WHERE pr.id = ?
            """,
            (protocol_id,),
        ).fetchone()
    if not row:
        return None
    return {k: row[k] for k in row.keys()}


def upsert_study_template_variant(
    *,
    study_type_id: int,
    variant: str,  # 'signed'|'unsigned'
    template_name: str | None,
    template_content: str,
) -> None:
    if variant not in ("signed", "unsigned"):
        raise ValueError("variant must be 'signed' or 'unsigned'")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO study_template_variants (study_type_id, variant, template_name, template_content)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(study_type_id, variant) DO UPDATE SET
              template_name = excluded.template_name,
              template_content = excluded.template_content,
              created_at = CURRENT_TIMESTAMP
            """,
            (study_type_id, variant, template_name, template_content),
        )
        conn.commit()


def get_study_template_variant(study_type_id: int, variant: str) -> str | None:
    if variant not in ("signed", "unsigned"):
        raise ValueError("variant must be 'signed' or 'unsigned'")
    with connect() as conn:
        row = conn.execute(
            """
            SELECT template_content
            FROM study_template_variants
            WHERE study_type_id = ? AND variant = ?
            """,
            (study_type_id, variant),
        ).fetchone()
    if row and row["template_content"]:
        return str(row["template_content"])
    return None


def delete_patient(patient_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        pid = int(patient_id)
        count = cur.execute("SELECT COUNT(*) AS cnt FROM protocols WHERE patient_id = ?", (pid,)).fetchone()
        if count and int(count["cnt"]) > 0:
            raise ValueError("У пациента есть протоколы. Сначала удалите протоколы, затем пациента.")
        cur.execute("DELETE FROM patients WHERE id = ?", (pid,))
        conn.commit()


def get_patient_brief(patient_id: int) -> tuple[str, str] | None:
    """Returns (full_name, gender) where gender is 'муж'|'жен'."""
    with connect() as conn:
        row = conn.execute(
            "SELECT full_name, gender FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
    if not row:
        return None
    return str(row["full_name"]), str(row["gender"])


def list_study_types() -> list[ComboItem]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name FROM study_types WHERE is_active = 1 ORDER BY name"
        ).fetchall()
    return [ComboItem(int(r["id"]), str(r["name"])) for r in rows]


@dataclass(frozen=True)
class StudyTypeRow:
    id: int
    name: str
    display_order: int
    is_active: bool


@dataclass(frozen=True)
class TabRow:
    id: int
    study_type_id: int
    name: str
    display_order: int


@dataclass(frozen=True)
class GroupRow:
    id: int
    tab_id: int
    name: str
    display_order: int
    is_expanded_by_default: bool


@dataclass(frozen=True)
class FieldRow:
    id: int
    group_id: int
    name: str
    template_tag: str | None
    field_type: str
    column_num: int
    display_order: int
    precision: int | None
    reference_male_min: float | None
    reference_male_max: float | None
    reference_female_min: float | None
    reference_female_max: float | None
    formula: str | None
    is_required: bool
    height: int
    width: int
    is_hidden: bool
    hidden_trigger_field_id: int | None
    hidden_trigger_value: str | None


@dataclass(frozen=True)
class DictionaryValueRow:
    id: int
    field_id: int
    value: str
    display_order: int


def list_study_types_all() -> list[StudyTypeRow]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, display_order, is_active FROM study_types ORDER BY display_order, name"
        ).fetchall()
    return [
        StudyTypeRow(
            id=int(r["id"]),
            name=str(r["name"]),
            display_order=int(r["display_order"] or 0),
            is_active=bool(r["is_active"]),
        )
        for r in rows
    ]


def create_study_type(name: str, *, is_active: bool = True) -> int:
    with connect() as conn:
        cur = conn.cursor()
        max_order = cur.execute("SELECT COALESCE(MAX(display_order), 0) FROM study_types").fetchone()[0]
        cur.execute(
            "INSERT INTO study_types (name, display_order, is_active) VALUES (?, ?, ?)",
            (name, int(max_order) + 1, 1 if is_active else 0),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_study_type(study_type_id: int, *, name: str, is_active: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE study_types SET name = ?, is_active = ? WHERE id = ?",
            (name, 1 if is_active else 0, int(study_type_id)),
        )
        conn.commit()


def delete_study_type(study_type_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        st_id = int(study_type_id)

        tabs_cnt = cur.execute(
            "SELECT COUNT(*) AS cnt FROM tabs WHERE study_type_id = ?",
            (st_id,),
        ).fetchone()
        if tabs_cnt and int(tabs_cnt["cnt"]) > 0:
            raise ValueError("Нельзя удалить протокол: сначала удалите вкладки.")

        groups_cnt = cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM groups g
            JOIN tabs t ON t.id = g.tab_id
            WHERE t.study_type_id = ?
            """,
            (st_id,),
        ).fetchone()
        if groups_cnt and int(groups_cnt["cnt"]) > 0:
            raise ValueError("Нельзя удалить протокол: сначала удалите группы.")

        fields_cnt = cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM fields f
            JOIN groups g ON g.id = f.group_id
            JOIN tabs t ON t.id = g.tab_id
            WHERE t.study_type_id = ?
            """,
            (st_id,),
        ).fetchone()
        if fields_cnt and int(fields_cnt["cnt"]) > 0:
            raise ValueError("Нельзя удалить протокол: сначала удалите поля.")

        # Чтобы не оставлять "битые" ссылки — удаляем также протоколы этого типа и их значения.
        prot_ids = [
            int(r["id"])
            for r in cur.execute("SELECT id FROM protocols WHERE study_type_id = ?", (st_id,)).fetchall()
        ]
        for pid in prot_ids:
            cur.execute("DELETE FROM protocol_values WHERE protocol_id = ?", (int(pid),))
        cur.execute("DELETE FROM protocols WHERE study_type_id = ?", (st_id,))

        # Шаблоны печати (новая и legacy таблица)
        cur.execute("DELETE FROM study_template_variants WHERE study_type_id = ?", (st_id,))
        # legacy table may exist; ignore if not
        try:
            cur.execute("DELETE FROM study_templates WHERE study_type_id = ?", (st_id,))
        except Exception:
            pass

        # Структура: вкладки -> группы -> поля -> значения
        cur.execute(
            """
            DELETE FROM dictionary_values
            WHERE field_id IN (
              SELECT f.id
              FROM fields f
              JOIN groups g ON g.id = f.group_id
              JOIN tabs t ON t.id = g.tab_id
              WHERE t.study_type_id = ?
            )
            """,
            (st_id,),
        )
        cur.execute(
            """
            DELETE FROM protocol_values
            WHERE field_id IN (
              SELECT f.id
              FROM fields f
              JOIN groups g ON g.id = f.group_id
              JOIN tabs t ON t.id = g.tab_id
              WHERE t.study_type_id = ?
            )
            """,
            (st_id,),
        )
        cur.execute(
            """
            DELETE FROM fields
            WHERE group_id IN (
              SELECT g.id
              FROM groups g
              JOIN tabs t ON t.id = g.tab_id
              WHERE t.study_type_id = ?
            )
            """,
            (st_id,),
        )
        cur.execute(
            "DELETE FROM groups WHERE tab_id IN (SELECT id FROM tabs WHERE study_type_id = ?)",
            (st_id,),
        )
        cur.execute("DELETE FROM tabs WHERE study_type_id = ?", (st_id,))
        cur.execute("DELETE FROM study_types WHERE id = ?", (st_id,))
        conn.commit()


def move_study_type(study_type_id: int, direction: int) -> None:
    """direction: -1 up, +1 down"""
    with connect() as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, display_order FROM study_types ORDER BY display_order, id"
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if int(study_type_id) not in ids:
            return
        i = ids.index(int(study_type_id))
        j = i + direction
        if j < 0 or j >= len(ids):
            return
        a_id, b_id = ids[i], ids[j]
        a_order = int(rows[i]["display_order"] or 0)
        b_order = int(rows[j]["display_order"] or 0)
        cur.execute("UPDATE study_types SET display_order = ? WHERE id = ?", (b_order, a_id))
        cur.execute("UPDATE study_types SET display_order = ? WHERE id = ?", (a_order, b_id))
        conn.commit()


def list_tabs(study_type_id: int) -> list[TabRow]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, study_type_id, name, display_order FROM tabs WHERE study_type_id = ? ORDER BY display_order, id",
            (int(study_type_id),),
        ).fetchall()
    return [
        TabRow(
            id=int(r["id"]),
            study_type_id=int(r["study_type_id"]),
            name=str(r["name"]),
            display_order=int(r["display_order"] or 0),
        )
        for r in rows
    ]


def create_tab(study_type_id: int, name: str) -> int:
    with connect() as conn:
        cur = conn.cursor()
        max_order = cur.execute(
            "SELECT COALESCE(MAX(display_order), 0) FROM tabs WHERE study_type_id = ?",
            (int(study_type_id),),
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO tabs (study_type_id, name, display_order) VALUES (?, ?, ?)",
            (int(study_type_id), name, int(max_order) + 1),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_tab(tab_id: int, *, name: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE tabs SET name = ? WHERE id = ?", (name, int(tab_id)))
        conn.commit()


def delete_tab(tab_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cnt = cur.execute("SELECT COUNT(*) FROM groups WHERE tab_id = ?", (int(tab_id),)).fetchone()[0]
        if int(cnt) > 0:
            raise ValueError("Нельзя удалить вкладку: сначала удалите группы/поля.")
        cur.execute("DELETE FROM tabs WHERE id = ?", (int(tab_id),))
        conn.commit()


def move_tab(tab_id: int, direction: int) -> None:
    """direction: -1 left, +1 right (по display_order)."""
    with connect() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT study_type_id FROM tabs WHERE id = ?", (int(tab_id),)).fetchone()
        if not row:
            return
        st_id = int(row["study_type_id"])
        rows = cur.execute(
            "SELECT id, display_order FROM tabs WHERE study_type_id = ? ORDER BY display_order, id",
            (st_id,),
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if int(tab_id) not in ids:
            return
        i = ids.index(int(tab_id))
        j = i + direction
        if j < 0 or j >= len(ids):
            return
        a_id, b_id = ids[i], ids[j]
        a_order = int(rows[i]["display_order"] or 0)
        b_order = int(rows[j]["display_order"] or 0)
        cur.execute("UPDATE tabs SET display_order = ? WHERE id = ?", (b_order, a_id))
        cur.execute("UPDATE tabs SET display_order = ? WHERE id = ?", (a_order, b_id))
        conn.commit()


def list_groups(tab_id: int) -> list[GroupRow]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, tab_id, name, display_order, is_expanded_by_default
            FROM groups
            WHERE tab_id = ?
            ORDER BY display_order, id
            """,
            (int(tab_id),),
        ).fetchall()
    return [
        GroupRow(
            id=int(r["id"]),
            tab_id=int(r["tab_id"]),
            name=str(r["name"]),
            display_order=int(r["display_order"] or 0),
            is_expanded_by_default=bool(r["is_expanded_by_default"]),
        )
        for r in rows
    ]


def create_group(tab_id: int, name: str, *, is_expanded_by_default: bool = False) -> int:
    with connect() as conn:
        cur = conn.cursor()
        max_order = cur.execute(
            "SELECT COALESCE(MAX(display_order), 0) FROM groups WHERE tab_id = ?",
            (int(tab_id),),
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO groups (tab_id, name, display_order, is_expanded_by_default) VALUES (?, ?, ?, ?)",
            (int(tab_id), name, int(max_order) + 1, 1 if is_expanded_by_default else 0),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_group(group_id: int, *, name: str, is_expanded_by_default: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE groups SET name = ?, is_expanded_by_default = ? WHERE id = ?",
            (name, 1 if is_expanded_by_default else 0, int(group_id)),
        )
        conn.commit()


def delete_group(group_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cnt = cur.execute("SELECT COUNT(*) FROM fields WHERE group_id = ?", (int(group_id),)).fetchone()[0]
        if int(cnt) > 0:
            raise ValueError("Нельзя удалить группу: сначала удалите поля данной группы.")
        cur.execute("DELETE FROM groups WHERE id = ?", (int(group_id),))
        conn.commit()


def move_group(group_id: int, direction: int) -> None:
    """direction: -1 up, +1 down (within tab)."""
    with connect() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT tab_id FROM groups WHERE id = ?", (int(group_id),)).fetchone()
        if not row:
            return
        tab_id = int(row["tab_id"])
        rows = cur.execute(
            "SELECT id, display_order FROM groups WHERE tab_id = ? ORDER BY display_order, id",
            (tab_id,),
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if int(group_id) not in ids:
            return
        i = ids.index(int(group_id))
        j = i + direction
        if j < 0 or j >= len(ids):
            return
        a_id, b_id = ids[i], ids[j]
        a_order = int(rows[i]["display_order"] or 0)
        b_order = int(rows[j]["display_order"] or 0)
        cur.execute("UPDATE groups SET display_order = ? WHERE id = ?", (b_order, a_id))
        cur.execute("UPDATE groups SET display_order = ? WHERE id = ?", (a_order, b_id))
        conn.commit()


def list_fields(group_id: int) -> list[FieldRow]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              id, group_id, name, template_tag, field_type, column_num, display_order,
              precision, reference_male_min, reference_male_max,
              reference_female_min, reference_female_max, formula,
              is_required, height, width, is_hidden,
              hidden_trigger_field_id, hidden_trigger_value
            FROM fields
            WHERE group_id = ?
            ORDER BY column_num, display_order, id
            """,
            (int(group_id),),
        ).fetchall()
    return [
        FieldRow(
            id=int(r["id"]),
            group_id=int(r["group_id"]),
            name=str(r["name"]),
            template_tag=str(r["template_tag"]) if r["template_tag"] is not None else None,
            field_type=str(r["field_type"]),
            column_num=int(r["column_num"] or 1),
            display_order=int(r["display_order"] or 0),
            precision=int(r["precision"]) if r["precision"] is not None else None,
            reference_male_min=float(r["reference_male_min"]) if r["reference_male_min"] is not None else None,
            reference_male_max=float(r["reference_male_max"]) if r["reference_male_max"] is not None else None,
            reference_female_min=float(r["reference_female_min"]) if r["reference_female_min"] is not None else None,
            reference_female_max=float(r["reference_female_max"]) if r["reference_female_max"] is not None else None,
            formula=str(r["formula"]) if r["formula"] is not None else None,
            is_required=bool(r["is_required"]),
            height=int(r["height"] or 1),
            width=int(r["width"] or 20),
            is_hidden=bool(r["is_hidden"]),
            hidden_trigger_field_id=int(r["hidden_trigger_field_id"]) if r["hidden_trigger_field_id"] is not None else None,
            hidden_trigger_value=str(r["hidden_trigger_value"]) if r["hidden_trigger_value"] is not None else None,
        )
        for r in rows
    ]


def create_field(
    *,
    group_id: int,
    name: str,
    template_tag: str | None = None,
    field_type: str,
    column_num: int = 1,
    precision: int | None = None,
    reference_male_min: float | None = None,
    reference_male_max: float | None = None,
    reference_female_min: float | None = None,
    reference_female_max: float | None = None,
    formula: str | None = None,
    is_required: bool = False,
    height: int = 1,
    width: int = 20,
    is_hidden: bool = False,
    hidden_trigger_field_id: int | None = None,
    hidden_trigger_value: str | None = None,
) -> int:
    with connect() as conn:
        cur = conn.cursor()
        max_order = cur.execute(
            "SELECT COALESCE(MAX(display_order), 0) FROM fields WHERE group_id = ? AND column_num = ?",
            (int(group_id), int(column_num)),
        ).fetchone()[0]
        cur.execute(
            """
            INSERT INTO fields (
              group_id, name, template_tag, field_type, column_num, display_order,
              precision, reference_male_min, reference_male_max,
              reference_female_min, reference_female_max, formula,
              is_required, height, width, is_hidden,
              hidden_trigger_field_id, hidden_trigger_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(group_id),
                name,
                template_tag,
                field_type,
                int(column_num),
                int(max_order) + 1,
                precision,
                reference_male_min,
                reference_male_max,
                reference_female_min,
                reference_female_max,
                formula,
                1 if is_required else 0,
                int(height),
                int(width),
                1 if is_hidden else 0,
                hidden_trigger_field_id,
                hidden_trigger_value,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_field(
    field_id: int,
    *,
    name: str,
    template_tag: str | None,
    field_type: str,
    column_num: int,
    precision: int | None,
    reference_male_min: float | None,
    reference_male_max: float | None,
    reference_female_min: float | None,
    reference_female_max: float | None,
    formula: str | None,
    is_required: bool,
    height: int,
    width: int,
    is_hidden: bool,
    hidden_trigger_field_id: int | None,
    hidden_trigger_value: str | None,
) -> None:
    with connect() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT group_id, column_num, display_order FROM fields WHERE id = ?",
            (int(field_id),),
        ).fetchone()
        if row:
            group_id = int(row["group_id"])
            current_col = int(row["column_num"] or 1)
            current_order = int(row["display_order"] or 0)
        else:
            group_id = None
            current_col = int(column_num)
            current_order = 0

        new_order = current_order
        if group_id is not None and int(column_num) != current_col:
            max_order = cur.execute(
                "SELECT COALESCE(MAX(display_order), 0) FROM fields WHERE group_id = ? AND column_num = ?",
                (group_id, int(column_num)),
            ).fetchone()[0]
            new_order = int(max_order) + 1

        conn.execute(
            """
            UPDATE fields SET
              name = ?,
              template_tag = ?,
              field_type = ?,
              column_num = ?,
              display_order = ?,
              precision = ?,
              reference_male_min = ?,
              reference_male_max = ?,
              reference_female_min = ?,
              reference_female_max = ?,
              formula = ?,
              is_required = ?,
              height = ?,
              width = ?,
              is_hidden = ?,
              hidden_trigger_field_id = ?,
              hidden_trigger_value = ?
            WHERE id = ?
            """,
            (
                name,
                template_tag,
                field_type,
                int(column_num),
                int(new_order),
                precision,
                reference_male_min,
                reference_male_max,
                reference_female_min,
                reference_female_max,
                formula,
                1 if is_required else 0,
                int(height),
                int(width),
                1 if is_hidden else 0,
                hidden_trigger_field_id,
                hidden_trigger_value,
                int(field_id),
            ),
        )
        conn.commit()


def delete_field(field_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM dictionary_values WHERE field_id = ?", (int(field_id),))
        conn.execute("DELETE FROM protocol_values WHERE field_id = ?", (int(field_id),))
        conn.execute("DELETE FROM fields WHERE id = ?", (int(field_id),))
        conn.commit()


def move_field(field_id: int, direction: int) -> None:
    """direction -1 up, +1 down within same group & column."""
    with connect() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT group_id, column_num FROM fields WHERE id = ?", (int(field_id),)).fetchone()
        if not row:
            return
        group_id = int(row["group_id"])
        col = int(row["column_num"] or 1)
        rows = cur.execute(
            """
            SELECT id, display_order
            FROM fields
            WHERE group_id = ? AND column_num = ?
            ORDER BY display_order, id
            """,
            (group_id, col),
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if int(field_id) not in ids:
            return
        i = ids.index(int(field_id))
        j = i + direction
        if j < 0 or j >= len(ids):
            return
        a_id, b_id = ids[i], ids[j]
        a_order = int(rows[i]["display_order"] or 0)
        b_order = int(rows[j]["display_order"] or 0)
        cur.execute("UPDATE fields SET display_order = ? WHERE id = ?", (b_order, a_id))
        cur.execute("UPDATE fields SET display_order = ? WHERE id = ?", (a_order, b_id))
        conn.commit()


def list_dictionary_values(field_id: int) -> list[DictionaryValueRow]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, field_id, value, display_order FROM dictionary_values WHERE field_id = ? ORDER BY display_order, id",
            (int(field_id),),
        ).fetchall()
    return [
        DictionaryValueRow(
            id=int(r["id"]),
            field_id=int(r["field_id"]),
            value=str(r["value"]),
            display_order=int(r["display_order"] or 0),
        )
        for r in rows
    ]


def create_dictionary_value(field_id: int, value: str) -> int:
    with connect() as conn:
        cur = conn.cursor()
        max_order = cur.execute(
            "SELECT COALESCE(MAX(display_order), 0) FROM dictionary_values WHERE field_id = ?",
            (int(field_id),),
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO dictionary_values (field_id, value, display_order) VALUES (?, ?, ?)",
            (int(field_id), value, int(max_order) + 1),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_dictionary_value(value_id: int, value: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE dictionary_values SET value = ? WHERE id = ?", (value, int(value_id)))
        conn.commit()


def delete_dictionary_value(value_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM dictionary_values WHERE id = ?", (int(value_id),))
        conn.commit()


def move_dictionary_value(value_id: int, direction: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT field_id FROM dictionary_values WHERE id = ?", (int(value_id),)).fetchone()
        if not row:
            return
        field_id = int(row["field_id"])
        rows = cur.execute(
            "SELECT id, display_order FROM dictionary_values WHERE field_id = ? ORDER BY display_order, id",
            (field_id,),
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if int(value_id) not in ids:
            return
        i = ids.index(int(value_id))
        j = i + direction
        if j < 0 or j >= len(ids):
            return
        a_id, b_id = ids[i], ids[j]
        a_order = int(rows[i]["display_order"] or 0)
        b_order = int(rows[j]["display_order"] or 0)
        cur.execute("UPDATE dictionary_values SET display_order = ? WHERE id = ?", (b_order, a_id))
        cur.execute("UPDATE dictionary_values SET display_order = ? WHERE id = ?", (a_order, b_id))
        conn.commit()


def get_protocol_draft_id(patient_id: int, study_type_id: int) -> int | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id FROM protocols
            WHERE patient_id = ? AND study_type_id = ? AND finished_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (patient_id, study_type_id),
        ).fetchone()
    return int(row["id"]) if row else None


def load_protocol_values(protocol_id: int) -> dict[int, str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT field_id, value FROM protocol_values WHERE protocol_id = ?",
            (protocol_id,),
        ).fetchall()
    out: dict[int, str] = {}
    for r in rows:
        if r["value"] is None:
            continue
        out[int(r["field_id"])] = str(r["value"])
    return out


def save_protocol(
    *,
    protocol_id: int | None,
    patient_id: int,
    study_type_id: int,
    doctor_id: int,
    device_id: int | None,
    institution_id: int,
    values: dict[int, str],
    finalize: bool = False,
) -> int:
    """
    По ТЗ:
    - "Сохранить" сохраняет значения незаконченных протоколов (finished_at = NULL)
    - "Печать" также сохраняет (как "Сохранить") и открывает меню печати.
    Завершение/подпись будет отдельным действием.
    """
    from datetime import datetime  # noqa: PLC0415

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    with connect() as conn:
        cur = conn.cursor()
        if protocol_id:
            if finalize:
                cur.execute(
                    "UPDATE protocols SET finished_at = ? WHERE id = ?",
                    (now, protocol_id),
                )
            pid = protocol_id
        else:
            cur.execute(
                """
                INSERT INTO protocols
                  (patient_id, study_type_id, doctor_id, device_id, institution_id, created_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    study_type_id,
                    doctor_id,
                    device_id,
                    institution_id,
                    now,
                    now if finalize else None,
                ),
            )
            pid = int(cur.lastrowid)

        for field_id, value in values.items():
            if value is None:
                continue
            v = str(value)
            if not v.strip():
                continue
            cur.execute(
                """
                INSERT OR REPLACE INTO protocol_values (protocol_id, field_id, value)
                VALUES (?, ?, ?)
                """,
                (pid, int(field_id), v),
            )

        conn.commit()
        return int(pid)


def finalize_protocol(protocol_id: int) -> None:
    """
    Помечает протокол завершённым (finished_at = now).
    Нужно, чтобы можно было начать новый протокол того же исследования у пациента.
    """
    from datetime import datetime  # noqa: PLC0415

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    with connect() as conn:
        conn.execute("UPDATE protocols SET finished_at = ? WHERE id = ?", (now, int(protocol_id)))
        conn.commit()


def finalize_open_protocols(*, patient_id: int, study_type_id: int) -> int:
    """
    Закрывает ВСЕ незавершённые протоколы (finished_at IS NULL) для пациента/типа исследования.
    Возвращает количество закрытых протоколов.
    """
    from datetime import datetime  # noqa: PLC0415

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE protocols
            SET finished_at = ?
            WHERE patient_id = ? AND study_type_id = ? AND finished_at IS NULL
            """,
            (now, int(patient_id), int(study_type_id)),
        )
        conn.commit()
        return int(cur.rowcount or 0)
