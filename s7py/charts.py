"""Diagramm-Daten aus SQLite laden."""

import sqlite3
from datetime import datetime
from typing import Iterable, Optional

import matplotlib.axes

from s7py.constants import parse_db_timestamp_string
from s7py.db import quote_identifier, table_columns
from s7py.log import log_msg, logger
from s7py.schema import PlcDbSchema

# Cache: (connection-id, Tabellenname) -> Spaltennamen (PRAGMA nur bei Bedarf).
_table_columns_cache: dict[tuple[int, str], frozenset[str]] = {}


def invalidate_table_columns_cache(connection: sqlite3.Connection | None = None) -> None:
    """Leert den Spalten-Cache fuer eine Verbindung oder komplett."""
    if connection is None:
        _table_columns_cache.clear()
        return
    conn_id = id(connection)
    for key in [k for k in _table_columns_cache if k[0] == conn_id]:
        del _table_columns_cache[key]


def _cached_table_columns(cursor: sqlite3.Cursor, table_name: str) -> frozenset[str]:
    key = (id(cursor.connection), table_name)
    cached = _table_columns_cache.get(key)
    if cached is not None:
        return cached
    cols = frozenset(table_columns(cursor, table_name))
    _table_columns_cache[key] = cols
    return cols


def ensure_min_yrange(ax: matplotlib.axes.Axes, min_span: float) -> None:
    """Erweitert die Y-Achse symmetrisch um den Mittelpunkt, falls die aktuelle
    Spanne kleiner ist als ``min_span``.

    Hintergrund: Sind alle sichtbaren Y-Werte (nahezu) identisch, zoomt
    matplotlibs ``autoscale_view`` auf eine winzige Spanne — Float-Reste der
    SPS-32-Bit-Werte oder Rundungsartefakte erscheinen dann optisch als wilde
    Spruenge. Diese Funktion stellt eine sinnvolle Mindest-Spanne sicher.
    """
    lo, hi = ax.get_ylim()
    span = hi - lo
    if span >= min_span:
        return
    mid = (hi + lo) / 2.0
    half = min_span / 2.0
    ax.set_ylim(mid - half, mid + half, auto=True)


def plottable_numeric_fields(schema: PlcDbSchema) -> list[str]:
    """Numerische SQLite-Spalten, die im Diagramm dargestellt werden koennen."""
    text_types = {"String"}
    items_dict = {it.name: it for it in schema.items}
    fields: list[str] = []
    for name in schema.sqlite_columns:
        item = items_dict.get(name)
        if item is not None and item.datatype in text_types:
            continue
        fields.append(name)
    return fields


def _parse_chart_rows(
    rows: Iterable[tuple],
    fields: list[str],
) -> list[tuple[int, datetime, dict[str, float | int | str]]]:
    """Wandelt rohe DB-Zeilen in ``(id, Zeit, {Feld: Wert})`` um."""
    parsed: list[tuple[int, datetime, dict[str, float | int | str]]] = []
    for row in rows:
        rid, ts_str = row[0], row[1]
        values: dict[str, float | int | str] = {}
        skip = False
        for idx, field in enumerate(fields):
            val = row[2 + idx]
            if val is None:
                logger.debug("NULL-Messwert in DB, Zeile id=%s uebersprungen.", rid)
                skip = True
                break
            try:
                values[field] = float(val)
            except (TypeError, ValueError):
                logger.debug(
                    "Nicht-numerischer Messwert in DB, Zeile id=%s, Feld %r uebersprungen.",
                    rid,
                    field,
                )
                skip = True
                break
        if skip:
            continue
        try:
            ts = parse_db_timestamp_string(ts_str)
        except (TypeError, ValueError) as exc:
            logger.debug(
                "Ungueltiger Zeitstempel in DB, Zeile uebersprungen: %r (%s)",
                ts_str,
                exc,
            )
            continue
        parsed.append((rid, ts, values))
    return parsed


def _chart_select_columns(
    cursor: sqlite3.Cursor, fields: list[str]
) -> Optional[str]:
    """Baut die SELECT-Liste fuer das Diagramm."""
    table_cols = _cached_table_columns(cursor, "projects")
    missing = [field for field in fields if field not in table_cols]
    if missing:
        log_msg(
            "Diagramm: Spalten nicht in SQLite-Tabelle: "
            + ", ".join(missing)
        )
        return None
    return "id, time, " + ", ".join(quote_identifier(f) for f in fields)


def fetch_chart_rows_initial(
    cursor: sqlite3.Cursor,
    schema: PlcDbSchema,
    last_n: Optional[int] = None,
) -> list[tuple[int, datetime, dict[str, float]]]:
    """Initiale Diagrammladung.

    Args:
        last_n: ``None`` liefert die gesamte Tabelle, sonst die letzten
            ``last_n`` Zeilen.

    Returns:
        Liste chronologisch (id ASC) sortierter Tupel, leere Liste bei DB-Fehler.
    """
    fields = plottable_numeric_fields(schema)
    if not fields:
        return []
    select_cols = _chart_select_columns(cursor, fields)
    if select_cols is None:
        return []
    try:
        if last_n is not None:
            cursor.execute(
                f"""
                SELECT {select_cols} FROM (
                    SELECT {select_cols} FROM projects
                    ORDER BY id DESC LIMIT ?
                ) sub
                ORDER BY id ASC
                """,
                (last_n,),
            )
        else:
            cursor.execute(
                f"""
                SELECT {select_cols} FROM projects
                ORDER BY id ASC
                """
            )
        return _parse_chart_rows(cursor.fetchall(), fields)
    except sqlite3.Error as exc:
        log_msg(f"SQLite-Lesefehler (Diagramm/Initial): {exc}")
        return []


def fetch_chart_rows_since(
    cursor: sqlite3.Cursor, since_id: int, schema: PlcDbSchema
) -> list[tuple[int, datetime, dict[str, float]]]:
    """Inkrementelles Nachladen: nur Zeilen mit ``id > since_id``."""
    fields = plottable_numeric_fields(schema)
    if not fields:
        return []
    select_cols = _chart_select_columns(cursor, fields)
    if select_cols is None:
        return []
    try:
        cursor.execute(
            f"""
            SELECT {select_cols} FROM projects
            WHERE id > ?
            ORDER BY id ASC
            """,
            (since_id,),
        )
        return _parse_chart_rows(cursor.fetchall(), fields)
    except sqlite3.Error as exc:
        log_msg(f"SQLite-Lesefehler (Diagramm/Delta): {exc}")
        return []
