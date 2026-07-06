"""Tests fuer Diagramm-Datenparsing."""

from datetime import datetime

from s7py.charts import _parse_chart_rows


def test_parse_chart_rows_accepts_millisecond_timestamps() -> None:
    rows = [
        (1, "2026-07-06 10:15:30.123", 42.0, 1234.5),
    ]
    parsed = _parse_chart_rows(rows, ["Count", "ActualPosition"])
    assert len(parsed) == 1
    assert parsed[0][0] == 1
    assert parsed[0][1] == datetime(2026, 7, 6, 10, 15, 30, 123000)
    assert parsed[0][2]["ActualPosition"] == 1234.5
