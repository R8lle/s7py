"""Hilfe-Markdown als PDF speichern (reine Standardbibliothek, WinAnsi/Helvetica)."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path


def _plain(line: str) -> str:
    plain = re.sub(r"`([^`]+)`", r"\1", line)
    plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", plain)
    plain = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", plain)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    return plain


def _blocks(markdown: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    in_code = False
    code: list[str] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                blocks.append(("code", "\n".join(code)))
                code = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code.append(raw)
            continue
        if re.match(r"^[-*]{3,}\s*$", line):
            blocks.append(("blank", ""))
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            blocks.append((f"h{len(heading.group(1))}", _plain(heading.group(2).strip())))
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if bullet:
            blocks.append(("bullet", _plain(bullet.group(1))))
            continue
        number = re.match(r"^(\d+)\.\s+(.*)$", line)
        if number:
            blocks.append(("number", f"{number.group(1)}. {_plain(number.group(2))}"))
            continue
        if not line.strip():
            blocks.append(("blank", ""))
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells):
                continue
            blocks.append(("body", "  |  ".join(_plain(c) for c in cells)))
            continue
        blocks.append(("body", _plain(line)))
    if code:
        blocks.append(("code", "\n".join(code)))
    return blocks


def _pdf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "")
    )


def _to_pdf_string(text: str) -> str:
    """Helvetica + WinAnsi: Umlaute ok, sonst '?'."""
    encoded = text.encode("cp1252", errors="replace")
    return _pdf_escape(encoded.decode("latin-1"))


def _wrap_lines(kind: str, text: str, *, chars_body: int = 90, chars_code: int = 95) -> list[tuple[str, str]]:
    if kind == "blank":
        return [("blank", "")]
    if kind == "code":
        rows: list[tuple[str, str]] = []
        for row in text.splitlines() or [""]:
            wrapped = textwrap.wrap(
                row, width=chars_code, replace_whitespace=False, drop_whitespace=False
            ) or [""]
            rows.extend(("code", w) for w in wrapped)
        return rows
    prefix = ""
    content = text
    width = chars_body
    if kind == "bullet":
        prefix = "- "
        width = chars_body - 2
    elif kind == "number":
        match = re.match(r"^(\d+\.\s+)(.*)$", text)
        if match:
            prefix, content = match.group(1), match.group(2)
            width = max(40, chars_body - len(prefix))
    wrapped = textwrap.wrap(content, width=width) or [""]
    rows: list[tuple[str, str]] = []
    for i, part in enumerate(wrapped):
        if i == 0:
            rows.append((kind, prefix + part))
        else:
            rows.append((kind, (" " * len(prefix)) + part))
    return rows


_FONT_SIZE = {
    "h1": 16,
    "h2": 13,
    "h3": 11,
    "body": 10,
    "bullet": 10,
    "number": 10,
    "code": 8,
    "blank": 10,
}
_LINE_GAP = {
    "h1": 20,
    "h2": 18,
    "h3": 15,
    "body": 13,
    "bullet": 13,
    "number": 13,
    "code": 11,
    "blank": 8,
}


def export_markdown_pdf(markdown: str, path: str | Path, *, title: str = "s7py Hilfe") -> None:
    """Schreibt den Hilfetext als mehrseitiges A4-PDF (ohne Extra-Abhaengigkeit)."""
    out = Path(path)
    page_w, page_h = 595.28, 841.89  # A4 pt
    margin = 50.0
    y_top = page_h - margin
    y_bottom = margin + 28.0

    drawn: list[tuple[str, str]] = []
    for kind, text in _blocks(markdown):
        drawn.extend(_wrap_lines(kind, text))

    pages: list[list[tuple[str, str, float]]] = [[]]
    y = y_top
    for kind, text in drawn:
        gap = _LINE_GAP.get(kind, 13)
        if y - gap < y_bottom:
            pages.append([])
            y = y_top
        pages[-1].append((kind, text, y))
        y -= gap

    objects: list[bytes] = []

    def add_obj(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    # 1: Catalog, 2: Pages (spaeter), dann Fonts, dann Contents+Page je Seite
    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(b"<< /Type /Pages /Kids [] /Count 0 >>")  # Platzhalter
    font_helv = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold = add_obj(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    font_mono = add_obj(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    )

    page_ids: list[int] = []
    for page_lines in pages:
        content_parts: list[str] = []
        # Fusszeile
        content_parts.append("BT")
        content_parts.append(f"/F1 8 Tf")
        content_parts.append(f"1 0 0 1 {margin:.2f} {margin * 0.45:.2f} Tm")
        content_parts.append(f"({_to_pdf_string(title)}) Tj")
        content_parts.append("ET")

        for kind, text, y_pos in page_lines:
            if kind == "blank" or not text:
                continue
            size = _FONT_SIZE.get(kind, 10)
            if kind in ("h1", "h2", "h3"):
                font = "F2"
            elif kind == "code":
                font = "F3"
            else:
                font = "F1"
            x = margin + (12.0 if kind in ("bullet", "number") else 0.0)
            content_parts.append("BT")
            content_parts.append(f"/{font} {size} Tf")
            content_parts.append(f"1 0 0 1 {x:.2f} {y_pos:.2f} Tm")
            content_parts.append(f"({_to_pdf_string(text)}) Tj")
            content_parts.append("ET")

        stream = "\n".join(content_parts).encode("latin-1", errors="replace")
        content_id = add_obj(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        page_id = add_obj(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {page_w:.2f} {page_h:.2f}] "
                f"/Resources << /Font << /F1 {font_helv} 0 R /F2 {font_bold} 0 R /F3 {font_mono} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    with out.open("wb") as fh:
        fh.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for i, obj in enumerate(objects, start=1):
            offsets.append(fh.tell())
            fh.write(f"{i} 0 obj\n".encode("ascii"))
            fh.write(obj)
            fh.write(b"\nendobj\n")
        xref_pos = fh.tell()
        fh.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        fh.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            fh.write(f"{off:010d} 00000 n \n".encode("ascii"))
        fh.write(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n"
            ).encode("ascii")
        )
