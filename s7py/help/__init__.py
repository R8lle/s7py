"""Benutzerdokumentation: eine Markdown-Quelle je Dokument, Anzeige im Programm.

``kurzanleitung.md`` (Schnellhilfe) und ``anleitung.md`` (Bedienungsanleitung)
liegen neben dieser Datei.
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCUMENTS = {
    "kurzanleitung": "Schnellhilfe",
    "anleitung": "Bedienungsanleitung",
}


def source(name: str) -> str:
    if name not in DOCUMENTS:
        raise KeyError(name)
    return (HERE / f"{name}.md").read_text(encoding="utf-8")


def headings(markdown: str) -> list[tuple[int, str]]:
    """``(Ebene, Titel)`` aller ``#``-Ueberschriften fuer das Inhaltsverzeichnis."""
    out: list[tuple[int, str]] = []
    in_code = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = re.match(r"^(#{1,3})\s+(.*)$", line)
        if match:
            out.append((len(match.group(1)), match.group(2).strip()))
    return out
