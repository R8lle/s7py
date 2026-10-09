"""OPC-UA-Variablen manuell pflegen und Schema/DB synchronisieren."""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from s7py.constants import APP_DIR, DB_CONFIG_PATH, WINDOW_ID_OPCUA_VARS
from s7py.db import (
    create_connection,
    create_database,
    load_window_geometry,
    migrate_database,
    resolve_db_path,
    sanitize_sqlite_save_path,
    sqlite_save_dialog_params,
    save_plc_schema,
    save_window_geometry,
)
from s7py.schema import (
    DbItem,
    OPCUA_DATATYPES,
    default_plc_schema,
    schema_from_opcua_manual,
)
from s7py.ui_base import S7PyAppProtocol
from s7py.ui_flow import (
    capture_window_geometry,
    center_toplevel_on_parent,
    restore_window_geometry,
)
from s7py.opcua_browse import suggested_name_from_node_id
from s7py.ui_opcua_browse import open_opcua_browse_dialog


@dataclass
class _OpcUaEditorRow:
    row_idx: int
    widgets: list[tk.Widget]
    name_var: tk.StringVar
    type_var: tk.StringVar
    node_var: tk.StringVar
    store_var: tk.BooleanVar
    group_id: str = ""
    group_label: str = ""
    group_label_widget: ttk.Label | None = None


# Spalten: Name, Typ, NodeId, Browse, SQLite, Gruppe, Loeschen.
_OPCUA_COL_WIDTHS = (280, 100, 200, 44, 56, 110, 44)


def _configure_opcua_table_columns(table: ttk.Frame) -> None:
    for col, width in enumerate(_OPCUA_COL_WIDTHS):
        table.columnconfigure(col, minsize=width, weight=1 if col in (0, 2) else 0)


def _grid_opcua_row(row_idx: int, widgets: list[tk.Widget]) -> None:
    for col, widget in enumerate(widgets):
        sticky = "ew" if col in (0, 2, 5) else "w"
        widget.grid(row=row_idx, column=col, sticky=sticky, padx=(0, 8), pady=2)


