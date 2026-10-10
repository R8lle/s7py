"""Hilfe-Fenster: Schnellhilfe, Bedienungsanleitung, TIA (Markdown, Tkinter)."""

from __future__ import annotations

import re
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from s7py import help as manual
from s7py.constants import APP_DIR, WINDOW_ID_HELP
from s7py.db import load_window_geometry, save_window_geometry
from s7py.ui_flow import (
    capture_window_geometry,
    center_toplevel_on_parent,
    restore_window_geometry,
)


# Dokumentfarben wie einvoice-de (helles Dokument, blaue Kapitelbaender).
_HELP_BG = "#FFFFFF"
_HELP_FG = "#1F2933"
_HELP_ACCENT = "#1565C0"
_HELP_ACCENT_LIGHT = "#E3EEFB"
_HELP_CODE_BG = "#F3F6FA"
_HELP_TOC_BG = "#F8F9FA"
_HELP_TOC_SELECT_BG = "#D0E3F7"
_HELP_SEARCH_BG = "#FFF3A3"
_HELP_H2_PAD = 160  # Leerzeichen fuer sichtbares Kapitelband in Tk


def _configure_tags(text: tk.Text) -> None:
    text.tag_configure(
        "h1",
        font=("TkDefaultFont", 18, "bold"),
        foreground=_HELP_ACCENT,
        spacing1=8,
        spacing3=10,
    )
    # Kapitelband: weisse Schrift auf Accent-Blau (wie einvoice-de h2-Tabellen).
    text.tag_configure(
        "h2",
        font=("TkDefaultFont", 14, "bold"),
        foreground="#FFFFFF",
        background=_HELP_ACCENT,
        spacing1=16,
        spacing3=10,
        lmargin1=6,
        lmargin2=6,
        rmargin=6,
    )
    text.tag_configure(
        "h3",
        font=("TkDefaultFont", 12, "bold"),
        foreground=_HELP_ACCENT,
        spacing1=12,
        spacing3=4,
    )
    text.tag_configure("body", font=("TkDefaultFont", 11), foreground=_HELP_FG, spacing3=4)
    text.tag_configure(
        "bullet",
        font=("TkDefaultFont", 11),
        foreground=_HELP_FG,
        lmargin1=20,
        lmargin2=36,
        spacing3=2,
    )
    text.tag_configure(
        "number",
        font=("TkDefaultFont", 11),
        foreground=_HELP_FG,
        lmargin1=20,
        lmargin2=36,
        spacing3=2,
    )
    text.tag_configure(
        "code",
        font=("Menlo", 10) if tk.TkVersion >= 8.5 else ("Courier", 10),
        background=_HELP_CODE_BG,
        foreground=_HELP_FG,
        lmargin1=12,
        lmargin2=12,
        spacing1=4,
        spacing3=6,
    )
    text.tag_configure(
        "inline_code",
        font=("Menlo", 10),
        background=_HELP_ACCENT_LIGHT,
        foreground=_HELP_ACCENT,
    )
    text.tag_configure("bold", font=("TkDefaultFont", 11, "bold"), foreground=_HELP_FG)
    text.tag_configure(
        "link",
        font=("TkDefaultFont", 11, "underline"),
        foreground=_HELP_ACCENT,
    )
    mono = ("Menlo", 10) if tk.TkVersion >= 8.5 else ("Courier", 10)
    text.tag_configure(
        "table_header",
        font=(mono[0], mono[1], "bold"),
        foreground=_HELP_ACCENT,
        background=_HELP_ACCENT_LIGHT,
        lmargin1=8,
        lmargin2=8,
        spacing1=2,
        spacing3=2,
    )
    text.tag_configure(
        "table_row",
        font=mono,
        foreground=_HELP_FG,
        background=_HELP_CODE_BG,
        lmargin1=8,
        lmargin2=8,
        spacing3=1,
    )
    text.tag_configure("search", background=_HELP_SEARCH_BG, foreground=_HELP_FG)


_INLINE_TOKEN = re.compile(
    r"(`[^`]+`)"
    r"|(\*\*[^*]+\*\*)"
    r"|(\[[^\]]+\]\([^)]+\))"
)


def _insert_inline(text: tk.Text, line: str, tag: str) -> None:
    """Schreibt eine Zeile mit ``code``, **fett** und [Links](url)."""
    pos = 0
    for match in _INLINE_TOKEN.finditer(line):
        if match.start() > pos:
            text.insert(tk.END, line[pos : match.start()], tag)
        token = match.group(0)
        if token.startswith("`") and token.endswith("`") and len(token) >= 2:
            text.insert(tk.END, token[1:-1], ("inline_code", tag))
        elif token.startswith("**") and token.endswith("**") and len(token) >= 4:
            text.insert(tk.END, token[2:-2], ("bold", tag))
        elif token.startswith("[") and "](" in token:
            label, _, rest = token[1:].partition("](")
            url = rest[:-1] if rest.endswith(")") else rest
            # URL als Tag am Insert (tag_add auf END ist unter Tk unzuverlaessig).
            text.insert(tk.END, label, ("link", tag, f"url:{url}"))
        else:
            text.insert(tk.END, token, tag)
        pos = match.end()
    if pos < len(line):
        text.insert(tk.END, line[pos:], tag)
    text.insert(tk.END, "\n", tag)


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    """Markdown-Trenner wie ``|---|---|``."""
    if not _is_table_row(line):
        return False
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells)


