"""PDF-Export der Hilfe-Dokumente."""

from __future__ import annotations

from s7py import help as manual
from s7py.help_pdf import export_markdown_pdf


def test_export_tia_pdf(tmp_path):
    path = tmp_path / "tia.pdf"
    export_markdown_pdf(manual.source("tia"), path, title="s7py – TIA")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"%%EOF" in data
    assert path.stat().st_size > 500
    assert b"Seite 1" in data


def test_export_kurzanleitung_pdf(tmp_path):
    path = tmp_path / "kurz.pdf"
    export_markdown_pdf(manual.source("kurzanleitung"), path, title="s7py – Schnellhilfe")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"Seite 1" in data
