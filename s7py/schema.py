"""SPS-Datenbaustein-Schema und TIA-Import."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from s7py.constants import DEFAULT_DB_LAYOUT, PLC_DB_NUMBER

OPCUA_DATATYPES: tuple[str, ...] = (
    "Real",
    "DWord",
    "Int",
    "Bool",
    "String",
    "Byte",
)

SNAP7_DATATYPES: tuple[str, ...] = (
    "Real",
    "LReal",
    "DWord",
    "Int",
    "Bool",
    "Byte",
    "String",
)

S7_ALIGNMENT: dict[str, int] = {
    "BOOL": 1,
    "BYTE": 1,
    "SINT": 1,
    "USINT": 1,
    "CHAR": 1,
    "WORD": 2,
    "INT": 2,
    "UINT": 2,
    "WCHAR": 2,
    "DWORD": 4,
    "DINT": 4,
    "UDINT": 4,
    "REAL": 4,
    "TIME": 4,
    "DATE": 4,
    "TIME_OF_DAY": 4,
    "TOD": 4,
    "DT": 4,
    "DATE_AND_TIME": 4,
    "STRING": 1,
    "WSTRING": 2,
    # LREAL ist 8 Byte gross, startet in nicht-optimierten DBs aber auf 4-Byte-Grenze
    # (direkt nach DInt/DWord ohne zusaetzliches Padding bis Byte 8).
    "LREAL": 4,
    "LINT": 4,
    "ULINT": 4,
    "LWORD": 4,
}

S7_TO_SNAP7: dict[str, str] = {
    "BOOL": "Bool",
    "BYTE": "Byte",
    "SINT": "Int",
    "USINT": "Int",
    "CHAR": "Byte",
    "WORD": "Int",
    "INT": "Int",
    "UINT": "Int",
    "WCHAR": "Int",
    "DWORD": "DWord",
    "DINT": "DWord",
    "UDINT": "DWord",
    "REAL": "Real",
    "LREAL": "LReal",
    "TIME": "DWord",
    "DATE": "DWord",
    "TIME_OF_DAY": "DWord",
    "TOD": "DWord",
    "DT": "DWord",
    "DATE_AND_TIME": "DWord",
    "STRING": "String",
    "WSTRING": "String",
}

S7_BASE_SIZE: dict[str, int] = {
    "BOOL": 1,
    "BYTE": 1,
    "SINT": 1,
    "USINT": 1,
    "CHAR": 1,
    "WORD": 2,
    "INT": 2,
    "UINT": 2,
    "WCHAR": 2,
    "DWORD": 4,
    "DINT": 4,
    "UDINT": 4,
    "REAL": 4,
    "LREAL": 8,
    "TIME": 4,
    "DATE": 2,
    "TIME_OF_DAY": 4,
    "TOD": 4,
    "DT": 8,
    "DATE_AND_TIME": 8,
}


@dataclass
class DbItem:
    """Ein Feld im SPS-Datenbaustein (Snap7-Lesen und optional SQLite)."""

    name: str
    datatype: str
    bytebit: str
    store: bool = True
    size: int = 0
    s7_type: str = ""
    node_id: str = ""
    # OPC-UA-Unterbaum-Import: NodeId der Import-Wurzel (leer = Einzelvariable).
    group_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert fuer ``s7py_db.json`` (rueckwaertskompatibel)."""
        data: dict[str, Any] = {
            "name": self.name,
            "datatype": self.datatype,
            "bytebit": self.bytebit,
        }
        if not self.store:
            data["store"] = False
        if self.size > 0:
            data["size"] = self.size
        if self.s7_type:
            data["s7_type"] = self.s7_type
        if self.node_id:
            data["node_id"] = self.node_id
        if self.group_id:
            data["group_id"] = self.group_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DbItem:
        item = cls(
            name=str(data["name"]),
            datatype=str(data["datatype"]),
            bytebit=str(data["bytebit"]),
            store=data.get("store", True) is not False,
            size=int(data["size"]) if data.get("size") else 0,
            s7_type=str(data.get("s7_type", "") or ""),
            node_id=str(data.get("node_id", "") or ""),
            group_id=str(data.get("group_id", "") or ""),
        )
        return normalize_snap7_db_item(item)


