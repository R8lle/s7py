"""Snap7-Variablen pflegen (TIA-Import, Aktiv-Flag, manuelle Zeilen)."""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from s7py.constants import APP_DIR, DB_CONFIG_PATH
from s7py.db import (
    create_connection,
    create_database,
    migrate_database,
    resolve_db_path,
    sanitize_sqlite_save_path,
    save_plc_db_number,
    save_plc_schema,
)
from s7py.schema import (
    DbItem,
    SNAP7_DATATYPES,
    parse_tia_data_block_file,
    schema_from_snap7_manual,
)
from s7py.ui_base import S7PyAppProtocol
from s7py.ui_flow import center_toplevel_on_parent


@dataclass
class _Snap7EditorRow:
    row_idx: int
    widgets: list[tk.Widget]
    name_var: tk.StringVar
    type_var: tk.StringVar
    bytebit_var: tk.StringVar
    store_var: tk.BooleanVar
    s7_type: str = ""
    item_size: int = 0


# Spaltenbreiten (Pixel) fuer scroll_frame.columnconfigure(minsize=...).
_SNAP7_COL_WIDTHS = (180, 100, 100, 56, 44)


def _configure_snap7_table_columns(table: ttk.Frame) -> None:
    for col, width in enumerate(_SNAP7_COL_WIDTHS):
        table.columnconfigure(col, minsize=width)


def _grid_snap7_row(row_idx: int, widgets: list[tk.Widget]) -> None:
    for col, widget in enumerate(widgets):
        sticky = "ew" if col < 3 else "w"
        widget.grid(row=row_idx, column=col, sticky=sticky, padx=(0, 8), pady=2)


def _relayout_snap7_rows(rows: list[_Snap7EditorRow]) -> None:
    for index, row in enumerate(rows):
        row.row_idx = index + 1
        _grid_snap7_row(row.row_idx, row.widgets)


