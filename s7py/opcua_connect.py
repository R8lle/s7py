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
class OpcUaConnectionInfo:
    """Beschreibt den erfolgreichen OPC-UA-Verbindungsweg fuer Logs."""

    method: str
    path: str
    policy: str
    security_mode: str
    identity: str
    endpoint_url: str

    def log_message(self) -> str:
        return (
            f"Verbindungsmethode: {self.method} | "
            f"Weg: {self.path} | "
            f"Policy {self.policy}, Modus {self.security_mode}, {self.identity} | "
            f"Endpoint {self.endpoint_url}"
        )


@dataclass(frozen=True)
class OpcUaSecurityConfig:
    """OPC-UA-Sicherheit: optional Zertifikat und/oder Benutzer/Passwort."""

    client_cert: str = ""
    client_key: str = ""
    client_key_password: str = ""
    username: str = ""
    password: str = ""

    def has_certs(self) -> bool:
        return bool(self.client_cert.strip() and self.client_key.strip())

    def has_credentials(self) -> bool:
        return bool(self.username.strip())


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


def _supports_username(endpoint: Any) -> bool:
    from asyncua import ua

    tokens = getattr(endpoint, "UserIdentityTokens", None) or []
    return any(token.TokenType == ua.UserTokenType.UserName for token in tokens)


def _policy_class_for_uri(uri: str) -> type[Any] | None:
    from asyncua.crypto import security_policies

    for name in dir(security_policies):
        if not name.startswith("SecurityPolicy"):
            continue
        cls = getattr(security_policies, name)
        if getattr(cls, "URI", None) == uri:
            return cls
    return None


def _endpoint_sort_key(endpoint: Any, security: OpcUaSecurityConfig) -> tuple[int, int, int]:
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    is_none = uri == NONE_POLICY_URI
    mode = getattr(getattr(endpoint, "SecurityMode", None), "value", 999)
    if security.has_credentials():
        identity_rank = 0 if _supports_username(endpoint) else 1
    else:
        identity_rank = 0 if _supports_anonymous(endpoint) else 1
    return (0 if is_none else 1, int(mode), identity_rank)


def select_endpoint(endpoints: list[Any], security: OpcUaSecurityConfig) -> Any | None:
    """Besten Endpoint waehlen (Anonymous, UserName oder gesichert mit Zertifikat)."""
    if not endpoints:
        return None
    ranked = sorted(endpoints, key=lambda ep: _endpoint_sort_key(ep, security))

    if security.has_credentials():
        for endpoint in ranked:
            uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
            if uri == NONE_POLICY_URI and _supports_username(endpoint):
                return endpoint
        if security.has_certs():
            for endpoint in ranked:
                uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
                if (
                    uri != NONE_POLICY_URI
                    and _policy_class_for_uri(uri) is not None
                    and _supports_username(endpoint)
                ):
                    return endpoint
        return None

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


def _endpoint_identity_summary(endpoint: Any) -> str:
    parts: list[str] = []
    if _supports_anonymous(endpoint):
        parts.append("Anonymous")
    if _supports_username(endpoint):
        parts.append("UserName")
    return ", ".join(parts) if parts else "keine"


def _path_label_for_endpoint(
    endpoint: Any,
    security: OpcUaSecurityConfig,
    *,
    after_policy_error: bool = False,
) -> str:
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    is_none = uri == NONE_POLICY_URI
    if security.has_credentials():
        if is_none:
            return "Endpoint-Auswahl mit Benutzer/Passwort (Policy None)"
        return "Endpoint-Auswahl mit Benutzer/Passwort und Client-Zertifikat"
    if after_policy_error:
        return "Endpoint-Auswahl nach Policy-Fehler (anonym, Policy None)"
    if is_none:
        return "Endpoint-Auswahl (anonym, Policy None)"
    return "Endpoint-Auswahl mit Client-Zertifikat (anonym)"


def _connection_info_from_endpoint(
    endpoint: Any,
    security: OpcUaSecurityConfig,
    *,
    path: str,
) -> OpcUaConnectionInfo:
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    policy = uri.rsplit("#", 1)[-1] if uri else "?"
    mode = getattr(getattr(endpoint, "SecurityMode", None), "name", "?")
    if security.has_credentials():
        identity = f"Benutzer '{security.username.strip()}'"
    else:
        identity = "anonym"
    url = str(getattr(endpoint, "EndpointUrl", "") or "")
    return OpcUaConnectionInfo(
        method="OPC UA",
        path=path,
        policy=policy,
        security_mode=mode,
        identity=identity,
        endpoint_url=url,
    )


def _quick_anonymous_connection_info(endpoint_url: str) -> OpcUaConnectionInfo:
    return OpcUaConnectionInfo(
        method="OPC UA",
        path="Schnellverbindung (anonym, ohne Endpoint-Auswahl)",
        policy="(Standard)",
        security_mode="None",
        identity="anonym",
        endpoint_url=endpoint_url,
    )


def _endpoint_summary(endpoint: Any) -> str:
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    policy = uri.rsplit("#", 1)[-1] if uri else "?"
    mode = getattr(getattr(endpoint, "SecurityMode", None), "name", "?")
    url = str(getattr(endpoint, "EndpointUrl", "") or "")
    return f"{policy} / {mode} / {_endpoint_identity_summary(endpoint)} — {url}"


