"""Tests fuer Fenstergroesse/-position speichern und wiederherstellen."""

from s7py.ui_flow import clamp_geometry, parse_geometry


def test_parse_geometry_accepts_tk_format():
    assert parse_geometry("1200x800+40+60") == (1200, 800, 40, 60)
    assert parse_geometry("900x500-20+30") == (900, 500, -20, 30)
    assert parse_geometry("") is None
    assert parse_geometry("broken") is None
    assert parse_geometry("50x50+0+0") is None


def test_clamp_geometry_keeps_window_reachable():
    w, h, x, y = clamp_geometry(
        2000,
        2000,
        -5000,
        -100,
        1440,
        900,
        min_w=720,
        min_h=640,
    )
    assert w == int(1440 * 0.98)
    assert h == 900 - 30 - 80
    assert x >= 80 - w
    assert y >= 30


def test_window_geometry_roundtrip(tmp_path, monkeypatch):
    from s7py.db import load_window_geometry, save_window_geometry

    cfg = tmp_path / "s7py_db.json"
    monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
    assert load_window_geometry("main") == ""
    save_window_geometry("main", "1100x720+12+48")
    save_window_geometry("snap7_vars", "920x520+40+60")
    save_window_geometry("opcua_vars", "980x540+50+70")
    save_window_geometry("db_table", "not-a-geometry")
    assert load_window_geometry("main") == "1100x720+12+48"
    assert load_window_geometry("snap7_vars") == "920x520+40+60"
    assert load_window_geometry("opcua_vars") == "980x540+50+70"
    assert load_window_geometry("db_table") == ""
