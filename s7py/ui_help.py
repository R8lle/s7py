"""Hilfe-Fenster: Schnellhilfe und Bedienungsanleitung (Markdown, Tkinter)."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

from s7py import help as manual
from s7py.constants import WINDOW_ID_HELP
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
    text.tag_configure("search", background=_HELP_SEARCH_BG, foreground=_HELP_FG)


def _insert_inline(text: tk.Text, line: str, tag: str) -> None:
    """Schreibt eine Zeile und markiert ``code``-Fragmente."""
    parts = re.split(r"(`[^`]+`)", line)
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) >= 2:
            text.insert(tk.END, part[1:-1], ("inline_code", tag))
        else:
            text.insert(tk.END, part, tag)
    text.insert(tk.END, "\n", tag)


def render_markdown(text: tk.Text, markdown: str) -> dict[str, str]:
    """Fuellt das Text-Widget; Rueckgabe: Titel → Tk-Index fuer Inhaltsverzeichnis."""
    text.configure(state=tk.NORMAL)
    text.delete("1.0", tk.END)
    anchors: dict[str, str] = {}
    in_code = False
    code_lines: list[str] = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            text.insert(tk.END, "\n".join(code_lines) + "\n", "code")
            code_lines = []

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(raw)
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
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if bullet:
            _insert_inline(text, f"• {bullet.group(1)}", "bullet")
            continue

        number = re.match(r"^(\d+)\.\s+(.*)$", line)
        if number:
            _insert_inline(text, f"{number.group(1)}. {number.group(2)}", "number")
            continue

        if not line.strip():
            text.insert(tk.END, "\n", "body")
            continue

        _insert_inline(text, line, "body")

    flush_code()
    text.configure(state=tk.DISABLED)
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
        self.btn_manual.pack(side=tk.LEFT)

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
        self.text.see("1.0")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _jump(self, _event: object = None) -> None:
        selection = self.toc.curselection()
        if not selection:
            return
        label = self.toc.get(selection[0]).strip()
        index = self._anchors.get(label)
        if index:
            self.text.see(index)

    def find_next(self) -> None:
        query = self.search.get().strip()
        if not query:
            return
        self.text.configure(state=tk.NORMAL)
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
        self.text.configure(state=tk.DISABLED)

    def _on_close(self) -> None:
        geometry = capture_window_geometry(self.window)
        if geometry:
            save_window_geometry(WINDOW_ID_HELP, geometry)
        self.window.destroy()


def open_help(parent: tk.Misc, name: str = "kurzanleitung") -> HelpWindow:
    window = HelpWindow(parent)
    window.show_document(name)
    return window
