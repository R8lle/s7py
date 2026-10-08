"""Selbsttest-Einstieg ohne GUI."""

from pathlib import Path

from s7py.selftest import run_selftest


def test_selftest_writes_ok_report(tmp_path: Path) -> None:
    report = tmp_path / "selftest.txt"
    assert run_selftest(report) == 0
    text = report.read_text(encoding="utf-8")
    assert "SELFTEST OK" in text
    assert "s7py" in text
