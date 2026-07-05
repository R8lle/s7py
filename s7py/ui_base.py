"""Gemeinsame Typ-Deklarationen fuer ``S7PyApp`` und ihre Mixins.

:class:`S7PyAppProtocol` listet Attribute und Hilfsmethoden, die die Mixins
von der Hauptklasse erwarten. Methoden in den Mixins koennen ``self`` damit
annotieren (``def foo(self: S7PyAppProtocol) -> None``), damit IDEs
Autovervollstaendigung und Typpruefung bieten — ohne Laufzeit-Auswirkung.
"""

from __future__ import annotations

import sqlite3
import threading
import tkinter as tk
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from matplotlib.axes import Axes
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tkinter import scrolledtext, ttk

from s7py.schema import DbItem, PlcDbSchema
from s7py.ui_flow import FlowFrame

# Plot-Cache-Zeile: (id, datetime, {feldname: wert})
PlotCacheRow = tuple[int, datetime, dict[str, float | int | str]]


@runtime_checkable
class S7PyAppProtocol(Protocol):
    """Gemeinsamer Zustand und UI-Hilfen, die alle Mixins voraussetzen."""

    # --- Tk / Fenster ---
    def after(
        self,
        ms: int,
        func: Optional[Callable[..., Any]] = None,
        /,
        *args: Any,
    ) -> str: ...
    def winfo_exists(self) -> bool: ...

    # --- SPS / Threads ---
    plc_backend: Any
    plc_lock: threading.RLock
    stop_event: threading.Event
    write_thread: Optional[threading.Thread]
    _plc_ip: str
    _session_active: bool
    _reconnecting: bool
    _reconnect_attempt: int
    _reconnect_generation: int
    _connecting: bool
    _connection_lost: bool
    items: list[DbItem]
    DBlength: int

    # --- SQLite (Leseverbindung fuer Diagramm) ---
    conn_read: Optional[sqlite3.Connection]
    cursor_read: Optional[sqlite3.Cursor]
    _db_path: str
    _db_stats: dict[str, object] | None
    _db_stats_tick: int
    _count_gap_hint_shown: bool
    _recording_paused: bool
    _db_table_window: tk.Toplevel | None

    # --- Schema ---
    _schema: PlcDbSchema
    _app_config: dict[str, Any]

    # --- Tk-Variablen (Bedienleiste) ---
    var_ip: tk.StringVar
    var_plc_transport: tk.StringVar
    var_opcua_endpoint: tk.StringVar
    var_opcua_username: tk.StringVar
    var_opcua_password: tk.StringVar
    var_db: tk.StringVar
    var_poll_interval_ms: tk.IntVar
    var_plc_rack: tk.IntVar
    var_plc_slot: tk.IntVar
    var_plc_db_number: tk.IntVar
    var_auto_reconnect: tk.BooleanVar
    var_plot_scope: tk.StringVar
    var_plot_limit: tk.IntVar
    var_plot_refresh_ms: tk.IntVar
    var_recording: tk.StringVar
    status_var: tk.StringVar
    _live_value_vars: list[tk.StringVar]

    # --- Widgets (Bedienleiste) ---
    btn_connect: ttk.Button
    btn_disconnect: ttk.Button
    btn_start: ttk.Button
    btn_pause: ttk.Button
    btn_browse_db: ttk.Button
    chk_auto_reconnect: ttk.Checkbutton
    btn_export_csv: ttk.Button
    btn_db_table: ttk.Button
    entry_ip: ttk.Entry
    entry_opcua_endpoint: ttk.Entry
    entry_opcua_username: ttk.Entry
    entry_opcua_password: ttk.Entry
    opcua_auth_row: ttk.Frame
    cmb_plc_transport: ttk.Combobox
    lbl_ip: ttk.Label
    lbl_opcua_endpoint: ttk.Label
    entry_db: ttk.Entry
    spin_poll_interval: ttk.Spinbox
    spin_plc_rack: ttk.Spinbox
    spin_plc_slot: ttk.Spinbox
    spin_plc_db_number: ttk.Spinbox
    spin_plot_limit: ttk.Spinbox
    spin_plot_refresh: ttk.Spinbox
    plot_field_checks_frame: FlowFrame
    _live_title_labels: list[ttk.Label]
    log: scrolledtext.ScrolledText

    # --- Diagramm (Matplotlib) ---
    fig: Figure
    ax_plot: Axes
    ax_plot_right: Optional[Axes]
    canvas: FigureCanvasTkAgg
    _plot_lines: dict[str, Any]
    _plot_field_vars: dict[str, tk.BooleanVar]
    _plot_cache_scope: Optional[tuple[str, ...]]
    _plot_cache_rows: list[PlotCacheRow]
    _markers_on: bool
    _recording_phase: int

    # --- Von Mixins / App aufgerufene Hilfsmethoden ---
    def _log(self, message: object) -> None: ...
    def _set_connected_ui(self, connected: bool) -> None: ...
    def _set_connecting_ui(self, busy: bool) -> None: ...
    def _clear_plot_cache(self) -> None: ...
    def _clear_plot_display(self) -> None: ...
    def _draw_plot_from_cache(self) -> None: ...
    def _sync_dual_axis_layout(
        self, selected: Optional[list[str]] = None
    ) -> None: ...
    def _get_selected_plot_fields(self) -> list[str]: ...
    def _rebuild_plot_field_checkboxes(self) -> None: ...
    def _ensure_plot_lines(self) -> None: ...
    def _sync_plot_scope_widgets(self) -> None: ...
    def _get_plot_fetch_limit(self) -> Optional[int]: ...
    def _get_plot_refresh_ms(self) -> int: ...
    def _on_export_plot_png(self) -> None: ...
    def _update_plot_cache_and_draw(self) -> None: ...
    def _update_marker_visibility(self, n_points: int) -> None: ...
    def _reset_live_labels(self) -> None: ...
    def _get_plc_transport(self) -> str: ...
    def _resolve_active_db_path(self) -> str: ...
    def _get_opcua_endpoint(self) -> str: ...
    def _get_connection_target(self) -> str: ...
    def _ensure_plc_backend(self) -> None: ...
    def _on_transport_changed(self) -> None: ...
    def _sync_transport_widgets(self) -> None: ...
    def _sync_poll_interval_spin(self) -> int: ...
    def _on_poll_interval_spin_changed(self) -> None: ...
    def _on_poll_interval_focus_out(self, _event=None) -> None: ...
    def _get_poll_interval_s(self) -> float: ...
    def _get_plc_rack(self) -> int: ...
    def _get_plc_slot(self) -> int: ...
    def _get_plc_db_number(self) -> int: ...
    def _refresh_db_stats(self) -> None: ...
    def _db_stats_suffix(self) -> str: ...
    def _refresh_status_display(self) -> None: ...
    def _on_count_gap_hint(self, missed: int, poll_interval_s: float) -> None: ...
    def _on_pause(self) -> None: ...
    def _on_db_maintenance(self) -> None: ...
    def _on_edit_opcua_variables(self) -> None: ...
    def _on_open_db_table(self) -> None: ...
    def _format_table_cell(self, value: object) -> str: ...
    def _is_recording_active(self) -> bool: ...
    def _on_auto_reconnect_toggle(self) -> None: ...
    def _tick_connection_watchdog(self) -> None: ...
    def _update_connected_status(self) -> None: ...
    def _set_connection_lost_ui(self) -> None: ...
    def _attach_database(
        self,
        db_path: str,
        *,
        create_if_missing: bool = False,
        silent: bool = False,
    ) -> bool: ...
