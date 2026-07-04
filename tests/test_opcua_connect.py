"""Tests fuer OPC-UA-Endpoint-Auswahl."""

from types import SimpleNamespace

from s7py.opcua_connect import (
    NONE_POLICY_URI,
    OpcUaSecurityConfig,
    format_no_usable_endpoint,
    select_endpoint,
)

BASIC256_URI = "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"


def _endpoint(policy_uri: str, *, mode_name: str = "None_", anonymous: bool = True) -> SimpleNamespace:
    from asyncua import ua

    mode = getattr(ua.MessageSecurityMode, mode_name)
    tokens = [SimpleNamespace(TokenType=ua.UserTokenType.Anonymous)] if anonymous else []
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
            _endpoint(BASIC256_URI, mode_name="SignAndEncrypt"),
            _endpoint(NONE_POLICY_URI),
        ]
        chosen = select_endpoint(endpoints, OpcUaSecurityConfig())
        assert chosen.SecurityPolicyUri == NONE_POLICY_URI

    def test_secure_only_without_certs_returns_none(self):
        endpoints = [_endpoint(BASIC256_URI, mode_name="SignAndEncrypt")]
        assert select_endpoint(endpoints, OpcUaSecurityConfig()) is None

    def test_secure_with_certs(self):
        endpoints = [_endpoint(BASIC256_URI, mode_name="SignAndEncrypt")]
        sec = OpcUaSecurityConfig(client_cert="/c.der", client_key="/k.pem")
        chosen = select_endpoint(endpoints, sec)
        assert chosen.SecurityPolicyUri == BASIC256_URI

    def test_no_usable_endpoint_message_lists_policies(self):
        endpoints = [_endpoint(BASIC256_URI, mode_name="SignAndEncrypt")]
        msg = format_no_usable_endpoint(endpoints, OpcUaSecurityConfig())
        assert "Basic256Sha256" in msg
        assert "TIA Portal" in msg


class TestPrepareOpcUaClient:
    def test_session_timeout_matches_s7_default(self, monkeypatch):
        class FakeAio:
            session_timeout = 3_600_000

        class FakeClient:
            def __init__(self, _url: str) -> None:
                self.aio_obj = FakeAio()

        monkeypatch.setattr("s7py.opcua_connect.import_opcua_client_class", lambda: FakeClient)
        from s7py.constants import OPCUA_SESSION_TIMEOUT_MS
        from s7py.opcua_connect import _create_client

        client = _create_client("opc.tcp://127.0.0.1:4840")
        assert client.aio_obj.session_timeout == OPCUA_SESSION_TIMEOUT_MS