def normalize_snap7_db_item(item: DbItem) -> DbItem:
    """Korrigiert aeltere Schemas, in denen LREAL faelschlich als Real gespeichert wurde."""
    datatype = (item.datatype or "").strip()
    s7 = (item.s7_type or "").upper()
    if s7 == "LREAL" and datatype.lower() == "real":
        return DbItem(
            name=item.name,
            datatype="LReal",
            bytebit=item.bytebit,
            store=item.store,
            size=item.size or 8,
            s7_type=item.s7_type or "LREAL",
            node_id=item.node_id,
            group_id=item.group_id,
        )
    if datatype.lower() == "lreal":
        return DbItem(
            name=item.name,
            datatype="LReal",
            bytebit=item.bytebit,
            store=item.store,
            size=item.size or 8,
            s7_type=item.s7_type or "LREAL",
            node_id=item.node_id,
            group_id=item.group_id,
        )
    if datatype.lower() == "real" and item.size >= 8:
        return DbItem(
            name=item.name,
            datatype="LReal",
            bytebit=item.bytebit,
            store=item.store,
            size=item.size,
            s7_type=item.s7_type or "LREAL",
            node_id=item.node_id,
            group_id=item.group_id,
        )
    return item


def coerce_db_items(raw: list[Any]) -> list[DbItem]:
    """Wandelt gespeicherte Dicts oder vorhandene :class:`DbItem` in eine Liste um."""
    items: list[DbItem] = []
    for entry in raw:
        if isinstance(entry, DbItem):
            items.append(entry)
        elif isinstance(entry, dict):
            items.append(DbItem.from_dict(entry))
        else:
            raise TypeError(f"Ungueltiger DB-Item-Typ: {type(entry)!r}")
    return items


def is_opcua_schema_items(items: list[DbItem]) -> bool:
    """True, wenn alle Items aus dem manuellen OPC-UA-Schema stammen."""
    return bool(items) and all(
        (item.bytebit or "").strip().lower() == "opcua" for item in items
    )


@dataclass
class PlcDbSchema:
    """Aus einem TIA-Datenbaustein abgeleitete Snap7- und SQLite-Struktur."""

    source_file: str = ""
    block_name: str = ""
    db_number: int = PLC_DB_NUMBER
    layout: str = ""
    items: list[DbItem] = field(default_factory=list)
    read_length: int = 0
    count_field: str = "Count"
    plot_fields: list[str] = field(default_factory=lambda: ["Temperature", "DistanceOverAll"])
    live_fields: list[str] = field(default_factory=list)
    sqlite_columns: list[str] = field(default_factory=list)


def _align_s7_offset(offset: int, alignment: int) -> int:
    if alignment <= 1:
        return offset
    remainder = offset % alignment
    if remainder:
        offset += alignment - remainder
    return offset


def _parse_s7_type(type_expr: str) -> tuple[str, int, bool]:
    """Parst einen SPS-Typausdruck in (Basistyp, Bytegroesse, in SQLite speichern)."""
    expr = type_expr.strip()
    upper = expr.upper()

    array_match = re.match(
        r"ARRAY\[(\d+)\.\.(\d+)\]\s+OF\s+(\w+)", upper
    )
    if array_match:
        lo = int(array_match.group(1))
        hi = int(array_match.group(2))
        elem = array_match.group(3)
        elem_size = S7_BASE_SIZE.get(elem, 1)
        return elem, (hi - lo + 1) * elem_size, False

    string_match = re.match(r"STRING(?:\[(\d+)\])?", upper)
    if string_match:
        max_len = int(string_match.group(1)) if string_match.group(1) else 254
        return "STRING", 2 + max_len, True

    wstring_match = re.match(r"WSTRING(?:\[(\d+)\])?", upper)
    if wstring_match:
        max_len = int(wstring_match.group(1)) if wstring_match.group(1) else 254
        return "WSTRING", 4 + 2 * max_len, True

    base = upper.split()[0]
    size = S7_BASE_SIZE.get(base)
    if size is None:
        raise ValueError(f"Unbekannter SPS-Typ: {type_expr}")
    return base, size, True


