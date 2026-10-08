"""Datenbank- und CSV-Export-Logik fuer ``S7PyApp`` (Mixin).

Oeffnet/erstellt SQLite-Datenbanken fuer Diagramm und Aufzeichnung, laesst
Migrationen mitlaufen und exportiert die Tabelle ``projects`` als CSV.
"""

import csv
import os
import sqlite3
import tkinter as tk
from datetime import datetime
from sqlite3 import Error
from tkinter import filedialog, messagebox, ttk

from s7py.charts import invalidate_table_columns_cache
from s7py.ui_base import S7PyAppProtocol
from s7py.ui_flow import (
    capture_window_geometry,
    center_toplevel_on_parent,
    restore_window_geometry,
)
from s7py.constants import (
    APP_DIR,
    PLOT_MAX_ROWS_DEFAULT,
    TABLE_VIEW_ALL_CONFIRM_ROWS,
    TIMESTAMP_FORMAT_FILE,
    WINDOW_ID_DB_TABLE,
)
from s7py.db import (
    clear_projects_table,
    create_connection,
    create_database,
    csv_export_columns,
    default_db_path_for_transport,
    fetch_projects_for_csv,
    fetch_projects_stats,
    format_projects_stats_suffix,
    load_window_geometry,
    migrate_database,
    projects_row_count,
    resolve_csv_export_columns,
    resolve_db_path,
    normalize_db_path,
    save_last_db_path,
    save_window_geometry,
    trim_projects_keep_last,
    vacuum_sqlite_database,
)


