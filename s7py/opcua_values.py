"""OPC-UA-Werte in Snap7-kompatible Python-Typen umwandeln."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def coerce_opcua_value(value: Any, datatype: str) -> object:
    """Mappt einen OPC-UA-Lesewert auf den erwarteten s7py-Datentyp."""
    if value is None:
        return None

    dt = datatype.strip()
    if dt == "Real":
        return round(float(value), 3)
    if dt == "Bool":
        return bool(value)
    if dt == "String":
        return str(value)
    if dt == "Byte":
        return int(value) & 0xFF
    if dt == "Int":
        return int(value)
    if dt == "DWord":
        return int(value) & 0xFFFFFFFF
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value
