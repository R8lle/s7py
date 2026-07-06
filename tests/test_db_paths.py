"""Tests fuer SQLite-Pfad-Hilfsfunktionen."""

from s7py.db import normalize_db_path, sanitize_sqlite_save_path


def test_normalize_db_path_removes_double_extension() -> None:
    assert normalize_db_path("measure.db.db") == "measure.db"
    assert normalize_db_path("/tmp/data/s7py.db.db") == "/tmp/data/s7py.db"


def test_sanitize_sqlite_save_path_adds_extension() -> None:
    assert sanitize_sqlite_save_path("neu") == "neu.db"


def test_sanitize_sqlite_save_path_keeps_single_db_extension() -> None:
    assert sanitize_sqlite_save_path("s7py.db") == "s7py.db"
    assert sanitize_sqlite_save_path("s7py.db.db") == "s7py.db"
