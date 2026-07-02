"""Hintergrund-Thread: SPS lesen und in SQLite schreiben."""

import sqlite3
import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

from s7py.constants import (
    DEFAULT_POLL_INTERVAL_S,
    PLC_DB_NUMBER,
    PLC_RACK,
    PLC_SLOT,
    TIMESTAMP_FORMAT_DB,
)
from s7py.db import create_connection, create_newline, normalize_poll_interval_s
from s7py.log import log_msg, logger, notify_count_gap, push_live_snapshot, show_msg
from s7py.plc import read_plc_db_with_retry
from s7py.schema import DbItem, PlcDbSchema

def format_plc_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def round_plc_value(value: object, datatype: str) -> object:
    if datatype == "Real" and isinstance(value, (int, float)):
        return round(float(value), 3)
    return value


def build_insert_row(meh: SimpleNamespace, schema: PlcDbSchema) -> tuple:
    values: list[object] = [datetime.now().strftime(TIMESTAMP_FORMAT_DB)]
    for name in schema.sqlite_columns:
        item = next((it for it in schema.items if it.name == name), None)
        if item is None:
            raise ValueError(f"Item '{name}' nicht im Schema gefunden")
        values.append(round_plc_value(getattr(meh, name), item.datatype))
    return tuple(values)


def detect_count_gap(old_count: int, count_value: int) -> int | None:
    """Ermittelt verpasste Messpunkte; None wenn keine Luecke."""
    if old_count > 0 and count_value > old_count and count_value - old_count > 1:
        return count_value - old_count - 1
    return None


def write_data_to_db(
    database: str,
    plc,
    DBlength: int,
    items: list[DbItem],
    schema: PlcDbSchema,
    stop_event: threading.Event,
    plc_address: str,
    plc_lock: Optional[threading.RLock] = None,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    plc_rack: int = PLC_RACK,
    plc_slot: int = PLC_SLOT,
    plc_db_number: int = PLC_DB_NUMBER,
) -> None:
    """Worker-Thread: liest die SPS-DB zyklisch und schreibt neue Messpunkte nach SQLite.

    Schreibt nur, wenn ``Count`` gestiegen ist; erkennt Count-Ruecksprung
    (SPS-Reset) und setzt den internen Vergleichswert zurueck. Beendet
    sich, sobald ``stop_event`` gesetzt wird.

    Unerwartete Fehler (z.B. ``ValueError`` aus ``get_string`` bei
    korruptem String-Header) beenden den Thread nicht mehr still,
    sondern werden in GUI-Meldungsbox und Logfile gemeldet.
    """
    conn = create_connection(database)
    if conn is None:
        log_msg("Fehler: Schreibverbindung zur DB konnte nicht erstellt werden.")
        return
    cursor = conn.cursor()

    try:
        OldCount = 0
        # Fortlaufende Abfrage-Nr aus der DB initialisieren (rein fuer Anzeige/Log).
        try:
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM projects")
            i = int(cursor.fetchone()[0])
        except (sqlite3.Error, TypeError, ValueError) as exc:
            log_msg(f"Konnte Zaehler nicht aus DB initialisieren: {exc}")
            i = 0
        if i > 0:
            log_msg(f"Abfrage-Nr startet bei {i + 1} (letzte vorhandene id = {i}).")
        interval_s = normalize_poll_interval_s(poll_interval_s)
        while not stop_event.is_set():
            meh = read_plc_db_with_retry(
                plc,
                plc_db_number,
                DBlength,
                items,
                plc_address=plc_address,
                plc_rack=plc_rack,
                plc_slot=plc_slot,
                plc_lock=plc_lock,
                stop_event=stop_event,
            )
            if meh is None:
                stop_event.wait(0.5)
                continue

            count_value = getattr(meh, schema.count_field)
            if count_value < OldCount:
                log_msg(
                    f"Count-Ruecksprung erkannt: {OldCount} -> {count_value} "
                    f"(SPS-Reset?). Aufzeichnung wird fortgesetzt."
                )
                OldCount = -1

            if count_value > OldCount:
                # Luecke erkennen: Count ist um mehr als 1 gestiegen, obwohl
                # bereits ein Messpunkt erfasst wurde (OldCount > 0). Das deutet
                # darauf hin, dass die SPS schneller zaehlt als die Abfrage pollt
                # und Zwischenwerte nicht erfasst wurden. Reset-Faelle (OldCount
                # == -1) und der allererste Messpunkt (OldCount == 0) loesen
                # bewusst keine Warnung aus.
                missed = detect_count_gap(OldCount, count_value)
                if missed is not None:
                    notify_count_gap(missed, interval_s)
                i = i + 1
                msg_parts = [
                    f"{name}={format_plc_value(getattr(meh, name))}"
                    for name in schema.sqlite_columns
                ]
                show_msg(f"Abfrage Nr {i} | " + " | ".join(msg_parts))
                live_values = {
                    name: getattr(meh, name) for name in schema.live_fields
                }
                push_live_snapshot(live_values)
                OldCount = count_value

                newline = build_insert_row(meh, schema)
                try:
                    create_newline(cursor, conn, newline, schema)
                except sqlite3.Error as db_exc:
                    log_msg(f"Datensatz konnte nicht gespeichert werden: {db_exc}")
            stop_event.wait(interval_s)
    except Exception as exc:
        # Letzte Verteidigungslinie: Daemon-Threads sterben sonst still,
        # der Nutzer saehe nur den erloschenen REC-Indikator.
        log_msg(f"Aufzeichnung unerwartet beendet: {exc!r}")
        logger.exception("Unerwarteter Fehler im Aufzeichnungs-Thread")
    finally:
        conn.close()
