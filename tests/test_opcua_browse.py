"""Tests fuer OPC-UA-Browse-Hilfsfunktionen."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from s7py.opcua_browse import connect_opcua_client
from s7py.opcua_connect import OpcUaConnectionInfo


class TestConnectOpcuaClient:
    def test_returns_client_not_tuple(self):
        client = MagicMock(name="opcua_client")
        info = OpcUaConnectionInfo(
            method="OPC UA",
            path="test",
            policy="None",
            security_mode="None_",
            identity="anonym",
            endpoint_url="opc.tcp://10.0.0.1:4840",
        )
        with patch(
            "s7py.opcua_browse.connect_opcua_sync_client",
            return_value=(client, info),
        ) as connect_mock:
            result = connect_opcua_client("opc.tcp://10.0.0.1:4840")

        connect_mock.assert_called_once_with("opc.tcp://10.0.0.1:4840")
        assert result is client
        assert not isinstance(result, tuple)
