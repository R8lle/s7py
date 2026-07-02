"""Tests fuer SQLite-Hilfsfunktionen."""

import sqlite3

import pytest

from s7py.db import (
    build_create_projects_sql,
    create_database,
    quote_identifier,
    table_columns,
)
from s7py.schema import DbItem, PlcDbSchema, default_plc_schema


class TestQuoteIdentifier:
    def test_simple_name(self):
        assert quote_identifier("Temperature") == '"Temperature"'

    def test_name_with_quotes(self):
        assert quote_identifier('a"b') == '"a""b"'

    def test_injection_becomes_harmless_identifier(self):
        malicious = 'x"); DROP TABLE projects;--'
        quoted = quote_identifier(malicious)
        conn = sqlite3.connect(":memory:")
        conn.execute(f"CREATE TABLE projects (id INTEGER, {quoted} REAL)")
        cols = table_columns(conn.cursor(), "projects")
        assert malicious in cols
        conn.close()

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            quote_identifier("")

    def test_null_byte_raises(self):
        with pytest.raises(ValueError):
            quote_identifier("bad\x00name")


class TestBuildCreateProjectsSql:
    def test_default_schema_uses_quoted_columns(self):
        sql = build_create_projects_sql(default_plc_schema())
        assert '"Temperature"' in sql
        assert '"Count"' in sql
        assert "CREATE TABLE IF NOT EXISTS projects" in sql

    def test_malicious_column_name_quoted(self):
        schema = PlcDbSchema(
            sqlite_columns=['evil"; DROP TABLE projects;--'],
            items=[
                DbItem(
                    name='evil"; DROP TABLE projects;--',
                    datatype="Real",
                    bytebit="0.0",
                )
            ],
        )
        sql = build_create_projects_sql(schema)
        assert 'evil""; DROP TABLE projects;--' in sql


class TestCreateDatabase:
    def test_creates_projects_table(self, tmp_path):
        db_path = tmp_path / "test.db"
        assert create_database(str(db_path), default_plc_schema())
        conn = sqlite3.connect(db_path)
        cols = set(table_columns(conn.cursor(), "projects"))
        assert "Temperature" in cols
        assert "time" in cols
        conn.close()


class TestDbPathStorage:
    def test_save_last_db_path_relative(self, tmp_path, monkeypatch):
        import json

        from s7py.db import load_last_db_path, save_last_db_path

        app = tmp_path / "app"
        app.mkdir()
        db = app / "s7py.db"
        cfg = app / "s7py_db.json"
        monkeypatch.setattr("s7py.constants.APP_DIR", app)
        monkeypatch.setattr("s7py.db.APP_DIR", app)
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))

        save_last_db_path(str(db))
        stored = json.loads(cfg.read_text(encoding="utf-8"))["last_database"]
        assert stored == "s7py.db"
        assert load_last_db_path() == str(db.resolve())


class TestPollInterval:
    def test_normalize_clamps_range(self):
        from s7py.constants import DEFAULT_POLL_INTERVAL_S, MAX_POLL_INTERVAL_S, MIN_POLL_INTERVAL_S
        from s7py.db import normalize_poll_interval_s

        assert normalize_poll_interval_s(0.001) == MIN_POLL_INTERVAL_S
        assert normalize_poll_interval_s(99) == MAX_POLL_INTERVAL_S
        assert normalize_poll_interval_s("bad") == DEFAULT_POLL_INTERVAL_S

    def test_clamp_poll_interval_ms(self):
        from s7py.constants import MIN_POLL_INTERVAL_S
        from s7py.db import clamp_poll_interval_ms

        min_ms = int(MIN_POLL_INTERVAL_S * 1000)
        assert clamp_poll_interval_ms(5) == min_ms
        assert clamp_poll_interval_ms(250) == 250
        assert clamp_poll_interval_ms("bad") == int(round(0.1 * 1000))

    def test_ms_roundtrip(self, tmp_path, monkeypatch):
        from s7py.constants import DB_CONFIG_PATH
        from s7py.db import (
            load_poll_interval_s,
            poll_interval_ms_from_s,
            poll_interval_s_from_ms,
            save_poll_interval_s,
        )

        cfg = tmp_path / "s7py_db.json"
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
        save_poll_interval_s(0.25)
        assert load_poll_interval_s() == 0.25
        assert poll_interval_ms_from_s(0.25) == 250
        assert poll_interval_s_from_ms(250) == 0.25

    def test_plot_refresh_ms(self, tmp_path, monkeypatch):
        from s7py.constants import DEFAULT_PLOT_REFRESH_MS, MAX_PLOT_REFRESH_MS, MIN_PLOT_REFRESH_MS
        from s7py.db import (
            load_plot_refresh_ms,
            normalize_plot_refresh_ms,
            save_plot_refresh_ms,
        )

        cfg = tmp_path / "s7py_db.json"
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
        assert normalize_plot_refresh_ms(100) == MIN_PLOT_REFRESH_MS
        assert normalize_plot_refresh_ms(99999) == MAX_PLOT_REFRESH_MS
        assert normalize_plot_refresh_ms("bad") == DEFAULT_PLOT_REFRESH_MS
        save_plot_refresh_ms(750)
        assert load_plot_refresh_ms() == 750

    def test_auto_reconnect_default_and_save(self, tmp_path, monkeypatch):
        from s7py.db import load_auto_reconnect, save_auto_reconnect

        cfg = tmp_path / "s7py_db.json"
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
        assert load_auto_reconnect() is True
        save_auto_reconnect(False)
        assert load_auto_reconnect() is False


