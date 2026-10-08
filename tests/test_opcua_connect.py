"""Tests fuer OPC-UA-Endpoint-Auswahl."""

from types import SimpleNamespace

from s7py.opcua_connect import (
    NONE_POLICY_URI,
    OpcUaConnectionInfo,
    OpcUaSecurityConfig,
    _path_label_for_endpoint,
    format_no_usable_endpoint,
    select_endpoint,
)

BASIC256_URI = "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"


def _endpoint(
    policy_uri: str,
    *,
    mode_name: str = "None_",
    anonymous: bool = False,
    username: bool = False,
) -> SimpleNamespace:
    from asyncua import ua

    mode = getattr(ua.MessageSecurityMode, mode_name)
    tokens: list[SimpleNamespace] = []
    if anonymous:
        tokens.append(SimpleNamespace(TokenType=ua.UserTokenType.Anonymous))
    if username:
        tokens.append(SimpleNamespace(TokenType=ua.UserTokenType.UserName))
    return SimpleNamespace(
        SecurityPolicyUri=policy_uri,
        SecurityMode=mode,
        EndpointUrl=f"opc.tcp://plc:4840/{policy_uri.rsplit('#', 1)[-1]}",
        UserIdentityTokens=tokens,
        ServerCertificate=b"cert",
    )


class TestSelectEndpoint:
    def test_prefers_none_over_secure(self):
        endpoints = [
            _endpoint(BASIC256_URI, mode_name="SignAndEncrypt", anonymous=True),
            _endpoint(NONE_POLICY_URI, anonymous=True),
        ]
        chosen = select_endpoint(endpoints, OpcUaSecurityConfig())
        assert chosen.SecurityPolicyUri == NONE_POLICY_URI

    def test_secure_only_without_certs_returns_none(self):
        endpoints = [_endpoint(BASIC256_URI, mode_name="SignAndEncrypt", anonymous=True)]
        assert select_endpoint(endpoints, OpcUaSecurityConfig()) is None

    def test_secure_with_certs(self):
        endpoints = [_endpoint(BASIC256_URI, mode_name="SignAndEncrypt", anonymous=True)]
        sec = OpcUaSecurityConfig(client_cert="/c.der", client_key="/k.pem")
        chosen = select_endpoint(endpoints, sec)
        assert chosen.SecurityPolicyUri == BASIC256_URI

    def test_credentials_prefers_none_with_username(self):
        endpoints = [
            _endpoint(BASIC256_URI, mode_name="SignAndEncrypt", username=True),
            _endpoint(NONE_POLICY_URI, username=True),
            _endpoint(NONE_POLICY_URI, anonymous=True),
        ]
        sec = OpcUaSecurityConfig(username="plcuser", password="secret")
        chosen = select_endpoint(endpoints, sec)
        assert chosen.SecurityPolicyUri == NONE_POLICY_URI

    def test_credentials_ignore_anonymous_only_endpoint(self):
        endpoints = [_endpoint(NONE_POLICY_URI, anonymous=True)]
        sec = OpcUaSecurityConfig(username="plcuser", password="secret")
        assert select_endpoint(endpoints, sec) is None

    def test_no_usable_endpoint_message_lists_policies(self):
        endpoints = [_endpoint(BASIC256_URI, mode_name="SignAndEncrypt", anonymous=True)]
        msg = format_no_usable_endpoint(endpoints, OpcUaSecurityConfig())
        assert "Basic256Sha256" in msg
        assert "TIA Portal" in msg

    def test_credentials_message_mentions_username(self):
        endpoints = [_endpoint(NONE_POLICY_URI, anonymous=True)]
        msg = format_no_usable_endpoint(
            endpoints, OpcUaSecurityConfig(username="u", password="p")
        )
        assert "Benutzer/Passwort" in msg


class TestPrepareOpcUaClient:
    def test_session_timeout_matches_s7_default(self, monkeypatch):
        class FakeAio:
            session_timeout = 3_600_000

        class FakeClient:
            def __init__(self, _url: str, **_kwargs: object) -> None:
                self.aio_obj = FakeAio()
                self.kwargs = _kwargs

        monkeypatch.setattr("s7py.opcua_connect.import_opcua_client_class", lambda: FakeClient)
        from s7py.constants import (
            OPCUA_REQUEST_TIMEOUT_S,
            OPCUA_SESSION_TIMEOUT_MS,
            OPCUA_SYNC_WRAPPER_TIMEOUT_S,
        )
        from s7py.opcua_connect import _create_client

        client = _create_client("opc.tcp://127.0.0.1:4840")
        assert client.aio_obj.session_timeout == OPCUA_SESSION_TIMEOUT_MS
        assert client.kwargs["timeout"] == OPCUA_REQUEST_TIMEOUT_S
        assert client.kwargs["sync_wrapper_timeout"] == OPCUA_SYNC_WRAPPER_TIMEOUT_S

    def test_apply_client_identity_sets_user_and_password(self):
        class FakeAio:
            pass

        class FakeClient:
            def __init__(self) -> None:
                self.aio_obj = FakeAio()
                self.user = ""
                self.pwd = ""

            def set_user(self, username: str) -> None:
                self.user = username

            def set_password(self, pwd: str) -> None:
                self.pwd = pwd

        from s7py.opcua_connect import _apply_client_identity

        client = FakeClient()
        _apply_client_identity(
            client, OpcUaSecurityConfig(username="plcuser", password="geheim")
        )
        assert client.user == "plcuser"
        assert client.pwd == "geheim"


class TestConnectionPathLabels:
    def test_quick_anonymous_info(self):
        from s7py.opcua_connect import _quick_anonymous_connection_info

        info = _quick_anonymous_connection_info("opc.tcp://192.168.0.10:4840")
        msg = info.log_message()
        assert "OPC UA" in msg
        assert "Schnellverbindung" in msg
        assert "opc.tcp://192.168.0.10:4840" in msg

    def test_path_label_after_policy_error(self):
        endpoint = _endpoint(NONE_POLICY_URI, anonymous=True)
        label = _path_label_for_endpoint(
            endpoint, OpcUaSecurityConfig(), after_policy_error=True
        )
        assert "Policy-Fehler" in label

    def test_path_label_credentials_none(self):
        endpoint = _endpoint(NONE_POLICY_URI, username=True)
        label = _path_label_for_endpoint(
            endpoint, OpcUaSecurityConfig(username="plcuser", password="x")
        )
        assert "Benutzer/Passwort" in label
        assert "Policy None" in label

    def test_connection_info_log_message(self):
        endpoint = _endpoint(
            NONE_POLICY_URI, mode_name="None_", username=True, anonymous=True
        )
        from s7py.opcua_connect import _connection_info_from_endpoint

        info = _connection_info_from_endpoint(
            endpoint,
            OpcUaSecurityConfig(username="plcuser", password="x"),
            path="Endpoint-Auswahl mit Benutzer/Passwort (Policy None)",
        )
        assert isinstance(info, OpcUaConnectionInfo)
        assert "plcuser" in info.log_message()
        assert "None" in info.log_message()
