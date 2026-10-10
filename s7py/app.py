"""Tkinter-Hauptfenster fuer s7py.

Die umfangreiche Logik ist thematisch auf Mixins verteilt:

* :class:`s7py.ui_plot.PlotMixin` — Diagramm-Aufbau und -Aktualisierung
* :class:`s7py.ui_connection.ConnectionMixin` — SPS-Verbindung/Aufzeichnung
* :class:`s7py.ui_database.DatabaseMixin` — SQLite-Anbindung und CSV-Export
* :class:`s7py.ui_schema.SchemaImportMixin` — Schema anwenden
* :class:`s7py.ui_snap7_schema.Snap7SchemaMixin` — Snap7-Variablen-Editor

Dieses Modul enthaelt nur noch den Fenster-Aufbau (Menue, Bedienleiste,
Meldungsbox), das Logging, die Anfangsgeometrie und den Lebenszyklus.
"""

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from sqlite3 import Error
from tkinter import messagebox, scrolledtext, ttk

from s7py.backends import create_backend
from s7py.constants import (
    CONNECTION_WATCH_MS,
    DEFAULT_PLC_IP,
    INITIAL_MINSIZE_H,
    INITIAL_REQ_HEIGHT_FLOOR,
    LIVE_LABEL_EMPTY,
    LOG_BOX_LINES,
    LOG_DRAIN_MAX_PER_TICK,
    LOG_DRAIN_MS,
    LOG_MAX_LINES,
    LOG_TRIM_THRESHOLD,
    MACOS_DOCK_HEIGHT,
    MACOS_MENU_BAR_HEIGHT,
    MAX_POLL_INTERVAL_S,
    MIN_POLL_INTERVAL_S,
    PLOT_MAX_ROWS_DEFAULT,
    MIN_PLOT_REFRESH_MS,
    MAX_PLOT_REFRESH_MS,
    PLC_TRANSPORT_OPCUA,
    PLC_TRANSPORT_SNAP7,
    RECORDING_TICK_MS,
    RECORDING_RESUME_LABEL,
    RECORDING_START_BUTTON_WIDTH,
    RECORDING_START_LABEL,
    RECORDING_MODE_UI_LABELS,
    TIMESTAMP_FORMAT_LOG,
    TRANSPORT_UI_LABELS,
    WINDOW_ID_DB_TABLE,
    WINDOW_ID_MAIN,
    WINDOW_MIN_WIDTH,
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
    load_window_geometry,
    poll_interval_ms_from_s,
    resolve_db_path,
    save_auto_reconnect,
    save_plc_db_number,
    save_plc_rack_slot,
    save_plc_schema,
    save_plot_refresh_ms,
    save_poll_interval_s,
    save_recording_mode,
    save_window_geometry,
    schema_from_config,
)
from s7py.log import COUNT_GAP_QUEUE, LIVE_VALUES_QUEUE, LOG_QUEUE, logger
from s7py.schema import DbItem
from s7py.ui_connection import ConnectionMixin
from s7py.ui_database import DatabaseMixin
from s7py.ui_named_config import NamedConfigMixin
from s7py.ui_opcua_schema import OpcUaSchemaMixin
from s7py.ui_plot import PlotMixin
from s7py.ui_schema import SchemaImportMixin
from s7py.ui_snap7_schema import Snap7SchemaMixin
from s7py.ui_flow import FlowFrame, capture_window_geometry, restore_window_geometry