class DatabaseMixin:
    """SQLite-Anbindung und CSV-Export."""

    def _resolve_active_db_path(self: S7PyAppProtocol) -> str:
        raw = self.var_db.get().strip() or self._db_path or default_db_path_for_transport()
        return resolve_db_path(normalize_db_path(raw))

    def _on_db_path_focus_out(self: S7PyAppProtocol, _event: object = None) -> None:
        raw = self.var_db.get().strip()
        if not raw:
            return
        normalized = normalize_db_path(raw)
        if normalized != raw:
            self.var_db.set(resolve_db_path(normalized))

    def _format_table_cell(self: S7PyAppProtocol, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    def _is_recording_active(self: S7PyAppProtocol) -> bool:
        return self.write_thread is not None and self.write_thread.is_alive()

    def _refresh_db_stats(self: S7PyAppProtocol) -> None:
        if self.cursor_read is None:
            self._db_stats = None
            return
        self._db_stats = fetch_projects_stats(self.cursor_read, self._db_path)

    def _db_stats_suffix(self: S7PyAppProtocol) -> str:
        if not self._db_stats:
            return ""
        return format_projects_stats_suffix(self._db_stats)

    def _ask_csv_export_options(self: S7PyAppProtocol) -> dict | None:
        """Modaler Dialog fuer CSV-Exportfilter. None = Abbruch."""
        dialog = tk.Toplevel(self)
        dialog.title("CSV-Export — Filter")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Zeilen:").grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        scope_var = tk.StringVar(value="all")
        scopes = ttk.Frame(frame)
        scopes.grid(row=0, column=1, sticky=tk.W, pady=(0, 6))
        ttk.Radiobutton(scopes, text="Alle", variable=scope_var, value="all").pack(
            anchor=tk.W
        )
        last_row = ttk.Frame(scopes)
        last_row.pack(anchor=tk.W)
        ttk.Radiobutton(
            last_row, text="Letzte", variable=scope_var, value="last_n"
        ).pack(side=tk.LEFT)
        last_n_var = tk.IntVar(value=min(1000, int(self.var_plot_limit.get())))
        ttk.Spinbox(last_row, from_=1, to=99_999_999, width=8, textvariable=last_n_var).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        plot_row = ttk.Frame(scopes)
        plot_row.pack(anchor=tk.W)
        plot_limit = self._get_plot_fetch_limit()
        plot_label = (
            f"Diagramm-Limit ({plot_limit} Zeilen)"
            if plot_limit is not None
            else "Diagramm (gesamte DB)"
        )
        ttk.Radiobutton(
            plot_row, text=plot_label, variable=scope_var, value="plot_limit"
        ).pack(anchor=tk.W)

        ttk.Label(frame, text="Spalten:").grid(row=1, column=0, sticky=tk.NW, pady=(0, 6))
        cols_var = tk.StringVar(value="all")
        cols_frame = ttk.Frame(frame)
        cols_frame.grid(row=1, column=1, sticky=tk.W, pady=(0, 6))
        ttk.Radiobutton(
            cols_frame, text="Alle Spalten", variable=cols_var, value="all"
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            cols_frame,
            text="Nur ausgewaehlte Kurven (+ id, time)",
            variable=cols_var,
            value="selected",
        ).pack(anchor=tk.W)

        result: dict = {}

        def on_ok() -> None:
            scope = scope_var.get()
            if scope not in {"all", "last_n", "plot_limit"}:
                scope = "all"
            try:
                last_n = max(1, int(last_n_var.get()))
            except (ValueError, tk.TclError):
                last_n = PLOT_MAX_ROWS_DEFAULT
            if scope == "plot_limit":
                limit = self._get_plot_fetch_limit()
                if limit is None:
                    scope = "all"
                else:
                    last_n = limit
            selected = None
            if cols_var.get() == "selected":
                selected = self._get_selected_plot_fields()
            result.update(
                {
                    "scope": scope,
                    "last_n": last_n,
                    "selected_fields": selected,
                }
            )
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))
        ttk.Button(buttons, text="Abbrechen", command=on_cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Exportieren...", command=on_ok).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        dialog.bind("<Escape>", lambda _e: on_cancel())
        center_toplevel_on_parent(dialog, self)
        self.wait_window(dialog)
        return result or None

    def _ask_db_maintenance_options(self: S7PyAppProtocol) -> dict | None:
        """Dialog fuer DB-Wartung. None = Abbruch."""
        rows = 0
        if self.cursor_read is not None:
            try:
                rows = projects_row_count(self.cursor_read)
            except sqlite3.Error:
                rows = 0

        dialog = tk.Toplevel(self)
        dialog.title("Datenbank warten")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=f"Aktuell {rows} Messpunkt(e) in der Datenbank.",
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        action_var = tk.StringVar(value="keep_last")
        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        keep_row = ttk.Frame(actions)
        keep_row.pack(anchor=tk.W)
        ttk.Radiobutton(
            keep_row, text="Letzte", variable=action_var, value="keep_last"
        ).pack(side=tk.LEFT)
        keep_n_var = tk.IntVar(value=min(1000, max(1, int(self.var_plot_limit.get()))))
        ttk.Spinbox(keep_row, from_=1, to=99_999_999, width=8, textvariable=keep_n_var).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Label(keep_row, text="Messpunkte behalten").pack(side=tk.LEFT, padx=(4, 0))

        ttk.Radiobutton(
            actions,
            text="Alle Messpunkte loeschen",
            variable=action_var,
            value="clear_all",
        ).pack(anchor=tk.W)

        vacuum_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="Anschliessend VACUUM (Dateigroesse reduzieren)",
            variable=vacuum_var,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        result: dict = {}

        def on_ok() -> None:
            action = action_var.get()
            if action not in {"keep_last", "clear_all"}:
                action = "keep_last"
            try:
                keep_n = max(1, int(keep_n_var.get()))
            except (ValueError, tk.TclError):
                keep_n = PLOT_MAX_ROWS_DEFAULT
            result.update(
                {
                    "action": action,
                    "keep_n": keep_n,
                    "vacuum": bool(vacuum_var.get()),
                }
            )
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky=tk.E)
        ttk.Button(buttons, text="Abbrechen", command=on_cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Ausfuehren", command=on_ok).pack(side=tk.RIGHT, padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        dialog.bind("<Escape>", lambda _e: on_cancel())
        center_toplevel_on_parent(dialog, self)
        self.wait_window(dialog)
        return result or None

    def _on_db_maintenance(self: S7PyAppProtocol) -> None:
        """Messpunkte kuerzen, loeschen oder Datenbank komprimieren."""
        if self._is_recording_active():
            messagebox.showwarning(
                "Datenbank warten",
                "Bitte zuerst die Aufzeichnung pausieren, bevor die "
                "Datenbank bearbeitet wird.",
            )
            return

        db_path = self._resolve_active_db_path()
        if not os.path.isfile(db_path):
            messagebox.showerror(
                "Datenbank warten",
                f"Datenbank nicht gefunden:\n{db_path}",
            )
            return

        options = self._ask_db_maintenance_options()
        if not options:
            return

        action = str(options.get("action", "keep_last"))
        if action == "clear_all":
            if not messagebox.askyesno(
                "Datenbank warten",
                "Alle Messpunkte unwiderruflich loeschen?",
                icon="warning",
            ):
                return

        if self.conn_read is not None:
            try:
                self.conn_read.close()
            except Error:
                pass
            self.conn_read = None
            self.cursor_read = None

        deleted = 0
        try:
            conn = create_connection(db_path)
            if conn is None:
                raise sqlite3.Error("Verbindung fehlgeschlagen")
            cursor = conn.cursor()
            if action == "clear_all":
                deleted = clear_projects_table(cursor, conn)
            else:
                deleted = trim_projects_keep_last(
                    cursor, conn, int(options.get("keep_n", 0) or 0)
                )
            conn.close()
            if options.get("vacuum"):
                vacuum_sqlite_database(db_path)
        except sqlite3.Error as exc:
            messagebox.showerror("Datenbank warten", f"Wartung fehlgeschlagen:\n{exc}")
            self._log(f"DB-Wartung fehlgeschlagen: {exc}")
            self._attach_database(db_path, create_if_missing=False, silent=True)
            return

        invalidate_table_columns_cache()
        self._attach_database(db_path, create_if_missing=False, silent=True)
        self._refresh_status_display()

        if action == "clear_all":
            self._log(f"DB-Wartung: {deleted} Messpunkt(e) geloescht.")
            msg = f"{deleted} Messpunkt(e) geloescht."
        else:
            self._log(
                f"DB-Wartung: {deleted} aeltere Messpunkt(e) entfernt, "
                f"letzte {int(options.get('keep_n', 0))} behalten."
            )
            msg = f"{deleted} Messpunkt(e) entfernt."
        if options.get("vacuum"):
            msg += "\nVACUUM ausgefuehrt."
        messagebox.showinfo("Datenbank warten", msg)

    def _attach_database(
        self: S7PyAppProtocol,
        db_path: str,
        *,
        create_if_missing: bool = False,
        silent: bool = False,
    ) -> bool:
        """SQLite-DB fuer Diagramm und Aufzeichnung oeffnen.

        Bestehende Dateien werden geoeffnet (Migrationen laufen mit).
        Fehlt die Datei und ``create_if_missing`` ist gesetzt, wird sie neu
        angelegt (inkl. uebergeordnetem Verzeichnis) und anschliessend geladen.
        """
        db_path = normalize_db_path(db_path.strip())
        if not db_path:
            if not silent:
                messagebox.showerror("Datenbank", "Kein Datenbankpfad angegeben.")
            return False

        db_path = resolve_db_path(db_path)
        is_new = not os.path.isfile(db_path)

        if is_new:
            if not create_if_missing:
                if not silent:
                    messagebox.showerror(
                        "Datenbank",
                        f"Datei nicht gefunden:\n{db_path}",
                    )
                return False
            parent = os.path.dirname(db_path)
            if parent:
                try:
                    os.makedirs(parent, exist_ok=True)
                except OSError as exc:
                    if not silent:
                        messagebox.showerror(
                            "Datenbank",
                            f"Verzeichnis konnte nicht angelegt werden:\n{exc}",
                        )
                    return False
            if not create_database(db_path, self._schema):
                if not silent:
                    messagebox.showerror(
                        "Datenbank",
                        f"Datenbank konnte nicht angelegt werden:\n{db_path}",
                    )
                return False
        else:
            conn_migrate = create_connection(db_path)
            if conn_migrate is not None:
                migrate_database(conn_migrate, self._schema)
                conn_migrate.close()

        if self.conn_read is not None:
            try:
                self.conn_read.close()
            except Error:
                pass
            self.conn_read = None
            self.cursor_read = None

        self.conn_read = create_connection(db_path)
        if self.conn_read is None:
            if not silent:
                messagebox.showerror("Datenbank", "SQLite-Verbindung fehlgeschlagen.")
            return False

        self.cursor_read = self.conn_read.cursor()
        self._db_path = db_path
        self.var_db.set(db_path)
        self._clear_plot_cache()
        save_last_db_path(db_path)

        if is_new and not silent:
            self._log(f"Neue Datenbank angelegt und geladen: {db_path}")

        self._refresh_db_stats()
        if self.cursor_read is not None:
            try:
                self._update_plot_cache_and_draw()
                self.canvas.draw_idle()
            except Exception as exc:
                if not silent:
                    self._log(f"Diagramm nach DB-Laden: {exc}")

        return True

    def _on_browse_db(self: S7PyAppProtocol) -> None:
        """Bestehende SQLite-Datei oeffnen (kein Ueberschreiben-Dialog)."""
        current = self._resolve_active_db_path()
        initial_dir = os.path.dirname(current) or str(APP_DIR)
        initial_file = os.path.basename(current) or "s7py.db"
        path = filedialog.askopenfilename(
            parent=self,
            title="SQLite-Datenbank oeffnen",
            initialdir=initial_dir,
            initialfile=initial_file,
            filetypes=[
                ("SQLite-Datenbanken", "*.db *.sqlite *.sqlite3"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not path:
            return
        if self._attach_database(path, create_if_missing=False):
            self._log(f"Datenbank geoeffnet: {path}")
            self._refresh_status_display()

    def _on_export_csv(self: S7PyAppProtocol) -> None:
        """Exportiert die Tabelle ``projects`` als CSV mit Filterdialog."""
        options = self._ask_csv_export_options()
        if not options:
            return

        db_path = self._resolve_active_db_path()
        if not os.path.isfile(db_path):
            messagebox.showerror(
                "CSV-Export",
                f"Datenbank nicht gefunden:\n{db_path}",
            )
            return

        default_name = (
            os.path.splitext(os.path.basename(db_path))[0]
            + datetime.now().strftime(TIMESTAMP_FORMAT_FILE)
            + ".csv"
        )
        target = filedialog.asksaveasfilename(
            parent=self,
            title="CSV-Export — Zieldatei",
            defaultextension=".csv",
            initialdir=os.path.dirname(db_path) or str(APP_DIR),
            initialfile=default_name,
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if not target:
            return

        owns_conn = False
        conn = self.conn_read
        if conn is None:
            try:
                conn = sqlite3.connect(
                    f"file:{db_path}?mode=ro", uri=True, check_same_thread=False
                )
                owns_conn = True
            except sqlite3.Error as exc:
                messagebox.showerror("CSV-Export", f"DB konnte nicht geoeffnet werden:\n{exc}")
                return

        export_columns = resolve_csv_export_columns(
            self._schema, options.get("selected_fields")
        )
        try:
            rows = fetch_projects_for_csv(
                conn.cursor(),
                self._schema,
                columns=export_columns,
                scope=str(options.get("scope", "all")),
                limit=int(options.get("last_n", 0) or 0),
            )
            with open(target, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(export_columns)
                writer.writerows(rows)
            rows_written = len(rows)
        except (sqlite3.Error, OSError) as exc:
            messagebox.showerror("CSV-Export", f"Export fehlgeschlagen:\n{exc}")
            self._log(f"CSV-Export fehlgeschlagen: {exc}")
            return
        finally:
            if owns_conn and conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

        self._log(f"CSV-Export: {rows_written} Zeilen nach {target}")
        messagebox.showinfo(
            "CSV-Export",
            f"{rows_written} Zeilen exportiert:\n{target}",
        )

    def _on_open_db_table(self: S7PyAppProtocol) -> None:
        """Oeffnet die SQLite-Daten als Tabelle in einem eigenen Fenster."""
        existing = getattr(self, "_db_table_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except tk.TclError:
                pass

        db_path = self._resolve_active_db_path()
        if not os.path.isfile(db_path):
            messagebox.showerror(
                "Datenbank-Tabelle",
                f"Datenbank nicht gefunden:\n{db_path}",
            )
            return

        win = tk.Toplevel(self)
        self._db_table_window = win
        win.title("s7py — Datenbank-Tabelle")
        win.minsize(640, 320)
        saved = load_window_geometry(WINDOW_ID_DB_TABLE)
        if not restore_window_geometry(win, saved, min_w=640, min_h=320):
            center_toplevel_on_parent(win, self, width=900, height=520)

        def on_close() -> None:
            geometry = capture_window_geometry(win)
            if geometry:
                save_window_geometry(WINDOW_ID_DB_TABLE, geometry)
            self._db_table_window = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

        header = ttk.Frame(win, padding=(8, 8, 8, 0))
        header.pack(fill=tk.X)
        ttk.Label(header, text=db_path, wraplength=900).pack(anchor=tk.W)

        toolbar = ttk.Frame(win, padding=8)
        toolbar.pack(fill=tk.X)

        scope_var = tk.StringVar(value="last_n")
        try:
            default_limit = max(1, int(self.var_plot_limit.get()))
        except (ValueError, tk.TclError):
            default_limit = PLOT_MAX_ROWS_DEFAULT
        limit_var = tk.IntVar(value=default_limit)
        status_var = tk.StringVar(value="")

        ttk.Label(toolbar, text="Anzeige:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Radiobutton(
            toolbar, text="Letzte", variable=scope_var, value="last_n"
        ).pack(side=tk.LEFT)
        ttk.Spinbox(
            toolbar, from_=1, to=99_999_999, width=8, textvariable=limit_var
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(toolbar, text="Zeilen").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(
            toolbar, text="Gesamte Datenbank", variable=scope_var, value="all"
        ).pack(side=tk.LEFT, padx=(0, 12))

        table_frame = ttk.Frame(win, padding=(8, 0, 8, 8))
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(table_frame, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)

        footer = ttk.Frame(win, padding=(8, 0, 8, 8))
        footer.pack(fill=tk.X)
        ttk.Label(footer, textvariable=status_var).pack(side=tk.LEFT)
        ttk.Button(footer, text="Schliessen", command=on_close).pack(side=tk.RIGHT)

        def reload_table() -> None:
            scope = scope_var.get()
            if scope not in {"all", "last_n"}:
                scope = "last_n"
            try:
                limit = max(1, int(limit_var.get()))
            except (ValueError, tk.TclError):
                limit = PLOT_MAX_ROWS_DEFAULT

            if scope == "all":
                try:
                    count_conn = create_connection(db_path)
                    if count_conn is None:
                        raise sqlite3.Error("Verbindung fehlgeschlagen")
                    total = projects_row_count(count_conn.cursor())
                    count_conn.close()
                except sqlite3.Error as exc:
                    messagebox.showerror(
                        "Datenbank-Tabelle",
                        f"Zeilenanzahl konnte nicht ermittelt werden:\n{exc}",
                        parent=win,
                    )
                    return
                if total > TABLE_VIEW_ALL_CONFIRM_ROWS and not messagebox.askyesno(
                    "Datenbank-Tabelle",
                    f"Die Datenbank enthaelt {total} Zeilen. "
                    f"Alle laden kann die Anzeige verzoegern.\n\nTrotzdem fortfahren?",
                    parent=win,
                ):
                    return

            columns = csv_export_columns(self._schema)
            owns_conn = False
            conn = self.conn_read
            if conn is None:
                try:
                    conn = sqlite3.connect(
                        f"file:{db_path}?mode=ro", uri=True, check_same_thread=False
                    )
                    owns_conn = True
                except sqlite3.Error as exc:
                    messagebox.showerror(
                        "Datenbank-Tabelle",
                        f"DB konnte nicht geoeffnet werden:\n{exc}",
                        parent=win,
                    )
                    return

            try:
                rows = fetch_projects_for_csv(
                    conn.cursor(),
                    self._schema,
                    columns=columns,
                    scope=scope,
                    limit=limit if scope == "last_n" else None,
                )
            except sqlite3.Error as exc:
                messagebox.showerror(
                    "Datenbank-Tabelle",
                    f"Daten konnten nicht geladen werden:\n{exc}",
                    parent=win,
                )
                return
            finally:
                if owns_conn and conn is not None:
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass

            tree.delete(*tree.get_children())
            tree["columns"] = columns
            for col in columns:
                tree.heading(col, text=col, anchor=tk.W)
                width = 160 if col == "time" else 90
                if col == "id":
                    width = 50
                tree.column(col, width=width, minwidth=48, stretch=tk.YES, anchor=tk.W)

            for row in rows:
                tree.insert(
                    "",
                    tk.END,
                    values=[self._format_table_cell(v) for v in row],
                )
            status_var.set(f"{len(rows)} Zeile(n) angezeigt")

        ttk.Button(toolbar, text="Aktualisieren", command=reload_table).pack(side=tk.LEFT)
        reload_table()
        center_toplevel_on_parent(win, self, width=960, height=520)