class Snap7SchemaMixin:
    """Dialog zum Pflegen von Snap7-Datenpunkten analog zum OPC-UA-Editor."""

    def _on_edit_snap7_variables(self: S7PyAppProtocol) -> None:
        if self.write_thread is not None and self.write_thread.is_alive():
            messagebox.showwarning(
                "Snap7",
                "Bitte zuerst die Aufzeichnung pausieren, bevor Snap7-Variablen "
                "geaendert werden.",
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("Snap7 — Variablen")
        dialog.transient(self)
        dialog.grab_set()
        dialog.minsize(840, 420)

        outer = ttk.Frame(dialog, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        imported_source = self._schema.source_file
        imported_block = self._schema.block_name or "Standard"
        if imported_source:
            source_hint = f"{imported_block} ({os.path.basename(imported_source)})"
        else:
            source_hint = imported_block

        ttk.Label(
            outer,
            text=(
                f"Aktuelle Quelle: {source_hint}. TIA-DB importieren ersetzt alle "
                "Zeilen. Pro Datenpunkt „Aktiv“ steuert, ob der Wert von der SPS "
                "gelesen und in SQLite geschrieben wird. Gespeichert in s7py_db.json."
            ),
            wraplength=880,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        toolbar = ttk.Frame(outer)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text="Count-Feld:").pack(side=tk.LEFT, padx=(0, 4))
        count_var = tk.StringVar(
            value=self._schema.count_field
            if self._schema.count_field
            else (self._schema.items[0].name if self._schema.items else "Count")
        )
        count_combo = ttk.Combobox(
            toolbar, textvariable=count_var, width=18, state="readonly"
        )
        count_combo.pack(side=tk.LEFT, padx=(0, 12))

        table_host = ttk.Frame(outer)
        table_host.grid(row=2, column=0, sticky="nsew")
        table_host.columnconfigure(0, weight=1)
        table_host.rowconfigure(0, weight=1)

        canvas = tk.Canvas(table_host, highlightthickness=0)
        scrollbar = ttk.Scrollbar(table_host, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _sync_scroll_width(event: tk.Event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        canvas.bind("<Configure>", _sync_scroll_width)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        _configure_snap7_table_columns(scroll_frame)
        bold = ("", 10, "bold")
        for col, title in enumerate(("Name", "Typ", "Byte/Bit", "Aktiv", "")):
            ttk.Label(scroll_frame, text=title, font=bold).grid(
                row=0, column=col, sticky="w", padx=(0, 8), pady=(0, 6)
            )

        rows: list[_Snap7EditorRow] = []

        def refresh_count_choices() -> None:
            names = [
                row.name_var.get().strip() for row in rows if row.name_var.get().strip()
            ]
            count_combo["values"] = names
            if count_var.get() not in names and names:
                count_var.set(names[0])

        def remove_row(row: _Snap7EditorRow) -> None:
            if row in rows:
                for widget in row.widgets:
                    widget.destroy()
                rows.remove(row)
                _relayout_snap7_rows(rows)
                refresh_count_choices()

        def add_row(
            *,
            name: str = "",
            datatype: str = "Real",
            bytebit: str = "0.0",
            store: bool = True,
            s7_type: str = "",
            size: int = 0,
        ) -> None:
            row_idx = len(rows) + 1

            name_var = tk.StringVar(value=name)
            type_var = tk.StringVar(
                value=datatype if datatype in SNAP7_DATATYPES else "Real"
            )
            bytebit_var = tk.StringVar(value=bytebit)
            store_var = tk.BooleanVar(value=store)

            widgets: list[tk.Widget] = [
                ttk.Entry(scroll_frame, textvariable=name_var, width=22),
                ttk.Combobox(
                    scroll_frame,
                    textvariable=type_var,
                    values=list(SNAP7_DATATYPES),
                    width=10,
                    state="readonly",
                ),
                ttk.Entry(scroll_frame, textvariable=bytebit_var, width=12),
                ttk.Checkbutton(scroll_frame, variable=store_var),
                ttk.Button(scroll_frame, text="X", width=3),
            ]
            editor_row = _Snap7EditorRow(
                row_idx,
                widgets,
                name_var,
                type_var,
                bytebit_var,
                store_var,
                s7_type=s7_type,
                item_size=size,
            )
            _grid_snap7_row(row_idx, widgets)
            rows.append(editor_row)
            widgets[4].configure(command=lambda r=editor_row: remove_row(r))
            name_var.trace_add("write", lambda *_a: refresh_count_choices())
            refresh_count_choices()

        if self._schema.items and not all(
            (it.bytebit or "").strip().lower() == "opcua" for it in self._schema.items
        ):
            for item in self._schema.items:
                add_row(
                    name=item.name,
                    datatype=item.datatype,
                    bytebit=item.bytebit,
                    store=item.store,
                    s7_type=item.s7_type,
                    size=item.size,
                )
        else:
            add_row(name="Count", datatype="DWord", bytebit="0.0", store=True)
            add_row(name="Temperature", datatype="Real", bytebit="4.0", store=True)

        row_btn = ttk.Frame(outer)
        row_btn.grid(row=3, column=0, sticky="w", pady=(8, 0))

        def import_tia_db() -> None:
            nonlocal imported_source, imported_block

            if rows and not messagebox.askyesno(
                "TIA-Import",
                "Alle aktuellen Zeilen durch den TIA-Datenbaustein ersetzen?",
                parent=dialog,
            ):
                return

            initial_dir = str(
                Path(imported_source).parent if imported_source else APP_DIR
            )
            path = filedialog.askopenfilename(
                parent=dialog,
                title="TIA-Datenbaustein importieren",
                initialdir=initial_dir,
                filetypes=[
                    ("TIA Datenbaustein", "*.db"),
                    ("Alle Dateien", "*.*"),
                ],
            )
            if not path:
                return

            try:
                imported = parse_tia_data_block_file(path)
            except (OSError, ValueError) as exc:
                messagebox.showerror("TIA-Import", str(exc), parent=dialog)
                return

            db_number = self._ask_plc_db_number()
            if db_number is None:
                return
            imported.db_number = db_number
            self.var_plc_db_number.set(db_number)
            save_plc_db_number(db_number)

            for row in list(rows):
                remove_row(row)
            for item in imported.items:
                add_row(
                    name=item.name,
                    datatype=item.datatype,
                    bytebit=item.bytebit,
                    store=item.store,
                    s7_type=item.s7_type,
                    size=item.size,
                )
            count_var.set(imported.count_field)
            imported_source = imported.source_file
            imported_block = imported.block_name

        ttk.Button(row_btn, text="+ Zeile", command=lambda: add_row()).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(row_btn, text="TIA-DB importieren…", command=import_tia_db).pack(
            side=tk.LEFT
        )

        btn_row = ttk.Frame(outer)
        btn_row.grid(row=4, column=0, sticky="e", pady=(12, 0))

        def build_items() -> list[DbItem]:
            built: list[DbItem] = []
            for row in rows:
                name = row.name_var.get().strip()
                if not name:
                    continue
                built.append(
                    DbItem(
                        name=name,
                        datatype=row.type_var.get().strip(),
                        bytebit=row.bytebit_var.get().strip(),
                        store=bool(row.store_var.get()),
                        s7_type=row.s7_type,
                        size=row.item_size,
                    )
                )
            return built

        def on_save() -> None:
            try:
                schema = schema_from_snap7_manual(
                    build_items(),
                    count_field=count_var.get().strip(),
                    source_file=imported_source,
                    block_name=imported_block,
                    db_number=self._get_plc_db_number(),
                )
            except ValueError as exc:
                messagebox.showerror("Snap7", str(exc), parent=dialog)
                return

            choice = messagebox.askyesnocancel(
                "Datenbank",
                "Wie soll die SQLite-Datenbank behandelt werden?\n\n"
                "Ja = Bestehende DB anpassen (fehlende Spalten ergaenzen)\n"
                "Nein = Neue leere Datenbank anlegen...\n"
                "Abbrechen = Aenderung verwerfen",
                parent=dialog,
            )
            if choice is None:
                return

            save_plc_schema(schema, last_database=self._db_path)
            self._apply_plc_schema(schema)
            self._log(
                f"Snap7-Schema gespeichert: {len(schema.items)} Datenpunkte, "
                f"{len(schema.sqlite_columns)} aktiv, Count={schema.count_field}."
            )

            if choice:
                db_path = resolve_db_path(self.var_db.get().strip() or self._db_path)
                if os.path.isfile(db_path):
                    conn = create_connection(db_path)
                    if conn is not None:
                        migrate_database(conn, schema)
                        conn.close()
                        self._log(f"SQLite-Schema angepasst: {db_path}")
                if self.conn_read is not None:
                    migrate_database(self.conn_read, schema)
                    self._refresh_db_stats()
                    self._clear_plot_cache()
                    self._update_plot_cache_and_draw()
                elif db_path and os.path.isfile(db_path):
                    self._attach_database(db_path, create_if_missing=False, silent=True)
            else:
                current_db = Path(resolve_db_path(self._db_path))
                initial = str(current_db.parent) if current_db.parent.parts else str(APP_DIR)
                initial_name = current_db.name or "s7py.db"
                db_path = filedialog.asksaveasfilename(
                    parent=dialog,
                    title="Neue SQLite-Datenbank",
                    initialdir=initial,
                    initialfile=initial_name,
                    defaultextension="",
                    filetypes=[("SQLite", "*.db"), ("Alle Dateien", "*.*")],
                )
                if not db_path:
                    messagebox.showinfo(
                        "Snap7",
                        "Schema gespeichert. Datenbank wurde nicht geaendert.",
                        parent=dialog,
                    )
                    dialog.destroy()
                    return
                db_path = resolve_db_path(sanitize_sqlite_save_path(db_path))
                if self.conn_read is not None:
                    try:
                        self.conn_read.close()
                    except Exception:
                        pass
                    self.conn_read = None
                    self.cursor_read = None
                if not create_database(db_path, schema, replace=True):
                    messagebox.showerror(
                        "Datenbank",
                        f"Neue Datenbank konnte nicht angelegt werden:\n{db_path}",
                        parent=dialog,
                    )
                    return
                save_plc_schema(schema, last_database=db_path)
                self._attach_database(db_path, create_if_missing=False, silent=False)

            messagebox.showinfo(
                "Snap7",
                f"{len(schema.items)} Datenpunkte gespeichert "
                f"({len(schema.sqlite_columns)} aktiv).\n"
                f"Konfiguration: {DB_CONFIG_PATH}",
                parent=dialog,
            )
            dialog.destroy()

        ttk.Button(btn_row, text="Abbrechen", command=dialog.destroy).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(btn_row, text="Speichern", command=on_save).pack(side=tk.RIGHT)
        center_toplevel_on_parent(dialog, self, width=920, height=520)
