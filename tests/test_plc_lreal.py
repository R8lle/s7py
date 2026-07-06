"""Tests fuer LREAL-Lesen aus Snap7-DB-Puffern."""

from snap7.util import set_lreal

from s7py.plc import is_lreal_item, read_item_value
from s7py.schema import DbItem, normalize_snap7_db_item


def test_normalize_legacy_lreal_item() -> None:
    item = DbItem.from_dict(
        {
            "name": "Position",
            "datatype": "Real",
            "bytebit": "8.0",
            "size": 8,
            "s7_type": "LREAL",
        }
    )
    assert item.datatype == "LReal"
    assert is_lreal_item(item)


def test_normalize_real_without_s7_type_but_size_8() -> None:
    item = normalize_snap7_db_item(
        DbItem(name="Position", datatype="Real", bytebit="8.0", size=8)
    )
    assert item.datatype == "LReal"
    assert is_lreal_item(item)


def test_read_lreal_value() -> None:
    data = bytearray(16)
    set_lreal(data, 8, 123.456789)
    item = DbItem(
        name="Position",
        datatype="LReal",
        bytebit="8.0",
        s7_type="LREAL",
        size=8,
    )
    value = read_item_value(data, item)
    assert abs(float(value) - 123.456789) < 1e-6


def test_legacy_real_with_s7_type_lreal_uses_get_lreal() -> None:
    data = bytearray(16)
    set_lreal(data, 0, -0.125)
    legacy = DbItem(
        name="Position",
        datatype="Real",
        bytebit="0.0",
        s7_type="LREAL",
        size=8,
    )
    assert abs(float(read_item_value(data, legacy)) - (-0.125)) < 1e-9
