from __future__ import annotations

import sqlite3
from pathlib import Path
import shutil

from .paths import db_path
from .migrations import run_migrations


def ensure_db_initialized() -> Path:
    """
    Гарантирует, что SQLite файл существует.
    Если базы нет — создаёт новую и применяет миграции.
    """
    path = db_path()
    if path.exists():
        # ensure migrations for existing DB
        with sqlite3.connect(str(path)) as conn:
            run_migrations(conn)
        return path

    # Создаём папку данных
    path.parent.mkdir(parents=True, exist_ok=True)

    # Миграция со старой структуры репозитория (если файл БД был внутри проекта)
    legacy_db = Path(__file__).resolve().parent.parent / "UltrasoundProtocolSystem" / "uzi_protocols.db"
    if legacy_db.exists():
        try:
            shutil.copy2(legacy_db, path)
        except Exception:
            # если не получилось скопировать — просто создадим новую
            pass

    if not path.exists():
        with sqlite3.connect(str(path)) as conn:
            _init_schema(conn)

    # migrations
    with sqlite3.connect(str(path)) as conn:
        run_migrations(conn)

    return path


def connect() -> sqlite3.Connection:
    path = ensure_db_initialized()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """
    Базовая схема БД для Qt-версии (без зависимости от старого Tkinter-проекта).
    """
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_active BOOLEAN DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            institution_id INTEGER,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (institution_id) REFERENCES institutions (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            institution_id INTEGER,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (institution_id) REFERENCES institutions (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admission_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_active BOOLEAN DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            iin TEXT UNIQUE CHECK(length(iin) = 12),
            birth_date DATE NOT NULL,
            gender TEXT CHECK(gender IN ('муж', 'жен')),
            admission_channel_id INTEGER,
            institution_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admission_channel_id) REFERENCES admission_channels (id),
            FOREIGN KEY (institution_id) REFERENCES institutions (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS study_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            display_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tabs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_type_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            display_order INTEGER DEFAULT 0,
            FOREIGN KEY (study_type_id) REFERENCES study_types (id),
            UNIQUE(study_type_id, name)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tab_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            display_order INTEGER DEFAULT 0,
            is_expanded_by_default BOOLEAN DEFAULT 0,
            FOREIGN KEY (tab_id) REFERENCES tabs (id),
            UNIQUE(tab_id, name)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            field_type TEXT CHECK(field_type IN (
                'строка', 'текст', 'число', 'дата', 'время',
                'словарь', 'шаблон', 'скрытое', 'формула'
            )),
            template_tag TEXT,
            column_num INTEGER DEFAULT 1,
            display_order INTEGER DEFAULT 0,
            precision INTEGER DEFAULT 0,
            reference_male_min REAL,
            reference_male_max REAL,
            reference_female_min REAL,
            reference_female_max REAL,
            formula TEXT,
            is_required BOOLEAN DEFAULT 0,
            height INTEGER DEFAULT 1,
            width INTEGER DEFAULT 20,
            is_hidden BOOLEAN DEFAULT 0,
            hidden_trigger_field_id INTEGER,
            hidden_trigger_value TEXT,
            FOREIGN KEY (group_id) REFERENCES groups (id),
            FOREIGN KEY (hidden_trigger_field_id) REFERENCES fields (id),
            UNIQUE(group_id, name)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_id INTEGER NOT NULL,
            value TEXT NOT NULL,
            display_order INTEGER DEFAULT 0,
            FOREIGN KEY (field_id) REFERENCES fields (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS protocols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            study_type_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            device_id INTEGER,
            institution_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            is_signed BOOLEAN DEFAULT 0,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (study_type_id) REFERENCES study_types (id),
            FOREIGN KEY (doctor_id) REFERENCES doctors (id),
            FOREIGN KEY (device_id) REFERENCES devices (id),
            FOREIGN KEY (institution_id) REFERENCES institutions (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS protocol_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocol_id INTEGER NOT NULL,
            field_id INTEGER NOT NULL,
            value TEXT,
            FOREIGN KEY (protocol_id) REFERENCES protocols (id),
            FOREIGN KEY (field_id) REFERENCES fields (id),
            UNIQUE(protocol_id, field_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS study_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_type_id INTEGER NOT NULL,
            template_name TEXT NOT NULL,
            template_content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (study_type_id) REFERENCES study_types (id),
            UNIQUE(study_type_id)
        )
        """
    )

    conn.commit()

