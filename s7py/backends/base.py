"""Gemeinsames Interface fuer SPS-Lese-Backends."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import Optional, Protocol, runtime_checkable

from s7py.schema import DbItem

from s7py.constants import (
    PLC_TRANSPORT_OPCUA,
    PLC_TRANSPORT_SNAP7,
    PLC_TRANSPORTS,
)
class PlcBackend(Protocol):
    """Protokoll fuer Snap7- und OPC-UA-Anbindungen."""

    @property
    def transport(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    def connect(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        endpoint_url: str = "",
    ) -> None: ...

    def disconnect(self) -> None: ...

    def is_connected(self, lock: Optional[threading.RLock] = None) -> bool: ...

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
    ) -> Optional[SimpleNamespace]: ...

    def status_detail(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        db_number: int = 0,
        endpoint_url: str = "",
    ) -> str: ...


class AbstractPlcBackend(ABC):
    """Basisklasse mit gemeinsamer Struktur fuer konkrete Backends."""

    @property
    @abstractmethod
    def transport(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @abstractmethod
    def connect(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        endpoint_url: str = "",
    ) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self, lock: Optional[threading.RLock] = None) -> bool: ...

    @abstractmethod
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
    ) -> Optional[SimpleNamespace]: ...

    @abstractmethod
    def status_detail(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        db_number: int = 0,
        endpoint_url: str = "",
    ) -> str: ...
