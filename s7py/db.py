"""SQLite-Datenbank und Anwendungskonfiguration."""

import json
import os
import sqlite3
import time
from pathlib import Path
from sqlite3 import Error
from typing import Optional

from s7py.constants import (
    APP_DIR,
    AUTO_RECONNECT_DEFAULT,
    DB_CONFIG_PATH,
    DEFAULT_DATABASE,
    DEFAULT_PLOT_REFRESH_MS,
    DEFAULT_POLL_INTERVAL_S,
    LAST_DATABASE_KEY,
    MAX_PLOT_REFRESH_MS,
    MAX_POLL_INTERVAL_S,
    MIN_PLOT_REFRESH_MS,
    MIN_POLL_INTERVAL_S,
    PLC_DB_NUMBER,
    PLC_RACK,
    PLC_SLOT,
    PLC_STRUCTURE_KEY_OPCUA,
    PLC_STRUCTURE_KEY_SNAP7,
    PLC_TRANSPORT_OPCUA,
    PLC_TRANSPORT_SNAP7,
    SQLITE_WRITE_BASE_DELAY_S,
    SQLITE_WRITE_MAX_ATTEMPTS,
)
from s7py.log import log_msg
from s7py.plc import get_db_size
from s7py.schema import (
    DbItem,
    PlcDbSchema,
    coerce_db_items,
    default_plc_schema,
    is_opcua_schema_items,
    parse_db_layout,
)


def normalize_db_path(path: str) -> str:
    """Bereinigt SQLite-Pfade: doppelte .db-Endungen entfernen (z. B. foo.db.db)."""
    raw = (path or "").strip()
    if not raw:
        return ""
    p = Path(raw)
    name = p.name
    if not name:
        return raw
    lower = name.lower()
    while lower.endswith(".db.db"):
        name = name[:-3]
        lower = name.lower()
    for suffix in (".sqlite3", ".sqlite"):
        if lower.endswith(f"{suffix}.db"):
            name = name[: -len(".db")]
            lower = name.lower()
            break
    if name == p.name:
        return raw
    if len(p.parts) > 1:
        return str(p.parent / name)
    return name


def resolve_db_path(path: str) -> str:
    """Macht DB-Pfade unabhaengig vom aktuellen Arbeitsverzeichnis."""
    path = normalize_db_path(path)
    if not path:
        return DEFAULT_DATABASE
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate.resolve())
    return str((APP_DIR / candidate).resolve())


def _path_for_storage(path: str) -> str:
    """Speichert Pfade relativ zu APP_DIR, wenn moeglich (ohne Benutzernamen im JSON)."""
    resolved = Path(resolve_db_path(path)).resolve()
    try:
        return str(resolved.relative_to(APP_DIR.resolve()))
    except ValueError:
        return str(resolved)


