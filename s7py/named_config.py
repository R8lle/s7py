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
