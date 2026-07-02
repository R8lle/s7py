"""Tests fuer Diagramm-Datenaufbereitung."""

import sqlite3
from datetime import datetime

from s7py.charts import (
    _parse_chart_rows,
    fetch_chart_rows_initial,
    invalidate_table_columns_cache,
    plottable_numeric_fields,
)
from s7py.constants import TIMESTAMP_FORMAT_DB
from s7py.db import create_database
from s7py.schema import DbItem, PlcDbSchema, default_plc_schema


class TestPlottableNumericFields:
    def test_excludes_string_columns(self):
        schema = PlcDbSchema(
            sqlite_columns=["Count", "DB_String"],
            items=[
                DbItem(name="Count", datatype="DWord", bytebit="0.0"),
                DbItem(name="DB_String", datatype="String", bytebit="20.0"),
            ],
        )
        fields = plottable_numeric_fields(schema)
        assert fields == ["Count"]


class TestParseChartRows:
    def test_parses_valid_row(self):
        ts = datetime.now().strftime(TIMESTAMP_FORMAT_DB)
        rows = [(1, ts, 42.0, 3.14)]
        parsed = _parse_chart_rows(rows, ["Count", "Temperature"])
        assert len(parsed) == 1
        assert parsed[0][0] == 1
        assert parsed[0][2]["Count"] == 42.0

    def test_skips_null_value(self):
        ts = datetime.now().strftime(TIMESTAMP_FORMAT_DB)
        rows = [(1, ts, None, 1.0)]
        parsed = _parse_chart_rows(rows, ["Count", "Temperature"])
        assert parsed == []

    def test_skips_bad_timestamp(self):
        rows = [(1, "not-a-date", 1.0)]
        parsed = _parse_chart_rows(rows, ["Count"])
        assert parsed == []


class TestFetchChartRowsInitial:
    def test_reads_from_memory_db(self, tmp_path):
        db_path = tmp_path / "chart.db"
        schema = default_plc_schema()
        create_database(str(db_path), schema)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        ts = datetime.now().strftime(TIMESTAMP_FORMAT_DB)
        cur.execute(
            'INSERT INTO projects(time, "Count", "Temperature", '
            '"DistanceOverAll", "CyclesOverAll", "MotorCurrent") '
            "VALUES (?, 1, 20.5, 100.0, 2, 0.5)",
            (ts,),
        )
        conn.commit()
        invalidate_table_columns_cache()
        rows = fetch_chart_rows_initial(cur, schema, last_n=10)
        assert len(rows) == 1
        assert rows[0][2]["Temperature"] == 20.5
        conn.close()
