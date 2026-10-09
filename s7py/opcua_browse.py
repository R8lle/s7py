"""OPC-UA-Server durchsuchen (Browse)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from s7py.opcua_connect import OpcUaSecurityConfig, connect_opcua_sync_client
from s7py.opcua_import import wrap_opcua_connect_error
from s7py.schema import OPCUA_DATATYPES

# Standard-OPC-UA-Ordner (Namespace 0).
OBJECTS_FOLDER_NODEID = "i=85"
ROOT_FOLDER_NODEID = "i=84"

# OPC-UA VariantType-Name → s7py-Datentyp (OPCUA_DATATYPES).
_VARIANT_TO_S7PY: dict[str, str] = {
    "Boolean": "Bool",
    "SByte": "Byte",
    "Byte": "Byte",
    "Int16": "Int",
    "UInt16": "Int",
    "Int32": "Int",
    "UInt32": "DWord",
    "Int64": "DWord",
    "UInt64": "DWord",
    "Float": "Real",
    "Double": "Real",
    "String": "String",
}


@dataclass(frozen=True)
class OpcUaBrowseEntry:
    """Ein Kindknoten beim Browse."""

    display_name: str
    node_id: str
    node_class: str
    data_type: str = ""  # s7py-Typ wenn bekannt, sonst OPC-UA-Typname


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


def suggested_name_from_node_id(node_id: str, display_name: str = "") -> str:
    """Lesbaren Variablennamen aus Siemens-NodeId oder DisplayName ableiten.

    Beispiel: ``ns=3;s="DB1"."Motor"."Speed"`` → ``DB1_Motor_Speed``.
    """
    import re

    raw = (node_id or "").strip()
    leaf = (display_name or "").strip().replace(" ", "_")
    match = re.search(r";s=(.+)$", raw, flags=re.IGNORECASE)
    if match:
        body = match.group(1).strip()
        parts = [p for p in re.findall(r'"([^"]+)"|([^."\s]+)', body) for p in (p[0] or p[1],) if p]
        if parts:
            return "_".join(part.replace(" ", "_") for part in parts)
    return leaf


def map_opcua_variant_to_s7py(variant_name: str) -> str:
    """OPC-UA-VariantType auf s7py-Datentyp abbilden (oder leer)."""
    key = (variant_name or "").strip()
    mapped = _VARIANT_TO_S7PY.get(key, "")
    if mapped in OPCUA_DATATYPES:
        return mapped
    if key in OPCUA_DATATYPES:
        return key
    return ""


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


def _read_variable_data_type(client: Any, node_id: str) -> str:
    """Datentyp einer Variable lesen (s7py-Name bevorzugt, sonst OPC-UA-Name)."""
    node = client.get_node(node_id)
    read_vt = getattr(node, "read_data_type_as_variant_type", None)
    if callable(read_vt):
        variant = read_vt()
        raw = getattr(variant, "name", None) or str(variant)
        mapped = map_opcua_variant_to_s7py(str(raw))
        return mapped or str(raw)
    # Fallback: DataType-NodeId BrowseName
    read_dt = getattr(node, "read_data_type", None)
    if not callable(read_dt):
        return ""
    dt_id = read_dt()
    dt_node = client.get_node(dt_id)
    browse = dt_node.read_browse_name()
    raw = getattr(browse, "Name", None) or str(dt_id)
    mapped = map_opcua_variant_to_s7py(str(raw))
    return mapped or str(raw)


def is_variable_node_class(node_class: str) -> bool:
    """True fuer Variable (nicht VariableType)."""
    name = (node_class or "").strip()
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name == "Variable"


def _enrich_variable_types(client: Any, entries: list[OpcUaBrowseEntry]) -> list[OpcUaBrowseEntry]:
    """DataType nur fuer Variable-Knoten nachlesen."""
    enriched: list[OpcUaBrowseEntry] = []
    for entry in entries:
        if not is_variable_node_class(entry.node_class) or entry.data_type:
            enriched.append(entry)
            continue
        try:
            data_type = _read_variable_data_type(client, entry.node_id)
        except Exception:
            data_type = ""
        enriched.append(replace(entry, data_type=data_type) if data_type else entry)
    return enriched


def _browse_descriptions(node: Any, refs: int | None = None) -> list[Any]:
    get_desc = getattr(node, "get_children_descriptions", None)
    if not callable(get_desc):
        return []
    try:
        if refs is None:
            raw = get_desc()
        else:
            raw = get_desc(refs=refs)
        return list(raw or [])
    except TypeError:
        # Aeltere Signatur ohne refs=
        if refs is None:
            return list(get_desc() or [])
        return []
    except Exception:
        return []


def _merge_entries(entries: list[OpcUaBrowseEntry]) -> list[OpcUaBrowseEntry]:
    seen: set[str] = set()
    merged: list[OpcUaBrowseEntry] = []
    for entry in entries:
        if entry.node_id in seen:
            continue
        seen.add(entry.node_id)
        merged.append(entry)
    merged.sort(key=lambda item: item.display_name.lower())
    return merged


def list_child_nodes(
    client: Any,
    node_id: str | None = None,
    *,
    enrich_types: bool = True,
) -> list[OpcUaBrowseEntry]:
    """Listet die Kinder eines Knotens (Standard: Objects-Ordner i=85).

    Enthaelt auch UDT-/Strukturfelder (Siemens: oft unter Variable mit
    HasComponent / HasStructuredComponent).

    ``enrich_types=False``: kein DataType-Nachlesen (wichtig fuer schnellen
    Unterbaum-Import ueber WAN).
    """
    node = _resolve_browse_node(client, node_id)
    get_desc = getattr(node, "get_children_descriptions", None)
    if callable(get_desc):
        refs_list = _browse_descriptions(node)
        # UDT-Felder: zusaetzlich strukturierte Komponenten (Siemens S7-1500).
        try:
            from asyncua import ua

            for ref_id in (
                ua.ObjectIds.HasComponent,
                ua.ObjectIds.HasStructuredComponent,
            ):
                refs_list.extend(_browse_descriptions(node, refs=int(ref_id)))
        except Exception:
            pass
        entries = _merge_entries(_entries_from_descriptions(refs_list))
        if enrich_types:
            return _enrich_variable_types(client, entries)
        return entries

    entries: list[OpcUaBrowseEntry] = []
    children: list[Any] = []
    try:
        children = list(node.get_children())
    except Exception:
        children = []
    if not children:
        try:
            from asyncua import ua

            for ref_id in (
                ua.ObjectIds.HasComponent,
                ua.ObjectIds.HasStructuredComponent,
            ):
                try:
                    children.extend(list(node.get_children(refs=int(ref_id))))
                except Exception:
                    pass
        except Exception:
            pass
    seen_ids: set[str] = set()
    for child in children:
        try:
            cid = child.nodeid.to_string()
        except Exception:
            continue
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        try:
            browse_name = child.read_browse_name()
            display = browse_name.Name if browse_name else str(child.nodeid)
        except Exception:
            display = str(child.nodeid)
        try:
            node_class = child.read_node_class().name
        except Exception:
            node_class = "?"
        data_type = ""
        if enrich_types and is_variable_node_class(str(node_class)):
            try:
                data_type = _read_variable_data_type(client, cid)
            except Exception:
                data_type = ""
        entries.append(
            OpcUaBrowseEntry(
                display_name=str(display),
                node_id=cid,
                node_class=str(node_class),
                data_type=data_type,
            )
        )
    entries.sort(key=lambda entry: entry.display_name.lower())
    return entries


def list_root_nodes(client: Any) -> list[OpcUaBrowseEntry]:
    """Kinder des Root-Ordners (Objects, Types, Views)."""
    return list_child_nodes(client, ROOT_FOLDER_NODEID)


# Harte Limits fuer Unterbaum-Import (UI warnt bei Cap).
MAX_SUBTREE_VARIABLES = 500
# Schutz vor Endlosbaeumen (z. B. Milo „Turtles“) und zu tiefen UDT-Ketten.
MAX_SUBTREE_NODES = 1500
MAX_SUBTREE_DEPTH = 25


def collect_variable_descendants(
    client: Any,
    root_node_id: str,
    *,
    max_variables: int = MAX_SUBTREE_VARIABLES,
    max_nodes: int = MAX_SUBTREE_NODES,
    max_depth: int = MAX_SUBTREE_DEPTH,
) -> tuple[list[OpcUaBrowseEntry], bool, str]:
    """Sammelt rekursiv alle Variable-Nachfahren unter ``root_node_id``.

    Der Wurzelknoten selbst wird nicht als Ordner geliefert; Variable-Kinder
    werden aufgenommen. DataTypes werden beim Sammeln nicht nachgelesen
    (Geschwindigkeit); die UI setzt fehlende Typen auf Real.

    Rueckgabe: ``(variablen, truncated, limit_reason)`` —
    ``limit_reason`` ist leer oder ``variables`` / ``nodes`` / ``depth``.
    """
    root = (root_node_id or "").strip()
    if not root:
        return [], False, ""

    found: list[OpcUaBrowseEntry] = []
    found_ids: set[str] = set()
    visited: set[str] = set()
    # (node_id, depth)
    queue: list[tuple[str, int]] = [(root, 0)]
    limit_reason = ""

    while queue:
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        if len(visited) > max_nodes:
            limit_reason = "nodes"
            break
        if depth > max_depth:
            limit_reason = "depth"
            continue
        try:
            # Ohne Typ-Enrichment — sonst haengt der Import an Demo-/Mass-Servern.
            children = list_child_nodes(client, current, enrich_types=False)
        except Exception:
            children = []
        for child in children:
            cid = (child.node_id or "").strip()
            if not cid:
                continue
            if is_variable_node_class(child.node_class):
                if cid not in found_ids:
                    found_ids.add(cid)
                    found.append(child)
                    if len(found) >= max_variables:
                        return found, True, "variables"
                # Variable kann UDT-Felder haben — eine Ebene tiefer browsen.
                if cid not in visited and depth < max_depth:
                    queue.append((cid, depth + 1))
            elif cid not in visited and depth < max_depth:
                queue.append((cid, depth + 1))
    return found, bool(limit_reason), limit_reason


def disconnect_opcua_client(client: Any) -> None:
    from s7py.opcua_connect import _quiet_asyncua_logs

    with _quiet_asyncua_logs():
        try:
            client.disconnect()
        except Exception:
            pass
