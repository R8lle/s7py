"""Verbindungs- und Aufzeichnungslogik fuer ``S7PyApp`` (Mixin).

Steuert Verbinden/Trennen der SPS, Start/Stopp der Aufzeichnung (Worker-
Thread), Auto-Reconnect und den blinkenden REC-Indikator. Threads rufen
Ergebnisse stets ueber ``self.after(...)`` in den Tk-Hauptthread zurueck.
"""

import threading
import tkinter as tk
from sqlite3 import Error
from tkinter import messagebox

from s7py.ui_base import S7PyAppProtocol
from s7py.opcua_import import OpcUaError, format_opcua_connect_error
from s7py.backends import create_backend
from s7py.constants import (
    AUTO_RECONNECT_BASE_DELAY_S,
    AUTO_RECONNECT_MAX_DELAY_S,
    CONNECTION_WATCH_MS,
    DB_STATS_REFRESH_MS,
    DEFAULT_PLC_IP,
    MIN_POLL_INTERVAL_S,
    PLC_TRANSPORT_OPCUA,
    PLC_TRANSPORT_SNAP7,
    RECORDING_GLYPHS,
    RECORDING_MODE_COUNT,
    RECORDING_MODE_UI_LABELS,
    RECORDING_MODE_UI_TO_ID,
    RECORDING_TICK_MS,
    WORKER_JOIN_TIMEOUT_S,
)
from s7py.db import (
    default_db_path_for_transport,
    load_plc_transport,
    merge_opcua_security_config,
    normalize_plc_rack,
    normalize_plc_slot,
    normalize_plc_db_number,
    poll_interval_ms_from_s,
    poll_interval_s_from_ms,
    resolve_db_path,
    save_auto_reconnect,
    save_last_plc_ip,
    save_opcua_credentials,
    save_opcua_endpoint,
    save_plc_db_number,
    save_plc_rack_slot,
    save_plc_schema,
    save_plc_transport,
    save_poll_interval_s,
    save_recording_mode,
)
from s7py.plc import PLC_IO_ERRORS
from s7py.opcua_connect import OpcUaSecurityConfig
from s7py.schema import DbItem, items_for_plc_read
from s7py.worker import write_data_to_db


