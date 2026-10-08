"""Selbsttest fuer gebuendelte Windows-/macOS-Pakete (ohne GUI)."""

from __future__ import annotations

import traceback
from pathlib import Path


def run_selftest(report_path: str | Path) -> int:
    """Prueft Imports und Hilfedokumente; schreibt einen Klartext-Bericht.

    Rueckgabe: 0 bei Erfolg, sonst 1. Oeffnet kein Tk-Fenster.
    """
    lines: list[str] = []
    ok = True
    try:
        import matplotlib

        matplotlib.use("Agg")

        from s7py import COPYRIGHT, LICENSE_NAME, __version__
        from s7py.about import build_info, license_text, third_party
        from s7py import help as manual

        lines.append(f"s7py {__version__}")
        lines.append(f"Build: {build_info()}")
        lines.append(f"{COPYRIGHT} – {LICENSE_NAME}")
        lines.append(f"Lizenz: {license_text().splitlines()[0]}")

        import snap7  # noqa: F401
        from s7py.backends import create_backend
        from s7py.db import load_app_config
        from s7py.schema import default_plc_schema

        create_backend("snap7")
        load_app_config()
        default_plc_schema()
        for name in manual.DOCUMENTS:
            text = manual.source(name)
            if not text.strip():
                raise RuntimeError(f"Hilfedokument leer: {name}")
            lines.append(f"Hilfe {name}: {len(text)} Zeichen")

        components = ", ".join(f"{c.name} {c.version}" for c in third_party())
        lines.append(f"Komponenten: {components}")
        lines.append("SELFTEST OK")
    except Exception as exc:  # noqa: BLE001 - Bericht fuer Support
        ok = False
        lines.append(f"SELFTEST FEHLER: {exc}")
        lines.append(traceback.format_exc())

    path = Path(report_path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1
