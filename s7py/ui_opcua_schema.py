"""OPC-UA-Variablen manuell pflegen und Schema/DB synchronisieren."""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

from s7py.constants import APP_DIR, DB_CONFIG_PATH
from s7py.db import (
    create_connection,
    create_database,
    migrate_database,
    resolve_db_path,
    save_plc_schema,
)
from s7py.schema import (
    DbItem,
    OPCUA_DATATYPES,
    default_plc_schema,
    schema_from_opcua_manual,
)
from s7py.ui_base import S7PyAppProtocol
from s7py.ui_opcua_browse import open_opcua_browse_dialog


@dataclass
class _OpcUaEditorRow:
    row_idx: int
    widgets: list[tk.Widget]
    name_var: tk.StringVar
    type_var: tk.StringVar
    node_var: tk.StringVar
    store_var: tk.BooleanVar


# Spaltenbreiten (Pixel); NodeId-Spalte (Index 2) dehnt sich mit weight=1.
_OPCUA_COL_WIDTHS = (180, 100, 240, 44, 56, 44)


def _configure_opcua_table_columns(table: ttk.Frame) -> None:
    for col, width in enumerate(_OPCUA_COL_WIDTHS):
        table.columnconfigure(col, minsize=width, weight=1 if col == 2 else 0)


def _grid_opcua_row(row_idx: int, widgets: list[tk.Widget]) -> None:
    for col, widget in enumerate(widgets):
        sticky = "ew" if col <= 2 else "w"
        widget.grid(row=row_idx, column=col, sticky=sticky, padx=(0, 8), pady=2)


def _relayout_opcua_rows(rows: list[_OpcUaEditorRow]) -> None:
    for index, row in enumerate(rows):
        row.row_idx = index + 1
        _grid_opcua_row(row.row_idx, row.widgets)