def _table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _plain_inline(value: str) -> str:
    plain = re.sub(r"`([^`]+)`", r"\1", value)
    plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", plain)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    return plain


def _insert_table(text: tk.Text, rows: list[str]) -> None:
    """Rendert eine Markdown-Tabelle als ausgerichteten Mono-Block."""
    body_rows = [r for r in rows if not _is_table_separator(r)]
    if not body_rows:
        return
    parsed = [_table_cells(r) for r in body_rows]
    cols = max(len(r) for r in parsed)
    for row in parsed:
        while len(row) < cols:
            row.append("")
    widths = [0] * cols
    for row in parsed:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(_plain_inline(cell)))

    for idx, row in enumerate(parsed):
        tag = "table_header" if idx == 0 else "table_row"
        for i, cell in enumerate(row):
            if i:
                text.insert(tk.END, "  ", tag)
            plain = _plain_inline(cell)
            pad = widths[i] - len(plain)
            # Code-Spans farbig; restlichen Text (inkl. Header) plain.
            for part in re.split(r"(`[^`]+`)", cell):
                if part.startswith("`") and part.endswith("`") and len(part) >= 2:
                    text.insert(tk.END, part[1:-1], ("inline_code", tag))
                elif part:
                    text.insert(tk.END, _plain_inline(part), tag)
            if pad > 0:
                text.insert(tk.END, " " * pad, tag)
        text.insert(tk.END, "\n", tag)
    text.insert(tk.END, "\n", "body")


def render_markdown(text: tk.Text, markdown: str) -> dict[str, str]:
    """Fuellt das Text-Widget; Rueckgabe: Titel → Tk-Index fuer Inhaltsverzeichnis."""
    text.configure(state=tk.NORMAL)
    text.delete("1.0", tk.END)
    anchors: dict[str, str] = {}
    in_code = False
    code_lines: list[str] = []
    lines = markdown.splitlines()
    i = 0

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            text.insert(tk.END, "\n".join(code_lines) + "\n", "code")
            code_lines = []

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(raw)
            i += 1
            continue

        if _is_table_row(line):
            table_rows: list[str] = []
            while i < len(lines) and _is_table_row(lines[i].rstrip()):
                table_rows.append(lines[i].rstrip())
                i += 1
            _insert_table(text, table_rows)
            continue

        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            tag = f"h{level}"
            anchors[title] = text.index(tk.END)
            if level == 2:
                # Auffuellende Leerzeichen → Hintergrund wirkt wie Kapitelband.
                band = f"  {title}"
                if len(band) < _HELP_H2_PAD:
                    band = band + (" " * (_HELP_H2_PAD - len(band)))
                text.insert(tk.END, band + "\n", tag)
            else:
                text.insert(tk.END, title + "\n", tag)
            i += 1
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if bullet:
            _insert_inline(text, f"• {bullet.group(1)}", "bullet")
            i += 1
            continue

        number = re.match(r"^(\d+)\.\s+(.*)$", line)
        if number:
            _insert_inline(text, f"{number.group(1)}. {number.group(2)}", "number")
            i += 1
            continue

        if not line.strip():
            text.insert(tk.END, "\n", "body")
            i += 1
            continue

        _insert_inline(text, line, "body")
        i += 1

    flush_code()
    # Nicht DISABLED: unter macOS Aqua kommen sonst keine Mausklicks auf Links an.
    text.configure(state=tk.NORMAL)
    return anchors


