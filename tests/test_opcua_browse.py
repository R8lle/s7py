"""Tests fuer OPC-UA-Browse-Hilfsfunktionen."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from s7py.opcua_browse import (
    OBJECTS_FOLDER_NODEID,
    connect_opcua_client,
    list_child_nodes,
)
from s7py.opcua_connect import OpcUaConnectionInfo


class TestListChildNodes:
    def test_uses_children_descriptions(self):
        ref = SimpleNamespace(
            DisplayName=SimpleNamespace(Text="ServerInterfaces"),
            BrowseName=SimpleNamespace(Name="ServerInterfaces"),
            NodeId=SimpleNamespace(to_string=lambda: 'ns=3;s="ServerInterfaces"'),
            NodeClass=SimpleNamespace(name="Object"),
        )
        node = MagicMock()
        node.get_children_descriptions.return_value = [ref]
        client = MagicMock()
        client.get_node.return_value = node

        entries = list_child_nodes(client, None)

        client.get_node.assert_called_once_with(OBJECTS_FOLDER_NODEID)
        assert len(entries) == 1
        assert entries[0].display_name == "ServerInterfaces"
        assert entries[0].node_class == "Object"
        node.get_children.assert_not_called()

    def test_falls_back_to_get_children(self):
        child = MagicMock()
        child.read_browse_name.return_value = SimpleNamespace(Name="Server")
        child.read_node_class.return_value = SimpleNamespace(name="Object")
        child.nodeid.to_string.return_value = "i=2253"

        node = MagicMock(spec=["get_children"])
        node.get_children.return_value = [child]
        # kein get_children_descriptions
        client = MagicMock()
        client.get_node.return_value = node

        entries = list_child_nodes(client, "i=85")

        assert len(entries) == 1
        assert entries[0].display_name == "Server"
        assert entries[0].node_id == "i=2253"


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

        connect_mock.assert_called_once_with(
            "opc.tcp://10.0.0.1:4840", security=None
        )
        assert result is client
        assert not isinstance(result, tuple)

    def test_passes_security_config(self):
        from s7py.opcua_connect import OpcUaSecurityConfig

        client = MagicMock(name="opcua_client")
        info = OpcUaConnectionInfo(
            method="OPC UA",
            path="test",
            policy="None",
            security_mode="None_",
            identity="user",
            endpoint_url="opc.tcp://10.0.0.1:4840",
        )
        sec = OpcUaSecurityConfig(username="plc", password="secret")
        with patch(
            "s7py.opcua_browse.connect_opcua_sync_client",
            return_value=(client, info),
        ) as connect_mock:
            result = connect_opcua_client(
                "opc.tcp://10.0.0.1:4840", security=sec
            )

        connect_mock.assert_called_once_with(
            "opc.tcp://10.0.0.1:4840", security=sec
        )
        assert result is client