class OpcUaSchemaMixin:
    """Dialog zum manuellen Anlegen und Aendern von OPC-UA-Variablen."""

    def _on_edit_opcua_variables(self: S7PyAppProtocol) -> None:
        if self.write_thread is not None and self.write_thread.is_alive():
            messagebox.showwarning(
                "OPC UA",
                "Bitte zuerst die Aufzeichnung pausieren, bevor OPC-UA-Variablen "
                "geaendert werden.",
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("OPC UA — Variablen manuell")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("980x520")
        dialog.minsize(900, 420)

        outer = ttk.Frame(dialog, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        source_hint = self._schema.block_name or "Standard"
        if self._schema.source_file:
            source_hint = f"{source_hint} ({os.path.basename(self._schema.source_file)})"
        ttk.Label(
            outer,
            text=(
                f"Aktuelle Quelle: {source_hint}. Hier koennen Sie Variablennamen, "
                "Typ, NodeId und SQLite-Speicherung frei festlegen — unabhaengig "
                "von Standard oder TIA-Import. Gespeichert wird in s7py_db.json."
            ),
            wraplength=940,
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

        _configure_opcua_table_columns(scroll_frame)
        bold = ("", 10, "bold")
        for col, title in enumerate(("Name", "Typ", "NodeId", "", "SQLite", "")):
            ttk.Label(scroll_frame, text=title, font=bold).grid(
                row=0, column=col, sticky="w", padx=(0, 8), pady=(0, 6)
            )

        rows: list[_OpcUaEditorRow] = []

        def browse_for_row(row: _OpcUaEditorRow) -> None:
            endpoint = self._get_opcua_endpoint()
            if not endpoint:
                messagebox.showwarning(
                    "OPC UA Browse",
                    "Bitte zuerst einen OPC-UA-Endpoint in der Verbindungszeile "
                    "eintragen (oder Protokoll OPC UA waehlen).",
                    parent=dialog,
                )
                return

            def on_select(node_id: str, display_name: str) -> None:
                row.node_var.set(node_id)
                if not row.name_var.get().strip():
                    row.name_var.set(display_name.replace(" ", "_"))

            open_opcua_browse_dialog(dialog, endpoint, on_select=on_select)

        def refresh_count_choices() -> None:
            names = [row.name_var.get().strip() for row in rows if row.name_var.get().strip()]
            count_combo["values"] = names
            if count_var.get() not in names and names:
                count_var.set(names[0])

        def remove_row(row: _OpcUaEditorRow) -> None:
            if row in rows:
                for widget in row.widgets:
                    widget.destroy()
                rows.remove(row)
                _relayout_opcua_rows(rows)
                refresh_count_choices()

        def add_row(
            *,
            name: str = "",
            datatype: str = "Real",
            node_id: str = "",
            store: bool = True,
        ) -> None:
            row_idx = len(rows) + 1

            name_var = tk.StringVar(value=name)
            type_var = tk.StringVar(value=datatype if datatype in OPCUA_DATATYPES else "Real")
            node_var = tk.StringVar(value=node_id)
            store_var = tk.BooleanVar(value=store)

            browse_btn = ttk.Button(scroll_frame, text="...", width=3)
            del_btn = ttk.Button(scroll_frame, text="X", width=3)
            widgets: list[tk.Widget] = [
                ttk.Entry(scroll_frame, textvariable=name_var, width=22),
                ttk.Combobox(
                    scroll_frame,
                    textvariable=type_var,
                    values=list(OPCUA_DATATYPES),
                    width=10,
                    state="readonly",
                ),
                ttk.Entry(scroll_frame, textvariable=node_var),
                browse_btn,
                ttk.Checkbutton(scroll_frame, variable=store_var),
                del_btn,
            ]
            editor_row = _OpcUaEditorRow(
                row_idx, widgets, name_var, type_var, node_var, store_var
            )
            browse_btn.configure(command=lambda r=editor_row: browse_for_row(r))
            _grid_opcua_row(row_idx, widgets)
            rows.append(editor_row)
            del_btn.configure(command=lambda r=editor_row: remove_row(r))
            name_var.trace_add("write", lambda *_a: refresh_count_choices())
            refresh_count_choices()

        if self._schema.items:
            for item in self._schema.items:
                add_row(
                    name=item.name,
                    datatype=item.datatype,
                    node_id=item.node_id,
                    store=item.store,
                )
        else:
            add_row(name="Count", datatype="DWord", store=True)
            add_row(name="Temperature", datatype="Real", store=True)

        row_btn = ttk.Frame(outer)
        row_btn.grid(row=3, column=0, sticky="w", pady=(8, 0))

        def load_default_template() -> None:
            if rows and not messagebox.askyesno(
                "OPC UA",
                "Aktuelle Zeilen durch die Standard-Struktur ersetzen?",
                parent=dialog,
            ):
                return
            for row in list(rows):
                remove_row(row)
            for item in default_plc_schema().items:
                add_row(
                    name=item.name,
                    datatype=item.datatype,
                    node_id=item.node_id,
                    store=item.store,
                )
            count_var.set("Count")

        ttk.Button(row_btn, text="+ Zeile", command=lambda: add_row()).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(row_btn, text="Aus Standard laden", command=load_default_template).pack(
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
                        bytebit="opcua",
                        store=bool(row.store_var.get()),
                        node_id=row.node_var.get().strip(),
                    )
                )
            return built

        def on_save() -> None:
            try:
                schema = schema_from_opcua_manual(
                    build_items(),
                    count_field=count_var.get().strip(),
                )
            except ValueError as exc:
                messagebox.showerror("OPC UA", str(exc), parent=dialog)
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
                f"OPC-UA-Schema gespeichert: {len(schema.items)} Variablen, "
                f"Count={schema.count_field}."
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
                initial = os.path.dirname(resolve_db_path(self._db_path)) or str(APP_DIR)
                db_path = filedialog.asksaveasfilename(
                    parent=dialog,
                    title="Neue SQLite-Datenbank",
                    initialdir=initial,
                    initialfile="s7py_opcua.db",
                    defaultextension=".db",
                    filetypes=[("SQLite", "*.db"), ("Alle Dateien", "*.*")],
                )
                if not db_path:
                    messagebox.showinfo(
                        "OPC UA",
                        "Schema gespeichert. Datenbank wurde nicht geaendert.",
                        parent=dialog,
                    )
                    dialog.destroy()
                    return
                db_path = resolve_db_path(db_path)
                if not create_database(db_path, schema):
                    messagebox.showerror(
                        "Datenbank",
                        f"Neue Datenbank konnte nicht angelegt werden:\n{db_path}",
                        parent=dialog,
                    )
                    return
                save_plc_schema(schema, last_database=db_path)
                self._attach_database(db_path, create_if_missing=False, silent=False)

            messagebox.showinfo(
                "OPC UA",
                f"{len(schema.items)} Variablen gespeichert.\n"
                f"Konfiguration: {DB_CONFIG_PATH}",
                parent=dialog,
            )
            dialog.destroy()

        ttk.Button(btn_row, text="Abbrechen", command=dialog.destroy).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(btn_row, text="Speichern", command=on_save).pack(side=tk.RIGHT)