class TestDbMaintenance:
    def test_trim_keep_last_and_clear(self, tmp_path):
        from s7py.db import (
            clear_projects_table,
            create_database,
            create_newline,
            projects_row_count,
            trim_projects_keep_last,
            vacuum_sqlite_database,
        )
        from s7py.schema import default_plc_schema

        db_path = tmp_path / "maint.db"
        schema = default_plc_schema()
        assert create_database(str(db_path), schema)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for i in range(1, 6):
            create_newline(
                cursor,
                conn,
                (f"2026-01-01 12:00:{i:02d}", i, 20.0 + i, 100 + i, i, 0.5, ""),
                schema,
            )
        assert projects_row_count(cursor) == 5
        deleted = trim_projects_keep_last(cursor, conn, 2)
        assert deleted == 3
        assert projects_row_count(cursor) == 2
        cursor.execute("SELECT MIN(id), MAX(id) FROM projects")
        min_id, max_id = cursor.fetchone()
        assert min_id == 4
        assert max_id == 5

        cleared = clear_projects_table(cursor, conn)
        assert cleared == 2
        assert projects_row_count(cursor) == 0
        conn.close()

        create_database(str(db_path), schema)
        vacuum_sqlite_database(str(db_path))


class TestPlcRackSlot:
    def test_normalize_clamps(self):
        from s7py.db import normalize_plc_rack, normalize_plc_slot

        assert normalize_plc_rack(-1) == 0
        assert normalize_plc_rack(99) == 7
        assert normalize_plc_slot("bad") == 0
        assert normalize_plc_slot(31) == 31
        assert normalize_plc_slot(50) == 31

    def test_save_and_load(self, tmp_path, monkeypatch):
        from s7py.db import load_plc_rack, load_plc_slot, save_plc_rack_slot

        cfg = tmp_path / "s7py_db.json"
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
        save_plc_rack_slot(2, 1)
        assert load_plc_rack() == 2
        assert load_plc_slot() == 1


class TestPlcDbNumber:
    def test_normalize_clamps(self):
        from s7py.constants import PLC_DB_NUMBER
        from s7py.db import normalize_plc_db_number

        assert normalize_plc_db_number(0) == 1
        assert normalize_plc_db_number(70000) == 65535
        assert normalize_plc_db_number("bad") == PLC_DB_NUMBER

    def test_save_and_load(self, tmp_path, monkeypatch):
        from s7py.db import load_plc_db_number, save_plc_db_number

        cfg = tmp_path / "s7py_db.json"
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
        save_plc_db_number(42)
        assert load_plc_db_number() == 42

    def test_fallback_to_schema(self, tmp_path, monkeypatch):
        import json

        from s7py.db import load_plc_db_number

        cfg = tmp_path / "s7py_db.json"
        cfg.write_text(
            json.dumps({"plc_structure": {"db_number": 17}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
        assert load_plc_db_number() == 17


class TestProjectsStats:
    def test_fetch_and_format(self, tmp_path):
        from s7py.db import (
            create_database,
            create_newline,
            fetch_projects_stats,
            format_projects_stats_suffix,
        )
        from s7py.schema import default_plc_schema

        db_path = tmp_path / "stats.db"
        schema = default_plc_schema()
        assert create_database(str(db_path), schema)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        stats = fetch_projects_stats(cursor, str(db_path))
        assert stats["rows"] == 0
        suffix = format_projects_stats_suffix(stats)
        assert "0 Messpunkte" in suffix

        row = ("2026-01-01 12:00:00", 1, 20.5, 100, 5, 0.5, "")
        create_newline(cursor, conn, row, schema)
        stats = fetch_projects_stats(cursor, str(db_path))
        assert stats["rows"] == 1
        suffix = format_projects_stats_suffix(stats)
        assert "1 Messpunkte" in suffix
        assert "2026-01-01" in suffix
        conn.close()


class TestCsvExport:
    def test_resolve_columns_selected(self):
        from s7py.db import csv_export_columns, resolve_csv_export_columns
        from s7py.schema import default_plc_schema

        schema = default_plc_schema()
        all_cols = csv_export_columns(schema)
        selected = resolve_csv_export_columns(schema, ["Temperature"])
        assert selected == ("id", "time", "Temperature")
        assert len(all_cols) > len(selected)

    def test_fetch_last_n(self, tmp_path):
        from s7py.db import (
            create_database,
            create_newline,
            csv_export_columns,
            fetch_projects_for_csv,
        )
        from s7py.schema import default_plc_schema

        db_path = tmp_path / "export.db"
        schema = default_plc_schema()
        assert create_database(str(db_path), schema)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for i in range(1, 4):
            create_newline(
                cursor,
                conn,
                (f"2026-01-01 12:00:{i:02d}", i, 20.0 + i, 100 + i, i, 0.5, ""),
                schema,
            )
        cols = csv_export_columns(schema)
        rows = fetch_projects_for_csv(
            cursor, schema, columns=cols, scope="last_n", limit=2
        )
        assert len(rows) == 2
        assert rows[0][0] == 2
        assert rows[1][0] == 3
        conn.close()
