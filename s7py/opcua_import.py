"""asyncua-Import und unterscheidbare OPC-UA-Fehlermeldungen."""

from __future__ import annotations

import importlib.util
import sys
from typing import Any


class OpcUaError(Exception):
    """Basis fuer OPC-UA-Fehler in s7py."""


class OpcUaDependencyError(OpcUaError):
    """Paket asyncua fehlt oder laesst sich nicht laden."""


class OpcUaConfigError(OpcUaError):
    """OPC-UA-Konfiguration unvollstaendig."""


class OpcUaConnectionError(OpcUaError):
    """OPC-UA-Server nicht erreichbar oder Verbindung abgelehnt."""


# Abwaertskompatibilitaet (alter Name fuer Konfigurationsfehler)
OpcUaNotReadyError = OpcUaConfigError


def asyncua_is_installed() -> bool:
    """True, wenn das Paket asyncua in der aktuellen Python-Umgebung vorhanden ist."""
    return importlib.util.find_spec("asyncua") is not None


def import_opcua_client_class() -> type[Any]:
    """asyncua.sync.Client laden oder eine spezifische OpcUaDependencyError ausloesen."""
    if not asyncua_is_installed():
        exe = sys.executable
        raise OpcUaDependencyError(
            "Das Paket 'asyncua' ist in dieser Python-Umgebung nicht installiert.\n\n"
            f"Python: {exe}\n"
            f"Installation: {exe} -m pip install asyncua\n\n"
            "Hinweis: Wenn pip install bereits erfolgreich war, starten Sie s7py "
            "mit demselben Python-Interpreter."
        )
    try:
        from asyncua.sync import Client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OpcUaDependencyError(
            "Das Paket 'asyncua' ist vorhanden, laesst sich aber nicht laden.\n\n"
            f"Python: {sys.executable}\n"
            f"Details: {exc}\n\n"
            "Moegliche Loesung: pip install --upgrade asyncua"
        ) from exc
    return Client


def _looks_like_unreachable_server(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            ConnectionRefusedError,
            ConnectionResetError,
            TimeoutError,
            BrokenPipeError,
            OSError,
        ),
    ):
        return True
    type_name = type(exc).__name__
    module = type(exc).__module__.lower()
    if type_name.startswith("Ua") or "uaerror" in module:
        return True
    msg = str(exc).lower()
    keywords = (
        "connection refused",
        "connection reset",
        "timed out",
        "timeout",
        "no route to host",
        "network is unreachable",
        "host unreachable",
        "actively refused",
        "socket",
        "connect call failed",
        "server uri",
        "endpoint",
        "badconnection",
        "badtimeout",
        "badnotconnected",
    )
    return any(word in msg for word in keywords)


def format_opcua_connect_error(exc: BaseException, endpoint: str) -> str:
    """Verbindungsfehler fuer die UI — ohne asyncua-Fehlmeldung bei Server-Problemen."""
    if isinstance(exc, OpcUaError):
        return str(exc)
    url = (endpoint or "").strip() or "?"
    type_name = type(exc).__name__
    msg_lower = str(exc).lower()
    if "badsecuritypolicyrejected" in msg_lower or "security policy" in msg_lower:
        return (
            f"OPC-UA-Sicherheit vom Server abgelehnt: {url}\n\n"
            "Der Server erlaubt die aktuelle Security Policy nicht. "
            "s7py versucht automatisch einen passenden Endpoint zu waehlen; "
            "wenn diese Meldung bleibt, pruefen Sie die OPC-UA-Sicherheit in TIA "
            '(Policy "None" aktivieren) oder hinterlegen Sie Client-Zertifikate '
            "in s7py_db.json.\n\n"
            f"Details ({type_name}): {exc}"
        )
    if _looks_like_unreachable_server(exc):
        return (
            f"OPC-UA-Server nicht erreichbar: {url}\n\n"
            "Kein OPC-UA-Server antwortet (SPS aus, falsche Adresse/Port, "
            "OPC UA in TIA nicht aktiviert oder Netzwerk blockiert?).\n\n"
            f"Details ({type_name}): {exc}"
        )
    return f"OPC-UA-Verbindung fehlgeschlagen ({type_name}): {exc}"


def wrap_opcua_connect_error(exc: BaseException, endpoint: str) -> OpcUaError:
    """Verbindungsfehler als OpcUaConnectionError fuer den Connect-Pfad."""
    if isinstance(exc, OpcUaError):
        return exc
    return OpcUaConnectionError(format_opcua_connect_error(exc, endpoint))
