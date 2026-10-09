"""Benannte Konfigurationen speichern und laden (Mixin fuer ``S7PyApp``)."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from s7py.constants import (
    DEFAULT_PLC_IP,
    PLC_TRANSPORT_SNAP7,
    RECORDING_MODE_UI_LABELS,
    TRANSPORT_UI_LABELS,
)
from s7py.db import (
    load_app_config,
    load_auto_reconnect,
    load_last_db_path,
    load_last_plc_ip,
    load_opcua_endpoint,
    load_opcua_password,
    load_opcua_username,
    load_plc_db_number,
    load_plc_rack,
    load_plc_slot,
    load_plc_transport,
    load_plot_refresh_ms,
    load_poll_interval_s,
    load_recording_mode,
    poll_interval_ms_from_s,
    poll_interval_s_from_ms,
    resolve_db_path,
    save_app_config,
    save_auto_reconnect,
    save_last_db_path,
    save_opcua_credentials,
    save_opcua_endpoint,
    save_plc_db_number,
    save_plc_rack_slot,
    save_plc_schema,
    save_plc_transport,
    save_plot_refresh_ms,
    save_poll_interval_s,
    save_recording_mode,
)
from s7py.named_config import (
    ACTIVE_CONFIG_NAME_KEY,
    config_path_for_name,
    delete_named_config,
    list_named_configs,
    load_named_config,
    rename_named_config,
    sanitize_config_name,
    save_named_config,
)
from s7py.ui_base import S7PyAppProtocol


class NamedConfigMixin:
    """Menueaktionen: Konfiguration unter Namen speichern / laden."""

    def _active_config_display_name(self: S7PyAppProtocol) -> str:
        name = str(self._app_config.get(ACTIVE_CONFIG_NAME_KEY) or "").strip()
        return name

    def _update_window_title_for_config(self: S7PyAppProtocol) -> None:
        name = self._active_config_display_name()
        base = "s7py — SPS / SQLite / Diagramm"
        self.title(f"{base} [{name}]" if name else base)

    def _flush_app_config_from_ui(self: S7PyAppProtocol) -> dict:
        """Alle UI-Einstellungen und Schemas in ``s7py_db.json`` schreiben."""
        self._persist_connection_settings_from_ui()
        save_plc_rack_slot(self._get_plc_rack(), self._get_plc_slot())
        save_plc_db_number(self._get_plc_db_number())
        save_poll_interval_s(poll_interval_s_from_ms(self._sync_poll_interval_spin()))
        save_recording_mode(self._get_recording_mode())
        save_auto_reconnect(bool(self.var_auto_reconnect.get()))
        save_plot_refresh_ms(self._get_plot_refresh_ms())
        db_path = resolve_db_path(self.var_db.get().strip() or self._db_path)
        if db_path:
            save_last_db_path(db_path)
        save_plc_schema(self._schema, last_database=db_path or None)
        if hasattr(self, "var_opcua_username"):
            username = self.var_opcua_username.get().strip()
            password = self._get_opcua_password() if username else ""
            # Credentials mit speichern (auch wenn gerade Snap7 aktiv ist).
            save_opcua_credentials(username, password)
            save_opcua_endpoint(self._get_opcua_endpoint())
        save_plc_transport(self._get_plc_transport())
        self._app_config = load_app_config()
        return dict(self._app_config)

    def _on_save_named_config(self: S7PyAppProtocol) -> None:
        current = self._active_config_display_name()
        raw = simpledialog.askstring(
            "Konfiguration speichern",
            "Name der Konfiguration:",
            parent=self,
            initialvalue=current or "",
        )
        if raw is None:
            return
        try:
            name = sanitize_config_name(raw)
        except ValueError as exc:
            messagebox.showerror("Konfiguration speichern", str(exc), parent=self)
            return
        path = config_path_for_name(name)
        if path.is_file():
            if not messagebox.askyesno(
                "Konfiguration speichern",
                f"„{name}“ existiert bereits.\nÜberschreiben?",
                parent=self,
            ):
                return
        try:
            config = self._flush_app_config_from_ui()
            config[ACTIVE_CONFIG_NAME_KEY] = name
            save_app_config(config)
            saved = save_named_config(name, config)
            self._app_config = load_app_config()
            self._update_window_title_for_config()
            self._log(f"Konfiguration gespeichert: {saved.name}")
            messagebox.showinfo(
                "Konfiguration speichern",
                f"Gespeichert als „{name}“.\n\n{saved}",
                parent=self,
            )
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Konfiguration speichern", str(exc), parent=self)

    def _ask_named_config_choice(self: S7PyAppProtocol) -> str | None:
        """Dialog: laden, umbenennen oder loeschen. Rueckgabe: Stem zum Laden oder None."""
        items: list[tuple[str, Path]] = list_named_configs()
        if not items:
            messagebox.showinfo(
                "Konfiguration laden",
                "Keine gespeicherten Konfigurationen.\n\n"
                "Zuerst unter Datei → Konfiguration speichern unter… anlegen.",
                parent=self,
            )
            return None

        dialog = tk.Toplevel(self)
        dialog.title("Konfiguration laden")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(True, True)

        ttk.Label(
            dialog,
            text="Konfiguration auswählen:",
        ).pack(anchor=tk.W, padx=12, pady=(12, 4))

        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        listbox = tk.Listbox(frame, height=min(12, max(4, len(items))), exportselection=False)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        result: dict[str, str | None] = {"name": None}

        def _selected_stem() -> str | None:
            sel = listbox.curselection()
            if not sel:
                return None
            return items[int(sel[0])][1].stem

        def _refresh_list(select_stem: str | None = None) -> None:
            nonlocal items
            items = list_named_configs()
            listbox.delete(0, tk.END)
            if not items:
                return
            select_idx = 0
            for idx, (display, path) in enumerate(items):
                listbox.insert(tk.END, display)
                if select_stem and path.stem == select_stem:
                    select_idx = idx
            listbox.selection_set(select_idx)
            listbox.see(select_idx)
            listbox.configure(height=min(12, max(4, len(items))))

        def _accept(_event=None) -> None:
            stem = _selected_stem()
            if not stem:
                return
            result["name"] = stem
            dialog.destroy()

        def _cancel(_event=None) -> None:
            result["name"] = None
            dialog.destroy()

        def _rename(_event=None) -> None:
            stem = _selected_stem()
            if not stem:
                return
            display = items[listbox.curselection()[0]][0]
            raw = simpledialog.askstring(
                "Konfiguration umbenennen",
                "Neuer Name:",
                parent=dialog,
                initialvalue=display,
            )
            if raw is None:
                return
            try:
                new_name = sanitize_config_name(raw)
                renamed = rename_named_config(stem, new_name)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Konfiguration umbenennen", str(exc), parent=dialog)
                return
            active = self._active_config_display_name()
            if active == stem:
                self._app_config = load_app_config()
                self._app_config[ACTIVE_CONFIG_NAME_KEY] = renamed.stem
                save_app_config(self._app_config)
                self._update_window_title_for_config()
            self._log(f"Konfiguration umbenannt: {stem} → {renamed.stem}")
            _refresh_list(select_stem=renamed.stem)
            if not items:
                dialog.destroy()

        def _delete(_event=None) -> None:
            stem = _selected_stem()
            if not stem:
                return
            display = items[listbox.curselection()[0]][0]
            if not messagebox.askyesno(
                "Konfiguration löschen",
                f"„{display}“ wirklich löschen?\n\nDie Datei wird entfernt.",
                parent=dialog,
            ):
                return
            try:
                delete_named_config(stem)
            except OSError as exc:
                messagebox.showerror("Konfiguration löschen", str(exc), parent=dialog)
                return
            active = self._active_config_display_name()
            if active == stem:
                self._app_config = load_app_config()
                self._app_config.pop(ACTIVE_CONFIG_NAME_KEY, None)
                save_app_config(self._app_config)
                self._update_window_title_for_config()
            self._log(f"Konfiguration gelöscht: {stem}")
            _refresh_list()
            if not items:
                messagebox.showinfo(
                    "Konfiguration laden",
                    "Keine weiteren gespeicherten Konfigurationen.",
                    parent=dialog,
                )
                dialog.destroy()

        for display, _path in items:
            listbox.insert(tk.END, display)
        listbox.selection_set(0)
        listbox.focus_set()

        btn_row = ttk.Frame(dialog)
        btn_row.pack(fill=tk.X, padx=12, pady=(4, 12))
        ttk.Button(btn_row, text="Abbrechen", command=_cancel).pack(side=tk.RIGHT)
        ttk.Button(btn_row, text="Laden", command=_accept).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(btn_row, text="Löschen", command=_delete).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Umbenennen", command=_rename).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        listbox.bind("<Double-Button-1>", _accept)
        listbox.bind("<Return>", _accept)
        dialog.bind("<Escape>", _cancel)
        dialog.protocol("WM_DELETE_WINDOW", _cancel)

        dialog.update_idletasks()
        dialog.wait_window()
        return result["name"]

    def _on_load_named_config(self: S7PyAppProtocol) -> None:
        if self._session_active or self._connecting or self._reconnecting:
            messagebox.showwarning(
                "Konfiguration laden",
                "Bitte zuerst die SPS-Verbindung trennen.",
                parent=self,
            )
            return
        if self.write_thread is not None and self.write_thread.is_alive():
            messagebox.showwarning(
                "Konfiguration laden",
                "Bitte zuerst die Aufzeichnung pausieren.",
                parent=self,
            )
            return

        name = self._ask_named_config_choice()
        if not name:
            return
        try:
            loaded_name, body = load_named_config(name)
            save_app_config(body)
            self._apply_loaded_app_config()
            self._log(f"Konfiguration geladen: {loaded_name}")
            self.status_var.set(f"Konfiguration „{loaded_name}“ geladen.")
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Konfiguration laden", str(exc), parent=self)
            return

        connect = messagebox.askyesno(
            "Konfiguration laden",
            f"„{loaded_name}“ geladen.\n\nJetzt verbinden und Aufzeichnung starten?",
            parent=self,
        )
        if connect:
            self._start_recording_after_connect = True
            self._on_connect()

    def _apply_loaded_app_config(self: S7PyAppProtocol) -> None:
        """Aktive ``s7py_db.json`` nach Laden einer benannten Config in die UI bringen."""
        self._app_config = load_app_config()
        transport = load_plc_transport()
        self.var_plc_transport.set(
            TRANSPORT_UI_LABELS.get(
                transport, TRANSPORT_UI_LABELS[PLC_TRANSPORT_SNAP7]
            )
        )
        self.var_ip.set(load_last_plc_ip() or DEFAULT_PLC_IP)
        self.var_opcua_endpoint.set(load_opcua_endpoint())
        self.var_opcua_username.set(load_opcua_username())
        self.var_opcua_password.set(load_opcua_password())
        self.var_plc_rack.set(load_plc_rack())
        self.var_plc_slot.set(load_plc_slot())
        self.var_plc_db_number.set(load_plc_db_number())
        self.var_poll_interval_ms.set(poll_interval_ms_from_s(load_poll_interval_s()))
        self.var_recording_mode.set(
            RECORDING_MODE_UI_LABELS.get(
                load_recording_mode(),
                next(iter(RECORDING_MODE_UI_LABELS.values())),
            )
        )
        self.var_auto_reconnect.set(load_auto_reconnect())
        self.var_plot_refresh_ms.set(load_plot_refresh_ms())

        db_path = load_last_db_path()
        self._db_path = db_path
        self.var_db.set(db_path)

        self._ensure_plc_backend()
        self._sync_transport_widgets()
        self._reload_schema_for_transport(transport)
        self._update_window_title_for_config()

        if self.conn_read is not None:
            try:
                self.conn_read.close()
            except Exception:
                pass
            self.conn_read = None
            self.cursor_read = None
        self._clear_plot_cache()
        self._reset_live_labels()
        if os.path.isfile(db_path):
            self._attach_database(db_path, create_if_missing=False, silent=True)
        self._refresh_status_display()