def parse_tia_data_block_file(path: str) -> PlcDbSchema:
    """Liest einen TIA-Portal-Export (DATA_BLOCK … STRUCT … END_STRUCT)."""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()

    block_match = re.search(r'DATA_BLOCK\s+"([^"]+)"', text, re.IGNORECASE)
    block_name = block_match.group(1) if block_match else os.path.splitext(
        os.path.basename(path)
    )[0]

    struct_match = re.search(
        r"STRUCT\s+(.*?)\s+END_STRUCT", text, re.DOTALL | re.IGNORECASE
    )
    if not struct_match:
        raise ValueError("Kein STRUCT-Block in der Datei gefunden.")

    members: list[tuple[str, str]] = []
    for raw_line in struct_match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        member_match = re.match(
            r"(\w+)(?:\s*\{[^}]*\})?\s*:\s*([^;]+);",
            line,
        )
        if member_match:
            members.append((member_match.group(1), member_match.group(2).strip()))

    if not members:
        raise ValueError("Keine Felder im STRUCT-Block gefunden.")

    offset = 0
    items: list[DbItem] = []
    layout_lines: list[str] = []
    sqlite_columns: list[str] = []

    for name, type_expr in members:
        base_type, size, store = _parse_s7_type(type_expr)
        alignment = S7_ALIGNMENT.get(base_type, 1)
        offset = _align_s7_offset(offset, alignment)

        snap7_type = S7_TO_SNAP7.get(base_type)
        if snap7_type is None:
            raise ValueError(f"Nicht unterstuetzter SPS-Typ: {type_expr}")

        if name.lower() == "reserve" or not store:
            store = False

        bytebit = f"{offset}.0"
        item = DbItem(
            name=name,
            datatype=snap7_type,
            bytebit=bytebit,
            s7_type=base_type,
            store=store,
            size=size,
        )
        items.append(item)
        layout_lines.append(f"{name}\t{snap7_type}\t{bytebit}")
        if store:
            sqlite_columns.append(name)
        offset += size

    count_field = next(
        (name for name, _ in members if name.lower() == "count"),
        members[0][0],
    )
    real_names = [
        it.name
        for it in items
        if it.datatype in ("Real", "LReal") and it.store
    ]
    temp_field = next(
        (it.name for it in items if "temp" in it.name.lower()),
        None,
    )
    dist_field = next(
        (it.name for it in items if "dist" in it.name.lower()),
        None,
    )
    plot_1 = temp_field or (real_names[0] if real_names else sqlite_columns[0])
    plot_2 = dist_field or (
        real_names[1]
        if len(real_names) > 1
        else (sqlite_columns[1] if len(sqlite_columns) > 1 else sqlite_columns[0])
    )

    live_fields: list[str] = []
    for pattern in ("count", "temp", "dist", "motor"):
        for col in sqlite_columns:
            if pattern in col.lower() and col not in live_fields:
                live_fields.append(col)
                break
    if not live_fields:
        live_fields = sqlite_columns[:4]

    return PlcDbSchema(
        source_file=os.path.abspath(path),
        block_name=block_name,
        layout="\n".join(layout_lines),
        items=items,
        read_length=offset,
        count_field=count_field,
        plot_fields=[plot_1, plot_2],
        live_fields=live_fields,
        sqlite_columns=sqlite_columns,
    )


