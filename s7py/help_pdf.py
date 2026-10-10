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
            level = len(heading.group(1))
            title = _plain(heading.group(2).strip())
            if level == 2 and blocks and blocks[-1][0] != "blank":
                blocks.append(("blank", ""))
            blocks.append((f"h{level}", title))
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


def _wrap_lines(kind: str, text: str, *, chars_body: int = 88, chars_code: int = 92) -> list[tuple[str, str]]:
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
    "h1": 18,
    "h2": 14,
    "h3": 12,
    "body": 10,
    "bullet": 10,
    "number": 10,
    "code": 8,
    "blank": 10,
}
_LINE_GAP = {
    "h1": 24,
    "h2": 22,
    "h3": 16,
    "body": 13,
    "bullet": 13,
    "number": 13,
    "code": 11,
    "blank": 10,
}


def export_markdown_pdf(markdown: str, path: str | Path, *, title: str = "s7py Hilfe") -> None:
    """Schreibt den Hilfetext als mehrseitiges A4-PDF (ohne Extra-Abhaengigkeit)."""
    out = Path(path)
    page_w, page_h = 595.28, 841.89  # A4 pt
    margin = 52.0
    y_top = page_h - margin
    y_bottom = margin + 36.0

    drawn: list[tuple[str, str]] = []
    for kind, text in _blocks(markdown):
        drawn.extend(_wrap_lines(kind, text))

    pages: list[list[tuple[str, str, float]]] = [[]]
    y = y_top
    for kind, text in drawn:
        gap = _LINE_GAP.get(kind, 13)
        # Vor h2 etwas mehr Luft / ggf. neue Seite bei wenig Platz
        if kind == "h2" and y < y_top - 2:
            gap += 6
        if y - gap < y_bottom:
            pages.append([])
            y = y_top
        pages[-1].append((kind, text, y))
        y -= gap

    total_pages = max(1, len(pages))
    objects: list[bytes] = []

    def add_obj(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(b"<< /Type /Pages /Kids [] /Count 0 >>")
    font_helv = add_obj(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    font_bold = add_obj(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    font_mono = add_obj(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    )

    page_ids: list[int] = []
    for page_index, page_lines in enumerate(pages, start=1):
        content_parts: list[str] = []

        # Feiner Kopfstrich
        content_parts.append("0.85 0.88 0.92 rg")
        content_parts.append(
            f"{margin:.2f} {page_h - margin + 10:.2f} {page_w - 2 * margin:.2f} 1.2 re f"
        )

        for kind, text, y_pos in page_lines:
            if kind == "blank":
                continue
            if kind == "h2":
                # Hellblaues Kapitelband hinter der Ueberschrift
                band_y = y_pos - 4
                content_parts.append("0.89 0.93 0.98 rg")
                content_parts.append(
                    f"{margin - 4:.2f} {band_y - 3:.2f} {page_w - 2 * margin + 8:.2f} 18 re f"
                )
            if not text:
                continue
            size = _FONT_SIZE.get(kind, 10)
            if kind in ("h1", "h2", "h3"):
                font = "F2"
                # Accent-Blau fuer Ueberschriften
                content_parts.append("0.082 0.396 0.753 rg")
            elif kind == "code":
                font = "F3"
                content_parts.append("0.12 0.16 0.20 rg")
            else:
                font = "F1"
                content_parts.append("0.12 0.16 0.20 rg")
            x = margin + (12.0 if kind in ("bullet", "number") else 0.0)
            content_parts.append("BT")
            content_parts.append(f"/{font} {size} Tf")
            content_parts.append(f"1 0 0 1 {x:.2f} {y_pos:.2f} Tm")
            content_parts.append(f"({_to_pdf_string(text)}) Tj")
            content_parts.append("ET")

        # Fusszeile: Titel links, Seitenzahl rechts
        footer_y = margin * 0.55
        content_parts.append("0.42 0.45 0.50 rg")
        content_parts.append("BT")
        content_parts.append("/F1 8 Tf")
        content_parts.append(f"1 0 0 1 {margin:.2f} {footer_y:.2f} Tm")
        content_parts.append(f"({_to_pdf_string(title)}) Tj")
        content_parts.append("ET")
        page_label = f"Seite {page_index} / {total_pages}"
        # grobe Rechtsausrichtung: Zeichenbreite ~4.5 pt bei 8 pt Helvetica
        label_x = page_w - margin - len(page_label) * 4.5
        content_parts.append("BT")
        content_parts.append("/F1 8 Tf")
        content_parts.append(f"1 0 0 1 {label_x:.2f} {footer_y:.2f} Tm")
        content_parts.append(f"({_to_pdf_string(page_label)}) Tj")
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
