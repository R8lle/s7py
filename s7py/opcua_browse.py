"""OPC-UA-Server durchsuchen (Browse)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from s7py.opcua_connect import OpcUaSecurityConfig, connect_opcua_sync_client
from s7py.opcua_import import wrap_opcua_connect_error

# Standard-OPC-UA-Ordner (Namespace 0).
OBJECTS_FOLDER_NODEID = "i=85"
ROOT_FOLDER_NODEID = "i=84"


@dataclass(frozen=True)
class OpcUaBrowseEntry:
    """Ein Kindknoten beim Browse."""

    display_name: str
    node_id: str
    node_class: str


def connect_opcua_client(
    endpoint_url: str,
    *,
    security: OpcUaSecurityConfig | None = None,
) -> Any:
    """Verbindet einen synchronen asyncua-Client (gleiche Auth wie Hauptverbindung)."""
    url = (endpoint_url or "").strip()
    if not url:
        raise ValueError("OPC-UA-Endpoint fehlt.")
    try:
        client, _info = connect_opcua_sync_client(url, security=security)
        return client
    except Exception as exc:
        raise wrap_opcua_connect_error(exc, url) from exc


def _display_from_ref(ref: Any) -> str:
    display = getattr(ref, "DisplayName", None)
    text = getattr(display, "Text", None) if display is not None else None
    if text:
        return str(text)
    browse = getattr(ref, "BrowseName", None)
    name = getattr(browse, "Name", None) if browse is not None else None
    if name:
        return str(name)
    nodeid = getattr(ref, "NodeId", None)
    return str(nodeid) if nodeid is not None else "?"


def _class_from_ref(ref: Any) -> str:
    node_class = getattr(ref, "NodeClass", None)
    name = getattr(node_class, "name", None)
    if name:
        return str(name)
    return "?"


def _node_id_string(ref: Any) -> str:
    nodeid = getattr(ref, "NodeId", None)
    if nodeid is None:
        return ""
    to_string = getattr(nodeid, "to_string", None)
    if callable(to_string):
        return str(to_string())
    return str(nodeid)


def _entries_from_descriptions(refs: list[Any]) -> list[OpcUaBrowseEntry]:
    entries: list[OpcUaBrowseEntry] = []
    for ref in refs:
        node_id = _node_id_string(ref)
        if not node_id:
            continue
        entries.append(
            OpcUaBrowseEntry(
                display_name=_display_from_ref(ref),
                node_id=node_id,
                node_class=_class_from_ref(ref),
            )
        )
    entries.sort(key=lambda entry: entry.display_name.lower())
    return entries


def _resolve_browse_node(client: Any, node_id: str | None) -> Any:
    if node_id:
        return client.get_node(node_id)
    # Explizit Objects-Folder (i=85) — robuster als client.nodes.objects
    # nach Endpoint-/Security-Reconnect.
    try:
        return client.get_node(OBJECTS_FOLDER_NODEID)
    except Exception:
        return client.nodes.objects


def list_child_nodes(client: Any, node_id: str | None = None) -> list[OpcUaBrowseEntry]:
    """Listet die Kinder eines Knotens (Standard: Objects-Ordner i=85)."""
    node = _resolve_browse_node(client, node_id)
    # Ein Roundtrip: DisplayName + NodeClass + NodeId (ohne N× ReadAttribute).
    get_desc = getattr(node, "get_children_descriptions", None)
    if callable(get_desc):
        refs = get_desc()
        return _entries_from_descriptions(list(refs or []))

    entries: list[OpcUaBrowseEntry] = []
    for child in node.get_children():
        try:
            browse_name = child.read_browse_name()
            display = browse_name.Name if browse_name else str(child.nodeid)
        except Exception:
            display = str(child.nodeid)
        try:
            node_class = child.read_node_class().name
        except Exception:
            node_class = "?"
        entries.append(
            OpcUaBrowseEntry(
                display_name=str(display),
                node_id=child.nodeid.to_string(),
                node_class=str(node_class),
            )
        )
    entries.sort(key=lambda entry: entry.display_name.lower())
    return entries


def list_root_nodes(client: Any) -> list[OpcUaBrowseEntry]:
    """Kinder des Root-Ordners (Objects, Types, Views)."""
    return list_child_nodes(client, ROOT_FOLDER_NODEID)


def disconnect_opcua_client(client: Any) -> None:
    from s7py.opcua_connect import _quiet_asyncua_logs

    with _quiet_asyncua_logs():
        try:
            client.disconnect()
        except Exception:
            pass
