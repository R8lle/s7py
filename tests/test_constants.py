"""Tests fuer gemeinsame Konstanten und Hilfsfunktionen."""

from datetime import datetime

from s7py.constants import format_db_timestamp


def test_format_db_timestamp_millisecond_resolution() -> None:
    ts = format_db_timestamp(datetime(2026, 7, 6, 10, 15, 30, 123456))
    assert ts == "2026-07-06 10:15:30.123"


def test_parse_db_timestamp_string_with_milliseconds() -> None:
    from s7py.constants import parse_db_timestamp_string

    ts = parse_db_timestamp_string("2026-07-06 10:15:30.123")
    assert ts.year == 2026
    assert ts.microsecond == 123000


def test_parse_db_timestamp_string_without_milliseconds() -> None:
    from s7py.constants import parse_db_timestamp_string

    ts = parse_db_timestamp_string("2026-07-06 10:15:30")
    assert ts.second == 30
    assert ts.microsecond == 0
