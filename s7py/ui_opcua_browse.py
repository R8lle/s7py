"""Dialog zum Durchsuchen eines OPC-UA-Servers."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from s7py.opcua_browse import (
    OpcUaBrowseEntry,
    connect_opcua_client,
    disconnect_opcua_client,
    list_child_nodes,
)
from s7py.ui_flow import center_toplevel_on_parent


def open_opcua_browse_dialog(
    parent: tk.Misc,
    endpoint: str,
    *,
    on_select: Callable[[str, str], None],
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

    def populate_root() -> None:
        tree.delete(*tree.get_children())
        node_id_by_iid.clear()
        name_by_iid.clear()
        root_iid = next_iid()
        node_id_by_iid[root_iid] = None
        name_by_iid[root_iid] = "Objects"
        tree.insert(
            "",
            "end",
            iid=root_iid,
            text="Objects",
            values=("", "Folder"),
            tags=("branch",),
        )
        try:
            entries = list_child_nodes(client_holder[0], None)
        except Exception as exc:
            messagebox.showerror("OPC UA Browse", str(exc), parent=dialog)
            set_status("Browse fehlgeschlagen.")
            return
        insert_entries(root_iid, entries)
        tree.item(root_iid, open=True)
        set_status(f"Verbunden: {endpoint_var.get().strip()}")

    def set_status(text: str) -> None:
        status_var.set(text)

    def connect_worker() -> None:
        try:
            client = connect_opcua_client(endpoint_var.get())
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
        dialog.after(0, populate_root)
        dialog.after(0, lambda: loading.__setitem__("connect", False))

    def on_connect() -> None:
        if loading["connect"]:
            return
        loading["connect"] = True
        set_status("Verbinde ...")
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
            expanding.discard(iid)

        dialog.after(0, ui)

    def on_tree_open(_event: tk.Event) -> None:
        iid = tree.focus()
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
        if not node_id:
            messagebox.showinfo(
                "OPC UA Browse",
                "Bitte einen Unterknoten waehlen, nicht den Objects-Ordner.",
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
