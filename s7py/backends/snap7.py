"""Snap7-Backend (ISO-on-TCP, S7-Datenbaustein)."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Optional

import snap7.client

from s7py.backends.base import AbstractPlcBackend, PLC_TRANSPORT_SNAP7
from s7py.plc import PLC_IO_ERRORS, plc_is_connected, read_plc_db_with_retry
from s7py.schema import DbItem


class Snap7Backend(AbstractPlcBackend):
    """Liest SPS-Datenbausteine ueber python-snap7."""

    def __init__(self) -> None:
        self._client = snap7.client.Client()

    @property
    def client(self) -> snap7.client.Client:
        """Zugriff auf den Snap7-Client (Legacy / Tests)."""
        return self._client

    @property
    def transport(self) -> str:
        return PLC_TRANSPORT_SNAP7

    @property
    def display_name(self) -> str:
        return "Snap7"

    def connect(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        endpoint_url: str = "",
    ) -> None:
        del endpoint_url
        self._client.connect(address, rack, slot)

    def disconnect(self) -> None:
        try:
            self._client.disconnect()
        except PLC_IO_ERRORS:
            pass

    def is_connected(self, lock: Optional[threading.RLock] = None) -> bool:
        return plc_is_connected(self._client, lock)

    def read_with_retry(
        self,
        db_number: int,
        length: int,
        items: list[DbItem],
        *,
        address: str,
        rack: int = 0,
        slot: int = 0,
        lock: Optional[threading.RLock] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Optional[SimpleNamespace]:
        return read_plc_db_with_retry(
            self._client,
            db_number,
            length,
            items,
            plc_address=address,
            plc_rack=rack,
            plc_slot=slot,
            plc_lock=lock,
            stop_event=stop_event,
        )

    def status_detail(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        db_number: int = 0,
        endpoint_url: str = "",
    ) -> str:
        del endpoint_url
        return (
            f"Snap7: {address}  |  Rack {rack}  Slot {slot}  |  SPS-DB{db_number}"
        )

    def connection_log_detail(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        db_number: int = 0,
        endpoint_url: str = "",
    ) -> str:
        del endpoint_url, db_number
        return (
            f"Verbindungsmethode: Snap7 ISO-on-TCP | "
            f"Weg: Rack/Slot-Verbindung | "
            f"{address} Rack {rack} Slot {slot}"
        )
