"""Hilfe → Info und Lizenzen: Version, Build, Copyright, Lizenz, Fremdkomponenten."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from s7py import COPYRIGHT, LICENSE_NAME, __version__
from s7py.about import (
    build_info,
    license_text,
    system_info,
    third_party,
    third_party_license_text,
)
from s7py.constants import APP_DIR, WINDOW_ID_ABOUT
from s7py.db import load_window_geometry, save_window_geometry
from s7py.ui_flow import (
    capture_window_geometry,
    center_toplevel_on_parent,
    restore_window_geometry,
)


def open_about(parent: tk.Misc) -> tk.Toplevel:
    dialog = tk.Toplevel(parent)
    dialog.title("Info und Lizenzen")
    dialog.transient(parent)
    dialog.minsize(640, 420)

    def close_dialog() -> None:
        geometry = capture_window_geometry(dialog)
        if geometry:
            save_window_geometry(WINDOW_ID_ABOUT, geometry)
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    notebook = ttk.Notebook(dialog)
    notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    info = ttk.Frame(notebook, padding=12)
    notebook.add(info, text="Info")
    head = (
        f"s7py {__version__}\n\n"
        "SPS-Daten lesen (Snap7 / OPC UA), in SQLite speichern und als Live-Diagramm anzeigen.\n\n"
        f"Version  {__version__}\n"
        f"Build    {build_info()}\n\n"
        f"{COPYRIGHT}\n"
        f"Freie Software unter der {LICENSE_NAME} (siehe Reiter „Lizenz“).\n\n"
        f"Datenordner\n{APP_DIR}"
    )
    ttk.Label(info, text=head, justify=tk.LEFT, wraplength=720).pack(anchor=tk.W)
    details = tk.Text(info, height=8, wrap=tk.WORD)
    details.insert("1.0", system_info())
    details.configure(state=tk.DISABLED)
    details.pack(fill=tk.BOTH, expand=True, pady=(12, 8))

    def copy_details() -> None:
        dialog.clipboard_clear()
        dialog.clipboard_append(details.get("1.0", "end-1c"))
        copy_btn.configure(text="Kopiert ✓")

    copy_btn = ttk.Button(info, text="Angaben kopieren", command=copy_details)
    copy_btn.pack(anchor=tk.W)

    license_tab = ttk.Frame(notebook, padding=8)
    notebook.add(license_tab, text="Lizenz")
    license_box = tk.Text(license_tab, wrap=tk.WORD)
    license_box.insert("1.0", license_text())
    license_box.configure(state=tk.DISABLED)
    license_box.pack(fill=tk.BOTH, expand=True)

    third = ttk.Frame(notebook, padding=8)
    notebook.add(third, text="Fremdkomponenten")
    columns = ("name", "version", "license", "purpose")
    tree = ttk.Treeview(third, columns=columns, show="headings", height=12)
    tree.heading("name", text="Komponente")
    tree.heading("version", text="Version")
    tree.heading("license", text="Lizenz")
    tree.heading("purpose", text="Zweck")
    tree.column("name", width=160, stretch=False)
    tree.column("version", width=90, stretch=False)
    tree.column("license", width=200, stretch=False)
    tree.column("purpose", width=260, stretch=True)
    for component in third_party():
        tree.insert(
            "",
            tk.END,
            values=(component.name, component.version, component.license, component.purpose),
        )
    tree.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        third,
        text="Ausfuehrliche Texte: Reiter „Drittlizenzen“ bzw. LICENSE_THIRD_PARTY.txt.",
        wraplength=720,
    ).pack(anchor=tk.W, pady=(8, 0))

    third_text = ttk.Frame(notebook, padding=8)
    notebook.add(third_text, text="Drittlizenzen")
    third_box = tk.Text(third_text, wrap=tk.WORD)
    third_box.insert("1.0", third_party_license_text())
    third_box.configure(state=tk.DISABLED)
    third_box.pack(fill=tk.BOTH, expand=True)

    bottom = ttk.Frame(dialog, padding=(8, 0, 8, 8))
    bottom.pack(fill=tk.X)
    ttk.Button(bottom, text="Schliessen", command=close_dialog).pack(side=tk.RIGHT)

    saved = load_window_geometry(WINDOW_ID_ABOUT)
    if not restore_window_geometry(dialog, saved, min_w=640, min_h=420):
        center_toplevel_on_parent(dialog, parent, width=820, height=600)
    dialog.lift()
    return dialog
