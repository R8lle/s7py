"""Version, Build, Copyright, Lizenz und Fremdkomponenten (Hilfe → Info und Lizenzen).

Der Build ist der Git-Commit und sein Datum. Ein Installationspaket liest ihn aus
``_build.py`` (geschrieben mit ``python -m s7py.about --stamp``); im Quellbaum
fragt das Modul Git direkt.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from importlib import metadata
from pathlib import Path

from s7py import COPYRIGHT, LICENSE_NAME, __version__

HERE = Path(__file__).resolve().parent


def repo_root() -> Path:
    """Projektroot (Entwicklung) bzw. Bundle-Root (PyInstaller)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return HERE.parent


REPO = repo_root()


@dataclass(frozen=True)
class Build:
    commit: str  # kurzer Hash, "" wenn unbekannt
    date: str  # ISO-Datum des Commits
    modified: bool = False  # uncommittete Aenderungen im Checkout

    def __str__(self) -> str:
        if not self.commit:
            return "unbekannt"
        when = date.fromisoformat(self.date).strftime("%d.%m.%Y") if self.date else ""
        text = self.commit + (f" vom {when}" if when else "")
        if self.modified:
            text += " (mit lokalen Aenderungen)"
        return text


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        timeout=5,
        stdin=subprocess.DEVNULL,
        check=False,
    ).stdout.strip()


def build_info() -> Build:
    try:
        from s7py import _build  # type: ignore[attr-defined]

        return Build(_build.COMMIT, _build.DATE, False)
    except ImportError:
        pass
    if not (REPO / ".git").exists():
        return Build("", "")
    try:
        commit = _git("rev-parse", "--short", "HEAD")
        day = _git("log", "-1", "--format=%cs")
        modified = bool(_git("status", "--porcelain", "--untracked-files=no"))
        return Build(commit, day, modified)
    except (OSError, subprocess.SubprocessError):
        return Build("", "")


def stamp_build() -> Path:
    """Schreibt ``_build.py`` fuer ein Installationspaket (ohne Git-Abhaengigkeit)."""
    build = build_info()
    target = HERE / "_build.py"
    target.write_text(
        f'COMMIT = "{build.commit}"\nDATE = "{build.date}"\n',
        encoding="utf-8",
    )
    return target


def license_text() -> str:
    """Eigener Lizenztext (Repository oder gebuendeltes Paket)."""
    for candidate in (REPO / "LICENSE", HERE.parent / "LICENSE"):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    try:
        dist = metadata.distribution("s7py")
        for file_info in dist.files or []:
            if file_info.name.upper().startswith("LICENSE") and "THIRD" not in file_info.name.upper():
                return file_info.read_text(encoding="utf-8")
    except metadata.PackageNotFoundError:
        pass
    return f"{LICENSE_NAME} – https://opensource.org/licenses/MIT"


def third_party_license_text() -> str:
    for candidate in (
        REPO / "LICENSE_THIRD_PARTY.txt",
        HERE.parent / "LICENSE_THIRD_PARTY.txt",
    ):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return "Siehe LICENSE_THIRD_PARTY.txt im Projektverzeichnis."


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    license: str
    purpose: str
    url: str = ""


def _v(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "–"


def third_party() -> list[Component]:
    components = [
        Component(
            "Python",
            platform.python_version(),
            "PSF-2.0",
            "Laufzeitumgebung",
            "https://www.python.org",
        ),
        Component(
            "Tkinter / Tcl/Tk",
            f"{_tk_version()}",
            "Tcl/Tk License (BSD-artig)",
            "Oberflaeche",
            "https://www.tcl.tk",
        ),
        Component(
            "matplotlib",
            _v("matplotlib"),
            "Matplotlib License (BSD-kompatibel)",
            "Live-Diagramm",
            "https://matplotlib.org",
        ),
        Component(
            "python-snap7",
            _v("python-snap7"),
            "MIT (reine Python-Implementierung)",
            "Snap7 / S7-Kommunikation",
            "https://github.com/gijzelaerr/python-snap7",
        ),
    ]
    asyncua_ver = _v("asyncua")
    if asyncua_ver != "–":
        components.append(
            Component(
                "asyncua",
                asyncua_ver,
                "LGPL-3.0",
                "OPC-UA-Client (optional)",
                "https://github.com/FreeOpcUa/opcua-asyncio",
            )
        )
    return components


def _tk_version() -> str:
    try:
        import tkinter

        return str(tkinter.Tcl().call("info", "patchlevel"))
    except Exception:  # noqa: BLE001 - nur Anzeige
        return "–"


def system_info() -> str:
    """Klartext fuer Support („Angaben kopieren“)."""
    return "\n".join(
        [
            f"s7py {__version__}",
            f"Build: {build_info()}",
            f"{COPYRIGHT} – {LICENSE_NAME}",
            f"System: {platform.system()} {platform.release()} ({platform.machine()})",
            f"Python {platform.python_version()}",
            "Komponenten: "
            + "; ".join(f"{c.name} {c.version}" for c in third_party()),
        ]
    )


if __name__ == "__main__":
    if "--stamp" in sys.argv:
        print(stamp_build())
    else:
        print(system_info())
