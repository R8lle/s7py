"""Benannte Anwendungskonfigurationen unter ``APP_DIR/configs/``."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

CONFIGS_DIR_NAME = "configs"
ACTIVE_CONFIG_NAME_KEY = "active_config_name"
_META_KEY = "meta"
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")


def configs_dir() -> Path:
    from s7py.constants import APP_DIR

    path = APP_DIR / CONFIGS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_config_name(name: str) -> str:
    """Anzeigenamen zu einem sicheren Dateinamen (ohne Endung) machen."""
    raw = (name or "").strip()
    cleaned = _SAFE_NAME_RE.sub("", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    if not cleaned:
        raise ValueError("Bitte einen gueltigen Konfigurationsnamen eingeben.")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip(" ._")
    return cleaned


def config_path_for_name(name: str) -> Path:
    safe = sanitize_config_name(name)
    return configs_dir() / f"{safe}.json"


def list_named_configs() -> list[tuple[str, Path]]:
    """``(Anzeigename, Pfad)`` sortiert nach Name."""
    items: list[tuple[str, Path]] = []
    for path in sorted(configs_dir().glob("*.json")):
        display = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.get(_META_KEY) if isinstance(data, dict) else None
            if isinstance(meta, dict):
                label = str(meta.get("name") or "").strip()
                if label:
                    display = label
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        items.append((display, path))
    items.sort(key=lambda item: item[0].lower())
    return items


def save_named_config(name: str, config: dict) -> Path:
    """Speichert eine vollstaendige App-Config unter dem Namen."""
    if not isinstance(config, dict):
        raise TypeError("config muss ein dict sein")
    safe = sanitize_config_name(name)
    path = configs_dir() / f"{safe}.json"
    payload = dict(config)
    payload[_META_KEY] = {
        "name": safe,
        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_named_config(name_or_path: str | Path) -> tuple[str, dict]:
    """Laedt eine benannte Config; Rueckgabe ``(Name, Config ohne meta)``."""
    path = Path(name_or_path)
    if not path.suffix:
        path = config_path_for_name(str(name_or_path))
    if not path.is_file():
        raise FileNotFoundError(f"Konfiguration nicht gefunden: {path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Ungueltige Konfigurationsdatei.")
    meta = data.get(_META_KEY) if isinstance(data.get(_META_KEY), dict) else {}
    name = str(meta.get("name") or path.stem).strip() or path.stem
    body = {key: value for key, value in data.items() if key != _META_KEY}
    body[ACTIVE_CONFIG_NAME_KEY] = name
    return name, body


def delete_named_config(name: str) -> None:
    path = config_path_for_name(name)
    if path.is_file():
        path.unlink()


def rename_named_config(old_name: str, new_name: str) -> Path:
    """Benennt eine gespeicherte Konfiguration um (Datei + Meta-Name)."""
    old_path = config_path_for_name(old_name)
    if not old_path.is_file():
        raise FileNotFoundError(f"Konfiguration nicht gefunden: {old_path.name}")
    new_safe = sanitize_config_name(new_name)
    new_path = configs_dir() / f"{new_safe}.json"
    if new_path.resolve() == old_path.resolve():
        # Nur Meta-Name aktualisieren (gleiche Datei nach Sanitize).
        name, body = load_named_config(old_path)
        del name
        return save_named_config(new_safe, body)
    if new_path.is_file():
        raise FileExistsError(f"Konfiguration „{new_safe}“ existiert bereits.")
    name, body = load_named_config(old_path)
    del name
    saved = save_named_config(new_safe, body)
    old_path.unlink(missing_ok=True)
    return saved


def export_config_dict(config: dict, dest: Path, *, name: str | None = None) -> Path:
    """Schreibt eine Config-JSON an einen beliebigen Pfad (Export/Teilen)."""
    if not isinstance(config, dict):
        raise TypeError("config muss ein dict sein")
    dest = Path(dest)
    if dest.suffix.lower() != ".json":
        dest = dest.with_suffix(".json")
    label = sanitize_config_name(name or dest.stem)
    payload = {key: value for key, value in config.items() if key != _META_KEY}
    payload[_META_KEY] = {
        "name": label,
        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exported": True,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def import_config_file(source: Path, *, name: str | None = None) -> tuple[str, Path]:
    """Importiert eine JSON-Datei nach ``configs/``; Rueckgabe ``(Name, Pfad)``."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Ungueltige Konfigurationsdatei.")
    meta = data.get(_META_KEY) if isinstance(data.get(_META_KEY), dict) else {}
    label = name or str(meta.get("name") or source.stem).strip() or source.stem
    body = {key: value for key, value in data.items() if key != _META_KEY}
    path = save_named_config(label, body)
    return sanitize_config_name(label), path
