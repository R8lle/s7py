"""Hilfs-Widgets fuer responsives Tkinter-Layout."""

import tkinter as tk
from tkinter import ttk

_REFLOW_DEBOUNCE_MS = 80


class FlowFrame(ttk.Frame):
    """Ordnet Kind-Widgets horizontal an und bricht bei Platzmangel um."""

    def __init__(
        self,
        master=None,
        *,
        h_pad: int = 6,
        v_pad: int = 4,
        debounce_ms: int = _REFLOW_DEBOUNCE_MS,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._h_pad = h_pad
        self._v_pad = v_pad
        self._debounce_ms = debounce_ms
        self._items: list[tuple[tk.Widget, int, int]] = []
        self._last_layout: tuple[int, ...] | None = None
        self._reflow_job: str | None = None
        self._reflowing = False
        self.bind("<Configure>", self._on_configure, add="+")

    def add(self, widget: tk.Widget, *, padx: int | None = None) -> tk.Widget:
        """Widget registrieren (statt ``pack``/``grid`` direkt auf dem Frame)."""
        gap = self._h_pad if padx is None else padx
        widget.update_idletasks()
        item_w = widget.winfo_reqwidth() + gap
        self._items.append((widget, gap, item_w))
        self._last_layout = None
        self._schedule_reflow(immediate=True)
        return widget

    def clear(self) -> None:
        """Alle registrierten Widgets entfernen."""
        for widget, _, _ in self._items:
            widget.grid_forget()
            widget.destroy()
        self._items.clear()
        self._last_layout = None

    def _on_configure(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        self._schedule_reflow()

    def _schedule_reflow(self, *, immediate: bool = False) -> None:
        if self._reflow_job is not None:
            self.after_cancel(self._reflow_job)
            self._reflow_job = None
        if immediate or self._debounce_ms <= 0:
            self._reflow_job = self.after_idle(self._reflow)
        else:
            self._reflow_job = self.after(self._debounce_ms, self._reflow)

    def _layout_for_width(self, width: int) -> tuple[int, ...]:
        rows: list[int] = []
        row = 0
        used = 0
        for _, _gap, item_w in self._items:
            if used > 0 and used + item_w > width:
                row += 1
                used = 0
            rows.append(row)
            used += item_w
        return tuple(rows)

    def _reflow(self) -> None:
        self._reflow_job = None
        if not self.winfo_exists() or not self._items or self._reflowing:
            return

        width = self.winfo_width()
        if width < 2:
            return

        layout = self._layout_for_width(width)
        if layout == self._last_layout:
            return

        self._reflowing = True
        try:
            row_cols: dict[int, int] = {}
            for (widget, gap, _), row in zip(self._items, layout, strict=True):
                col = row_cols.get(row, 0)
                widget.grid(
                    row=row,
                    column=col,
                    sticky=tk.W,
                    padx=(0, gap),
                    pady=(0, self._v_pad if row > 0 else 0),
                )
                row_cols[row] = col + 1

            self._last_layout = layout
        finally:
            self._reflowing = False


def center_toplevel_on_parent(
    window: tk.Toplevel,
    parent: tk.Misc,
    *,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Zentriert ein Dialogfenster ueber dem Elternfenster (sichtbarer Bereich)."""
    window.update_idletasks()
    parent.update_idletasks()
    win_w = width or max(window.winfo_width(), window.winfo_reqwidth())
    win_h = height or max(window.winfo_height(), window.winfo_reqheight())
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    pw = max(parent.winfo_width(), 1)
    ph = max(parent.winfo_height(), 1)
    x = px + max(0, (pw - win_w) // 2)
    y = py + max(0, (ph - win_h) // 2)
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = max(0, min(x, screen_w - win_w))
    y = max(0, min(y, screen_h - win_h))
    window.geometry(f"{win_w}x{win_h}+{x}+{y}")