class S7PyApp(
    PlotMixin,
    ConnectionMixin,
    DatabaseMixin,
    SchemaImportMixin,
    Snap7SchemaMixin,
    OpcUaSchemaMixin,
    NamedConfigMixin,
    tk.Tk,
):
    """SPS lesen, SQLite schreiben (Thread), Kurven aus DB — alles in einem Fenster."""

    def __init__(self):
        super().__init__()
        self.title("s7py — SPS / SQLite / Diagramm")

        self.plc_backend = create_backend(load_plc_transport())
        self.plc_lock = threading.RLock()
        self.conn_read = None
        self.cursor_read = None
        self._app_config = load_app_config()
        self._schema = schema_from_config(self._app_config, transport=load_plc_transport())
        self.items: list[DbItem] = self._schema.items
        self.DBlength = self._schema.read_length
        self._db_path = load_last_db_path()
        self._plc_ip = ""
        self._session_active = False
        self._reconnecting = False
        self._reconnect_attempt = 0
        self._reconnect_generation = 0
        self._connecting = False
        self._connection_lost = False
        self._db_stats = None
        self._db_stats_tick = 0
        self._count_gap_hint_shown = False
        self._recording_paused = False
        self._db_table_window: tk.Toplevel | None = None
        self._start_recording_after_connect = False
        # Vorbelegung des IP-Felds: zuletzt verbundene SPS, sonst Fallback.
        self._initial_plc_ip = load_last_plc_ip() or DEFAULT_PLC_IP
        self.stop_event = threading.Event()
        self.write_thread = None
        self.var_plot_scope = tk.StringVar(value="limit")
        self.var_plot_limit = tk.IntVar(value=PLOT_MAX_ROWS_DEFAULT)
        self.var_plot_refresh_ms = tk.IntVar(value=load_plot_refresh_ms())
        self.var_live_count = tk.StringVar(value=LIVE_LABEL_EMPTY)
        self.var_live_temp = tk.StringVar(value=LIVE_LABEL_EMPTY)
        self.var_live_dist = tk.StringVar(value=LIVE_LABEL_EMPTY)
        self.var_live_motor_current = tk.StringVar(value=LIVE_LABEL_EMPTY)
        self.var_recording = tk.StringVar(value="")
        self._plot_cache_scope = None
        self._plot_cache_rows = []
        self._plot_field_vars: dict[str, tk.BooleanVar] = {}
        self._plot_lines: dict[str, object] = {}
        self.ax_plot_right = None
        self._markers_on = True
        self._recording_phase = 0
        self._live_title_labels: list[ttk.Label] = []
        self._live_value_vars = [
            self.var_live_count,
            self.var_live_temp,
            self.var_live_dist,
            self.var_live_motor_current,
        ]

        self._build_ui()
        self._apply_schema_to_ui()
        self._update_window_title_for_config()
        self._apply_initial_geometry()
        if os.path.isfile(self._db_path):
            self._attach_database(self._db_path, create_if_missing=False, silent=True)
            self._refresh_status_display()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(load_plot_refresh_ms(), self._refresh_plots)
        self.after(LOG_DRAIN_MS, self._drain_log_queue)
        self.after(RECORDING_TICK_MS, self._tick_recording_indicator)
        self.after(CONNECTION_WATCH_MS, self._tick_connection_watchdog)

    def _log(self, message):
        text = str(message)
        self._append_log_lines([text])
        # Nutzeraktionen / Statusmeldungen aus dem Tk-Hauptthread
        # gehen zusaetzlich ins Diagnose-Logfile (analog zu _log_msg).
        logger.info(text)

    def _append_log_lines(self, messages):
        """Schreibt mehrere Log-Zeilen mit gemeinsamem Zeitstempel-Praefix in einem
        einzigen Widget-Update und kuerzt das Log auf LOG_MAX_LINES.
        """
        if not messages:
            return
        ts = datetime.now().strftime(TIMESTAMP_FORMAT_LOG)
        block = "".join(f"[{ts}] {m}\n" for m in messages)
        self.log.insert(tk.END, block)
        # Tk-Zeilen sind 1-indiziert; END liefert "<lines+1>.0"
        try:
            total_lines = int(self.log.index("end-1c").split(".")[0])
        except (ValueError, IndexError):
            total_lines = 0
        if total_lines > LOG_TRIM_THRESHOLD:
            cutoff = total_lines - LOG_MAX_LINES + 1
            self.log.delete("1.0", f"{cutoff}.0")
        self.log.see(tk.END)

    def _drain_log_queue(self):
        """Holt Nachrichten aus LOG_QUEUE und aktualisiert die Live-SPS-Anzeige.
        Laeuft im Tkinter-Hauptthread, daher thread-safe.
        """
        try:
            messages = []
            try:
                for _ in range(LOG_DRAIN_MAX_PER_TICK):
                    messages.append(LOG_QUEUE.get_nowait())
            except queue.Empty:
                pass
            if messages:
                self._append_log_lines(messages)
            latest_live = None
            while True:
                try:
                    latest_live = LIVE_VALUES_QUEUE.get_nowait()
                except queue.Empty:
                    break
            if latest_live is not None:
                items_by_name = {it.name: it for it in self._schema.items}
                for idx, var in enumerate(self._live_value_vars):
                    if idx < len(self._schema.live_fields):
                        field = self._schema.live_fields[idx]
                        value = latest_live.get(field, LIVE_LABEL_EMPTY)
                        if isinstance(value, float):
                            item = items_by_name.get(field)
                            precision = (
                                6 if item is not None and item.datatype == "LReal" else 3
                            )
                            var.set(f"{value:.{precision}f}")
                        else:
                            var.set(str(value))
            gap_hint = None
            while True:
                try:
                    gap_hint = COUNT_GAP_QUEUE.get_nowait()
                except queue.Empty:
                    break
            if gap_hint is not None:
                missed, poll_s = gap_hint
                self._on_count_gap_hint(missed, poll_s)
        finally:
            if self.winfo_exists():
                self.after(LOG_DRAIN_MS, self._drain_log_queue)

    def _reset_live_labels(self):
        for var in self._live_value_vars:
            var.set(LIVE_LABEL_EMPTY)

    def _on_count_gap_hint(self, missed: int, poll_interval_s: float) -> None:
        """Einmaliger Hinweis pro Aufzeichnung bei Count-Luecken."""
        if self._count_gap_hint_shown:
            return
        self._count_gap_hint_shown = True
        current_ms = poll_interval_ms_from_s(poll_interval_s)
        suggested_s = max(
            MIN_POLL_INTERVAL_S,
            poll_interval_s / max(1, missed + 1),
        )
        suggested_ms = poll_interval_ms_from_s(suggested_s)
        messagebox.showwarning(
            "Count-Luecke",
            f"Die SPS hat {missed} Messpunkt(e) nicht erfasst — "
            f"die Abfrage ist vermutlich zu langsam.\n\n"
            f"Aktuelles Intervall: {current_ms} ms\n"
            f"Vorschlag: {suggested_ms} ms\n\n"
            f"Bitte die Aufzeichnung pausieren und das Abfrage-Intervall "
            f"verkuerzen.",
        )

    def _apply_initial_geometry(self):
        """Setzt Fenstergroesse + Position: zuletzt gespeichert, sonst zentriert.

        Gespeicherte Werte landen im sichtbaren Bildschirmbereich (Reserve fuer
        macOS-Menueleiste/Dock). Ohne Speicherwert bleibt das bisherige
        Startlayout (Diagramm und Meldungsbox komplett sichtbar).
        """
        self.update_idletasks()
        saved = load_window_geometry(WINDOW_ID_MAIN)
        if restore_window_geometry(
            self,
            saved,
            min_w=WINDOW_MIN_WIDTH,
            min_h=INITIAL_MINSIZE_H,
        ):
            self.minsize(WINDOW_MIN_WIDTH, INITIAL_MINSIZE_H)
            return

        req_w = max(self.winfo_reqwidth(), WINDOW_MIN_WIDTH)
        req_h = max(self.winfo_reqheight(), INITIAL_REQ_HEIGHT_FLOOR)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        # Reservebereiche: oben Menueleiste (~30 px), unten Dock (~80 px).
        usable_top = MACOS_MENU_BAR_HEIGHT
        usable_bottom = MACOS_DOCK_HEIGHT
        max_w = int(screen_w * 0.95)
        max_h = screen_h - usable_top - usable_bottom
        w = min(req_w, max_w)
        h = min(req_h, max_h)
        x = max(0, (screen_w - w) // 2)
        y = max(usable_top, (screen_h - h) // 2 - 40)
        # Untere Kante nicht aus dem Bildschirm laufen lassen.
        if y + h > screen_h - usable_bottom:
            y = max(usable_top, screen_h - usable_bottom - h)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(w, 900), min(h, INITIAL_MINSIZE_H))

    def _set_connected_ui(self, connected):
        self.btn_connect["state"] = tk.DISABLED if connected else tk.NORMAL
        self.btn_disconnect["state"] = tk.NORMAL if connected else tk.DISABLED
        thread_alive = (
            self.write_thread is not None and self.write_thread.is_alive()
        )
        self.btn_start["state"] = (
            tk.NORMAL if connected and not thread_alive else tk.DISABLED
        )
        self.btn_pause["state"] = (
            tk.NORMAL if connected and thread_alive else tk.DISABLED
        )
        if connected and not thread_alive and self._recording_paused:
            self.btn_start.configure(text=RECORDING_RESUME_LABEL)
        else:
            self.btn_start.configure(text=RECORDING_START_LABEL)
        self.entry_ip["state"] = tk.DISABLED if connected else tk.NORMAL
        self.entry_db["state"] = tk.DISABLED if connected else tk.NORMAL
        self.btn_browse_db["state"] = tk.DISABLED if connected else tk.NORMAL
        self.spin_poll_interval["state"] = tk.DISABLED if connected else tk.NORMAL
        self.spin_plc_rack["state"] = tk.DISABLED if connected else tk.NORMAL
        self.spin_plc_slot["state"] = tk.DISABLED if connected else tk.NORMAL
        self.spin_plc_db_number["state"] = tk.DISABLED if connected else tk.NORMAL
        self.cmb_recording_mode["state"] = "disabled" if connected else "readonly"
        self.cmb_plc_transport["state"] = "disabled" if connected else "readonly"
        self.entry_opcua_endpoint["state"] = tk.DISABLED if connected else tk.NORMAL
        if hasattr(self, "entry_opcua_username"):
            self.entry_opcua_username["state"] = tk.DISABLED if connected else tk.NORMAL
            self.entry_opcua_password["state"] = tk.DISABLED if connected else tk.NORMAL
        self._sync_transport_widgets()

    def _sync_transport_widgets(self):
        from s7py.constants import PLC_TRANSPORT_OPCUA

        is_snap7 = self._get_plc_transport() == PLC_TRANSPORT_SNAP7
        connected = self._session_active
        snap7_state = tk.DISABLED if connected or not is_snap7 else tk.NORMAL
        opc_state = tk.DISABLED if connected or is_snap7 else tk.NORMAL

        if is_snap7:
            self.lbl_ip.pack(side=tk.LEFT, padx=(0, 4))
            self.entry_ip.pack(side=tk.LEFT, padx=(0, 12))
            self.lbl_opcua_endpoint.pack_forget()
            self.entry_opcua_endpoint.pack_forget()
            self.opcua_auth_row.grid_remove()
            self.entry_ip["state"] = tk.DISABLED if connected else tk.NORMAL
        else:
            self.lbl_ip.pack_forget()
            self.entry_ip.pack_forget()
            self.lbl_opcua_endpoint.pack(side=tk.LEFT, padx=(0, 4))
            self.entry_opcua_endpoint.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.opcua_auth_row.grid()
            self.entry_opcua_endpoint["state"] = opc_state
            self.entry_opcua_username["state"] = opc_state
            self.entry_opcua_password["state"] = opc_state

        self.spin_plc_rack["state"] = snap7_state
        self.spin_plc_slot["state"] = snap7_state
        self.spin_plc_db_number["state"] = snap7_state
        self._rebuild_file_menu()

    def _set_connecting_ui(self, busy):
        """Waehrend Verbindungsaufbau alle Bedienelemente sperren."""
        self._connecting = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_connect["state"] = state
        self.btn_disconnect["state"] = tk.DISABLED
        self.btn_start["state"] = tk.DISABLED
        self.btn_pause["state"] = tk.DISABLED
        self.entry_ip["state"] = state
        self.entry_db["state"] = state
        self.btn_browse_db["state"] = state
        self.spin_poll_interval["state"] = state
        self.spin_plc_rack["state"] = state
        self.spin_plc_slot["state"] = state
        self.spin_plc_db_number["state"] = state
        self.cmb_recording_mode["state"] = "disabled"
        self.cmb_plc_transport["state"] = "disabled"
        self.entry_opcua_endpoint["state"] = state
        if hasattr(self, "entry_opcua_username"):
            self.entry_opcua_username["state"] = state
            self.entry_opcua_password["state"] = state

    def _build_ui(self):
        self._build_menu()
        self._build_top_bar()
        self._build_plot_area()
        self._build_log_area()

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        self._file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Datei", menu=self._file_menu)
        self._rebuild_file_menu()

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Hilfe", menu=help_menu)
        help_menu.add_command(
            label="Schnellhilfe",
            command=lambda: self._open_help("kurzanleitung"),
            accelerator="F1",
        )
        help_menu.add_command(
            label="Bedienungsanleitung",
            command=lambda: self._open_help("anleitung"),
        )
        help_menu.add_command(
            label="TIA Portal (Put/Get & OPC UA)",
            command=lambda: self._open_help("tia"),
        )
        help_menu.add_separator()
        help_menu.add_command(
            label="Info und Lizenzen...",
            command=self._open_about,
        )
        self.bind_all("<F1>", lambda _e: self._open_help("kurzanleitung"))
        self._help_window = None

    def _open_help(self, name: str = "kurzanleitung") -> None:
        from s7py.ui_help import open_help

        existing = getattr(self, "_help_window", None)
        if existing is not None:
            try:
                if existing.window.winfo_exists():
                    existing.show_document(name)
                    return
            except tk.TclError:
                pass
        self._help_window = open_help(self, name)

    def _open_about(self) -> None:
        from s7py.ui_about import open_about

        open_about(self)

    def _rebuild_file_menu(self):
        """Datei-Menue abhaengig vom Protokoll (Snap7 / OPC UA) aufbauen."""
        from s7py.constants import PLC_TRANSPORT_OPCUA

        transport = (
            self._get_plc_transport()
            if hasattr(self, "var_plc_transport")
            else load_plc_transport()
        )
        self._file_menu.delete(0, "end")
        self._file_menu.add_command(
            label="Konfiguration speichern unter...",
            command=self._on_save_named_config,
        )
        self._file_menu.add_command(
            label="Konfiguration laden...",
            command=self._on_load_named_config,
        )
        self._file_menu.add_command(
            label="Konfiguration exportieren...",
            command=self._on_export_named_config,
        )
        self._file_menu.add_command(
            label="Konfiguration importieren...",
            command=self._on_import_named_config,
        )
        self._file_menu.add_separator()
        if transport == PLC_TRANSPORT_OPCUA:
            self._file_menu.add_command(
                label="OPC UA Variablen (manuell)...",
                command=self._on_edit_opcua_variables,
            )
        else:
            self._file_menu.add_command(
                label="Snap7 Variablen...",
                command=self._on_edit_snap7_variables,
            )
        self._file_menu.add_command(
            label="Diagramm als PNG speichern...",
            command=self._on_export_plot_png,
        )
        self._file_menu.add_separator()
        self._file_menu.add_command(
            label="Datenbank als Tabelle...",
            command=self._on_open_db_table,
        )
        self._file_menu.add_command(
            label="Datenbank warten...",
            command=self._on_db_maintenance,
        )

    def _build_top_bar(self):
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        transport_row = ttk.Frame(top)
        transport_row.grid(row=0, column=0, columnspan=12, sticky=tk.EW)
        ttk.Label(transport_row, text="Protokoll:").pack(side=tk.LEFT, padx=(0, 4))
        transport_label = TRANSPORT_UI_LABELS.get(
            load_plc_transport(), TRANSPORT_UI_LABELS[PLC_TRANSPORT_SNAP7]
        )
        self.var_plc_transport = tk.StringVar(value=transport_label)
        self.cmb_plc_transport = ttk.Combobox(
            transport_row,
            textvariable=self.var_plc_transport,
            values=list(TRANSPORT_UI_LABELS.values()),
            state="readonly",
            width=8,
        )
        self.cmb_plc_transport.pack(side=tk.LEFT, padx=(0, 12))
        self.cmb_plc_transport.bind("<<ComboboxSelected>>", lambda _e: self._on_transport_changed())

        self.lbl_ip = ttk.Label(transport_row, text="SPS-IP:")
        self.lbl_ip.pack(side=tk.LEFT, padx=(0, 4))
        self.var_ip = tk.StringVar(value=self._initial_plc_ip)
        self.entry_ip = ttk.Entry(transport_row, textvariable=self.var_ip, width=18)
        self.entry_ip.pack(side=tk.LEFT, padx=(0, 12))
        self.entry_ip.bind(
            "<FocusOut>", lambda _e: self._persist_connection_settings_from_ui()
        )

        self.lbl_opcua_endpoint = ttk.Label(transport_row, text="OPC-UA-Endpoint:")
        self.var_opcua_endpoint = tk.StringVar(value=load_opcua_endpoint())
        self.entry_opcua_endpoint = ttk.Entry(
            transport_row, textvariable=self.var_opcua_endpoint, width=36
        )
        self.entry_opcua_endpoint.bind(
            "<FocusOut>", lambda _e: self._persist_connection_settings_from_ui()
        )

        self.opcua_auth_row = ttk.Frame(top)
        self.opcua_auth_row.grid(row=1, column=0, columnspan=12, sticky=tk.EW, pady=(4, 0))
        ttk.Label(self.opcua_auth_row, text="Benutzer:").pack(side=tk.LEFT, padx=(0, 4))
        self.var_opcua_username = tk.StringVar(value=load_opcua_username())
        self.entry_opcua_username = ttk.Entry(
            self.opcua_auth_row, textvariable=self.var_opcua_username, width=16
        )
        self.entry_opcua_username.pack(side=tk.LEFT, padx=(0, 12))
        self.var_opcua_username.trace_add("write", self._on_opcua_username_changed)
        self.entry_opcua_username.bind(
            "<FocusOut>", lambda _e: self._persist_opcua_credentials_from_ui()
        )
        ttk.Label(self.opcua_auth_row, text="Passwort:").pack(side=tk.LEFT, padx=(0, 4))
        self.var_opcua_password = tk.StringVar(value=load_opcua_password())
        self.entry_opcua_password = ttk.Entry(
            self.opcua_auth_row, textvariable=self.var_opcua_password, width=16, show="*"
        )
        self.entry_opcua_password.pack(side=tk.LEFT)
        self.entry_opcua_password.bind("<FocusOut>", lambda _e: self._persist_opcua_credentials_from_ui())

        plc_params_row = ttk.Frame(top)
        plc_params_row.grid(row=2, column=0, columnspan=12, sticky=tk.W)
        ttk.Label(plc_params_row, text="Rack:").pack(side=tk.LEFT, padx=(0, 4))
        self.var_plc_rack = tk.IntVar(value=load_plc_rack())
        self.spin_plc_rack = ttk.Spinbox(
            plc_params_row, from_=0, to=7, width=4, textvariable=self.var_plc_rack
        )
        self.spin_plc_rack.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(plc_params_row, text="Slot:").pack(side=tk.LEFT, padx=(0, 4))
        self.var_plc_slot = tk.IntVar(value=load_plc_slot())
        self.spin_plc_slot = ttk.Spinbox(
            plc_params_row, from_=0, to=31, width=4, textvariable=self.var_plc_slot
        )
        self.spin_plc_slot.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(plc_params_row, text="SPS-DB:").pack(side=tk.LEFT, padx=(0, 4))
        self.var_plc_db_number = tk.IntVar(value=load_plc_db_number())
        self.spin_plc_db_number = ttk.Spinbox(
            plc_params_row, from_=1, to=65535, width=5, textvariable=self.var_plc_db_number
        )
        self.spin_plc_db_number.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(plc_params_row, text="Abfrage (ms):").pack(side=tk.LEFT, padx=(0, 4))
        self.var_poll_interval_ms = tk.IntVar(
            value=poll_interval_ms_from_s(load_poll_interval_s())
        )
        self.spin_poll_interval = ttk.Spinbox(
            plc_params_row,
            from_=int(MIN_POLL_INTERVAL_S * 1000),
            to=int(MAX_POLL_INTERVAL_S * 1000),
            increment=1,
            wrap=False,
            width=6,
            textvariable=self.var_poll_interval_ms,
            command=self._on_poll_interval_spin_changed,
        )
        self.spin_poll_interval.bind(
            "<FocusOut>", self._on_poll_interval_focus_out, add="+"
        )
        self.spin_poll_interval.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(plc_params_row, text="Aufzeichnung:").pack(side=tk.LEFT, padx=(0, 4))
        recording_label = RECORDING_MODE_UI_LABELS[load_recording_mode()]
        self.var_recording_mode = tk.StringVar(value=recording_label)
        self.cmb_recording_mode = ttk.Combobox(
            plc_params_row,
            textvariable=self.var_recording_mode,
            values=list(RECORDING_MODE_UI_LABELS.values()),
            state="readonly",
            width=20,
        )
        self.cmb_recording_mode.pack(side=tk.LEFT)
        self.cmb_recording_mode.bind(
            "<<ComboboxSelected>>", lambda _e: self._on_recording_mode_changed()
        )

        sqlite_row = ttk.Frame(top)
        sqlite_row.grid(row=3, column=0, columnspan=12, sticky=tk.EW, pady=(6, 0))
        sqlite_row.columnconfigure(1, weight=1)
        ttk.Label(sqlite_row, text="SQLite-Datei:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 4)
        )
        self.var_db = tk.StringVar(value=self._db_path)
        db_row = ttk.Frame(sqlite_row)
        db_row.grid(row=0, column=1, sticky=tk.EW)
        db_row.columnconfigure(0, weight=1)
        self.entry_db = ttk.Entry(db_row, textvariable=self.var_db, width=36)
        self.entry_db.grid(row=0, column=0, sticky=tk.EW)
        self.entry_db.bind("<FocusOut>", self._on_db_path_focus_out)
        self.btn_browse_db = ttk.Button(
            db_row, text="Durchsuchen...", width=14, command=self._on_browse_db
        )
        self.btn_browse_db.grid(row=0, column=1, sticky=tk.E, padx=(6, 0))

        btn_row = ttk.Frame(top)
        btn_row.grid(row=4, column=0, columnspan=12, sticky=tk.EW, pady=(8, 0))
        self.btn_connect = ttk.Button(btn_row, text="Verbinden", command=self._on_connect)
        self.btn_connect.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_disconnect = ttk.Button(
            btn_row, text="Trennen", command=self._on_disconnect, state=tk.DISABLED
        )
        self.btn_disconnect.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_start = ttk.Button(
            btn_row,
            text=RECORDING_START_LABEL,
            command=self._on_start,
            state=tk.DISABLED,
            width=RECORDING_START_BUTTON_WIDTH,
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_pause = ttk.Button(
            btn_row,
            text="Pausieren",
            command=self._on_pause,
            state=tk.DISABLED,
            width=RECORDING_START_BUTTON_WIDTH,
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 6))
        self.var_auto_reconnect = tk.BooleanVar(value=load_auto_reconnect())
        self.chk_auto_reconnect = ttk.Checkbutton(
            btn_row,
            text="Auto-Reconnect",
            variable=self.var_auto_reconnect,
            command=self._on_auto_reconnect_toggle,
        )
        self.chk_auto_reconnect.pack(side=tk.LEFT, padx=(12, 6))
        self.btn_export_csv = ttk.Button(
            btn_row, text="CSV exportieren...", command=self._on_export_csv
        )
        self.btn_export_csv.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_db_table = ttk.Button(
            btn_row, text="DB-Tabelle", command=self._on_open_db_table
        )
        self.btn_db_table.pack(side=tk.LEFT)

        live_f = ttk.LabelFrame(top, text="SPS (letzter Messpunkt)", padding=(8, 4))
        live_f.grid(row=5, column=0, columnspan=12, sticky=tk.EW, pady=(8, 0))
        live_inner = ttk.Frame(live_f)
        live_inner.pack(fill=tk.X)
        live_specs = (
            ("Count:", self.var_live_count),
            ("Temp.:", self.var_live_temp),
            ("Distanz:", self.var_live_dist),
            ("MotorCurrent:", self.var_live_motor_current),
        )
        for title, var in live_specs:
            title_lbl = ttk.Label(live_inner, text=title)
            title_lbl.pack(side=tk.LEFT, padx=(0, 2))
            self._live_title_labels.append(title_lbl)
            ttk.Label(live_inner, textvariable=var, width=10).pack(
                side=tk.LEFT, padx=(0, 10)
            )

        self.status_var = tk.StringVar(value="Nicht verbunden.")
        status_row = ttk.Frame(top)
        status_row.grid(row=6, column=0, columnspan=12, sticky=tk.EW, pady=(6, 0))
        status_row.columnconfigure(0, weight=1)
        ttk.Label(status_row, textvariable=self.status_var).grid(
            row=0, column=0, sticky=tk.W
        )
        self.lbl_recording = ttk.Label(
            status_row,
            textvariable=self.var_recording,
            foreground="#b00020",
            width=10,
            anchor=tk.E,
        )
        self.lbl_recording.grid(row=0, column=1, sticky=tk.E, padx=(8, 0))

        plot_opts = ttk.Frame(top)
        plot_opts.grid(row=7, column=0, columnspan=12, sticky=tk.EW, pady=(8, 0))
        ttk.Label(plot_opts, text="Diagramm:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(
            plot_opts,
            text="Letzte",
            variable=self.var_plot_scope,
            value="limit",
            command=self._sync_plot_scope_widgets,
        ).pack(side=tk.LEFT)
        self.spin_plot_limit = ttk.Spinbox(
            plot_opts,
            from_=1,
            to=99_999_999,
            width=10,
            textvariable=self.var_plot_limit,
        )
        self.spin_plot_limit.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(plot_opts, text="Zeilen").pack(side=tk.LEFT, padx=(4, 12))
        ttk.Radiobutton(
            plot_opts,
            text="Gesamte Datenbank",
            variable=self.var_plot_scope,
            value="all",
            command=self._sync_plot_scope_widgets,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(plot_opts, text="Aktualis. (ms):").pack(side=tk.LEFT, padx=(0, 4))
        self.spin_plot_refresh = ttk.Spinbox(
            plot_opts,
            from_=MIN_PLOT_REFRESH_MS,
            to=MAX_PLOT_REFRESH_MS,
            width=6,
            textvariable=self.var_plot_refresh_ms,
        )
        self.spin_plot_refresh.pack(side=tk.LEFT)
        self._sync_plot_scope_widgets()

        plot_field_row = ttk.Frame(top)
        plot_field_row.grid(row=8, column=0, columnspan=12, sticky=tk.EW, pady=(4, 0))
        ttk.Label(plot_field_row, text="Kurven:").pack(side=tk.LEFT, padx=(0, 6))
        self.plot_field_checks_frame = FlowFrame(plot_field_row, h_pad=8, v_pad=2)
        self.plot_field_checks_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._sync_transport_widgets()

    def _build_log_area(self):
        log_frame = ttk.LabelFrame(self, text="Meldungen", padding=4)
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, padx=8, pady=(0, 8))
        self.log = scrolledtext.ScrolledText(
            log_frame, height=LOG_BOX_LINES, wrap=tk.WORD
        )
        self.log.pack(fill=tk.BOTH, expand=True)

    def _on_close(self):
        """Fenster schliessen: Worker kurz (max. 2s) auslaufen lassen,
        DB-Verbindung schliessen, SPS im Hintergrund trennen.
        Der lange Join aus _stop_recording_async entfaellt hier bewusst —
        beim Beenden des Prozesses sterben Daemon-Threads ohnehin, und
        SQLite im WAL-Mode ist gegen harte Abbrueche robust.
        """
        self.stop_event.set()
        selected = self._get_selected_plot_fields()
        if selected:
            self._schema.plot_fields = selected
        save_plc_schema(
            self._schema,
            last_database=resolve_db_path(self.var_db.get().strip() or self._db_path),
            transport=self._get_plc_transport(),
        )
        save_poll_interval_s(self._get_poll_interval_s())
        save_plot_refresh_ms(int(self.var_plot_refresh_ms.get()))
        save_plc_rack_slot(self.var_plc_rack.get(), self.var_plc_slot.get())
        save_plc_db_number(self.var_plc_db_number.get())
        save_auto_reconnect(bool(self.var_auto_reconnect.get()))
        self._persist_connection_settings_from_ui()
        geometry = capture_window_geometry(self)
        if geometry:
            save_window_geometry(WINDOW_ID_MAIN, geometry)
        table_win = getattr(self, "_db_table_window", None)
        if table_win is not None:
            try:
                if table_win.winfo_exists():
                    table_geom = capture_window_geometry(table_win)
                    if table_geom:
                        save_window_geometry(WINDOW_ID_DB_TABLE, table_geom)
            except tk.TclError:
                pass
        if self._get_plc_transport() == PLC_TRANSPORT_OPCUA:
            self._persist_opcua_credentials_from_ui()
        if self.write_thread is not None:
            self.write_thread.join(timeout=2)
        if self.conn_read is not None:
            try:
                self.conn_read.close()
            except Error:
                pass
            self.conn_read = None
            self.cursor_read = None
        threading.Thread(
            target=self._plc_disconnect_worker, daemon=True, name="PLCDisconnect"
        ).start()
        self.destroy()