def parse_db_layout(
    db_layout: str, delimiter: str = "\t"
) -> list[DbItem]:
    """Parst eine textuelle DB-Layoutbeschreibung in eine Liste von :class:`DbItem`.

    Jede Zeile muss aus drei durch ``delimiter`` getrennten Feldern bestehen:
    ``name``, ``datatype``, ``bytebit``. Leere Zeilen werden ignoriert.

    Wirft ``ValueError`` bei Zeilen, die nicht genau drei Felder enthalten.
    """
    items: list[DbItem] = []
    for raw_line in db_layout.strip().splitlines():
        parts = raw_line.split(delimiter)
        if len(parts) != 3:
            raise ValueError(f"Ungueltige DB-Definition: {raw_line!r}")
        items.append(
            DbItem(
                name=parts[0].strip(),
                datatype=parts[1].strip(),
                bytebit=parts[2].strip(),
            )
        )
    return items


def _schema_from_layout(layout: str, *, source_file: str = "") -> PlcDbSchema:
    """Erzeugt ein Schema aus der textuellen Layout-Beschreibung."""
    from s7py.plc import get_db_size

    items = parse_db_layout(layout)
    sqlite_columns = [it.name for it in items]
    real_names = [it.name for it in items if it.datatype in ("Real", "LReal")]
    return PlcDbSchema(
        source_file=source_file,
        block_name="Default",
        db_number=PLC_DB_NUMBER,
        layout=layout.strip(),
        items=items,
        read_length=get_db_size(items),
        count_field="Count"
        if any(it.name == "Count" for it in items)
        else items[0].name,
        plot_fields=[
            col
            for col in ("Temperature", "DistanceOverAll")
            if col in sqlite_columns
        ]
        or (
            real_names[:2]
            if len(real_names) >= 2
            else sqlite_columns[: min(2, len(sqlite_columns))]
        ),
        live_fields=[
            col
            for col in ("Count", "Temperature", "DistanceOverAll", "MotorCurrent")
            if col in sqlite_columns
        ]
        or sqlite_columns[:4],
        sqlite_columns=sqlite_columns,
    )


def default_plc_schema() -> PlcDbSchema:
    return _schema_from_layout(DEFAULT_DB_LAYOUT)


def _derive_plot_and_live_fields(sqlite_columns: list[str]) -> tuple[list[str], list[str]]:
    real_names = [name for name in sqlite_columns]
    plot_1 = next(
        (name for name in sqlite_columns if "temp" in name.lower()),
        sqlite_columns[0] if sqlite_columns else "Temperature",
    )
    plot_2 = next(
        (name for name in sqlite_columns if "dist" in name.lower()),
        sqlite_columns[1] if len(sqlite_columns) > 1 else plot_1,
    )
    live_fields: list[str] = []
    for pattern in ("count", "temp", "dist", "motor"):
        for col in sqlite_columns:
            if pattern in col.lower() and col not in live_fields:
                live_fields.append(col)
                break
    if not live_fields:
        live_fields = sqlite_columns[:4]
    skip_names = {"db_string", "reserve"}
    for col in sqlite_columns:
        if col.lower() in skip_names:
            continue
        if col not in live_fields:
            live_fields.append(col)
        if len(live_fields) >= 4:
            break
    return [plot_1, plot_2], live_fields


def resolve_live_fields(
    sqlite_columns: list[str],
    saved: list[str] | None = None,
) -> list[str]:
    """Live-Anzeige: bis zu 4 Felder, bei veralteter Config auffuellen."""
    _, derived = _derive_plot_and_live_fields(sqlite_columns)
    if not saved:
        return derived
    saved_names = [str(name) for name in saved]
    if len(saved_names) < min(4, len(derived)):
        return derived
    return saved_names[:4]


def items_for_plc_read(schema: PlcDbSchema) -> list[DbItem]:
    """Snap7-Felder, die aus dem DB-Block geparst werden (aktiv + Count-Feld)."""
    names: set[str] = set()
    result: list[DbItem] = []
    for item in schema.items:
        if item.store or item.name == schema.count_field:
            if item.name not in names:
                result.append(item)
                names.add(item.name)
    return result


