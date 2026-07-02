"""OPC-UA-Server durchsuchen (Browse)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OpcUaBrowseEntry:
    """Ein Kindknoten beim Browse."""

    display_name: str
    node_id: str
    node_class: str


def connect_opcua_client(endpoint_url: str) -> Any:
    """Verbindet einen synchronen asyncua-Client."""
    try:
        from asyncua.sync import Client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "OPC UA benoetigt das Paket 'asyncua'. Installation: pip install asyncua"
        ) from exc

    url = (endpoint_url or "").strip()
    if not url:
        raise ValueError("OPC-UA-Endpoint fehlt.")
    client = Client(url)
    client.connect()
    return client


def list_child_nodes(client: Any, node_id: str | None = None) -> list[OpcUaBrowseEntry]:
    """Listet die Kinder eines Knotens (Standard: Objects-Ordner)."""
    if node_id:
        node = client.get_node(node_id)
    else:
        node = client.nodes.objects

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


def disconnect_opcua_client(client: Any) -> None:
    try:
        client.disconnect()
    except Exception:
        pass
