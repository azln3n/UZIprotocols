from __future__ import annotations

from pathlib import Path
import os
import sys


def project_root() -> Path:
    # qt_app/paths.py -> <root>/qt_app/paths.py
    return Path(__file__).resolve().parent.parent


def ultrasound_dir() -> Path:
    """
    Папка данных приложения (БД, протоколы, шаблоны).

    По требованию: путь не "жёсткий", а берётся из .env и по умолчанию лежит в репозитории
    рядом с main_qt.py.

    .env:
      UZI_DATA_DIR=UltrasoundProtocolSystem
    - может быть абсолютным путём
    - или относительным (тогда относительно project_root())
    """
    cfg = (os.environ.get("UZI_DATA_DIR") or "").strip()
    if cfg:
        p = Path(cfg)
        return (project_root() / p).resolve() if not p.is_absolute() else p
    # default: inside repo
    return project_root() / "UltrasoundProtocolSystem"


def db_path() -> Path:
    return ultrasound_dir() / "uzi_protocols.db"


def protocols_dir() -> Path:
    """
    Папка для сохранения итоговых протоколов и ассетов (шаблоны/фото).
    По просьбе: /protocols/date/... и /protocols/templates/...
    """
    return ultrasound_dir() / "protocols"


def protocols_templates_dir() -> Path:
    return protocols_dir() / "templates"


def app_base_dir() -> Path:
    """
    Папка, где лежит приложение (по ТЗ: рядом будут файлы Справка/Сервис/О программе).
    - В dev: корень проекта.
    - В .exe: папка с exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return project_root()

