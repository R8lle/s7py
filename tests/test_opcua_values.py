"""Tests fuer OPC-UA-Wertumwandlung und NodeId-Speicherung."""

from s7py.opcua_values import coerce_opcua_value
from s7py.schema import DbItem, schema_from_opcua_manual


class TestCoerceOpcuaValue:
    def test_real_rounds(self):
        assert coerce_opcua_value(12.34567, "Real") == 12.346

    def test_dword_masks(self):
        assert coerce_opcua_value(-1, "DWord") == 4294967295

    def test_bool(self):
        assert coerce_opcua_value(1, "Bool") is True


class TestDbItemNodeId:
    def test_roundtrip_dict(self):
        item = DbItem(
            name="Temperature",
            datatype="Real",
            bytebit="4.0",
            node_id="ns=2;s=Temperature",
        )
        restored = DbItem.from_dict(item.to_dict())
        assert restored.node_id == "ns=2;s=Temperature"

    def test_group_id_roundtrip(self):
        item = DbItem(
            name="Speed",
            datatype="Real",
            bytebit="opcua",
            node_id="ns=3;s=Speed",
            group_id='ns=3;s="DB1"."Motor"',
        )
        data = item.to_dict()
        assert data["group_id"] == 'ns=3;s="DB1"."Motor"'
        restored = DbItem.from_dict(data)
        assert restored.group_id == item.group_id

    def test_group_id_omitted_when_empty(self):
        item = DbItem(name="A", datatype="Int", bytebit="opcua", node_id="i=1")
        assert "group_id" not in item.to_dict()



class TestSchemaFromOpcuaManual:
    def test_builds_schema(self):
        items = [
            DbItem(
                name="Count",
                datatype="DWord",
                bytebit="opcua",
                node_id="ns=2;i=1",
            ),
            DbItem(
                name="Temperature",
                datatype="Real",
                bytebit="opcua",
                node_id="ns=2;s=Temperature",
            ),
        ]
        schema = schema_from_opcua_manual(items, count_field="Count")
        assert schema.block_name == "OPC UA manuell"
        assert schema.sqlite_columns == ["Count", "Temperature"]
        assert schema.read_length == 0

    def test_requires_count_node_id(self):
        items = [
            DbItem(name="Count", datatype="DWord", bytebit="opcua", node_id=""),
        ]
        try:
            schema_from_opcua_manual(items, count_field="Count")
        except ValueError as exc:
            assert "NodeId" in str(exc)
        else:
            raise AssertionError("expected ValueError")