def create_connection(db_file: str) -> Optional[sqlite3.Connection]:
    """Oeffnet eine SQLite-Verbindung mit WAL-Mode und 8s busy_timeout.

    ``check_same_thread=False`` erlaubt die Nutzung aus dem Worker-Thread.
    Returns ``None``, falls die Verbindung fehlschlaegt (Fehler wird geloggt).
    """
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(db_file, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=8000;")
        return conn
    except Error as e:
        log_msg(f"sqlite3 error: {e}")
    return conn


def create_table(cursor: sqlite3.Cursor, create_table_sql: str) -> None:
    """Fuehrt eine ``CREATE TABLE``-Anweisung aus. Fehler werden geloggt, nicht geworfen."""
    try:
        cursor.execute(create_table_sql)
    except Error as e:
        log_msg(f"table create error: {e}")


def load_app_config() -> dict:
    """Laedt die lokale Anwendungskonfiguration."""
    try:
        with open(DB_CONFIG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            legacy_db = str(data.get(LAST_DATABASE_KEY, "") or "").strip()
            had_unified_db = bool(legacy_db)
            had_snap7_schema = isinstance(data.get(PLC_STRUCTURE_KEY_SNAP7), dict)
            had_opcua_schema = isinstance(data.get(PLC_STRUCTURE_KEY_OPCUA), dict)
            legacy_schema = data.get("plc_structure")
            _migrate_legacy_db_config(data)
            _migrate_legacy_schema_config(data)
            _migrate_last_database_path(data)
            from s7py.credential_store import migrate_plaintext_secrets

            secrets_migrated = migrate_plaintext_secrets(data)
            if (not had_unified_db and str(data.get(LAST_DATABASE_KEY, "") or "").strip()) or (
                isinstance(legacy_schema, dict)
                and (
                    (not had_snap7_schema and isinstance(data.get(PLC_STRUCTURE_KEY_SNAP7), dict))
                    or (
                        not had_opcua_schema
                        and isinstance(data.get(PLC_STRUCTURE_KEY_OPCUA), dict)
                    )
                )
            ) or normalize_db_path(legacy_db) != legacy_db or secrets_migrated:
                save_app_config(data)
            return data
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        pass
    return {}


def save_app_config(config: dict) -> None:
    try:
        with open(DB_CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(config, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _plc_structure_config_key(transport: str) -> str:
    if normalize_plc_transport(transport) == PLC_TRANSPORT_OPCUA:
        return PLC_STRUCTURE_KEY_OPCUA
    return PLC_STRUCTURE_KEY_SNAP7


def _plc_schema_dict_from_items(plc: dict, items: list[DbItem]) -> dict:
    layout = str(plc.get("layout", "")).strip()
    sqlite_columns = plc.get("sqlite_columns")
    if not sqlite_columns:
        sqlite_columns = [it.name for it in items if it.store]
    if "read_length" in plc:
        read_length = int(plc.get("read_length") or 0)
    elif is_opcua_schema_items(items):
        read_length = 0
    else:
        read_length = get_db_size(items)
    return {
        "source_file": str(plc.get("source_file", "") or ""),
        "block_name": str(plc.get("block_name", "")),
        "db_number": int(plc.get("db_number", PLC_DB_NUMBER) or PLC_DB_NUMBER),
        "layout": layout
        or "\n".join(f"{it.name}\t{it.datatype}\t{it.bytebit}" for it in items),
        "items": plc.get("items") if plc.get("items") else [it.to_dict() for it in items],
        "read_length": read_length,
        "count_field": str(plc.get("count_field", "Count")),
        "plot_fields": list(plc.get("plot_fields") or ["Temperature", "DistanceOverAll"]),
        "live_fields": [str(name) for name in (plc.get("live_fields") or sqlite_columns[:4])],
        "sqlite_columns": [str(name) for name in sqlite_columns],
    }


def _plc_schema_dict_from_schema(schema: PlcDbSchema) -> dict:
    return {
        "source_file": _path_for_storage(schema.source_file) if schema.source_file else "",
        "block_name": schema.block_name,
        "db_number": schema.db_number,
        "layout": schema.layout,
        "items": [it.to_dict() for it in schema.items],
        "read_length": schema.read_length,
        "count_field": schema.count_field,
        "plot_fields": list(schema.plot_fields),
        "live_fields": schema.live_fields,
        "sqlite_columns": schema.sqlite_columns,
    }


def _schema_from_plc_dict(plc: dict) -> PlcDbSchema:
    layout = str(plc.get("layout", "")).strip()
    items_raw = plc.get("items")
    if not items_raw and layout:
        items = parse_db_layout(layout)
    elif items_raw:
        items = coerce_db_items(items_raw)
    else:
        return default_plc_schema()

    sqlite_columns = plc.get("sqlite_columns")
    if not sqlite_columns:
        sqlite_columns = [it.name for it in items if it.store]

    plot_fields_raw = plc.get("plot_fields") or ["Temperature", "DistanceOverAll"]
    if isinstance(plot_fields_raw, tuple):
        plot_fields_list = [str(plot_fields_raw[0]), str(plot_fields_raw[1])]
    else:
        plot_fields_list = [str(name) for name in plot_fields_raw]
    live_fields = plc.get("live_fields") or sqlite_columns[:4]
    if "read_length" in plc:
        read_length = int(plc.get("read_length") or 0)
    elif is_opcua_schema_items(items):
        read_length = 0
    else:
        read_length = get_db_size(items)

    source_raw = str(plc.get("source_file", "")).strip()
    return PlcDbSchema(
        source_file=resolve_db_path(source_raw) if source_raw else "",
        block_name=str(plc.get("block_name", "")),
        db_number=int(plc.get("db_number", PLC_DB_NUMBER) or PLC_DB_NUMBER),
        layout=layout or "\n".join(
            f"{it.name}\t{it.datatype}\t{it.bytebit}" for it in items
        ),
        items=items,
        read_length=read_length,
        count_field=str(plc.get("count_field", "Count")),
        plot_fields=plot_fields_list,
        live_fields=[str(name) for name in live_fields],
        sqlite_columns=[str(name) for name in sqlite_columns],
    )


def _migrate_legacy_schema_config(config: dict) -> None:
    """Altes plc_structure nach Snap7/OPC UA aufteilen."""
    legacy = config.get("plc_structure")
    if not isinstance(legacy, dict):
        return
    items_raw = legacy.get("items")
    layout = str(legacy.get("layout", "")).strip()
    if items_raw:
        items = coerce_db_items(items_raw)
    elif layout:
        items = parse_db_layout(layout)
    else:
        return
    target_key = (
        PLC_STRUCTURE_KEY_OPCUA
        if is_opcua_schema_items(items)
        else PLC_STRUCTURE_KEY_SNAP7
    )
    if not isinstance(config.get(target_key), dict):
        config[target_key] = _plc_schema_dict_from_items(legacy, items)


def schema_from_config(config: dict, transport: str | None = None) -> PlcDbSchema:
    """Laedt die SPS-Struktur fuer Snap7 oder OPC UA aus der Konfiguration."""
    _migrate_legacy_schema_config(config)
    transport = normalize_plc_transport(transport or config.get("plc_transport"))
    plc = config.get(_plc_structure_config_key(transport))
    if not isinstance(plc, dict):
        return default_plc_schema()
    return _schema_from_plc_dict(plc)


def default_db_path_for_transport(transport: str | None = None) -> str:
    """Standard-SQLite-Datei (Snap7 und OPC UA nutzen dieselbe DB)."""
    del transport
    return DEFAULT_DATABASE


def _migrate_last_database_path(config: dict) -> None:
    """Doppelte .db-Endung in last_database bereinigen."""
    path = str(config.get(LAST_DATABASE_KEY, "") or "").strip()
    if not path:
        return
    fixed = normalize_db_path(path)
    if fixed != path:
        config[LAST_DATABASE_KEY] = _path_for_storage(fixed)


def _migrate_legacy_db_config(config: dict) -> None:
    """Alte last_database_*-Schluessel auf last_database vereinheitlichen."""
    unified = str(config.get(LAST_DATABASE_KEY, "") or "").strip()
    if unified:
        return
    for legacy_key in (
        "last_database_snap7",
        "last_database",
        "last_database_opcua",
    ):
        legacy = str(config.get(legacy_key, "") or "").strip()
        if legacy:
            config[LAST_DATABASE_KEY] = legacy
            return


def save_plc_schema(
    schema: PlcDbSchema,
    *,
    last_database: Optional[str] = None,
    transport: str | None = None,
) -> None:
    config = load_app_config()
    _migrate_legacy_db_config(config)
    _migrate_legacy_schema_config(config)
    if transport is None:
        transport = (
            PLC_TRANSPORT_OPCUA
            if is_opcua_schema_items(schema.items)
            else PLC_TRANSPORT_SNAP7
        )
    if last_database:
        config[LAST_DATABASE_KEY] = _path_for_storage(last_database)
    config[_plc_structure_config_key(transport)] = _plc_schema_dict_from_schema(schema)
    save_app_config(config)


def load_last_db_path(transport: str | None = None) -> str:
    """Letzten SQLite-Pfad aus der Konfiguration laden."""
    del transport
    config = load_app_config()
    _migrate_legacy_db_config(config)
    path = str(config.get(LAST_DATABASE_KEY, "") or "").strip()
    if path:
        return resolve_db_path(path)
    return DEFAULT_DATABASE


def save_last_db_path(path: str, transport: str | None = None) -> None:
    """SQLite-Pfad fuer den naechsten Programmstart speichern."""
    del transport
    path = resolve_db_path(path.strip())
    if not path:
        return
    config = load_app_config()
    _migrate_legacy_db_config(config)
    config[LAST_DATABASE_KEY] = _path_for_storage(path)
    save_app_config(config)


def load_last_plc_ip() -> str:
    """Zuletzt erfolgreich verbundene SPS-IP aus der Konfiguration laden."""
    return str(load_app_config().get("last_plc_ip", "")).strip()


def save_last_plc_ip(ip: str) -> None:
    """Zuletzt verbundene SPS-IP fuer den naechsten Programmstart speichern."""
    ip = (ip or "").strip()
    if not ip:
        return
    config = load_app_config()
    config["last_plc_ip"] = ip
    save_app_config(config)


def normalize_plc_transport(value: object) -> str:
    """Transport-ID auf snap7 oder opcua normalisieren."""
    from s7py.constants import PLC_TRANSPORT_OPCUA, PLC_TRANSPORT_SNAP7

    raw = str(value or "").strip().lower()
    if raw in (PLC_TRANSPORT_OPCUA, "opc ua", "opc-ua", "opc_ua"):
        return PLC_TRANSPORT_OPCUA
    return PLC_TRANSPORT_SNAP7


def load_plc_transport() -> str:
    return normalize_plc_transport(load_app_config().get("plc_transport"))


def save_plc_transport(transport: str) -> None:
    config = load_app_config()
    config["plc_transport"] = normalize_plc_transport(transport)
    save_app_config(config)


def load_opcua_endpoint() -> str:
    from s7py.constants import DEFAULT_OPCUA_ENDPOINT

    raw = str(load_app_config().get("opcua_endpoint", "") or "").strip()
    return raw or DEFAULT_OPCUA_ENDPOINT


def save_opcua_endpoint(url: str) -> None:
    config = load_app_config()
    config["opcua_endpoint"] = (url or "").strip()
    save_app_config(config)


def load_opcua_security_config() -> "OpcUaSecurityConfig":
    from s7py.credential_store import (
        OPCUA_CLIENT_KEY_PASSWORD_ENC_KEY,
        OPCUA_CLIENT_KEY_PASSWORD_PLAIN_KEY,
        OPCUA_PASSWORD_ENC_KEY,
        OPCUA_PASSWORD_PLAIN_KEY,
        load_stored_secret,
    )
    from s7py.opcua_connect import OpcUaSecurityConfig

    cfg = load_app_config()
    return OpcUaSecurityConfig(
        client_cert=str(cfg.get("opcua_client_cert", "") or "").strip(),
        client_key=str(cfg.get("opcua_client_key", "") or "").strip(),
        client_key_password=load_stored_secret(
            cfg,
            plain_key=OPCUA_CLIENT_KEY_PASSWORD_PLAIN_KEY,
            enc_key=OPCUA_CLIENT_KEY_PASSWORD_ENC_KEY,
        ),
        username=str(cfg.get("opcua_username", "") or "").strip(),
        password=load_stored_secret(
            cfg,
            plain_key=OPCUA_PASSWORD_PLAIN_KEY,
            enc_key=OPCUA_PASSWORD_ENC_KEY,
        ),
    )


def load_opcua_username() -> str:
    return str(load_app_config().get("opcua_username", "") or "").strip()


def load_opcua_password() -> str:
    from s7py.credential_store import (
        OPCUA_PASSWORD_ENC_KEY,
        OPCUA_PASSWORD_PLAIN_KEY,
        load_stored_secret,
    )

    return load_stored_secret(
        load_app_config(),
        plain_key=OPCUA_PASSWORD_PLAIN_KEY,
        enc_key=OPCUA_PASSWORD_ENC_KEY,
    )


def save_opcua_credentials(username: str, password: str) -> None:
    from s7py.credential_store import (
        OPCUA_PASSWORD_ENC_KEY,
        OPCUA_PASSWORD_PLAIN_KEY,
        store_secret_in_config,
    )

    config = load_app_config()
    user = (username or "").strip()
    if user:
        config["opcua_username"] = user
        store_secret_in_config(
            config,
            plain_key=OPCUA_PASSWORD_PLAIN_KEY,
            enc_key=OPCUA_PASSWORD_ENC_KEY,
            value=password or "",
        )
    else:
        config.pop("opcua_username", None)
        store_secret_in_config(
            config,
            plain_key=OPCUA_PASSWORD_PLAIN_KEY,
            enc_key=OPCUA_PASSWORD_ENC_KEY,
            value="",
        )
    save_app_config(config)


def merge_opcua_security_config(
    *,
    username: str = "",
    password: str | None = None,
) -> "OpcUaSecurityConfig":
    """Zertifikate aus der Config; Benutzer/Passwort nur wenn in der UI gesetzt.

    Leerer Benutzername in der UI bedeutet: keine Credentials — auch nicht
    aus gespeicherten JSON-Werten zurueckfallen.
    """
    from s7py.opcua_connect import OpcUaSecurityConfig

    base = load_opcua_security_config()
    user = (username or "").strip()
    if user:
        pwd = password if password is not None else base.password
        return OpcUaSecurityConfig(
            client_cert=base.client_cert,
            client_key=base.client_key,
            client_key_password=base.client_key_password,
            username=user,
            password=pwd or "",
        )
    return OpcUaSecurityConfig(
        client_cert=base.client_cert,
        client_key=base.client_key,
        client_key_password=base.client_key_password,
        username="",
        password="",
    )


def normalize_poll_interval_s(value: object) -> float:
    """Poll-Intervall in Sekunden auf erlaubten Bereich begrenzen."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_POLL_INTERVAL_S
    if seconds < MIN_POLL_INTERVAL_S:
        return MIN_POLL_INTERVAL_S
    if seconds > MAX_POLL_INTERVAL_S:
        return MAX_POLL_INTERVAL_S
    return seconds


def load_poll_interval_s() -> float:
    """Abfrageintervall in Sekunden aus der Konfiguration laden."""
    raw = load_app_config().get("poll_interval_s")
    if raw is None:
        return DEFAULT_POLL_INTERVAL_S
    return normalize_poll_interval_s(raw)


def save_poll_interval_s(seconds: float) -> None:
    """Abfrageintervall fuer den naechsten Programmstart speichern."""
    config = load_app_config()
    config["poll_interval_s"] = normalize_poll_interval_s(seconds)
    save_app_config(config)


def poll_interval_ms_from_s(seconds: float) -> int:
    return int(round(normalize_poll_interval_s(seconds) * 1000))


def poll_interval_s_from_ms(milliseconds: object) -> float:
    try:
        ms = int(milliseconds)
    except (TypeError, ValueError):
        return DEFAULT_POLL_INTERVAL_S
    return normalize_poll_interval_s(ms / 1000.0)


def clamp_poll_interval_ms(milliseconds: object) -> int:
    """Poll-Intervall in Millisekunden auf erlaubten Bereich begrenzen."""
    return poll_interval_ms_from_s(poll_interval_s_from_ms(milliseconds))


def normalize_recording_mode(value: object) -> str:
    from s7py.constants import (
        RECORDING_MODE_COUNT,
        RECORDING_MODE_DEFAULT,
        RECORDING_MODE_EVERY_CYCLE,
    )

    mode = str(value or "").strip()
    if mode in (RECORDING_MODE_COUNT, RECORDING_MODE_EVERY_CYCLE):
        return mode
    return RECORDING_MODE_DEFAULT


def load_recording_mode() -> str:
    return normalize_recording_mode(load_app_config().get("recording_mode"))


def save_recording_mode(mode: str) -> None:
    config = load_app_config()
    config["recording_mode"] = normalize_recording_mode(mode)
    save_app_config(config)


def normalize_plot_refresh_ms(value: object) -> int:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PLOT_REFRESH_MS
    if ms < MIN_PLOT_REFRESH_MS:
        return MIN_PLOT_REFRESH_MS
    if ms > MAX_PLOT_REFRESH_MS:
        return MAX_PLOT_REFRESH_MS
    return ms


def load_plot_refresh_ms() -> int:
    raw = load_app_config().get("plot_refresh_ms")
    if raw is None:
        return DEFAULT_PLOT_REFRESH_MS
    return normalize_plot_refresh_ms(raw)


def save_plot_refresh_ms(milliseconds: int) -> None:
    config = load_app_config()
    config["plot_refresh_ms"] = normalize_plot_refresh_ms(milliseconds)
    save_app_config(config)


def load_auto_reconnect() -> bool:
    """Auto-Reconnect-Einstellung laden (Standard: an)."""
    raw = load_app_config().get("auto_reconnect")
    if raw is None:
        return AUTO_RECONNECT_DEFAULT
    return bool(raw)


def save_auto_reconnect(enabled: bool) -> None:
    """Auto-Reconnect-Einstellung speichern."""
    config = load_app_config()
    config["auto_reconnect"] = bool(enabled)
    save_app_config(config)


def normalize_plc_rack(value: object) -> int:
    try:
        rack = int(value)
    except (TypeError, ValueError):
        return PLC_RACK
    return max(0, min(7, rack))


def normalize_plc_slot(value: object) -> int:
    try:
        slot = int(value)
    except (TypeError, ValueError):
        return PLC_SLOT
    return max(0, min(31, slot))


def load_plc_rack() -> int:
    return normalize_plc_rack(load_app_config().get("plc_rack", PLC_RACK))


def load_plc_slot() -> int:
    return normalize_plc_slot(load_app_config().get("plc_slot", PLC_SLOT))


def save_plc_rack_slot(rack: int, slot: int) -> None:
    config = load_app_config()
    config["plc_rack"] = normalize_plc_rack(rack)
    config["plc_slot"] = normalize_plc_slot(slot)
    save_app_config(config)


def normalize_plc_db_number(value: object) -> int:
    try:
        db_number = int(value)
    except (TypeError, ValueError):
        return PLC_DB_NUMBER
    return max(1, min(65535, db_number))


def load_plc_db_number() -> int:
    config = load_app_config()
    _migrate_legacy_schema_config(config)
    if "plc_db_number" in config:
        return normalize_plc_db_number(config["plc_db_number"])
    transport = normalize_plc_transport(config.get("plc_transport"))
    plc = config.get(_plc_structure_config_key(transport))
    if isinstance(plc, dict) and plc.get("db_number") is not None:
        return normalize_plc_db_number(plc["db_number"])
    legacy = config.get("plc_structure")
    if isinstance(legacy, dict) and legacy.get("db_number") is not None:
        return normalize_plc_db_number(legacy["db_number"])
    return PLC_DB_NUMBER


def save_plc_db_number(db_number: int) -> None:
    config = load_app_config()
    config["plc_db_number"] = normalize_plc_db_number(db_number)
    save_app_config(config)


def format_db_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def fetch_projects_stats(cursor: sqlite3.Cursor, db_path: str) -> dict[str, object]:
    """Kurzstatistik fuer die Statuszeile (Zeilen, letzter Zeitstempel, Dateigroesse)."""
    stats: dict[str, object] = {
        "rows": 0,
        "last_id": 0,
        "last_time": "",
        "size_bytes": 0,
    }
    try:
        cursor.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0), MAX(time) FROM projects"
        )
        row = cursor.fetchone()
        if row is not None:
            stats["rows"] = int(row[0] or 0)
            stats["last_id"] = int(row[1] or 0)
            stats["last_time"] = str(row[2] or "")
    except sqlite3.Error:
        pass
    try:
        stats["size_bytes"] = os.path.getsize(db_path)
    except OSError:
        pass
    return stats


def format_projects_stats_suffix(stats: dict[str, object]) -> str:
    rows = int(stats.get("rows", 0) or 0)
    last_time = str(stats.get("last_time", "") or "")
    size_bytes = int(stats.get("size_bytes", 0) or 0)
    if rows <= 0:
        return f" | 0 Messpunkte | {format_db_size(size_bytes)}"
    time_part = last_time if last_time else "—"
    return f" | {rows} Messpunkte | letzte: {time_part} | {format_db_size(size_bytes)}"


def projects_row_count(cursor: sqlite3.Cursor) -> int:
    cursor.execute("SELECT COUNT(*) FROM projects")
    row = cursor.fetchone()
    return int(row[0] or 0) if row is not None else 0


def trim_projects_keep_last(
    cursor: sqlite3.Cursor, conn: sqlite3.Connection, keep: int
) -> int:
    """Behält die letzten ``keep`` Messpunkte; gibt gelöschte Zeilenanzahl zurück."""
    keep = max(0, int(keep))
    total = projects_row_count(cursor)
    if keep >= total:
        return 0
    cursor.execute(
        "SELECT COALESCE(MIN(id), 0) FROM ("
        "SELECT id FROM projects ORDER BY id DESC LIMIT ?)",
        (keep,),
    )
    min_keep_id = int(cursor.fetchone()[0] or 0)
    cursor.execute("DELETE FROM projects WHERE id < ?", (min_keep_id,))
    conn.commit()
    return total - keep


def clear_projects_table(cursor: sqlite3.Cursor, conn: sqlite3.Connection) -> int:
    """Löscht alle Messpunkte aus ``projects``."""
    total = projects_row_count(cursor)
    cursor.execute("DELETE FROM projects")
    conn.commit()
    return total


def vacuum_sqlite_database(db_path: str) -> None:
    """Dateigroesse nach Loeschungen reduzieren (keine offene Verbindung noetig)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()


def quote_identifier(name: object) -> str:
    """Macht einen Spalten-/Tabellennamen sicher als SQL-Bezeichner.

    Spaltennamen koennen aus importierten Projektdateien / der lokalen
    ``s7py_db.json`` stammen (also aus nicht vollstaendig vertrauenswuerdiger
    Quelle). Da Bezeichner nicht als gebundene Parameter (``?``) uebergeben
    werden koennen, werden sie hier nach SQLite-Regel maskiert: in doppelte
    Anfuehrungszeichen einschliessen und enthaltene ``"`` verdoppeln.
    So kann ein Name wie ``x"); DROP TABLE projects;--`` keine SQL-Injection
    ausloesen, sondern wird zu einem einzelnen, harmlosen Bezeichner.
    """
    text = str(name)
    if not text or "\x00" in text:
        raise ValueError(f"Ungueltiger SQL-Bezeichner: {name!r}")
    return '"' + text.replace('"', '""') + '"'


def sqlite_type_for_item(item: DbItem) -> str:
    if item.datatype == "Real":
        return "real"
    if item.datatype == "String":
        return "text"
    return "integer"


def ensure_projects_table(conn: sqlite3.Connection, schema: PlcDbSchema) -> None:
    """Legt ``projects`` an, falls die Tabelle in einer bestehenden DB fehlt."""
    cursor = conn.cursor()
    if table_columns(cursor, "projects"):
        return
    create_table(cursor, build_create_projects_sql(schema))
    try:
        conn.commit()
    except Error as exc:
        log_msg(f"commit after create projects table: {exc}")


def build_create_projects_sql(schema: PlcDbSchema) -> str:
    columns = ["id integer PRIMARY KEY", "time text"]
    for name in schema.sqlite_columns:
        item = next(it for it in schema.items if it.name == name)
        columns.append(f"{quote_identifier(name)} {sqlite_type_for_item(item)}")
    return "CREATE TABLE IF NOT EXISTS projects (" + ", ".join(columns) + ");"


def create_database(database: str, schema: Optional[PlcDbSchema] = None) -> bool:
    """Legt eine neue SQLite-Datei mit ``projects``-Tabelle an und fuehrt Migrationen aus.

    Returns:
        ``True``, wenn die Datei danach existiert und geoeffnet werden konnte.
    """
    if schema is None:
        schema = default_plc_schema()

    parent = os.path.dirname(os.path.abspath(database))
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            log_msg(f"Verzeichnis fuer neue DB konnte nicht angelegt werden: {exc}")
            return False

    conn = create_connection(database)
    if conn is not None:
        try:
            ensure_projects_table(conn, schema)
            if not table_columns(conn.cursor(), "projects"):
                log_msg("Error! projects table could not be created.")
                return False
            migrate_database(conn, schema)
            return os.path.isfile(database)
        finally:
            conn.close()
    log_msg("Error! cannot create the database connection.")
    return False


def table_columns(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
    """Liefert die Spaltennamen der angegebenen Tabelle.

    Nutzt die Tabellen-Funktion ``pragma_table_info(?)`` statt der
    ``PRAGMA``-Anweisung, da PRAGMA keine gebundenen Parameter (``?``)
    unterstuetzt (sonst: ``near "?": syntax error``).
    """
    cursor.execute("SELECT name FROM pragma_table_info(?)", (table_name,))
    return [row[0] for row in cursor.fetchall()]


def sync_projects_table_schema(
    conn: sqlite3.Connection, schema: PlcDbSchema
) -> None:
    """Legt in ``projects`` fehlende Spalten gemaess SPS-Schema an."""
    try:
        cursor = conn.cursor()
        table_cols = set(table_columns(cursor, "projects"))
        if not table_cols:
            return

        for col in schema.sqlite_columns:
            if col in table_cols:
                continue
            item = next(
                (it for it in schema.items if it.name == col), None
            )
            if item is None:
                continue
            sql_type = sqlite_type_for_item(item)
            log_msg(f"Migration: fuege Spalte '{col}' ({sql_type}) hinzu.")
            try:
                quoted_col = quote_identifier(col)
            except ValueError as exc:
                log_msg(f"Migration: Spaltenname uebersprungen ({exc}).")
                continue
            cursor.execute(
                f"ALTER TABLE projects ADD COLUMN {quoted_col} {sql_type}"
            )
            conn.commit()
            table_cols.add(col)
    except sqlite3.Error as exc:
        log_msg(f"Schema-Synchronisation fehlgeschlagen: {exc}")


def migrate_database(
    conn: sqlite3.Connection, schema: Optional[PlcDbSchema] = None
) -> None:
    """Einmalige Migrationen fuer bestehende Datenbanken.

    Aktuell: Entfernt die ueberfluessige Spalte ``name`` aus ``projects``
    (Voraussetzung: SQLite 3.35+ mit ``ALTER TABLE DROP COLUMN``). Fehler
    werden nur geloggt — eine bereits migrierte DB ist kein Problem.

    Mit ``schema`` werden zusaetzlich fehlende Spalten angelegt.
    """
    if schema is not None:
        ensure_projects_table(conn, schema)

    try:
        cursor = conn.cursor()
        columns = table_columns(cursor, "projects")
        if "DictanceOverAll" in columns and "DistanceOverAll" not in columns:
            log_msg(
                "Migration: korrigiere Spaltenname "
                "'DictanceOverAll' -> 'DistanceOverAll'."
            )
            cursor.execute(
                "ALTER TABLE projects RENAME COLUMN DictanceOverAll "
                "TO DistanceOverAll"
            )
            conn.commit()
            columns = table_columns(cursor, "projects")
        if "name" in columns:
            log_msg("Migration: entferne ueberfluessige Spalte 'projects.name' ...")
            cursor.execute("ALTER TABLE projects DROP COLUMN name")
            conn.commit()
            log_msg("Migration abgeschlossen.")
    except sqlite3.Error as exc:
        log_msg(f"Migration fehlgeschlagen (kann ignoriert werden, falls Spalte schon weg ist): {exc}")

    if schema is not None:
        sync_projects_table_schema(conn, schema)


def create_newline(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    newline: tuple,
    schema: PlcDbSchema,
) -> Optional[int]:
    """Fuegt eine Zeile in ``projects`` ein, mit Retry bei „locked/busy".

    Args:
        newline: Tupel passend zur INSERT-Spaltenliste (time + sqlite_columns).
    Returns:
        ``cursor.lastrowid`` der neuen Zeile, oder wirft die letzte
        SQLite-Exception bei dauerhaftem Schreibfehler.
    """
    columns = ["time"] + schema.sqlite_columns
    quoted_columns = ", ".join(quote_identifier(c) for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    sql = (
        f"INSERT INTO projects({quoted_columns}) VALUES({placeholders})"
    )

    for attempt in range(1, SQLITE_WRITE_MAX_ATTEMPTS + 1):
        try:
            cursor.execute(sql, newline)
            conn.commit()
            return cursor.lastrowid
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if attempt < SQLITE_WRITE_MAX_ATTEMPTS and (
                "locked" in msg or "busy" in msg
            ):
                # Offene Transaktion verwerfen: schlaegt erst conn.commit()
                # fehl, bleibt das INSERT sonst anhaengig und der Retry
                # wuerde eine Duplikat-Zeile erzeugen.
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                time.sleep(SQLITE_WRITE_BASE_DELAY_S * attempt)
                continue
            log_msg(f"SQLite-Schreibfehler (INSERT): {exc}")
            raise
        except Error as exc:
            log_msg(f"SQLite-Schreibfehler (INSERT): {exc}")
            raise


def csv_export_columns(schema: PlcDbSchema) -> tuple[str, ...]:
    """Spalten fuer den CSV-Export."""
    return ("id", "time", *schema.sqlite_columns)


def resolve_csv_export_columns(
    schema: PlcDbSchema,
    selected_fields: list[str] | None,
) -> tuple[str, ...]:
    """Spaltenliste fuer gefilterten Export (immer id/time, dann Auswahl)."""
    if not selected_fields:
        return csv_export_columns(schema)
    allowed = set(schema.sqlite_columns)
    extras = [name for name in selected_fields if name in allowed]
    if not extras:
        return csv_export_columns(schema)
    return ("id", "time", *extras)


def fetch_projects_for_csv(
    cursor: sqlite3.Cursor,
    schema: PlcDbSchema,
    *,
    columns: tuple[str, ...],
    scope: str = "all",
    limit: int | None = None,
) -> list[tuple]:
    """Liest Exportzeilen gemaess Umfang (all / last_n / plot_limit)."""
    col_sql = ", ".join(quote_identifier(c) for c in columns)
    if scope == "all" or not limit or limit <= 0:
        cursor.execute(f"SELECT {col_sql} FROM projects ORDER BY id ASC")
        return list(cursor.fetchall())
    cursor.execute(
        f"SELECT {col_sql} FROM projects ORDER BY id DESC LIMIT ?",
        (int(limit),),
    )
    rows = list(cursor.fetchall())
    rows.reverse()
    return rows
