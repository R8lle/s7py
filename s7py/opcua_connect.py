"""OPC-UA-Verbindung mit Endpoint-Erkennung und Security-Auswahl."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from s7py.opcua_import import (
    OpcUaConnectionError,
    import_opcua_client_class,
    wrap_opcua_connect_error,
)
from s7py.constants import OPCUA_SESSION_TIMEOUT_MS

NONE_POLICY_URI = "http://opcfoundation.org/UA/SecurityPolicy#None"


@dataclass(frozen=True)
class OpcUaSecurityConfig:
    """Optionale Client-Zertifikate fuer gesicherte OPC-UA-Verbindungen."""

    client_cert: str = ""
    client_key: str = ""
    client_key_password: str = ""

    def has_certs(self) -> bool:
        return bool(self.client_cert.strip() and self.client_key.strip())


def _is_security_policy_error(exc: BaseException) -> bool:
    type_name = type(exc).__name__
    if type_name in {"BadSecurityPolicyRejected", "UaStatusCodeError"}:
        return True
    msg = str(exc).lower()
    return "badsecuritypolicyrejected" in msg or "security policy" in msg


def _supports_anonymous(endpoint: Any) -> bool:
    from asyncua import ua

    tokens = getattr(endpoint, "UserIdentityTokens", None) or []
    return any(token.TokenType == ua.UserTokenType.Anonymous for token in tokens)


def _policy_class_for_uri(uri: str) -> type[Any] | None:
    from asyncua.crypto import security_policies

    for name in dir(security_policies):
        if not name.startswith("SecurityPolicy"):
            continue
        cls = getattr(security_policies, name)
        if getattr(cls, "URI", None) == uri:
            return cls
    return None


def _endpoint_sort_key(endpoint: Any) -> tuple[int, int, int]:
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    is_none = uri == NONE_POLICY_URI
    mode = getattr(getattr(endpoint, "SecurityMode", None), "value", 999)
    anon = _supports_anonymous(endpoint)
    return (0 if is_none else 1, int(mode), 0 if anon else 1)


def select_endpoint(endpoints: list[Any], security: OpcUaSecurityConfig) -> Any | None:
    """Besten Endpoint waehlen, den s7py ohne/mit Zertifikat nutzen kann."""
    if not endpoints:
        return None
    ranked = sorted(endpoints, key=_endpoint_sort_key)
    for endpoint in ranked:
        uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
        if uri == NONE_POLICY_URI and _supports_anonymous(endpoint):
            return endpoint
    if security.has_certs():
        for endpoint in ranked:
            uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
            if uri != NONE_POLICY_URI and _policy_class_for_uri(uri) is not None:
                return endpoint
    return None


def _endpoint_summary(endpoint: Any) -> str:
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    policy = uri.rsplit("#", 1)[-1] if uri else "?"
    mode = getattr(getattr(endpoint, "SecurityMode", None), "name", "?")
    url = str(getattr(endpoint, "EndpointUrl", "") or "")
    anon = "Anonymous" if _supports_anonymous(endpoint) else "Authentifizierung"
    return f"{policy} / {mode} / {anon} — {url}"


def format_no_usable_endpoint(
    endpoints: list[Any],
    security: OpcUaSecurityConfig,
) -> str:
    lines = [
        "Der OPC-UA-Server lehnt die Standard-Verbindung ab (Security Policy).",
        "",
        "Vom Server angebotene Endpoints:",
    ]
    for endpoint in endpoints:
        lines.append(f"  • {_endpoint_summary(endpoint)}")
    lines.extend(
        [
            "",
            "Moegliche Loesungen:",
            "  1. In TIA Portal unter OPC UA → Server-Sicherheit die Policy "
            '"None" und anonymen Zugriff aktivieren (Testbetrieb).',
            "  2. Oder Client-Zertifikat in s7py_db.json eintragen:",
            '       "opcua_client_cert": "/pfad/client.der"',
            '       "opcua_client_key": "/pfad/client_key.pem"',
            "     (Zertifikat muss in TIA als vertrauenswuerdig hinterlegt sein.)",
        ]
    )
    if security.has_certs():
        lines.append(
            "  Hinweis: Zertifikate sind konfiguriert, passen aber zu keinem "
            "Server-Endpoint."
        )
    return "\n".join(lines)


def _set_client_endpoint_url(client: Any, endpoint_url: str) -> None:
    client.aio_obj._server_url = urlparse(endpoint_url)


def _apply_none_policy(client: Any, endpoint: Any) -> None:
    from asyncua.crypto.security_policies import SecurityPolicyNone

    policy = SecurityPolicyNone(mode=endpoint.SecurityMode)
    client.aio_obj.security_policy = policy
    client.aio_obj.uaclient.security_policy = policy
    _set_client_endpoint_url(client, endpoint.EndpointUrl)


def _apply_secure_policy(client: Any, endpoint: Any, security: OpcUaSecurityConfig) -> None:
    policy_cls = _policy_class_for_uri(str(endpoint.SecurityPolicyUri or ""))
    if policy_cls is None:
        raise OpcUaConnectionError(
            f"Unbekannte Security Policy: {endpoint.SecurityPolicyUri}"
        )
    _set_client_endpoint_url(client, endpoint.EndpointUrl)
    password = security.client_key_password.strip() or None
    server_cert = getattr(endpoint, "ServerCertificate", None)
    client.set_security(
        policy_cls,
        security.client_cert.strip(),
        security.client_key.strip(),
        password,
        server_cert,
        endpoint.SecurityMode,
    )


def _dispose_client(client: Any | None) -> None:
    """Client freigeben; beendet den asyncua-ThreadLoop."""
    if client is None:
        return
    try:
        client.disconnect()
    except Exception:
        pass


def _create_client(url: str) -> Any:
    Client = import_opcua_client_class()
    client = Client(url)
    _prepare_opcua_client(client)
    return client


def _prepare_opcua_client(client: Any) -> None:
    """Client-Defaults fuer SPS-Server (z. B. S7-1500 Session-Timeout 30s)."""
    aio = client.aio_obj
    aio.session_timeout = OPCUA_SESSION_TIMEOUT_MS


def connect_opcua_sync_client(
    endpoint_url: str,
    *,
    security: OpcUaSecurityConfig | None = None,
) -> Any:
    """Neuen verbundenen asyncua-Sync-Client zurueckgeben."""
    from s7py.db import load_opcua_security_config

    url = (endpoint_url or "").strip()
    sec = security if security is not None else load_opcua_security_config()
    client = _create_client(url)

    try:
        client.connect()
        return client
    except OpcUaConnectionError:
        _dispose_client(client)
        raise
    except Exception as exc:
        if not _is_security_policy_error(exc):
            _dispose_client(client)
            raise wrap_opcua_connect_error(exc, url) from exc
        _dispose_client(client)

    client = _create_client(url)
    try:
        endpoints = client.connect_and_get_server_endpoints()
        endpoint = select_endpoint(endpoints, sec)
        if endpoint is None:
            raise OpcUaConnectionError(format_no_usable_endpoint(endpoints, sec))
        uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
        if uri == NONE_POLICY_URI:
            _apply_none_policy(client, endpoint)
        else:
            if not sec.has_certs():
                raise OpcUaConnectionError(format_no_usable_endpoint(endpoints, sec))
            _apply_secure_policy(client, endpoint, sec)
        client.connect()
        return client
    except OpcUaConnectionError:
        _dispose_client(client)
        raise
    except Exception as exc:
        _dispose_client(client)
        raise wrap_opcua_connect_error(exc, url) from exc