def _validate_snap7_bytebit(bytebit: str, *, field_name: str) -> None:
    parts = (bytebit or "").strip().split(".")
    if len(parts) != 2:
        raise ValueError(
            f"Feld „{field_name}“: Byte/Bit muss „Offset.Bit“ sein (z. B. 4.0)."
        )
    try:
        int(parts[0])
        int(parts[1])
    except ValueError as exc:
        raise ValueError(
            f"Feld „{field_name}“: ungueltiges Byte/Bit „{bytebit}“."
        ) from exc


def schema_from_snap7_manual(
    items: list[DbItem],
    *,
    count_field: str,
    source_file: str = "",
    block_name: str = "",
    db_number: int = PLC_DB_NUMBER,
) -> PlcDbSchema:
    """Erzeugt ein Snap7-Schema aus manuell gepflegten oder importierten Feldern."""
    from s7py.plc import get_db_size

    if not items:
        raise ValueError("Mindestens ein Datenpunkt erforderlich.")

    items = [normalize_snap7_db_item(it) for it in items]

    names = [it.name.strip() for it in items]
    if any(not name for name in names):
        raise ValueError("Jeder Datenpunkt braucht einen Namen.")
    if len(set(names)) != len(names):
        raise ValueError("Namen muessen eindeutig sein.")

    for it in items:
        if it.datatype not in SNAP7_DATATYPES:
            raise ValueError(f"Unbekannter Datentyp: {it.datatype}")
        _validate_snap7_bytebit(it.bytebit, field_name=it.name)

    if count_field not in names:
        raise ValueError(f"Count-Feld „{count_field}“ fehlt in der Liste.")

    sqlite_columns = [it.name for it in items if it.store]
    if not sqlite_columns:
        raise ValueError("Mindestens ein Datenpunkt als aktiv markieren.")

    read_length = get_db_size(items)
    plot_fields, live_fields = _derive_plot_and_live_fields(sqlite_columns)
    layout = "\n".join(
        f"{it.name}\t{it.datatype}\t{it.bytebit}" for it in items
    )
    return PlcDbSchema(
        source_file=source_file,
        block_name=block_name or "Snap7 manuell",
        db_number=db_number,
        layout=layout,
        items=items,
        read_length=read_length,
        count_field=count_field,
        plot_fields=plot_fields,
        live_fields=live_fields,
        sqlite_columns=sqlite_columns,
    )


def schema_from_opcua_manual(
    items: list[DbItem],
    *,
    count_field: str,
) -> PlcDbSchema:
    """Erzeugt ein OPC-UA-Schema aus manuell gepflegten Feldern."""
    if not items:
        raise ValueError("Mindestens eine Variable erforderlich.")

    names = [it.name.strip() for it in items]
    if any(not name for name in names):
        raise ValueError("Jede Variable braucht einen Namen.")
    if len(set(names)) != len(names):
        raise ValueError("Variablennamen muessen eindeutig sein.")

    for it in items:
        if it.datatype not in OPCUA_DATATYPES:
            raise ValueError(f"Unbekannter Datentyp: {it.datatype}")

    if count_field not in names:
        raise ValueError(f"Count-Feld „{count_field}“ fehlt in der Variablenliste.")

    count_item = next(it for it in items if it.name == count_field)
    if not count_item.node_id.strip():
        raise ValueError(f"Count-Feld „{count_field}“ braucht eine NodeId.")

    sqlite_columns = [it.name for it in items if it.store]
    if not sqlite_columns:
        raise ValueError("Mindestens ein Feld fuer SQLite aktivieren.")

    plot_fields, live_fields = _derive_plot_and_live_fields(sqlite_columns)
    layout = "\n".join(
        f"{it.name}\t{it.datatype}\t{it.node_id or 'opcua'}" for it in items
    )
    return PlcDbSchema(
        source_file="",
        block_name="OPC UA manuell",
        db_number=PLC_DB_NUMBER,
        layout=layout,
        items=items,
        read_length=0,
        count_field=count_field,
        plot_fields=plot_fields,
        live_fields=live_fields,
        sqlite_columns=sqlite_columns,
    )