class HelpWindow:
    """Einzelnes Hilfe-Fenster mit Inhaltsverzeichnis und Umschalten der Dokumente."""

    def __init__(self, parent: tk.Misc) -> None:
        self.parent = parent
        self.name = "kurzanleitung"
        self._anchors: dict[str, str] = {}
        self.window = tk.Toplevel(parent)
        self.window.title("s7py – Hilfe")
        self.window.minsize(720, 480)

        top = ttk.Frame(self.window, padding=(8, 8, 8, 0))
        top.pack(fill=tk.X)
        self.search = ttk.Entry(top)
        self.search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.search.insert(0, "")
        self.search.bind("<Return>", lambda _e: self.find_next())
        ttk.Button(top, text="Suchen", command=self.find_next).pack(side=tk.LEFT, padx=(0, 8))
        self.btn_quick = ttk.Button(
            top, text="Schnellhilfe", command=lambda: self.show_document("kurzanleitung")
        )
        self.btn_quick.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_manual = ttk.Button(
            top, text="Bedienungsanleitung", command=lambda: self.show_document("anleitung")
        )
        self.btn_manual.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_tia = ttk.Button(
            top, text="TIA Portal", command=lambda: self.show_document("tia")
        )
        self.btn_tia.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Als PDF speichern…", command=self._export_pdf).pack(side=tk.LEFT)

        split = ttk.Panedwindow(self.window, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        toc_frame = ttk.Frame(split)
        self.toc = tk.Listbox(
            toc_frame,
            exportselection=False,
            width=28,
            background=_HELP_TOC_BG,
            foreground=_HELP_FG,
            selectbackground=_HELP_TOC_SELECT_BG,
            selectforeground=_HELP_FG,
            activestyle="none",
            highlightthickness=0,
            borderwidth=1,
            relief=tk.SOLID,
        )
        toc_scroll = ttk.Scrollbar(toc_frame, orient=tk.VERTICAL, command=self.toc.yview)
        self.toc.configure(yscrollcommand=toc_scroll.set)
        self.toc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        toc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.toc.bind("<<ListboxSelect>>", self._jump)
        split.add(toc_frame, weight=1)

        body = ttk.Frame(split)
        # Dokument: dunkel auf weiss — wie einvoice-de QTextBrowser.
        self.text = tk.Text(
            body,
            wrap=tk.WORD,
            relief=tk.FLAT,
            padx=8,
            pady=8,
            background=_HELP_BG,
            foreground=_HELP_FG,
            insertbackground=_HELP_FG,
            selectbackground=_HELP_TOC_SELECT_BG,
            selectforeground=_HELP_FG,
            highlightthickness=0,
            borderwidth=0,
        )
        body_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=body_scroll.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        _configure_tags(self.text)
        # Nur lesen: Tippen blockieren, Links per Widget-Bind (zuverlaessig auf macOS).
        self.text.bind("<Key>", lambda _e: "break")
        self.text.bind("<<Paste>>", lambda _e: "break")
        self.text.bind("<<Cut>>", lambda _e: "break")
        self.text.bind("<Button-1>", self._open_link)
        self.text.tag_bind("link", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _e: self.text.configure(cursor=""))
        split.add(body, weight=3)

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        saved = load_window_geometry(WINDOW_ID_HELP)
        if not restore_window_geometry(self.window, saved, min_w=720, min_h=480):
            center_toplevel_on_parent(self.window, parent, width=1000, height=700)

    def show_document(self, name: str) -> None:
        self.name = name
        title = manual.DOCUMENTS[name]
        self.window.title(f"s7py – {title}")
        markdown = manual.source(name)
        self._anchors = render_markdown(self.text, markdown)
        self.toc.delete(0, tk.END)
        for level, heading in manual.headings(markdown)[1:]:
            indent = "  " * (level - 1)
            self.toc.insert(tk.END, f"{indent}{heading}")
        self.btn_quick.state(["disabled"] if name == "kurzanleitung" else ["!disabled"])
        self.btn_manual.state(["disabled"] if name == "anleitung" else ["!disabled"])
        self.btn_tia.state(["disabled"] if name == "tia" else ["!disabled"])
        self.text.see("1.0")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _export_pdf(self) -> None:
        title = manual.DOCUMENTS.get(self.name, "Hilfe")
        default_name = f"s7py_{self.name}.pdf"
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Hilfe als PDF speichern",
            initialdir=str(APP_DIR),
            initialfile=default_name,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            from s7py.help_pdf import export_markdown_pdf

            export_markdown_pdf(manual.source(self.name), path, title=f"s7py – {title}")
        except Exception as exc:
            messagebox.showerror(
                "PDF speichern",
                f"PDF konnte nicht geschrieben werden:\n{exc}",
                parent=self.window,
            )
            return
        messagebox.showinfo(
            "PDF speichern",
            f"Gespeichert:\n{path}",
            parent=self.window,
        )

    def _jump(self, _event: object = None) -> None:
        selection = self.toc.curselection()
        if not selection:
            return
        label = self.toc.get(selection[0]).strip()
        index = self._anchors.get(label)
        if index:
            self.text.see(index)

    def _open_link(self, event: tk.Event) -> str | None:
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag.startswith("url:"):
                webbrowser.open(tag[4:])
                return "break"
        return None

    def find_next(self) -> None:
        query = self.search.get().strip()
        if not query:
            return
        self.text.tag_remove("search", "1.0", tk.END)
        start = self.text.index(tk.INSERT)
        pos = self.text.search(query, start, tk.END, nocase=True)
        if not pos:
            pos = self.text.search(query, "1.0", tk.END, nocase=True)
        if pos:
            end = f"{pos}+{len(query)}c"
            self.text.tag_add("search", pos, end)
            self.text.mark_set(tk.INSERT, end)
            self.text.see(pos)

    def _on_close(self) -> None:
        geometry = capture_window_geometry(self.window)
        if geometry:
            save_window_geometry(WINDOW_ID_HELP, geometry)
        self.window.destroy()


def open_help(parent: tk.Misc, name: str = "kurzanleitung") -> HelpWindow:
    window = HelpWindow(parent)
    window.show_document(name)
    return window
