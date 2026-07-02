"""Tests fuer SPS-Schema und DbItem."""

import pytest

from s7py.plc import get_db_size
from s7py.schema import (
    DbItem,
    coerce_db_items,
    default_plc_schema,
    parse_db_layout,
)


class TestDbItem:
    def test_roundtrip_dict(self):
        item = DbItem(
            name="Count",
            datatype="DWord",
            bytebit="0.0",
            store=True,
            size=4,
            s7_type="DINT",
        )
        restored = DbItem.from_dict(item.to_dict())
        assert restored == item

    def test_store_false_serialized(self):
        item = DbItem(name="Reserve", datatype="Byte", bytebit="20.0", store=False)
        assert item.to_dict()["store"] is False


class TestCoerceDbItems:
    def test_from_dict_list(self):
        items = coerce_db_items(
            [{"name": "A", "datatype": "Real", "bytebit": "4.0"}]
        )
        assert len(items) == 1
        assert items[0].name == "A"

    def test_passthrough_dbitem(self):
        original = DbItem(name="X", datatype="Int", bytebit="0.0")
        assert coerce_db_items([original])[0] is original

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            coerce_db_items(["not-a-dict"])


class TestParseDbLayout:
    def test_parses_default_layout_lines(self):
        layout = "Count\tDWord\t0.0\nTemperature\tReal\t4.0"
        items = parse_db_layout(layout)
        assert len(items) == 2
        assert items[0].name == "Count"
        assert items[1].datatype == "Real"

    def test_invalid_line_raises(self):
        with pytest.raises(ValueError):
            parse_db_layout("only two\tcolumns")


class TestGetDbSize:
    def test_default_schema_matches_read_length(self):
        schema = default_plc_schema()
        assert get_db_size(schema.items) == schema.read_length

    def test_uses_explicit_size(self):
        items = [DbItem(name="Big", datatype="Byte", bytebit="0.0", size=100)]
        assert get_db_size(items) == 100
