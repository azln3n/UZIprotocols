from __future__ import annotations

import sqlite3


def run_migrations(conn: sqlite3.Connection) -> None:
    """
    Лёгкие миграции SQLite для Qt-ветки, не ломая Tkinter-ветку.
    """
    _create_study_template_variants(conn)
    _migrate_legacy_study_templates(conn)
    _add_fields_template_tag(conn)


def _create_study_template_variants(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS study_template_variants (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          study_type_id INTEGER NOT NULL,
          variant TEXT NOT NULL CHECK(variant IN ('signed', 'unsigned')),
          template_name TEXT,
          template_content TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (study_type_id) REFERENCES study_types (id),
          UNIQUE(study_type_id, variant)
        )
        """
    )
    conn.commit()


def _migrate_legacy_study_templates(conn: sqlite3.Connection) -> None:
    """
    Переносим старый `study_templates` (1 запись на study_type) в новый
    `study_template_variants` как 'unsigned', если вариант ещё не задан.
    Оставляем старую таблицу как есть (для совместимости с Tkinter кодом).
    """
    # does legacy table exist?
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='study_templates'"
    ).fetchone()
    if not row:
        return

    rows = conn.execute(
        "SELECT study_type_id, template_name, template_content FROM study_templates"
    ).fetchall()
    for st_id, name, content in rows:
        if not content:
            continue
        exists = conn.execute(
            """
            SELECT 1 FROM study_template_variants
            WHERE study_type_id = ? AND variant = 'unsigned'
            """,
            (st_id,),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO study_template_variants (study_type_id, variant, template_name, template_content)
            VALUES (?, 'unsigned', ?, ?)
            """,
            (st_id, name, content),
        )
    conn.commit()


def _add_fields_template_tag(conn: sqlite3.Connection) -> None:
    """
    Добавляем поле `template_tag` в таблицу `fields`, чтобы можно было хранить отдельный
    @тег для HTML-шаблонов печати (не равный "Название" поля).
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fields'"
    ).fetchone()
    if not row:
        return

    cols = [r[1] for r in conn.execute("PRAGMA table_info(fields)").fetchall()]
    if "template_tag" in cols:
        return

    conn.execute("ALTER TABLE fields ADD COLUMN template_tag TEXT")
    conn.commit()

