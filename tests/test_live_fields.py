"""Tests fuer resolve_live_fields."""

from s7py.schema import resolve_live_fields


def test_resolve_live_fields_fills_short_saved_list() -> None:
    columns = [
        "Count",
        "ActualPosition",
        "ActualVelocity",
        "ActualAcceleration",
    ]
    resolved = resolve_live_fields(columns, ["Count"])
    assert resolved == columns
