"""Tests fuer OPC-UA-Browse-Hilfsfunktionen."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from s7py.opcua_browse import (
    OBJECTS_FOLDER_NODEID,
    connect_opcua_client,
    list_child_nodes,
    map_opcua_variant_to_s7py,
    suggested_name_from_node_id,
)
from s7py.opcua_connect import OpcUaConnectionInfo


class TestSuggestedName:
    def test_siemens_string_node_id(self):
        assert (
            suggested_name_from_node_id('ns=3;s="DB1"."Motor"."Speed"')
            == "DB1_Motor_Speed"
        )

    def test_falls_back_to_display(self):
        assert suggested_name_from_node_id("i=2253", "Server") == "Server"


class TestMapOpcuaVariant:
    def test_common_siemens_types(self):
        assert map_opcua_variant_to_s7py("Boolean") == "Bool"
        assert map_opcua_variant_to_s7py("Float") == "Real"
        assert map_opcua_variant_to_s7py("Double") == "Real"
        assert map_opcua_variant_to_s7py("Int16") == "Int"
        assert map_opcua_variant_to_s7py("UInt32") == "DWord"
        assert map_opcua_variant_to_s7py("String") == "String"
        assert map_opcua_variant_to_s7py("UnknownCustom") == ""


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

    def test_enriches_variable_data_type(self):
        ref = SimpleNamespace(
            DisplayName=SimpleNamespace(Text="Temperature"),
            BrowseName=SimpleNamespace(Name="Temperature"),
            NodeId=SimpleNamespace(to_string=lambda: 'ns=3;s="Temp"'),
            NodeClass=SimpleNamespace(name="Variable"),
        )
        folder = MagicMock()
        folder.get_children_descriptions.side_effect = lambda refs=None: [ref]
        var_node = MagicMock()
        var_node.read_data_type_as_variant_type.return_value = SimpleNamespace(
            name="Float"
        )

        def get_node(node_id: str):
            if node_id == OBJECTS_FOLDER_NODEID:
                return folder
            return var_node

        client = MagicMock()
        client.get_node.side_effect = get_node

        entries = list_child_nodes(client, None)

        assert len(entries) == 1
        assert entries[0].data_type == "Real"

    def test_udt_fields_via_structured_component(self):
        parent = MagicMock()
        # Hierarchisch leer, UDT-Feld nur ueber HasStructuredComponent.
        field = SimpleNamespace(
            DisplayName=SimpleNamespace(Text="Speed"),
            BrowseName=SimpleNamespace(Name="Speed"),
            NodeId=SimpleNamespace(to_string=lambda: 'ns=3;s="DB"."UDT"."Speed"'),
            NodeClass=SimpleNamespace(name="Variable"),
        )

        def get_desc(refs=None):
            if refs is None:
                return []
            from asyncua import ua

            if int(refs) == int(ua.ObjectIds.HasStructuredComponent):
                return [field]
            return []

        parent.get_children_descriptions.side_effect = get_desc
        field_node = MagicMock()
        field_node.read_data_type_as_variant_type.return_value = SimpleNamespace(
            name="Float"
        )
        client = MagicMock()
        client.get_node.side_effect = lambda nid: (
            parent if nid == 'ns=3;s="DB"."UDT"' else field_node
        )

        entries = list_child_nodes(client, 'ns=3;s="DB"."UDT"')

        assert len(entries) == 1
        assert entries[0].display_name == "Speed"
        assert entries[0].data_type == "Real"

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
