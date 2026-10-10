"""Diagramm-Logik fuer ``S7PyApp`` (Mixin).

Enthaelt Aufbau der Plotflaeche, Kurvenauswahl, Ein-/Zwei-Achsen-Layout,
inkrementelles Nachladen und das periodische Diagramm-Update. Alle Methoden
greifen auf Attribute zu, die ``S7PyApp`` bereitstellt (z. B. ``self.fig``,
``self._schema``, ``self._plot_lines``).
"""

import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from s7py.charts import (
    ensure_min_yrange,
    fetch_chart_rows_initial,
    fetch_chart_rows_since,
    invalidate_table_columns_cache,
    plottable_numeric_fields,
)
from s7py.ui_base import S7PyAppProtocol
from s7py.constants import (
    APP_DIR,
    MARKER_AUTO_OFF_THRESHOLD,
    MAX_PLOT_REFRESH_MS,
    MIN_PLOT_REFRESH_MS,
    PLOT_FIG_DPI,
    PLOT_FIG_SIZE_IN,
    PLOT_LINE_COLORS,
    PLOT_MAX_ROWS_DEFAULT,
    PLOT_MIN_YRANGE,
    TIMESTAMP_FORMAT_FILE,
)
from s7py.db import normalize_plot_refresh_ms
from s7py.ui_flow import center_toplevel_on_parent

# Ab dieser Anzahl plotbarer Felder: Button+Dialog statt Inline-Checkboxen.
_PLOT_INLINE_CHECKBOX_LIMIT = 6


class _StableNavigationToolbar(NavigationToolbar2Tk):
    """Toolbar mit Koordinaten-Anzeige, aber ohne Layout-Spruenge.

    Matplotlib liefert beim Ueberfahren oft mehrzeilige ``format_coord``-Texte
    (z. B. bei zwei Y-Achsen). Die werden zu einer Zeile zusammengefasst, damit
    die Toolbar nicht hoeher wird und die Meldungsbox nicht mitwandert.
    """

    def set_message(self, s: str) -> None:
        if s:
            s = " ".join(str(s).split())
            if len(s) > 140:
                s = s[:137] + "..."
        super().set_message(s)


