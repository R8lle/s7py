"""Erzeugt das passende SPS-Backend."""

from __future__ import annotations

from s7py.backends.base import PlcBackend
from s7py.backends.opcua import OpcUaBackend
from s7py.backends.snap7 import Snap7Backend
from s7py.constants import PLC_TRANSPORT_OPCUA
from s7py.db import normalize_plc_transport


def create_backend(transport: str | None = None) -> PlcBackend:
    """Neues Backend fuer den gewaehlten Transport erzeugen."""
    kind = normalize_plc_transport(transport)
    if kind == PLC_TRANSPORT_OPCUA:
        return OpcUaBackend()
    return Snap7Backend()
