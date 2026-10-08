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


def _norm_node_id(node_id: str | None) -> str:
    """Vergleichshilfe: Leerzeichen und Anfuehrungszeichen entfernen."""
    raw = (node_id or "").strip()
    if not raw:
        return ""
    return (
        raw.replace(" ", "")
        .replace('"', "")
        .replace("'", "")
        .lower()
    )


def open_opcua_browse_dialog(
    parent: tk.Misc,
    endpoint: str,
    *,
    on_select: Callable[[str, str, str], None],
    security: OpcUaSecurityConfig | None = None,
    focus_node_id: str = "",
) -> None:
    """Server-Browser oeffnen; ``on_select(node_id, display_name, data_type)`` bei Uebernahme.

    ``focus_node_id``: vorhandene NodeId — Baum dorthin aufklappen und markieren.
    """

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
    want_focus = (focus_node_id or "").strip()

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
        columns=("data_type", "node_id", "class"),
        show="tree headings",
        selectmode="browse",
    )
    tree.heading("#0", text="Name")
    tree.heading("data_type", text="Typ")
    tree.heading("node_id", text="NodeId")
    tree.heading("class", text="Klasse")
    tree.column("#0", width=220, stretch=True)
    tree.column("data_type", width=90, stretch=False)
    tree.column("node_id", width=280, stretch=True)
    tree.column("class", width=90, stretch=False)
    tree.tag_configure("focus_hit", background="#FFF3A3")
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
    type_by_iid: dict[str, str] = {}
    iid_counter = 0
    loading = {"connect": False, "reveal": False}
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

    def find_iid_by_node_id(node_id: str) -> str | None:
        want = _norm_node_id(node_id)
        if not want:
            return None
        for iid, nid in node_id_by_iid.items():
            if is_placeholder(iid):
                continue
            if _norm_node_id(nid) == want:
                return iid
        return None

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
            type_by_iid[iid] = entry.data_type
            # Variable nicht als Blatt: Siemens-UDT-Felder als Kinder.
            may_expand = entry.node_class != "Method"
            tree.insert(
                parent_iid,
                "end",
                iid=iid,
                text=entry.display_name,
                values=(entry.data_type, entry.node_id, entry.node_class),
                tags=("branch" if may_expand else "leaf",),
            )
            if may_expand:
                tree.insert(iid, "end", iid=f"{iid}__ph", text="")

    def clear_focus_tags() -> None:
        for iid in tree.tag_has("focus_hit"):
            tags = [t for t in tree.item(iid, "tags") if t != "focus_hit"]
            tree.item(iid, tags=tags)

    def center_tree_item(iid: str) -> None:
        """Eintrag markieren, highlighten und vertikal etwa mittig halten."""
        if not tree.exists(iid):
            return
        clear_focus_tags()
        tags = list(tree.item(iid, "tags") or ())
        if "focus_hit" not in tags:
            tags.append("focus_hit")
        tree.item(iid, tags=tags)
        tree.selection_set(iid)
        tree.focus(iid)
        tree.see(iid)
        dialog.update_idletasks()
        bbox = tree.bbox(iid)
        if not bbox:
            tree.see(iid)
            dialog.update_idletasks()
            bbox = tree.bbox(iid)
        if not bbox:
            return
        _x, y, _w, h = bbox
        mid = max(tree.winfo_height(), 1) // 2
        delta_px = y + h // 2 - mid
        if abs(delta_px) < 4:
            return
        step = max(h, 18)
        tree.yview_scroll(int(round(delta_px / step)), "units")

    def expand_iid_async(iid: str, on_done: Callable[[], None]) -> None:
        """Kinder laden (OPC im Worker), UI-Update im Mainthread, dann on_done."""
        if not tree.exists(iid):
            on_done()
            return
        children = tree.get_children(iid)
        if children and not is_placeholder(children[0]):
            tree.item(iid, open=True)
            on_done()
            return
        if not client_holder:
            on_done()
            return
        if iid in expanding:
            def wait_then() -> None:
                if iid in expanding:
                    dialog.after(80, wait_then)
                else:
                    tree.item(iid, open=True)
                    on_done()

            wait_then()
            return

        node_id = node_id_by_iid.get(iid)
        expanding.add(iid)

        def worker() -> None:
            try:
                entries = list_child_nodes(client_holder[0], node_id)
            except Exception:
                entries = []

            def ui() -> None:
                try:
                    if not tree.exists(iid):
                        return
                    insert_entries(iid, entries)
                    if not entries:
                        tree.item(iid, open=False, tags=("leaf",))
                    else:
                        tree.item(iid, open=True)
                finally:
                    expanding.discard(iid)
                    on_done()

            dialog.after(0, ui)

        threading.Thread(target=worker, daemon=True, name="OpcUaBrowseExpandSync").start()

    def highlight_target(target: str) -> None:
        loading["reveal"] = False
        iid = find_iid_by_node_id(target)
        if iid and tree.exists(iid):
            parent = tree.parent(iid)
            while parent:
                tree.item(parent, open=True)
                parent = tree.parent(parent)
            center_tree_item(iid)
            dialog.after(30, lambda i=iid: center_tree_item(i))
            dialog.after(120, lambda i=iid: center_tree_item(i))
            set_status(f"Markiert: {target}")
        else:
            set_status(f"Verbunden — NodeId nicht im Baum gefunden: {target}")

    def reveal_path_on_ui(path_ids: list[str]) -> None:
        """Pfad nur im Tk-Mainthread aufklappen (kein Tree-Zugriff aus Worker)."""
        cleaned: list[str] = []
        for path_id in path_ids:
            if _norm_node_id(path_id) == _norm_node_id("i=84"):
                continue
            if cleaned and _norm_node_id(cleaned[-1]) == _norm_node_id(path_id):
                continue
            cleaned.append(path_id)
        if not cleaned or _norm_node_id(cleaned[-1]) != _norm_node_id(want_focus):
            cleaned.append(want_focus)

        def step(index: int) -> None:
            if index >= len(cleaned):
                highlight_target(want_focus)
                return
            path_id = cleaned[index]
            iid = find_iid_by_node_id(path_id)
            if iid is None:
                # Zwischenknoten fehlt — BFS ab hier.
                bfs_expand_for_target(want_focus, depth_left=14)
                return
            if _norm_node_id(path_id) == _norm_node_id(want_focus):
                highlight_target(want_focus)
                return
            tags = tree.item(iid, "tags") or ()
            if "branch" not in tags:
                # Blatt, aber nicht Ziel — weiter suchen.
                step(index + 1)
                return
            expand_iid_async(iid, lambda: step(index + 1))

        step(0)

    def bfs_expand_for_target(target: str, *, depth_left: int) -> None:
        if depth_left <= 0:
            highlight_target(target)
            return
        hit = find_iid_by_node_id(target)
        if hit:
            highlight_target(target)
            return

        # Naechste Ebene: alle Branches mit Placeholder expandieren.
        to_expand: list[str] = []
        found_during: list[str] = []

        def collect(parent: str = "") -> None:
            if found_during:
                return
            for iid in tree.get_children(parent):
                if is_placeholder(iid):
                    continue
                if _norm_node_id(node_id_by_iid.get(iid)) == _norm_node_id(target):
                    found_during.append(iid)
                    return
                children = tree.get_children(iid)
                tags = tree.item(iid, "tags") or ()
                if "branch" in tags and children and is_placeholder(children[0]):
                    to_expand.append(iid)
                elif "branch" in tags:
                    collect(iid)

        collect("")
        if found_during:
            highlight_target(target)
            return
        if not to_expand:
            highlight_target(target)
            return

        pending = {"n": len(to_expand)}

        def one_done() -> None:
            pending["n"] -= 1
            if pending["n"] <= 0:
                if find_iid_by_node_id(target):
                    highlight_target(target)
                else:
                    bfs_expand_for_target(target, depth_left=depth_left - 1)

        for iid in to_expand:
            expand_iid_async(iid, one_done)

    def start_reveal() -> None:
        target = want_focus
        if not target or not client_holder:
            return
        loading["reveal"] = True
        set_status(f"Suche NodeId … {target}")

        # Schnellpfad: schon sichtbar.
        if find_iid_by_node_id(target):
            highlight_target(target)
            return

        def worker() -> None:
            path_ids: list[str] = []
            try:
                node = client_holder[0].get_node(target)
                path_nodes = node.get_path(max_length=40)
                for path_node in path_nodes:
                    try:
                        path_ids.append(path_node.nodeid.to_string())
                    except Exception:
                        pass
            except Exception:
                path_ids = []
            dialog.after(0, lambda: reveal_path_on_ui(path_ids))

        threading.Thread(target=worker, daemon=True, name="OpcUaBrowseReveal").start()

    def apply_tree(
        root_entries: list[OpcUaBrowseEntry],
        objects_entries: list[OpcUaBrowseEntry],
    ) -> None:
        tree.delete(*tree.get_children())
        node_id_by_iid.clear()
        name_by_iid.clear()
        type_by_iid.clear()

        top_entries = root_entries or [
            OpcUaBrowseEntry("Objects", OBJECTS_FOLDER_NODEID, "Object")
        ]
        for entry in top_entries:
            iid = next_iid()
            node_id_by_iid[iid] = entry.node_id
            name_by_iid[iid] = entry.display_name
            type_by_iid[iid] = entry.data_type
            is_objects = entry.node_id == OBJECTS_FOLDER_NODEID or entry.display_name == "Objects"
            tree.insert(
                "",
                "end",
                iid=iid,
                text=entry.display_name,
                values=(entry.data_type, entry.node_id, entry.node_class),
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

        if want_focus:
            dialog.after(100, start_reveal)

    def set_status(text: str) -> None:
        status_var.set(text)

    def connect_worker() -> None:
        try:
            client = connect_opcua_client(endpoint_var.get(), security=sec)
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
        if loading["connect"] or loading["reveal"]:
            return
        loading["connect"] = True
        tree.delete(*tree.get_children())
        node_id_by_iid.clear()
        name_by_iid.clear()
        type_by_iid.clear()
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
            if not entries:
                tree.item(iid, open=False, tags=("leaf",))
                if node_id == OBJECTS_FOLDER_NODEID:
                    set_status("Objects leer (Rechte / Server-Interface?)")
            expanding.discard(iid)

        dialog.after(0, ui)

    def on_tree_open(event: tk.Event) -> None:
        iid = tree.focus()
        if not iid or "branch" not in tree.item(iid, "tags"):
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
        display = name_by_iid.get(iid, node_id)
        # Pfadnamen aus dem Baum (ohne Root-Ordner) fuer Variablenname.
        path_parts: list[str] = []
        cur: str | None = iid
        while cur:
            part = name_by_iid.get(cur) or str(tree.item(cur, "text") or "")
            part = part.strip().replace(" ", "_")
            if part and part not in {"Objects", "Types", "Views", "Server"}:
                path_parts.append(part)
            cur = tree.parent(cur) or None
        path_parts.reverse()
        path_name = "_".join(path_parts) if path_parts else display
        on_select(node_id, path_name, type_by_iid.get(iid, ""))
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

    center_toplevel_on_parent(dialog, parent, width=800, height=480)
