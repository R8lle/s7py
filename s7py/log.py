"""Logging und thread-sichere GUI-Queues."""

import logging
import queue
import sys
from logging.handlers import RotatingFileHandler

from s7py.constants import (
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    LOG_FILE_PATH,
    TIMESTAMP_FORMAT_DB,
)

def setup_file_logging() -> logging.Logger:
    """Konfiguriert den Modul-Logger ``s7py``.

    Zwei Handler:
    - ``RotatingFileHandler`` (Level INFO) auf ``LOG_FILE_PATH`` mit
      ``maxBytes`` / ``backupCount`` aus den Konstanten oben.
    - ``StreamHandler`` (Level WARNING) auf stderr, damit Fehler auch
      ohne Logdatei sichtbar sind.

    Idempotent: mehrfache Aufrufe legen keine doppelten Handler an.
    """
    log = logging.getLogger("s7py")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt=TIMESTAMP_FORMAT_DB,
    )
    try:
        fh = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        # Wenn das Anlegen der Logdatei scheitert (Rechte, read-only FS),
        # darf das die App nicht abreissen — die GUI hat ihre eigene Anzeige.
        pass
    sh = logging.StreamHandler(stream=sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    return log


LOG_QUEUE: "queue.Queue[str]" = queue.Queue()
# Letzte SPS-Messwerte fuer die Live-Anzeige (Feldname -> Wert).
LIVE_VALUES_QUEUE: "queue.Queue[dict[str, object]]" = queue.Queue()
# Count-Luecken: (verpasste Messpunkte, aktuelles Poll-Intervall in Sekunden).
COUNT_GAP_QUEUE: "queue.Queue[tuple[int, float]]" = queue.Queue()


def log_msg(message: object) -> None:
    """Threadsicheres Logging: Nachricht in die GUI-Queue legen und ins Logfile schreiben.

    Nutzen: Nutzeraktionen (Connect/Stop/Export/…) und Fehler. Daten-
    Zeilen (Messpunkte) gehen stattdessen ueber :func:`_show_msg`, damit
    das Logfile nicht durch hochfrequente Messwerte aufgeblaeht wird.

    ``LOG_QUEUE`` ist unbeschraenkt; ``put_nowait`` wirft praktisch nie
    ``queue.Full``. Der Fallback ist defensiv (z.B. falls die Queue
    spaeter mit ``maxsize`` betrieben wird).
    """
    text = str(message)
    try:
        LOG_QUEUE.put_nowait(text)
    except queue.Full:
        print(text)
    logger.info(text)


def show_msg(message: object) -> None:
    """Wie :func:`log_msg`, aber **nur** GUI-Meldungsbox, kein Logfile.

    Gedacht fuer hochfrequente Datenzeilen aus dem Worker-Thread (z.B.
    einen Eintrag pro Messpunkt). Diese sollen in der Meldungsbox
    sichtbar sein, aber das Diagnose-Logfile nicht beschreiben.
    """
    try:
        LOG_QUEUE.put_nowait(str(message))
    except queue.Full:
        pass


def push_live_snapshot(values: dict[str, object]) -> None:
    """Threadsicher: letzte SPS-Messwerte fuer die GUI-Live-Anzeige.

    Wird vom Worker-Thread aufgerufen, im Hauptthread (Tkinter) abgeholt.
    """
    try:
        LIVE_VALUES_QUEUE.put_nowait(values)
    except queue.Full:
        pass


def notify_count_gap(missed: int, poll_interval_s: float) -> None:
    """Count-Luecke melden (Log + Hinweis-Queue fuer die GUI)."""
    log_msg(
        f"Count-Luecke erkannt: {missed} Messpunkt(e) nicht erfasst — "
        f"SPS schneller als Abfrageintervall ({poll_interval_s:.3f} s)?"
    )
    try:
        COUNT_GAP_QUEUE.put_nowait((int(missed), float(poll_interval_s)))
    except queue.Full:
        pass


logger = setup_file_logging()
