"""Dialog zum Durchsuchen eines OPC-UA-Servers."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from s7py.constants import OPCUA_SYNC_WRAPPER_TIMEOUT_S
from s7py.opcua_browse import (
    OBJECTS_FOLDER_NODEID,
    OpcUaBrowseEntry,
    connect_opcua_client,
    disconnect_opcua_client,
    list_child_nodes,
    list_root_nodes,
)
from s7py.opcua_connect import OpcUaSecurityConfig
from s7py.ui_flow import center_toplevel_on_parent

_EMPTY_OBJECTS_HINT = (
    "Unter „Objects“ sind keine Knoten sichtbar.\n\n"
    "Haeufige Ursachen an der S7-1500 / TIA:\n"
    "  • Kein OPC-UA-Server-Interface freigegeben bzw. keine Variablen publiziert\n"
    "  • Zugriffssteuerung: Benutzer ohne Browse-Recht\n"
    "  • Falscher Benutzer/Passwort (Session ok, aber Adressraum leer)\n\n"
    "Pruefen Sie in TIA: OPC UA → Server-Interfaces und Benutzerrechte."
)


def open_opcua_browse_dialog(
    parent: tk.Misc,
    endpoint: str,
    *,
    on_select: Callable[[str, str], None],
    security: OpcUaSecurityConfig | None = None,
) -> None:
    """Server-Browser oeffnen; ``on_select(node_id, display_name)`` bei Uebernahme."""

    dialog = tk.Toplevel(parent)
    dialog.title("OPC UA — Server durchsuchen")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.minsize(520, 360)

    outer = ttk.Frame(dialog, padding=10)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(2, weight=1)

    endpoint_var = tk.StringVar(value=endpoint.strip())
    status_var = tk.StringVar(value="Nicht verbunden.")
    sec = security

    top = ttk.Frame(outer)
    top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    top.columnconfigure(1, weight=1)
    ttk.Label(top, text="Endpoint:").grid(row=0, column=0, sticky="w", padx=(0, 6))
    ttk.Entry(top, textvariable=endpoint_var).grid(row=0, column=1, sticky="ew")

    tree_frame = ttk.Frame(outer)
    tree_frame.grid(row=2, column=0, sticky="nsew")
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)

    tree = ttk.Treeview(
        tree_frame,
        columns=("node_id", "class"),
        show="tree headings",
        selectmode="browse",
    )
    tree.heading("#0", text="Name")
    tree.heading("node_id", text="NodeId")
    tree.heading("class", text="Klasse")
    tree.column("#0", width=220, stretch=True)
    tree.column("node_id", width=280, stretch=True)
    tree.column("class", width=100, stretch=False)
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")

    ttk.Label(outer, textvariable=status_var).grid(row=3, column=0, sticky="w", pady=(8, 0))

    btn_row = ttk.Frame(outer)
    btn_row.grid(row=4, column=0, sticky="e", pady=(8, 0))

    client_holder: list[object] = []
    node_id_by_iid: dict[str, str | None] = {}
    name_by_iid: dict[str, str] = {}
    iid_counter = 0
    loading = {"connect": False}
    expanding: set[str] = set()

    def cleanup() -> None:
        if client_holder:
            disconnect_opcua_client(client_holder[0])
            client_holder.clear()

    def next_iid() -> str:
        nonlocal iid_counter
        iid_counter += 1
        return f"node_{iid_counter}"

    def is_placeholder(iid: str) -> bool:
        return iid.endswith("__ph")

    def insert_entries(parent_iid: str, entries: list[OpcUaBrowseEntry]) -> None:
        for child in tree.get_children(parent_iid):
            if is_placeholder(child):
                tree.delete(child)
        if not entries:
            return
        for entry in entries:
            iid = next_iid()
            node_id_by_iid[iid] = entry.node_id
            name_by_iid[iid] = entry.display_name
            is_variable = entry.node_class == "Variable"
            tree.insert(
                parent_iid,
                "end",
                iid=iid,
                text=entry.display_name,
                values=(entry.node_id, entry.node_class),
                tags=("leaf" if is_variable else "branch",),
            )
            if not is_variable:
                tree.insert(iid, "end", iid=f"{iid}__ph", text="")

    def apply_tree(
        root_entries: list[OpcUaBrowseEntry],
        objects_entries: list[OpcUaBrowseEntry],
    ) -> None:
        tree.delete(*tree.get_children())
        node_id_by_iid.clear()
        name_by_iid.clear()

        # Root-Kinder (Objects / Types / Views), sonst nur Objects.
        top_entries = root_entries or [
            OpcUaBrowseEntry("Objects", OBJECTS_FOLDER_NODEID, "Object")
        ]
        for entry in top_entries:
            iid = next_iid()
            node_id_by_iid[iid] = entry.node_id
            name_by_iid[iid] = entry.display_name
            is_objects = entry.node_id == OBJECTS_FOLDER_NODEID or entry.display_name == "Objects"
            tree.insert(
                "",
                "end",
                iid=iid,
                text=entry.display_name,
                values=(entry.node_id, entry.node_class),
                tags=("branch",),
            )
            if is_objects:
                if objects_entries:
                    insert_entries(iid, objects_entries)
                else:
                    tree.insert(iid, "end", iid=f"{iid}__ph", text="")
                tree.item(iid, open=True)
            else:
                tree.insert(iid, "end", iid=f"{iid}__ph", text="")

        endpoint = endpoint_var.get().strip()
        if objects_entries:
            set_status(
                f"Verbunden: {endpoint} — {len(objects_entries)} Knoten unter Objects"
            )
        else:
            set_status(
                f"Verbunden: {endpoint} — Objects leer (Rechte / Server-Interface?)"
            )
            messagebox.showinfo("OPC UA Browse", _EMPTY_OBJECTS_HINT, parent=dialog)

    def set_status(text: str) -> None:
        status_var.set(text)

    def connect_worker() -> None:
        try:
            client = connect_opcua_client(endpoint_var.get(), security=sec)
            # Browse im Worker-Thread (nicht im Tk-Mainthread).
            try:
                root_entries = list_root_nodes(client)
            except Exception:
                root_entries = []
            try:
                objects_entries = list_child_nodes(client, OBJECTS_FOLDER_NODEID)
            except Exception as browse_exc:
                cleanup()
                client_holder.clear()
                try:
                    disconnect_opcua_client(client)
                except Exception:
                    pass
                dialog.after(
                    0,
                    lambda: messagebox.showerror(
                        "OPC UA Browse", str(browse_exc), parent=dialog
                    ),
                )
                dialog.after(0, lambda: set_status("Browse fehlgeschlagen."))
                dialog.after(0, lambda: loading.__setitem__("connect", False))
                return
        except Exception as exc:
            dialog.after(
                0,
                lambda: messagebox.showerror("OPC UA Browse", str(exc), parent=dialog),
            )
            dialog.after(0, lambda: set_status("Verbindung fehlgeschlagen."))
            dialog.after(0, lambda: loading.__setitem__("connect", False))
            return

        cleanup()
        client_holder.append(client)
        dialog.after(0, lambda: apply_tree(root_entries, objects_entries))
        dialog.after(0, lambda: loading.__setitem__("connect", False))

    def on_connect() -> None:
        if loading["connect"]:
            return
        loading["connect"] = True
        tree.delete(*tree.get_children())
        node_id_by_iid.clear()
        name_by_iid.clear()
        if sec is not None and sec.has_credentials():
            set_status(
                f"Verbinde als „{sec.username.strip()}“ "
                f"(Timeout {int(OPCUA_SYNC_WRAPPER_TIMEOUT_S)}s) ..."
            )
        else:
            set_status(
                f"Verbinde anonym "
                f"(Timeout {int(OPCUA_SYNC_WRAPPER_TIMEOUT_S)}s) ..."
            )
        threading.Thread(target=connect_worker, daemon=True, name="OpcUaBrowseConnect").start()

    def expand_worker(iid: str) -> None:
        if not client_holder:
            return
        node_id = node_id_by_iid.get(iid)
        try:
            entries = list_child_nodes(client_holder[0], node_id)
        except Exception as exc:
            dialog.after(
                0,
                lambda: tree.insert(iid, "end", text=f"(Fehler: {exc})", tags=("leaf",)),
            )
            dialog.after(0, lambda: expanding.discard(iid))
            return

        def ui() -> None:
            insert_entries(iid, entries)
            if not entries and node_id == OBJECTS_FOLDER_NODEID:
                set_status("Objects leer (Rechte / Server-Interface?)")
            expanding.discard(iid)

        dialog.after(0, ui)

    def on_tree_open(event: tk.Event) -> None:
        # geo-opened item: Focus ist bei <<TreeviewOpen>> der geoeffnete Knoten.
        iid = tree.focus()
        if not iid or "branch" not in tree.item(iid, "tags"):
            # Fallback: Item unter der Maus.
            if event is not None:
                iid = tree.identify_row(getattr(event, "y", 0)) or iid
        if not iid or "branch" not in tree.item(iid, "tags"):
            return
        children = tree.get_children(iid)
        if not children or not is_placeholder(children[0]):
            return
        if iid in expanding:
            return
        expanding.add(iid)
        threading.Thread(
            target=lambda: expand_worker(iid),
            daemon=True,
            name="OpcUaBrowseExpand",
        ).start()

    def apply_selection() -> None:
        iid = tree.focus()
        if not iid or iid not in node_id_by_iid:
            messagebox.showinfo("OPC UA Browse", "Bitte einen Knoten auswaehlen.", parent=dialog)
            return
        node_id = node_id_by_iid[iid]
        if not node_id or node_id in {OBJECTS_FOLDER_NODEID, "i=84", "i=86", "i=87"}:
            messagebox.showinfo(
                "OPC UA Browse",
                "Bitte einen Variablen-Knoten waehlen, nicht den Ordner.",
                parent=dialog,
            )
            return
        on_select(node_id, name_by_iid.get(iid, node_id))
        cleanup()
        dialog.destroy()

    def on_double_click(_event: tk.Event) -> None:
        iid = tree.focus()
        if iid and node_id_by_iid.get(iid):
            apply_selection()

    tree.bind("<<TreeviewOpen>>", on_tree_open)
    tree.bind("<Double-1>", on_double_click)

    def on_close() -> None:
        cleanup()
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", on_close)
    ttk.Button(btn_row, text="Schliessen", command=on_close).pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(btn_row, text="NodeId uebernehmen", command=apply_selection).pack(side=tk.RIGHT)
    ttk.Button(top, text="Verbinden", command=on_connect).grid(row=0, column=2, padx=(8, 0))

    if endpoint_var.get().strip():
        dialog.after(200, on_connect)

    center_toplevel_on_parent(dialog, parent, width=720, height=480)
