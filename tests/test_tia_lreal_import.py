"""Tests fuer TIA-Import mit LREAL und Attribut-Syntax."""

from pathlib import Path

from s7py.schema import parse_tia_data_block_file

ACHSE_DB = Path(__file__).resolve().parents[1] / "Achse_Daten_Main.db"


def test_achse_daten_main_packed_layout_after_dint() -> None:
    """DInt (4 Byte) @ 0, danach LREAL ohne Padding-Luecke bis Byte 8."""
    schema = parse_tia_data_block_file(str(ACHSE_DB))
    by_name = {item.name: item for item in schema.items}

    assert by_name["Count"].datatype == "DWord"
    assert by_name["Count"].s7_type == "DINT"
    assert by_name["Count"].bytebit == "0.0"

    assert by_name["ActualPosition"].datatype == "LReal"
    assert by_name["ActualPosition"].bytebit == "4.0"
    assert by_name["ActualVelocity"].bytebit == "12.0"
    assert by_name["ActualAcceleration"].bytebit == "20.0"
    assert by_name["MotorCurrent"].bytebit == "28.0"

    assert by_name["ControlDifference"].datatype == "LReal"
    assert by_name["ControlDifference"].bytebit == "36.0"

    assert by_name["DB_String"].bytebit == "44.0"
    assert by_name["Reserve"].bytebit == "300.0"
    assert schema.read_length == 556