def _server_offers_none_policy(endpoints: list[Any]) -> bool:
    return any(
        str(getattr(ep, "SecurityPolicyUri", "") or "") == NONE_POLICY_URI
        for ep in endpoints
    )


def format_no_usable_endpoint(
    endpoints: list[Any],
    security: OpcUaSecurityConfig,
) -> str:
    lines = [
        "Der OPC-UA-Server bietet keinen passenden Endpoint fuer die s7py-Konfiguration.",
        "",
        "Vom Server angebotene Endpoints:",
    ]
    for endpoint in endpoints:
        lines.append(f"  • {_endpoint_summary(endpoint)}")
    lines.append("")
    has_none = _server_offers_none_policy(endpoints)
    has_secure_username = any(
        str(getattr(ep, "SecurityPolicyUri", "") or "") != NONE_POLICY_URI
        and _supports_username(ep)
        for ep in endpoints
    )
    if security.has_credentials():
        if not has_none and has_secure_username and not security.has_certs():
            lines.extend(
                [
                    "Diagnose: Der Server bietet Benutzer/Passwort nur auf gesicherten",
                    "Endpoints (z. B. Basic256), aber keine Policy „None“.",
                    "Benutzer/Passwort allein reicht dann nicht — der Kanal muss",
                    "zusaetzlich mit Client-Zertifikat abgesichert werden.",
                    "",
                    "Moegliche Loesungen:",
                    '  1. TIA Portal → OPC UA → Server-Sicherheit: Policy „None"',
                    "     zusaetzlich aktivieren (Testbetrieb, Weg C in der Doku).",
                    "  2. Oder Client-Zertifikat einrichten (Weg B in der Doku):",
                    '       "opcua_client_cert" und "opcua_client_key" in s7py_db.json',
                    "     und Zertifikat in TIA als vertrauenswuerdig hinterlegen.",
                ]
            )
        else:
            lines.extend(
                [
                    "Moegliche Loesungen (Benutzer/Passwort konfiguriert):",
                    "  1. In TIA Portal unter OPC UA → Benutzerauthentifizierung",
                    '     „Benutzername und Kennwort" aktivieren und Benutzer anlegen.',
                    '  2. Security Policy "None" erlauben (Test) oder Client-Zertifikat',
                    "     fuer gesicherte Endpoints in s7py_db.json eintragen.",
                ]
            )
    else:
        lines.extend(
            [
                "Moegliche Loesungen:",
                "  1. In TIA Portal unter OPC UA → Server-Sicherheit die Policy "
                '"None" und anonymen Zugriff aktivieren (Testbetrieb).',
                "  2. Oder Benutzer/Passwort in s7py eintragen (OPC UA in der GUI).",
                "  3. Oder Client-Zertifikat in s7py_db.json eintragen:",
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


def _apply_client_identity(client: Any, security: OpcUaSecurityConfig) -> None:
    if security.has_credentials():
        client.set_user(security.username.strip())
        client.set_password(security.password)


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


def _connect_with_selected_endpoint(
    client: Any,
    endpoints: list[Any],
    sec: OpcUaSecurityConfig,
    *,
    after_policy_error: bool = False,
) -> tuple[Any, OpcUaConnectionInfo]:
    endpoint = select_endpoint(endpoints, sec)
    if endpoint is None:
        raise OpcUaConnectionError(format_no_usable_endpoint(endpoints, sec))
    path = _path_label_for_endpoint(
        endpoint, sec, after_policy_error=after_policy_error
    )
    info = _connection_info_from_endpoint(endpoint, sec, path=path)
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    if uri == NONE_POLICY_URI:
        _apply_none_policy(client, endpoint)
    else:
        if not sec.has_certs():
            raise OpcUaConnectionError(format_no_usable_endpoint(endpoints, sec))
        _apply_secure_policy(client, endpoint, sec)
    _apply_client_identity(client, sec)
    client.connect()
    return client, info


def connect_opcua_sync_client(
    endpoint_url: str,
    *,
    security: OpcUaSecurityConfig | None = None,
) -> tuple[Any, OpcUaConnectionInfo]:
    """Neuen verbundenen asyncua-Sync-Client und Verbindungsinfo zurueckgeben."""
    from s7py.db import load_opcua_security_config

    url = (endpoint_url or "").strip()
    sec = security if security is not None else load_opcua_security_config()

    if sec.has_credentials():
        client = _create_client(url)
        try:
            endpoints = client.connect_and_get_server_endpoints()
            return _connect_with_selected_endpoint(client, endpoints, sec)
        except OpcUaConnectionError:
            _dispose_client(client)
            raise
        except Exception as exc:
            _dispose_client(client)
            raise wrap_opcua_connect_error(exc, url) from exc

    client = _create_client(url)
    try:
        client.connect()
        return client, _quick_anonymous_connection_info(url)
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
        return _connect_with_selected_endpoint(
            client, endpoints, sec, after_policy_error=True
        )
    except OpcUaConnectionError:
        _dispose_client(client)
        raise
    except Exception as exc:
        _dispose_client(client)
        raise wrap_opcua_connect_error(exc, url) from exc