class ConnectionMixin:
    """SPS-Verbindung, Aufzeichnungssteuerung, Auto-Reconnect und REC-Indikator."""

    def _get_plc_transport(self: S7PyAppProtocol) -> str:
        from s7py.constants import TRANSPORT_UI_TO_ID

        label = self.var_plc_transport.get()
        return TRANSPORT_UI_TO_ID.get(label, PLC_TRANSPORT_SNAP7)

    def _get_opcua_endpoint(self: S7PyAppProtocol) -> str:
        from s7py.constants import DEFAULT_OPCUA_ENDPOINT

        url = self.var_opcua_endpoint.get().strip()
        return url or DEFAULT_OPCUA_ENDPOINT

    def _get_connection_target(self: S7PyAppProtocol) -> str:
        if self._get_plc_transport() == PLC_TRANSPORT_OPCUA:
            return self._get_opcua_endpoint()
        return self.var_ip.get().strip() or DEFAULT_PLC_IP

    def _persist_connection_settings_from_ui(self: S7PyAppProtocol) -> None:
        """SPS-IP / OPC-UA-Endpoint aus der UI speichern (auch ohne Verbinden)."""
        save_last_plc_ip(self.var_ip.get())
        save_opcua_endpoint(self._get_opcua_endpoint())
        save_plc_transport(self._get_plc_transport())

    def _ensure_plc_backend(self: S7PyAppProtocol) -> None:
        transport = self._get_plc_transport()
        if self.plc_backend.transport == transport:
            return
        try:
            with self.plc_lock:
                self.plc_backend.disconnect()
        except Exception:
            pass
        self.plc_backend = create_backend(transport)

    def _on_transport_changed(self: S7PyAppProtocol) -> None:
        if self._session_active:
            return
        old_transport = load_plc_transport()
        save_plc_schema(self._schema, transport=old_transport)
        save_plc_transport(self._get_plc_transport())
        save_opcua_endpoint(self._get_opcua_endpoint())
        if self._get_plc_transport() == PLC_TRANSPORT_OPCUA:
            self._persist_opcua_credentials_from_ui()
        self._ensure_plc_backend()
        self._sync_transport_widgets()
        self._reload_schema_for_transport(self._get_plc_transport())

    def _on_connect(self: S7PyAppProtocol) -> None:
        self._ensure_plc_backend()
        target = self._get_connection_target()
        db_path = resolve_db_path(
            self.var_db.get().strip()
            or default_db_path_for_transport(self._get_plc_transport())
        )

        try:
            if not self._schema.items:
                raise ValueError("Keine SPS-Struktur geladen.")
            items = self._schema.items
            db_length = self._schema.read_length
        except ValueError as exc:
            messagebox.showerror("Konfiguration", str(exc))
            return

        self._reconnect_generation += 1
        self._reconnecting = False
        save_plc_rack_slot(self._get_plc_rack(), self._get_plc_slot())
        save_plc_db_number(self._get_plc_db_number())
        save_plc_transport(self._get_plc_transport())
        save_opcua_endpoint(self._get_opcua_endpoint())
        opcua_security: OpcUaSecurityConfig | None = None
        if self._get_plc_transport() == PLC_TRANSPORT_OPCUA:
            opcua_security = self._get_opcua_security_config()
            if opcua_security.has_credentials() and not opcua_security.password:
                messagebox.showerror(
                    "OPC-UA-Verbindung",
                    "Benutzername ohne Passwort — bitte Passwort eintragen.",
                )
                return
            missing_nodes = [
                item.name
                for item in items
                if not str(getattr(item, "node_id", "") or "").strip()
            ]
            if missing_nodes:
                messagebox.showerror(
                    "OPC-UA-Verbindung",
                    "Im OPC-UA-Schema fehlen NodeIds "
                    f"({len(missing_nodes)} Variable(n)).\n\n"
                    "Bitte unter Variablen → OPC UA die Knoten neu auswaehlen "
                    "(…-Button) und speichern.\n\n"
                    "Hinweis: Die Desktop-App speichert unter\n"
                    "~/Library/Application Support/s7py/\n"
                    "— getrennt von der Cursor-/Projekt-Konfiguration.",
                )
                return
            self._persist_opcua_credentials_from_ui()
        self._set_connecting_ui(True)
        self.status_var.set(f"Verbinde mit {target} ...")
        self._log(
            f"Verbindungsaufbau zu {target} ({self.plc_backend.display_name}) ..."
        )

        threading.Thread(
            target=self._connect_worker,
            args=(
                target,
                db_path,
                items,
                db_length,
                self._get_plc_rack(),
                self._get_plc_slot(),
                opcua_security,
            ),
            daemon=True,
            name="PLCConnectWorker",
        ).start()

    def _get_plc_rack(self: S7PyAppProtocol) -> int:
        return normalize_plc_rack(self.var_plc_rack.get())

    def _get_plc_slot(self: S7PyAppProtocol) -> int:
        return normalize_plc_slot(self.var_plc_slot.get())

    def _get_plc_db_number(self: S7PyAppProtocol) -> int:
        return normalize_plc_db_number(self.var_plc_db_number.get())

    def _get_opcua_password(self: S7PyAppProtocol) -> str:
        if hasattr(self, "entry_opcua_password"):
            return self.entry_opcua_password.get()
        return self.var_opcua_password.get()

    def _persist_opcua_credentials_from_ui(self: S7PyAppProtocol) -> None:
        """Benutzer/Passwort aus der UI in s7py_db.json schreiben (auch leer = loeschen)."""
        if self._session_active:
            return
        if self._get_plc_transport() != PLC_TRANSPORT_OPCUA:
            return
        username = self.var_opcua_username.get().strip()
        password = self._get_opcua_password() if username else ""
        if not username and self.var_opcua_password.get():
            self.var_opcua_password.set("")
        save_opcua_credentials(username, password)

    def _on_opcua_username_changed(self: S7PyAppProtocol, *_args: object) -> None:
        if not self.var_opcua_username.get().strip():
            self.var_opcua_password.set("")

    def _get_opcua_security_config(self: S7PyAppProtocol) -> OpcUaSecurityConfig:
        return merge_opcua_security_config(
            username=self.var_opcua_username.get(),
            password=self._get_opcua_password(),
        )

    def _log_connection_details(self: S7PyAppProtocol) -> None:
        detail = self.plc_backend.connection_log_detail(
            self._plc_ip or "",
            rack=self._get_plc_rack(),
            slot=self._get_plc_slot(),
            db_number=self._get_plc_db_number(),
            endpoint_url=self._get_opcua_endpoint(),
        )
        if detail:
            self._log(detail)

    def _connect_worker(
        self: S7PyAppProtocol,
        target: str,
        db_path: str,
        items: list[DbItem],
        db_length: int,
        plc_rack: int,
        plc_slot: int,
        opcua_security: OpcUaSecurityConfig | None,
    ) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            with self.plc_lock:
                if self.plc_backend.transport == PLC_TRANSPORT_OPCUA:
                    self.plc_backend.connect(
                        "",
                        endpoint_url=target,
                        security=opcua_security,
                    )
                else:
                    self.plc_backend.connect(target, rack=plc_rack, slot=plc_slot)
        except (*PLC_IO_ERRORS, OpcUaError, ValueError) as exc:
            ok, err_text = False, str(exc)
        except Exception as exc:
            if self.plc_backend.transport == PLC_TRANSPORT_OPCUA:
                ok, err_text = False, format_opcua_connect_error(exc, target)
            else:
                ok, err_text = False, f"{type(exc).__name__}: {exc}"
        else:
            ok, err_text = True, None
        try:
            self.after(
                0, self._connect_done, ok, err_text, target, db_path, items, db_length
            )
        except (RuntimeError, tk.TclError):
            pass

    def _connect_done(
        self: S7PyAppProtocol,
        ok: bool,
        err_text: str | None,
        ip: str,
        db_path: str,
        items: list[DbItem],
        db_length: int,
    ) -> None:
        """Laeuft im Tkinter-Hauptthread."""
        if not ok:
            title = (
                "OPC-UA-Verbindung"
                if self._get_plc_transport() == PLC_TRANSPORT_OPCUA
                else "SPS-Verbindung"
            )
            messagebox.showerror(title, err_text or "Unbekannter Fehler")
            self._log(f"SPS-Verbindung fehlgeschlagen: {err_text}")
            self.status_var.set("Nicht verbunden.")
            self._set_connecting_ui(False)
            self._set_connected_ui(False)
            return

        self._plc_ip = ip
        self.items = items
        self.DBlength = db_length

        if not self._attach_database(
            db_path, create_if_missing=True, silent=False
        ):
            try:
                with self.plc_lock:
                    self.plc_backend.disconnect()
            except PLC_IO_ERRORS:
                pass
            self.status_var.set("Nicht verbunden.")
            self._set_connecting_ui(False)
            self._set_connected_ui(False)
            return

        if self._get_plc_transport() == PLC_TRANSPORT_OPCUA:
            save_opcua_endpoint(ip)
            save_last_plc_ip(self.var_ip.get())
        else:
            save_last_plc_ip(ip)
            save_opcua_endpoint(self._get_opcua_endpoint())
        self._session_active = True
        self._reconnecting = False
        self._reconnect_attempt = 0
        self._connection_lost = False
        self._recording_paused = False
        self._refresh_status_display()
        self._log(f"Verbunden mit {ip}, DB {db_path}")
        self._log_connection_details()
        self._set_connecting_ui(False)
        self._set_connected_ui(True)

    def _refresh_status_display(self: S7PyAppProtocol) -> None:
        """Statuszeile inkl. DB-Statistik aktualisieren."""
        self._refresh_db_stats()
        suffix = self._db_stats_suffix()
        if self._session_active and self._plc_ip and not self._reconnecting:
            if self.plc_backend.is_connected(self.plc_lock):
                detail = self.plc_backend.status_detail(
                    self._plc_ip,
                    rack=self._get_plc_rack(),
                    slot=self._get_plc_slot(),
                    db_number=self._get_plc_db_number(),
                    endpoint_url=self._get_opcua_endpoint(),
                )
                self.status_var.set(
                    f"Verbunden: {detail}  |  SQLite: {self._db_path}{suffix}"
                )
                return
        if self._reconnecting:
            return
        if self.cursor_read is not None:
            self.status_var.set(f"DB: {self._db_path}{suffix}")
            return
        if not self._session_active:
            self.status_var.set("Nicht verbunden.")

    def _update_connected_status(self: S7PyAppProtocol) -> None:
        self._refresh_status_display()

    def _on_auto_reconnect_toggle(self: S7PyAppProtocol) -> None:
        save_auto_reconnect(bool(self.var_auto_reconnect.get()))

    def _tick_connection_watchdog(self: S7PyAppProtocol) -> None:
        """Ueberwacht die SPS-Verbindung und startet bei Abbruch Auto-Reconnect."""
        try:
            if (
                self._session_active
                and not self._reconnecting
                and not self._connecting
                and self._plc_ip
            ):
                if not self.plc_backend.is_connected(self.plc_lock):
                    if not self._connection_lost:
                        self._connection_lost = True
                        self._log("SPS-Verbindung verloren.")
                        self.status_var.set(
                            f"Verbindung verloren: {self._plc_ip}"
                        )
                        self._set_connection_lost_ui()
                    if self.var_auto_reconnect.get():
                        self._begin_auto_reconnect(lost=False)
                elif self._connection_lost:
                    self._connection_lost = False
            if self.conn_read is not None:
                self._db_stats_tick = getattr(self, "_db_stats_tick", 0) + CONNECTION_WATCH_MS
                if self._db_stats_tick >= DB_STATS_REFRESH_MS:
                    self._db_stats_tick = 0
                    if not self._reconnecting:
                        self._refresh_status_display()
        finally:
            if self.winfo_exists():
                self.after(CONNECTION_WATCH_MS, self._tick_connection_watchdog)

    def _begin_auto_reconnect(self: S7PyAppProtocol, *, lost: bool) -> None:
        if not self._session_active or not self.var_auto_reconnect.get():
            return
        if self._reconnecting or self._connecting:
            return
        self._reconnecting = True
        self._reconnect_attempt = 0
        if lost:
            self.status_var.set(
                f"Verbindung verloren - Wiederverbindung mit {self._plc_ip} ..."
            )
        self._set_connection_lost_ui()
        self._try_auto_reconnect()

    def _try_auto_reconnect(self: S7PyAppProtocol) -> None:
        if not self._session_active or not self.var_auto_reconnect.get():
            self._reconnecting = False
            return
        generation = self._reconnect_generation
        self._reconnect_attempt += 1
        attempt = self._reconnect_attempt
        ip = self._plc_ip
        self.status_var.set(
            f"Wiederverbindung mit {ip} (Versuch {attempt}) ..."
        )
        threading.Thread(
            target=self._auto_reconnect_worker,
            args=(
                ip,
                generation,
                attempt,
                self._get_plc_rack(),
                self._get_plc_slot(),
                self._get_opcua_security_config()
                if self.plc_backend.transport == PLC_TRANSPORT_OPCUA
                else None,
            ),
            daemon=True,
            name="PLCAutoReconnect",
        ).start()

    def _auto_reconnect_worker(
        self: S7PyAppProtocol,
        ip: str,
        generation: int,
        attempt: int,
        plc_rack: int,
        plc_slot: int,
        opcua_security: OpcUaSecurityConfig | None,
    ) -> None:
        ok = False
        err_text: str | None = None
        try:
            with self.plc_lock:
                if self.plc_backend.is_connected(None):
                    ok = True
                else:
                    try:
                        self.plc_backend.disconnect()
                    except PLC_IO_ERRORS:
                        pass
                    if self.plc_backend.transport == PLC_TRANSPORT_OPCUA:
                        self.plc_backend.connect(
                            "",
                            endpoint_url=ip,
                            security=opcua_security,
                        )
                    else:
                        self.plc_backend.connect(ip, rack=plc_rack, slot=plc_slot)
                    ok = self.plc_backend.is_connected(None)
        except PLC_IO_ERRORS as exc:
            err_text = str(exc)
        except OpcUaError as exc:
            err_text = str(exc)
        except Exception as exc:
            if self.plc_backend.transport == PLC_TRANSPORT_OPCUA:
                err_text = format_opcua_connect_error(exc, ip)
            else:
                err_text = f"{type(exc).__name__}: {exc}"
        try:
            self.after(
                0,
                self._auto_reconnect_done,
                ok,
                err_text,
                generation,
                attempt,
            )
        except (RuntimeError, tk.TclError):
            pass

    def _auto_reconnect_done(
        self: S7PyAppProtocol,
        ok: bool,
        err_text: str | None,
        generation: int,
        attempt: int,
    ) -> None:
        if generation != self._reconnect_generation or not self._session_active:
            return
        if ok:
            self._reconnecting = False
            self._reconnect_attempt = 0
            self._connection_lost = False
            self._update_connected_status()
            self._log(f"Wiederverbindung mit {self._plc_ip} erfolgreich.")
            self._log_connection_details()
            self._set_connected_ui(True)
            return

        delay = min(
            AUTO_RECONNECT_BASE_DELAY_S * (2 ** (attempt - 1)),
            AUTO_RECONNECT_MAX_DELAY_S,
        )
        self._log(
            f"Wiederverbindung fehlgeschlagen: {err_text or 'Unbekannter Fehler'}. "
            f"Naechster Versuch in {delay:.0f} s."
        )
        self.status_var.set(
            f"Verbindung verloren — erneuter Versuch in {delay:.0f} s "
            f"(Versuch {attempt} fehlgeschlagen)"
        )
        self._set_connection_lost_ui()

        def retry() -> None:
            if generation != self._reconnect_generation or not self._session_active:
                return
            self._try_auto_reconnect()

        try:
            self.after(int(delay * 1000), retry)
        except (RuntimeError, tk.TclError):
            pass

    def _set_connection_lost_ui(self: S7PyAppProtocol) -> None:
        """UI waehrend Verbindungsverlust / Wiederverbindung."""
        thread_alive = (
            self.write_thread is not None and self.write_thread.is_alive()
        )
        self.btn_connect["state"] = tk.DISABLED
        self.btn_disconnect["state"] = tk.NORMAL
        self.btn_start["state"] = tk.DISABLED
        self.btn_pause["state"] = tk.NORMAL if thread_alive else tk.DISABLED
        self.entry_ip["state"] = tk.DISABLED
        self.entry_db["state"] = tk.DISABLED
        self.btn_browse_db["state"] = tk.DISABLED
        self.spin_poll_interval["state"] = tk.DISABLED
        self.spin_plc_rack["state"] = tk.DISABLED
        self.spin_plc_slot["state"] = tk.DISABLED
        self.spin_plc_db_number["state"] = tk.DISABLED
        self.cmb_plc_transport["state"] = "disabled"
        self.entry_opcua_endpoint["state"] = tk.DISABLED

    def _stop_recording_async(self: S7PyAppProtocol, on_done) -> None:
        """Stoppt die Aufzeichnung, ohne den Tk-Hauptthread zu blockieren."""
        thread = self.write_thread
        self.stop_event.set()
        if thread is None or not thread.is_alive():
            self.write_thread = None
            on_done()
            return

        self.btn_start["state"] = tk.DISABLED
        self.btn_pause["state"] = tk.DISABLED

        def finish():
            if thread.is_alive():
                self._log(
                    f"WARNUNG: Worker-Thread reagiert nach {WORKER_JOIN_TIMEOUT_S}s "
                    f"nicht (vermutlich in plc.read_area blockiert). Er laeuft im "
                    f"Hintergrund weiter; ein Neustart der Aufzeichnung ist erst "
                    f"moeglich, wenn er sich nach dem Snap7-Timeout beendet hat."
                )
            elif self.write_thread is thread:
                self.write_thread = None
            on_done()

        def joiner():
            thread.join(timeout=WORKER_JOIN_TIMEOUT_S)
            try:
                self.after(0, finish)
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=joiner, daemon=True, name="WorkerJoin").start()

    def _on_pause(self: S7PyAppProtocol) -> None:
        self._stop_recording_async(self._pause_done)

    def _pause_done(self: S7PyAppProtocol) -> None:
        self._recording_paused = True
        self._log("Aufzeichnung pausiert (SPS-Verbindung bleibt bestehen).")
        self._refresh_status_display()
        if self._reconnecting:
            self._set_connection_lost_ui()
        else:
            self._set_connected_ui(self.plc_backend.is_connected(self.plc_lock))

    def _plc_disconnect_worker(self: S7PyAppProtocol) -> None:
        try:
            with self.plc_lock:
                self.plc_backend.disconnect()
        except PLC_IO_ERRORS:
            pass

    def _on_disconnect(self: S7PyAppProtocol) -> None:
        self._stop_recording_async(self._finish_disconnect)

    def _finish_disconnect(self: S7PyAppProtocol) -> None:
        """Laeuft im Tk-Hauptthread, nachdem die Aufzeichnung gestoppt ist."""
        self._session_active = False
        self._recording_paused = False
        self._reconnecting = False
        self._connection_lost = False
        self._reconnect_generation += 1
        if self.conn_read is not None:
            try:
                self.conn_read.close()
            except Error as exc:
                self._log(f"DB schliessen: {exc}")
            self.conn_read = None
            self.cursor_read = None
        threading.Thread(
            target=self._plc_disconnect_worker, daemon=True, name="PLCDisconnect"
        ).start()
        self._clear_plot_cache()
        self.status_var.set("Nicht verbunden.")
        self._log("Getrennt.")
        self._reset_live_labels()
        self._set_connected_ui(False)

    def _sync_poll_interval_spin(self: S7PyAppProtocol) -> int:
        """Spinbox-Wert auf MIN/MAX begrenzen und Anzeige zurueckschreiben."""
        from s7py.db import clamp_poll_interval_ms

        ms = clamp_poll_interval_ms(self.var_poll_interval_ms.get())
        if self.var_poll_interval_ms.get() != ms:
            self.var_poll_interval_ms.set(ms)
        return ms

    def _on_poll_interval_spin_changed(self: S7PyAppProtocol) -> None:
        self._sync_poll_interval_spin()

    def _on_poll_interval_focus_out(self: S7PyAppProtocol, _event=None) -> None:
        self._sync_poll_interval_spin()

    def _get_poll_interval_s(self: S7PyAppProtocol) -> float:
        return poll_interval_s_from_ms(self._sync_poll_interval_spin())

    def _get_recording_mode(self: S7PyAppProtocol) -> str:
        return RECORDING_MODE_UI_TO_ID.get(
            self.var_recording_mode.get().strip(),
            RECORDING_MODE_COUNT,
        )

    def _on_recording_mode_changed(self: S7PyAppProtocol) -> None:
        if self._session_active:
            return
        save_recording_mode(self._get_recording_mode())

    def _on_start(self: S7PyAppProtocol) -> None:
        if self.cursor_read is None or not self._schema.items:
            return
        if self.write_thread is not None and self.write_thread.is_alive():
            return
        if not self.plc_backend.is_connected(self.plc_lock):
            messagebox.showwarning(
                "SPS-Verbindung",
                "Keine aktive SPS-Verbindung. Bitte warten, bis die "
                "Wiederverbindung abgeschlossen ist, oder erneut verbinden.",
            )
            return
        poll_interval_s = self._get_poll_interval_s()
        recording_mode = self._get_recording_mode()
        save_poll_interval_s(poll_interval_s)
        save_recording_mode(recording_mode)
        save_plc_rack_slot(self._get_plc_rack(), self._get_plc_slot())
        save_plc_db_number(self._get_plc_db_number())
        self._count_gap_hint_shown = False
        self._recording_paused = False
        self.stop_event.clear()
        self.write_thread = threading.Thread(
            target=write_data_to_db,
            args=(
                self._db_path,
                self.plc_backend,
                self._schema.read_length,
                items_for_plc_read(self._schema),
                self._schema,
                self.stop_event,
                self._plc_ip,
                self.plc_lock,
                poll_interval_s,
                self._get_plc_rack(),
                self._get_plc_slot(),
                self._get_plc_db_number(),
                recording_mode,
            ),
            daemon=True,
        )
        self.write_thread.start()
        mode_label = RECORDING_MODE_UI_LABELS.get(
            recording_mode, recording_mode
        )
        self._log(
            f"Aufzeichnung gestartet ({mode_label}, Hintergrund-Thread, Abfrage alle "
            f"{poll_interval_ms_from_s(poll_interval_s)} ms)."
        )
        self._set_connected_ui(True)

    def _tick_recording_indicator(self: S7PyAppProtocol) -> None:
        """Aktualisiert den blinkenden REC-Indikator und startet sich selbst neu."""
        try:
            alive = (
                self.write_thread is not None and self.write_thread.is_alive()
            )
            if alive:
                glyph = RECORDING_GLYPHS[self._recording_phase % len(RECORDING_GLYPHS)]
                self._recording_phase += 1
                self.var_recording.set(f"REC {glyph}")
            else:
                if self.write_thread is not None and self.stop_event.is_set():
                    self.write_thread = None
                    self._log("Worker-Thread hat sich beendet.")
                    if self._reconnecting:
                        self._set_connection_lost_ui()
                    else:
                        self._set_connected_ui(
                            self.plc_backend.is_connected(self.plc_lock)
                        )
                self._recording_phase = 0
                self.var_recording.set("")
        finally:
            if self.winfo_exists():
                self.after(RECORDING_TICK_MS, self._tick_recording_indicator)
