"""Snap7-Lesen und DB-Groessenberechnung."""

import threading
import time
from types import SimpleNamespace
from typing import Optional

import snap7.client
from snap7.type import Areas
from snap7.util import get_bool, get_byte, get_dword, get_int, get_real, get_string

from s7py.constants import (
    PLC_IO_ERRORS,
    PLC_RACK,
    PLC_READ_BASE_DELAY_S,
    PLC_READ_MAX_ATTEMPTS,
    PLC_SLOT,
)
from s7py.log import log_msg
from s7py.schema import DbItem

offsets = {
    "Bool"  : 2,
    "Byte"  : 1,
    "Int"   : 2,
    "Real"  : 4,
    "DWord" : 4,
    "String": 256
    }
def DBRead(
    plc: snap7.client.Client, db_num: int, length: int, dbitems: list[DbItem]
) -> SimpleNamespace:
    """Liest einen Datenbaustein der SPS und gibt einen Namespace mit Item-Attributen zurueck.

    Erwartet, dass ``plc`` bereits verbunden ist. Liest in einem Schwung
    ``length`` Bytes ab Offset 0 aus DB ``db_num`` und zerlegt sie gemaess
    ``dbitems`` (Schema siehe :func:`parse_db_layout`). Die einzelnen
    Felder erscheinen als Attribute am Rueckgabe-Namespace, z.B.
    ``ns.Count`` oder ``ns.Temperature``.
    """
    data = plc.read_area(Areas.DB, db_num, 0, length)
    obj = SimpleNamespace()
    for item in dbitems:
        value = None
        datatype = item.datatype
        try:
            byte_part, bit_part = item.bytebit.split('.')
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                f"Ungültiges bytebit-Format in Item {item.name}: {item.bytebit}"
            ) from exc
        offset = int(byte_part)

        if datatype == 'Real':
            value = get_real(data,offset)

        elif datatype == 'Bool':
            bit = int(bit_part)
            value = get_bool(data,offset,bit)

        elif datatype == 'DWord':
            value = get_dword(data, offset)

        elif datatype == 'Int':
            value = get_int(data, offset)

        elif datatype == 'Byte':
            value = get_byte(data, offset)

        elif datatype == 'String':
            value = get_string(data, offset)
        else:
            raise ValueError(f"Nicht unterstuetzter Datentyp in DBRead: {datatype}")
        
        setattr(obj, item.name, value)

    return obj


def _reconnect_plc(
    plc: snap7.client.Client,
    plc_address: str,
    plc_rack: int,
    plc_slot: int,
    plc_lock: Optional[threading.RLock] = None,
) -> None:
    """Hilfsfunktion zum SPS-Reconnect mit oder ohne Lock."""
    if plc_lock is None:
        try:
            plc.disconnect()
        except PLC_IO_ERRORS:
            pass
        try:
            plc.connect(plc_address, plc_rack, plc_slot)
        except PLC_IO_ERRORS:
            pass
    else:
        with plc_lock:
            try:
                plc.disconnect()
            except PLC_IO_ERRORS:
                pass
            try:
                plc.connect(plc_address, plc_rack, plc_slot)
            except PLC_IO_ERRORS:
                pass


def plc_is_connected(
    plc: snap7.client.Client,
    plc_lock: Optional[threading.RLock] = None,
) -> bool:
    """Prueft, ob die Snap7-Verbindung noch aktiv ist."""
    try:
        if plc_lock is None:
            return bool(plc.get_connected())
        with plc_lock:
            return bool(plc.get_connected())
    except PLC_IO_ERRORS:
        return False


def read_plc_db_with_retry(
    plc: snap7.client.Client,
    db_num: int,
    length: int,
    items: list[DbItem],
    *,
    plc_address: Optional[str] = None,
    plc_rack: int = PLC_RACK,
    plc_slot: int = PLC_SLOT,
    max_attempts: int = PLC_READ_MAX_ATTEMPTS,
    base_delay_s: float = PLC_READ_BASE_DELAY_S,
    plc_lock: Optional[threading.RLock] = None,
    stop_event: Optional[threading.Event] = None,
) -> Optional[SimpleNamespace]:
    """Liest die SPS-DB mit Retry-Logik bei Verbindungs-/Timeout-Fehlern.

    Bei wiederholten Fehlern (ab dem 3. Versuch, jedem zweiten) wird
    ``disconnect()`` + ``connect()`` versucht — sofern ``plc_address`` gesetzt
    ist. Wenn ``plc_lock`` uebergeben wird, sind alle SPS-Operationen
    (Lesen wie Wiederverbinden) damit serialisiert. Ein gesetztes
    ``stop_event`` bricht weitere Retries sofort ab, damit der Worker
    beim Stoppen nicht erst die volle Retry-Kaskade abwarten muss.

    Returns:
        Ein :class:`types.SimpleNamespace` mit den gelesenen Werten als
        Attribute, oder ``None`` falls nach ``max_attempts`` Versuchen kein
        erfolgreicher Lesevorgang moeglich war (Fehler wird geloggt) oder
        der Vorgang per ``stop_event`` abgebrochen wurde.
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            if plc_lock is None:
                return DBRead(plc, db_num, length, items)
            with plc_lock:
                return DBRead(plc, db_num, length, items)
        except PLC_IO_ERRORS as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            if stop_event is not None and stop_event.is_set():
                return None
            if plc_address is not None and attempt >= 3 and attempt % 2 == 1:
                _reconnect_plc(plc, plc_address, plc_rack, plc_slot, plc_lock)
            if stop_event is not None:
                if stop_event.wait(base_delay_s * attempt):
                    return None
            else:
                time.sleep(base_delay_s * attempt)
    log_msg(f"SPS-Lesefehler (nach {max_attempts} Versuchen): {last_exc}")
    return None

def get_db_size(
    items: list[DbItem],
) -> int:
    """Berechnet die minimal noetige Lesegroesse (Bytes) fuer einen DB.

    Nutzt ``max(offset + typgroesse)`` ueber alle Items. Wirft
    ``ValueError``, wenn ein Item einen unbekannten Datentyp hat.
    """
    max_end = 0
    for item in items:
        if (item.bytebit or "").strip().lower() == "opcua":
            continue
        datatype = item.datatype
        if item.size > 0:
            field_size = item.size
        elif datatype not in offsets:
            raise ValueError(f"Unbekannter Datentyp: {datatype}")
        else:
            field_size = int(offsets[datatype])
        byte_offset = int(float(item.bytebit))
        end_pos = byte_offset + field_size
        if end_pos > max_end:
            max_end = end_pos
    return max_end
