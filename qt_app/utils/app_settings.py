from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..paths import ultrasound_dir


@dataclass(frozen=True)
class ExternalFilesSettings:
    help_path: str | None = None
    service_path: str | None = None
    about_path: str | None = None


@dataclass(frozen=True)
class PrintUiSettings:
    # 'html' | 'word' | 'pdf'
    default_format: str = "html"
    # 'unsigned' | 'signed' (only used for html)
    default_variant: str = "unsigned"


def _settings_path() -> Path:
    d = ultrasound_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "app_files.json"


def load_external_files_settings() -> ExternalFilesSettings:
    p = _settings_path()
    if not p.exists():
        return ExternalFilesSettings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ExternalFilesSettings()
    return ExternalFilesSettings(
        help_path=str(data.get("help_path") or "") or None,
        service_path=str(data.get("service_path") or "") or None,
        about_path=str(data.get("about_path") or "") or None,
    )


def load_print_ui_settings() -> PrintUiSettings:
    p = _settings_path()
    if not p.exists():
        return PrintUiSettings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return PrintUiSettings()
    fmt = str(data.get("print_default_format") or "html").strip().lower()
    if fmt not in ("html", "word", "pdf"):
        fmt = "html"
    var = str(data.get("print_default_variant") or "unsigned").strip().lower()
    if var not in ("unsigned", "signed"):
        var = "unsigned"
    return PrintUiSettings(default_format=fmt, default_variant=var)


def save_external_files_settings(s: ExternalFilesSettings) -> None:
    p = _settings_path()
    # merge with existing json (same file)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        data = {}
    data.update({
        "help_path": s.help_path or "",
        "service_path": s.service_path or "",
        "about_path": s.about_path or "",
    })
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_print_ui_settings(s: PrintUiSettings) -> None:
    p = _settings_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        data = {}
    data["print_default_format"] = s.default_format
    data["print_default_variant"] = s.default_variant
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