def _short_group_label(group_id: str, fallback: str = "") -> str:
    if fallback.strip():
        return fallback.strip()[:40]
    if not group_id:
        return ""
    suggested = suggested_name_from_node_id(group_id, "")
    if suggested:
        return suggested[:40]
    return group_id[-40:] if len(group_id) > 40 else group_id


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
        dialog.minsize(900, 420)

        def close_dialog() -> None:
            geometry = capture_window_geometry(dialog)
            if geometry:
                save_window_geometry(WINDOW_ID_OPCUA_VARS, geometry)
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

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
        for col, title in enumerate(
            ("Name", "Typ", "NodeId", "", "SQLite", "Gruppe", "")
        ):
            ttk.Label(scroll_frame, text=title, font=bold).grid(
                row=0, column=col, sticky="w", padx=(0, 8), pady=(0, 6)
            )

        rows: list[_OpcUaEditorRow] = []
        focused_row: list[_OpcUaEditorRow | None] = [None]

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
                if focused_row[0] is row:
                    focused_row[0] = None
                _relayout_opcua_rows(rows)
                refresh_count_choices()

        def add_row(
            *,
            name: str = "",
            datatype: str = "Real",
            node_id: str = "",
            store: bool = True,
            group_id: str = "",
            group_label: str = "",
        ) -> _OpcUaEditorRow:
            row_idx = len(rows) + 1

            name_var = tk.StringVar(value=name)
            type_var = tk.StringVar(value=datatype if datatype in OPCUA_DATATYPES else "Real")
            node_var = tk.StringVar(value=node_id)
            store_var = tk.BooleanVar(value=store)
            label_text = _short_group_label(group_id, group_label) if group_id else ""

            browse_btn = ttk.Button(scroll_frame, text="...", width=3)
            del_btn = ttk.Button(scroll_frame, text="X", width=3)
            name_entry = ttk.Entry(scroll_frame, textvariable=name_var, width=40)
            type_combo = ttk.Combobox(
                scroll_frame,
                textvariable=type_var,
                values=list(OPCUA_DATATYPES),
                width=10,
                state="readonly",
            )
            node_entry = ttk.Entry(scroll_frame, textvariable=node_var)
            store_cb = ttk.Checkbutton(scroll_frame, variable=store_var)
            # ttk.Label folgt dem Dark/Light-Theme (kein helles tk.Label-Rechteck).
            group_lbl = ttk.Label(
                scroll_frame,
                text=label_text or "—",
                width=14,
                anchor="w",
            )
            if group_id:
                group_lbl.configure(foreground="#4FC3F7")
            widgets: list[tk.Widget] = [
                name_entry,
                type_combo,
                node_entry,
                browse_btn,
                store_cb,
                group_lbl,
                del_btn,
            ]
            editor_row = _OpcUaEditorRow(
                row_idx,
                widgets,
                name_var,
                type_var,
                node_var,
                store_var,
                group_id=group_id,
                group_label=label_text,
                group_label_widget=group_lbl,
            )

            def mark_focus(_event: object = None, r: _OpcUaEditorRow = editor_row) -> None:
                focused_row[0] = r

            for w in (name_entry, type_combo, node_entry, store_cb, browse_btn, group_lbl):
                w.bind("<FocusIn>", mark_focus)
                w.bind("<Button-1>", mark_focus, add="+")

            browse_btn.configure(command=lambda r=editor_row: browse_for_row(r))
            _grid_opcua_row(row_idx, widgets)
            rows.append(editor_row)
            del_btn.configure(command=lambda r=editor_row: remove_row(r))
            name_var.trace_add("write", lambda *_a: refresh_count_choices())
            refresh_count_choices()
            return editor_row

        def apply_group_to_row(row: _OpcUaEditorRow, group_id: str, group_label: str) -> None:
            row.group_id = group_id
            row.group_label = _short_group_label(group_id, group_label)
            if row.group_label_widget is not None:
                row.group_label_widget.configure(
                    text=row.group_label or "—",
                    foreground="#4FC3F7" if group_id else "",
                )

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

            def on_select(node_id: str, display_name: str, data_type: str = "") -> None:
                row.node_var.set(node_id)
                path_hint = (display_name or "").strip().replace(" ", "_")
                suggested = suggested_name_from_node_id(node_id, path_hint) or path_hint
                if suggested:
                    row.name_var.set(suggested)
                if data_type and data_type in OPCUA_DATATYPES:
                    row.type_var.set(data_type)
                # Einzeluebernahme: keine Gruppe.
                apply_group_to_row(row, "", "")

            def on_select_many(
                items: list[tuple[str, str, str]],
                group_id: str,
                group_label: str,
            ) -> None:
                existing_nodes = {
                    r.node_var.get().strip() for r in rows if r.node_var.get().strip()
                }
                added = 0
                skipped = 0
                reuse_starter = (
                    not row.node_var.get().strip()
                    and not row.name_var.get().strip()
                )
                for node_id, display_name, data_type in items:
                    nid = (node_id or "").strip()
                    if not nid:
                        continue
                    if nid in existing_nodes:
                        skipped += 1
                        continue
                    existing_nodes.add(nid)
                    dtype = data_type if data_type in OPCUA_DATATYPES else "Real"
                    if reuse_starter:
                        row.node_var.set(nid)
                        row.name_var.set(display_name)
                        row.type_var.set(dtype)
                        row.store_var.set(True)
                        apply_group_to_row(row, group_id, group_label)
                        reuse_starter = False
                        added += 1
                        continue
                    add_row(
                        name=display_name,
                        datatype=dtype,
                        node_id=nid,
                        store=True,
                        group_id=group_id,
                        group_label=group_label,
                    )
                    added += 1
                # Scrollbereich aktualisieren, damit neue Zeilen sichtbar werden.
                scroll_frame.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.yview_moveto(1.0)
                msg = f"{added} Variable(n) uebernommen" + (
                    f", {skipped} Duplikat(e) uebersprungen." if skipped else "."
                )
                dialog.after(
                    50,
                    lambda m=msg: messagebox.showinfo(
                        "OPC UA Browse", m, parent=dialog
                    ),
                )

            self._persist_opcua_credentials_from_ui()
            security = self._get_opcua_security_config()
            if security.has_credentials() and not security.password:
                messagebox.showerror(
                    "OPC UA Browse",
                    "Benutzername ohne Passwort — bitte Passwort in der "
                    "Verbindungszeile eintragen.",
                    parent=dialog,
                )
                return
            open_opcua_browse_dialog(
                dialog,
                endpoint,
                on_select=on_select,
                on_select_many=on_select_many,
                security=security,
                focus_node_id=row.node_var.get().strip(),
            )

        if self._schema.items:
            for item in self._schema.items:
                add_row(
                    name=item.name,
                    datatype=item.datatype,
                    node_id=item.node_id,
                    store=item.store,
                    group_id=item.group_id,
                    group_label=_short_group_label(item.group_id),
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

        def clear_all_rows() -> None:
            if not rows:
                return
            if not messagebox.askyesno(
                "OPC UA",
                "Wollen Sie das wirklich?\n\nAlle Variablenzeilen werden geloescht.",
                parent=dialog,
            ):
                return
            for row in list(rows):
                remove_row(row)
            count_var.set("")
            count_combo["values"] = []

        def delete_focused_group() -> None:
            target = focused_row[0]
            if target is None or not target.group_id:
                # Fallback: erste Zeile mit Gruppe, falls Fokus unklar.
                grouped = [r for r in rows if r.group_id]
                if len({r.group_id for r in grouped}) == 1:
                    target = grouped[0]
                else:
                    messagebox.showinfo(
                        "OPC UA",
                        "Bitte zuerst eine Zeile einer Import-Gruppe anklicken "
                        "(Spalte „Gruppe“ gefuellt).",
                        parent=dialog,
                    )
                    return
            gid = target.group_id
            label = target.group_label or gid
            members = [r for r in rows if r.group_id == gid]
            if not messagebox.askyesno(
                "OPC UA",
                f"Gruppe „{label}“ mit {len(members)} Variable(n) loeschen?",
                parent=dialog,
            ):
                return
            for row in list(members):
                remove_row(row)

        ttk.Button(row_btn, text="+ Zeile", command=lambda: add_row()).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(row_btn, text="Gruppe loeschen", command=delete_focused_group).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(row_btn, text="Alle loeschen", command=clear_all_rows).pack(
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
                        group_id=row.group_id.strip(),
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
                current_db = Path(resolve_db_path(self._db_path))
                initial = str(current_db.parent) if current_db.parent.parts else str(APP_DIR)
                initial_name, default_ext = sqlite_save_dialog_params(
                    current_db.name,
                    default="s7py_opcua.db",
                )
                db_path = filedialog.asksaveasfilename(
                    parent=dialog,
                    title="Neue SQLite-Datenbank",
                    initialdir=initial,
                    initialfile=initial_name,
                    defaultextension=default_ext,
                    filetypes=[("SQLite", "*.db"), ("Alle Dateien", "*.*")],
                )
                if not db_path:
                    messagebox.showinfo(
                        "OPC UA",
                        "Schema gespeichert. Datenbank wurde nicht geaendert.",
                        parent=dialog,
                    )
                    close_dialog()
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
                "OPC UA",
                f"{len(schema.items)} Variablen gespeichert.\n"
                f"Konfiguration: {DB_CONFIG_PATH}",
                parent=dialog,
            )
            close_dialog()

        ttk.Button(btn_row, text="Abbrechen", command=close_dialog).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(btn_row, text="Speichern", command=on_save).pack(side=tk.RIGHT)
        saved = load_window_geometry(WINDOW_ID_OPCUA_VARS)
        if not restore_window_geometry(dialog, saved, min_w=900, min_h=420):
            center_toplevel_on_parent(dialog, self, width=980, height=520)