class PlotMixin:
    """Diagramm-Aufbau und -Aktualisierung."""

    def _build_plot_area(self: S7PyAppProtocol) -> None:
        plot_frame = ttk.Frame(self)
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        self.fig = Figure(
            figsize=PLOT_FIG_SIZE_IN, dpi=PLOT_FIG_DPI, layout="constrained"
        )
        self.ax_plot = self.fig.add_subplot(1, 1, 1)
        self.ax_plot_right = None
        self.ax_plot.set_title("Messwerte (aus SQLite)")
        self.ax_plot.set_xlabel("Zeit")
        self.ax_plot.set_ylabel("Wert")
        xfmt = mdates.DateFormatter("%Y-%m-%d\n%H:%M:%S")
        self.ax_plot.xaxis.set_major_formatter(xfmt)

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.mpl_toolbar = _StableNavigationToolbar(self.canvas, plot_frame)
        self.mpl_toolbar.update()
        self._plot_lines = {}

    def _clear_plot_display(self: S7PyAppProtocol) -> None:
        """Leert die sichtbaren Kurven und setzt die Achsen zurueck."""
        for line in self._plot_lines.values():
            line.set_data([], [])
        self.ax_plot.relim()
        self.ax_plot.autoscale_view()
        if self.ax_plot_right is not None:
            self.ax_plot_right.relim()
            self.ax_plot_right.autoscale_view()
        self.canvas.draw_idle()

    def _remove_right_axis(self: S7PyAppProtocol) -> None:
        """Entfernt die rechte Y-Achse und Kurven, die darauf liegen."""
        if self.ax_plot_right is None:
            return
        for name in list(self._plot_lines):
            if self._plot_lines[name].axes is self.ax_plot_right:
                self._plot_lines[name].remove()
                del self._plot_lines[name]
        self.ax_plot_right.remove()
        self.ax_plot_right = None

    def _ensure_right_axis(self: S7PyAppProtocol):
        if self.ax_plot_right is None:
            self.ax_plot_right = self.ax_plot.twinx()
        return self.ax_plot_right

    def _plot_color_for_field(self: S7PyAppProtocol, name: str, selected: list[str]) -> str:
        if len(selected) == 2:
            if name == selected[0]:
                return PLOT_LINE_COLORS[0]
            if name == selected[1]:
                return PLOT_LINE_COLORS[1]
        plottable = plottable_numeric_fields(self._schema)
        idx = plottable.index(name) if name in plottable else 0
        return PLOT_LINE_COLORS[idx % len(PLOT_LINE_COLORS)]

    def _axis_for_field(self: S7PyAppProtocol, name: str, selected: list[str]):
        if len(selected) == 2 and name == selected[1]:
            return self._ensure_right_axis()
        return self.ax_plot

    def _ensure_line_on_axis(self: S7PyAppProtocol, name: str, axis, selected: list[str]) -> None:
        color = self._plot_color_for_field(name, selected)
        marker = "o" if self._markers_on else "None"
        label = name if name in selected else "_nolegend_"
        existing = self._plot_lines.get(name)
        if existing is not None and existing.axes is axis:
            existing.set_label(label)
            existing.set_color(color)
            return
        if existing is not None:
            existing.remove()
        line, = axis.plot(
            [],
            [],
            linestyle="-",
            marker=marker,
            color=color,
            markersize=2,
            markerfacecolor="red",
            markeredgecolor="black",
            lw=1,
            label=label,
        )
        self._plot_lines[name] = line

    def _style_dual_axis_labels(self: S7PyAppProtocol, left_field: str, right_field: str) -> None:
        left_color = PLOT_LINE_COLORS[0]
        right_color = PLOT_LINE_COLORS[1]
        self.ax_plot.set_ylabel(left_field)
        self.ax_plot.yaxis.label.set_color(left_color)
        self.ax_plot.spines["left"].set_color(left_color)
        self.ax_plot.tick_params(axis="y", colors=left_color)
        right_ax = self.ax_plot_right
        right_ax.set_ylabel(right_field)
        right_ax.yaxis.label.set_color(right_color)
        right_ax.spines["right"].set_color(right_color)
        right_ax.tick_params(axis="y", colors=right_color)

    def _reset_left_axis_style(self: S7PyAppProtocol) -> None:
        self.ax_plot.yaxis.label.set_color("black")
        self.ax_plot.spines["left"].set_color("black")
        self.ax_plot.tick_params(axis="y", colors="black")

    def _update_plot_legend(self: S7PyAppProtocol) -> None:
        """Legende nur fuer sichtbare, ausgewaehlte Kurven (kein _nolegend_)."""
        selected = set(self._get_selected_plot_fields())
        handles: list[object] = []
        labels: list[str] = []
        for name in plottable_numeric_fields(self._schema):
            line = self._plot_lines.get(name)
            if line is None or name not in selected:
                continue
            if not line.get_visible():
                continue
            label = line.get_label()
            if not label or str(label).startswith("_"):
                continue
            handles.append(line)
            labels.append(str(label))
        legend = self.ax_plot.get_legend()
        if handles:
            if legend is not None:
                legend.remove()
            self.ax_plot.legend(handles, labels, loc="upper left", fontsize=8)
        elif legend is not None:
            legend.remove()

    def _sync_dual_axis_layout(self: S7PyAppProtocol, selected: list[str] | None = None) -> None:
        """Bei genau zwei Kurven: linke/rechte Y-Achse mit passender Skalierung."""
        if selected is None:
            selected = self._get_selected_plot_fields()

        if len(selected) != 2:
            self._remove_right_axis()
            self._reset_left_axis_style()
            if len(selected) == 1:
                self.ax_plot.set_ylabel(selected[0])
            else:
                self.ax_plot.set_ylabel("Wert")
            for name in plottable_numeric_fields(self._schema):
                self._ensure_line_on_axis(name, self.ax_plot, selected)
            self._update_plot_legend()
            return

        left_field, right_field = selected
        self._ensure_right_axis()
        self._style_dual_axis_labels(left_field, right_field)
        for name in plottable_numeric_fields(self._schema):
            self._ensure_line_on_axis(
                name, self._axis_for_field(name, selected), selected
            )
        self._update_plot_legend()

    def _clear_plot_cache(self: S7PyAppProtocol) -> None:
        invalidate_table_columns_cache()
        self._plot_cache_scope = None
        self._plot_cache_rows = []
        if not self._markers_on:
            for line in self._plot_lines.values():
                line.set_marker("o")
            self._markers_on = True
        self._clear_plot_display()

    def _get_selected_plot_fields(self: S7PyAppProtocol) -> list[str]:
        return [
            name
            for name in plottable_numeric_fields(self._schema)
            if self._plot_field_vars.get(name) is not None
            and self._plot_field_vars[name].get()
        ]

    def _plot_fields_button_text(self: S7PyAppProtocol) -> str:
        plottable = plottable_numeric_fields(self._schema)
        selected = self._get_selected_plot_fields()
        return f"Kurven … ({len(selected)}/{len(plottable)})"

    def _update_plot_fields_button(self: S7PyAppProtocol) -> None:
        btn = getattr(self, "_plot_fields_button", None)
        if btn is not None:
            btn.configure(text=self._plot_fields_button_text())

    def _rebuild_plot_field_checkboxes(self: S7PyAppProtocol) -> None:
        self.plot_field_checks_frame.clear()
        self._plot_field_vars.clear()
        self._plot_fields_button = None

        plottable = plottable_numeric_fields(self._schema)
        use_dialog = len(plottable) >= _PLOT_INLINE_CHECKBOX_LIMIT
        # Gespeicherte Kurvenauswahl (Profil / s7py_db.json) hat Vorrang.
        defaults = {name for name in self._schema.plot_fields if name in plottable}
        if not use_dialog and not defaults and plottable:
            defaults = set(plottable[:2])
        # Dialog-Modus: leere plot_fields = bewusst alle aus (nicht Top-2).

        for name in plottable:
            self._plot_field_vars[name] = tk.BooleanVar(value=name in defaults)

        if use_dialog:
            self._plot_fields_button = ttk.Button(
                self.plot_field_checks_frame,
                text=self._plot_fields_button_text(),
                command=self._open_plot_fields_dialog,
            )
            self.plot_field_checks_frame.add(self._plot_fields_button)
        else:
            for name in plottable:
                self.plot_field_checks_frame.add(
                    ttk.Checkbutton(
                        self.plot_field_checks_frame,
                        text=name,
                        variable=self._plot_field_vars[name],
                        command=self._on_plot_field_toggle,
                    )
                )

    def _open_plot_fields_dialog(self: S7PyAppProtocol) -> None:
        """Dialog: Kurven einzeln an-/abwaehlen (bei vielen Variablen)."""
        plottable = plottable_numeric_fields(self._schema)
        if not plottable:
            messagebox.showinfo(
                "Kurven",
                "Keine plotbaren Variablen im aktuellen Schema.",
                parent=self,
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("Kurven auswaehlen")
        dialog.transient(self)
        dialog.grab_set()
        dialog.minsize(360, 420)

        outer = ttk.Frame(dialog, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        ttk.Label(
            outer,
            text=(
                "Nur aktivierte Variablen erscheinen im Diagramm und in der Legende. "
                "Standard bei vielen Variablen: alle aus."
            ),
            wraplength=420,
        ).grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))

        list_host = ttk.Frame(outer)
        list_host.grid(row=1, column=0, sticky=tk.NSEW)
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(0, weight=1)

        canvas = tk.Canvas(list_host, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_host, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _sync_width(event: tk.Event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        canvas.bind("<Configure>", _sync_width)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)

        def on_toggle() -> None:
            self._on_plot_field_toggle()
            self._update_plot_fields_button()

        for name in plottable:
            var = self._plot_field_vars.get(name)
            if var is None:
                var = tk.BooleanVar(value=False)
                self._plot_field_vars[name] = var
            ttk.Checkbutton(
                scroll_frame,
                text=name,
                variable=var,
                command=on_toggle,
            ).pack(anchor=tk.W, pady=1)

        btn_row = ttk.Frame(outer)
        btn_row.grid(row=2, column=0, sticky=tk.EW, pady=(10, 0))

        def set_all(value: bool) -> None:
            for name in plottable:
                var = self._plot_field_vars.get(name)
                if var is not None:
                    var.set(value)
            on_toggle()

        ttk.Button(btn_row, text="Alle an", command=lambda: set_all(True)).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_row, text="Alle aus", command=lambda: set_all(False)).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_row, text="Schliessen", command=dialog.destroy).pack(
            side=tk.RIGHT
        )

        center_toplevel_on_parent(dialog, self, width=440, height=520)

    def _ensure_plot_lines(self: S7PyAppProtocol) -> None:
        plottable = set(plottable_numeric_fields(self._schema))
        for name in list(self._plot_lines):
            if name not in plottable:
                self._plot_lines[name].remove()
                del self._plot_lines[name]
        self._sync_dual_axis_layout()

    def _on_plot_field_toggle(self: S7PyAppProtocol) -> None:
        selected = self._get_selected_plot_fields()
        self._schema.plot_fields = selected
        self._sync_dual_axis_layout()
        self._draw_plot_from_cache()
        self._update_plot_fields_button()

    def _draw_plot_from_cache(self: S7PyAppProtocol) -> None:
        rows = self._plot_cache_rows
        selected = self._get_selected_plot_fields()
        if not rows or not selected:
            self._clear_plot_display()
            # Legende leeren, wenn nichts ausgewaehlt ist.
            for name, line in self._plot_lines.items():
                line.set_label("_nolegend_")
                line.set_visible(False)
            self._update_plot_legend()
            self.canvas.draw_idle()
            return

        self._sync_dual_axis_layout(selected)
        times = [row[1] for row in rows]
        for name, line in self._plot_lines.items():
            if name in selected:
                values = [row[2].get(name) for row in rows]
                line.set_data(times, values)
                line.set_visible(True)
                line.set_label(name)
            else:
                line.set_data([], [])
                line.set_visible(False)
                line.set_label("_nolegend_")

        self.ax_plot.relim()
        self.ax_plot.autoscale_view()
        ensure_min_yrange(self.ax_plot, PLOT_MIN_YRANGE)
        if self.ax_plot_right is not None:
            self.ax_plot_right.relim()
            self.ax_plot_right.autoscale_view()
            ensure_min_yrange(self.ax_plot_right, PLOT_MIN_YRANGE)
        self._update_plot_legend()
        self._update_marker_visibility(len(rows))
        self.canvas.draw_idle()

    def _get_plot_refresh_ms(self: S7PyAppProtocol) -> int:
        return normalize_plot_refresh_ms(self.var_plot_refresh_ms.get())

    def _on_export_plot_png(self: S7PyAppProtocol) -> None:
        """Aktuelles Diagramm als PNG-Datei speichern."""
        if self.cursor_read is not None:
            try:
                self._update_plot_cache_and_draw()
                self.canvas.draw_idle()
            except Exception as exc:
                messagebox.showerror(
                    "PNG-Export",
                    f"Diagramm konnte nicht aktualisiert werden:\n{exc}",
                )
                return

        default_name = (
            "s7py_Diagramm" + datetime.now().strftime(TIMESTAMP_FORMAT_FILE) + ".png"
        )
        initial_dir = os.path.dirname(self._db_path) if self._db_path else str(APP_DIR)
        target = filedialog.asksaveasfilename(
            parent=self,
            title="Diagramm als PNG speichern",
            defaultextension=".png",
            initialdir=initial_dir or str(APP_DIR),
            initialfile=default_name,
            filetypes=[("PNG-Bilder", "*.png"), ("Alle Dateien", "*.*")],
        )
        if not target:
            return
        try:
            self.fig.savefig(target, dpi=PLOT_FIG_DPI, bbox_inches="tight")
        except OSError as exc:
            messagebox.showerror("PNG-Export", f"Speichern fehlgeschlagen:\n{exc}")
            self._log(f"PNG-Export fehlgeschlagen: {exc}")
            return
        self._log(f"Diagramm exportiert: {target}")
        messagebox.showinfo("PNG-Export", f"Diagramm gespeichert:\n{target}")

    def _sync_plot_scope_widgets(self: S7PyAppProtocol) -> None:
        if self.var_plot_scope.get() == "all":
            self.spin_plot_limit.configure(state="disabled")
        else:
            self.spin_plot_limit.configure(state="normal")

    def _get_plot_fetch_limit(self: S7PyAppProtocol):
        """None = alle Zeilen; sonst positive Ganzzahl fuer LIMIT."""
        if self.var_plot_scope.get() == "all":
            return None
        try:
            n = int(self.var_plot_limit.get())
        except (ValueError, tk.TclError):
            n = PLOT_MAX_ROWS_DEFAULT
        return max(1, n)

    def _refresh_plots(self: S7PyAppProtocol) -> None:
        if self.winfo_exists():
            if self.cursor_read is not None:
                try:
                    self._update_plot_cache_and_draw()
                except Exception as exc:
                    self._log(f"Plot-Update: {exc}")
            self.after(self._get_plot_refresh_ms(), self._refresh_plots)

    def _update_plot_cache_and_draw(self: S7PyAppProtocol) -> None:
        """Inkrementelles Diagramm-Update.
        Bei unveraendertem Scope werden nur neue Zeilen seit der letzten id nachgeladen.
        """
        limit = self._get_plot_fetch_limit()
        scope_key = ("all",) if limit is None else ("limit", int(limit))
        data_changed = False

        if scope_key != self._plot_cache_scope:
            self._plot_cache_rows = fetch_chart_rows_initial(
                self.cursor_read, self._schema, last_n=limit
            )
            self._plot_cache_scope = scope_key
            data_changed = True
        else:
            last_id = self._plot_cache_rows[-1][0] if self._plot_cache_rows else 0
            new_rows = fetch_chart_rows_since(self.cursor_read, last_id, self._schema)
            if new_rows:
                self._plot_cache_rows.extend(new_rows)
                if limit is not None and len(self._plot_cache_rows) > limit:
                    self._plot_cache_rows = self._plot_cache_rows[-limit:]
                data_changed = True

        if not data_changed:
            return

        rows = self._plot_cache_rows
        if not rows:
            self._clear_plot_display()
            return
        self._draw_plot_from_cache()

    def _update_marker_visibility(self: S7PyAppProtocol, n_points: int) -> None:
        """Schaltet Marker bei sehr grossen Datenmengen ab — sonst bremsen die
        Tausende Marker das Zeichnen spuerbar (siehe G-1).
        """
        markers_on = n_points <= MARKER_AUTO_OFF_THRESHOLD
        if markers_on == self._markers_on:
            return
        marker = "o" if markers_on else "None"
        for line in self._plot_lines.values():
            line.set_marker(marker)
        self._markers_on = markers_on
        self._log(
            "Diagramm: Marker " + ("an" if markers_on else "aus")
            + f" ({n_points} Punkte, Schwelle {MARKER_AUTO_OFF_THRESHOLD})"
        )
