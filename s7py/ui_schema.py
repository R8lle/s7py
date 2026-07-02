"""Schema-Anwendung und TIA-Import fuer ``S7PyApp`` (Mixin).

Uebernimmt geladene SPS-Strukturen in die Oberflaeche (Live-Anzeige,
Kurvenauswahl, Diagramm) und importiert TIA-Datenbausteine ueber das Menue.
"""

from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Optional

from s7py.ui_base import S7PyAppProtocol
from s7py.constants import APP_DIR, DB_CONFIG_PATH
from s7py.db import migrate_database, save_plc_db_number, save_plc_schema
from s7py.schema import PlcDbSchema, parse_tia_data_block_file


class SchemaImportMixin:
    """SPS-Schema auf die UI anwenden und TIA-Datenbausteine importieren."""

    def _apply_schema_to_ui(self: S7PyAppProtocol) -> None:
        """Aktualisiert Live-Anzeige, Diagramm-Kurvenauswahl und Beschriftungen."""
        for idx, title_lbl in enumerate(self._live_title_labels):
            if idx < len(self._schema.live_fields):
                title_lbl.configure(text=f"{self._schema.live_fields[idx]}:")
            else:
                title_lbl.configure(text="\u2014")

        self._rebuild_plot_field_checkboxes()
        self._ensure_plot_lines()
        self.ax_plot.set_title("Messwerte (aus SQLite)")
        self._sync_dual_axis_layout()
        self._clear_plot_cache()

    def _apply_plc_schema(self: S7PyAppProtocol, schema: PlcDbSchema) -> None:
        self._schema = schema
        self.items = schema.items
        self.DBlength = schema.read_length
        self._apply_schema_to_ui()
        source = schema.source_file or schema.block_name
        self._log(
            f"SPS-Struktur geladen: {schema.block_name} (DB{schema.db_number}), "
            f"{len(schema.sqlite_columns)} SQLite-Felder, "
            f"{schema.read_length} Bytes lesen — {source}"
        )

    def _ask_plc_db_number(self: S7PyAppProtocol) -> Optional[int]:
        """Fragt die SPS-Datenbausteinnummer nach dem Strukturimport ab."""
        return simpledialog.askinteger(
            "Datenbausteinnummer",
            "Nummer des Datenbausteins in der SPS (DB-Nummer):",
            parent=self,
            initialvalue=self._get_plc_db_number(),
            minvalue=1,
            maxvalue=65535,
        )

    def _on_import_plc_db(self: S7PyAppProtocol) -> None:
        if self.write_thread is not None and self.write_thread.is_alive():
            messagebox.showwarning(
                "Import",
                "Bitte zuerst die Aufzeichnung pausieren, bevor die SPS-Struktur "
                "geaendert wird.",
            )
            return

        initial_dir = str(
            Path(self._schema.source_file).parent
            if self._schema.source_file
            else APP_DIR
        )
        path = filedialog.askopenfilename(
            parent=self,
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
            schema = parse_tia_data_block_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("SPS-Struktur importieren", str(exc))
            return

        db_number = self._ask_plc_db_number()
        if db_number is None:
            return
        schema.db_number = db_number
        self.var_plc_db_number.set(db_number)
        save_plc_db_number(db_number)

        self._apply_plc_schema(schema)
        if self.conn_read is not None:
            migrate_database(self.conn_read, schema)
        save_plc_schema(schema, last_database=self._db_path)
        messagebox.showinfo(
            "SPS-Struktur importieren",
            f"Struktur aus „{schema.block_name}“ importiert.\n"
            f"DB-Nummer: {schema.db_number}\n"
            f"{len(schema.sqlite_columns)} Felder fuer SQLite, "
            f"{schema.read_length} Bytes fuer Snap7.\n\n"
            f"Gespeichert in {DB_CONFIG_PATH}",
        )
