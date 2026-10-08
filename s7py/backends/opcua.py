"""OPC-UA-Backend (Verbindung und NodeId-Lesen)."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Optional

from s7py.backends.base import AbstractPlcBackend, PLC_TRANSPORT_OPCUA
from s7py.constants import PLC_READ_BASE_DELAY_S, PLC_READ_MAX_ATTEMPTS
from s7py.log import log_msg
from s7py.opcua_connect import OpcUaSecurityConfig, connect_opcua_sync_client
from s7py.opcua_import import (
    OpcUaConfigError,
    OpcUaError,
    wrap_opcua_connect_error,
)
from s7py.opcua_values import coerce_opcua_value
from s7py.schema import DbItem


# Abwaertskompatibilitaet fuer aeltere Importe
OpcUaNotReadyError = OpcUaConfigError


class OpcUaBackend(AbstractPlcBackend):
    """OPC-UA-Client — liest konfigurierte NodeIds aus dem Schema."""

    def __init__(self) -> None:
        self._endpoint_url = ""
        self._connected = False
        self._client = None
        self._connection_info = None
        self._security: OpcUaSecurityConfig | None = None

    @property
    def transport(self) -> str:
        return PLC_TRANSPORT_OPCUA

    @property
    def display_name(self) -> str:
        return "OPC UA"

    def connect(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        endpoint_url: str = "",
        security: OpcUaSecurityConfig | None = None,
    ) -> None:
        del address, rack, slot
        url = (endpoint_url or "").strip()
        if not url:
            raise ValueError("OPC-UA-Endpoint fehlt (z. B. opc.tcp://192.168.0.10:4840).")

        self.disconnect()
        sec = security if security is not None else self._security
        try:
            def _do_connect():
                return connect_opcua_sync_client(url, security=sec)

            try:
                from s7py.macos_local_network import (
                    connect_with_local_network_retry,
                    is_frozen_macos_app,
                )

                if is_frozen_macos_app():
                    self._client, self._connection_info = connect_with_local_network_retry(
                        _do_connect
                    )
                else:
                    self._client, self._connection_info = _do_connect()
            except ImportError:
                self._client, self._connection_info = _do_connect()
        except Exception as exc:
            self._client = None
            self._connection_info = None
            self._connected = False
            raise wrap_opcua_connect_error(exc, url) from exc
        self._endpoint_url = url
        self._security = sec
        self._connected = True

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self._client = None
        self._connection_info = None
        self._connected = False

    def is_connected(self, lock: Optional[threading.RLock] = None) -> bool:
        del lock
        return self._connected and self._client is not None

    def _read_snapshot(self, items: list[DbItem]) -> SimpleNamespace:
        if self._client is None:
            raise ConnectionError("OPC-UA-Client nicht verbunden.")
        mapped = [item for item in items if item.node_id.strip()]
        if not mapped:
            raise OpcUaConfigError(
                "OPC UA: Keine NodeIds konfiguriert. "
                "Bitte Menue Datei -> OPC UA Variablen..."
            )
        obj = SimpleNamespace()
        for item in mapped:
            node = self._client.get_node(item.node_id.strip())
            raw = node.read_value()
            setattr(obj, item.name, coerce_opcua_value(raw, item.datatype))
        return obj

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
        del db_number, length, rack, slot
        if not self.is_connected():
            return None

        last_exc: Exception | None = None
        for attempt in range(1, PLC_READ_MAX_ATTEMPTS + 1):
            try:
                if lock is None:
                    return self._read_snapshot(items)
                with lock:
                    return self._read_snapshot(items)
            except Exception as exc:
                last_exc = exc
                if attempt >= PLC_READ_MAX_ATTEMPTS:
                    break
                if stop_event is not None and stop_event.is_set():
                    return None
                if address and attempt >= 3 and attempt % 2 == 1:
                    self._try_reconnect(address)
                delay = PLC_READ_BASE_DELAY_S * attempt
                if stop_event is not None:
                    if stop_event.wait(delay):
                        return None
                else:
                    time.sleep(delay)
        log_msg(f"OPC-UA-Lesefehler (nach {PLC_READ_MAX_ATTEMPTS} Versuchen): {last_exc}")
        return None

    def _try_reconnect(self, endpoint_url: str) -> None:
        try:
            self.disconnect()
            self.connect("", endpoint_url=endpoint_url)
        except Exception:
            pass

    def status_detail(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        db_number: int = 0,
        endpoint_url: str = "",
    ) -> str:
        del address, rack, slot, db_number
        url = endpoint_url or self._endpoint_url or "?"
        return f"OPC UA: {url}"

    def connection_log_detail(
        self,
        address: str,
        *,
        rack: int = 0,
        slot: int = 0,
        db_number: int = 0,
        endpoint_url: str = "",
    ) -> str:
        del address, rack, slot, db_number, endpoint_url
        if self._connection_info is None:
            return ""
        return self._connection_info.log_message()
