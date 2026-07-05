"""Tests fuer Snap7-Schema-Hilfsfunktionen."""

from s7py.schema import DbItem, items_for_plc_read, schema_from_snap7_manual


def test_schema_from_snap7_manual_active_columns() -> None:
    items = [
        DbItem(name="Count", datatype="DWord", bytebit="0.0", store=True),
        DbItem(name="Temperature", datatype="Real", bytebit="4.0", store=True),
        DbItem(name="Reserve", datatype="Byte", bytebit="8.0", store=False),
    ]
    schema = schema_from_snap7_manual(items, count_field="Count")
    assert schema.sqlite_columns == ["Count", "Temperature"]
    assert schema.read_length == 9
    assert schema.count_field == "Count"


def test_items_for_plc_read_includes_count_when_inactive() -> None:
    items = [
        DbItem(name="Count", datatype="DWord", bytebit="0.0", store=False),
        DbItem(name="Temperature", datatype="Real", bytebit="4.0", store=True),
    ]
    schema = schema_from_snap7_manual(items, count_field="Count")
    read_items = items_for_plc_read(schema)
    names = [it.name for it in read_items]
    assert names == ["Count", "Temperature"]


def test_schema_from_snap7_manual_requires_active_field() -> None:
    items = [
        DbItem(name="Count", datatype="DWord", bytebit="0.0", store=False),
    ]
    try:
        schema_from_snap7_manual(items, count_field="Count")
    except ValueError as exc:
        assert "aktiv" in str(exc).lower()
    else:
        raise AssertionError("ValueError erwartet")
