"""Gemeinsame Konstanten fuer s7py."""

import os
import sys
from pathlib import Path

from snap7.error import S7Error


def _resolve_app_dir() -> Path:
    """Schreibbares App-Verzeichnis (Config, DB, Log).

    Entwicklung: ``s7py/`` neben dem Paket. Gebuendelt (PyInstaller): nutzer-
    spezifisches Datenverzeichnis, damit keine Schreibrechte im .app-Bundle noetig sind.
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            data_dir = Path.home() / "Library" / "Application Support" / "s7py"
        elif os.name == "nt":
            data_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "s7py"
        else:
            data_dir = Path.home() / ".config" / "s7py"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    return Path(__file__).resolve().parent.parent


# Verzeichnis fuer Konfiguration, SQLite und Logdatei.
APP_DIR = _resolve_app_dir()

TIMESTAMP_FORMAT_DB = "%Y-%m-%d %H:%M:%S"
TIMESTAMP_FORMAT_LOG = "%H:%M:%S"
TIMESTAMP_FORMAT_FILE = "_%Y%m%d_%H%M%S"

# Rotierende Diagnose-Logdatei (siehe I-3 in der Code-Analyse).
LOG_FILE_PATH = str(APP_DIR / "s7py.log")
LOG_FILE_MAX_BYTES = 1_000_000
LOG_FILE_BACKUP_COUNT = 5

DEFAULT_DB_LAYOUT = """\
Count\tDWord\t0.0
Temperature\tReal\t4.0
DistanceOverAll\tReal\t8.0
CyclesOverAll\tDWord\t12.0
MotorCurrent\tReal\t16.0
DB_String\tString\t20.0
"""

PLC_DB_NUMBER = 30
PLC_RACK = 0
PLC_SLOT = 0
DEFAULT_POLL_INTERVAL_S = 0.1
MIN_POLL_INTERVAL_S = 0.01
MAX_POLL_INTERVAL_S = 10.0
PLC_READ_MAX_ATTEMPTS = 6
PLC_READ_BASE_DELAY_S = 0.2
SQLITE_WRITE_MAX_ATTEMPTS = 8
SQLITE_WRITE_BASE_DELAY_S = 0.03
DEFAULT_PLC_IP = "192.168.0.1"
PLC_TRANSPORT_SNAP7 = "snap7"
PLC_TRANSPORT_OPCUA = "opcua"
PLC_TRANSPORTS = (PLC_TRANSPORT_SNAP7, PLC_TRANSPORT_OPCUA)
DEFAULT_OPCUA_ENDPOINT = "opc.tcp://127.0.0.1:4840"
# S7-1500 begrenzt Session-Timeout oft auf 30s; asyncua-Standard waere 1h.
OPCUA_SESSION_TIMEOUT_MS = 30_000
TRANSPORT_UI_LABELS: dict[str, str] = {
    PLC_TRANSPORT_SNAP7: "Snap7",
    PLC_TRANSPORT_OPCUA: "OPC UA",
}
TRANSPORT_UI_TO_ID: dict[str, str] = {
    label: key for key, label in TRANSPORT_UI_LABELS.items()
}
WINDOW_MIN_WIDTH = 720
MACOS_MENU_BAR_HEIGHT = 30
MACOS_DOCK_HEIGHT = 80

# Erwartbare Fehler bei SPS-I/O (Lesen, Verbinden, Trennen).
# Kein breites "except Exception" — Programmierfehler sollen durchfallen.
PLC_IO_ERRORS = (S7Error, OSError, TimeoutError, ConnectionError)

DEFAULT_DATABASE = str(APP_DIR / "s7py.db")
DB_CONFIG_PATH = str(APP_DIR / "s7py_db.json")

PLOT_REFRESH_MS = 1000
DEFAULT_PLOT_REFRESH_MS = PLOT_REFRESH_MS
MIN_PLOT_REFRESH_MS = 250
MAX_PLOT_REFRESH_MS = 5000
PLOT_MAX_ROWS_DEFAULT = 3000
# Ab dieser Zeilenanzahl vor dem Laden der gesamten DB im Tabellenfenster nachfragen.
TABLE_VIEW_ALL_CONFIRM_ROWS = 20_000
# Layout-Budget: optimiert fuer 1440x900 Displays (MacBook Air 13" u.a.).
# Bei 1440x900 sind nach macOS-Menueleiste/Dock rund 790 px Hoehe nutzbar.
# Aufteilung (ungefaehr): Top-Bar ~130 + MPL-Toolbar ~35 + Log-Box ~85 +
# Frame-Padding ~30 + Figure ~440 = 720 px → passt mit Reserve.
PLOT_FIG_SIZE_IN = (8.0, 4.4)
PLOT_FIG_DPI = 100
LOG_BOX_LINES = 5
INITIAL_REQ_HEIGHT_FLOOR = 760
INITIAL_MINSIZE_H = 640
# Mindest-Y-Spanne fuer das Diagramm (siehe _ensure_min_yrange).
PLOT_MIN_YRANGE = 1.0
PLOT_LINE_COLORS = (
    "tab:blue",
    "tab:green",
    "tab:red",
    "tab:orange",
    "tab:purple",
    "tab:brown",
    "tab:pink",
    "tab:gray",
    "tab:olive",
    "tab:cyan",
)
LOG_DRAIN_MS = 150
LOG_DRAIN_MAX_PER_TICK = 200
LOG_MAX_LINES = 1000
LOG_TRIM_THRESHOLD = LOG_MAX_LINES + 200
# Manche Linux-Tk-Setups rendern Unicode-Symbole unzuverlaessig (z. B. als "@").
# Daher dort ASCII-Fallbacks fuer Platzhalter und REC-Blinken verwenden.
if sys.platform.startswith("linux"):
    LIVE_LABEL_EMPTY = "-"
else:
    LIVE_LABEL_EMPTY = "\u2014"
WORKER_JOIN_TIMEOUT_S = 12
# Verbindungs-Ueberwachung und Auto-Reconnect (GUI-Ebene).
CONNECTION_WATCH_MS = 3000
DB_STATS_REFRESH_MS = 5000
AUTO_RECONNECT_DEFAULT = True
AUTO_RECONNECT_BASE_DELAY_S = 2.0
AUTO_RECONNECT_MAX_DELAY_S = 30.0
# Bei mehr als so vielen Punkten werden Marker im Diagramm abgeschaltet,
# damit das Zeichnen grosser Datenmengen fluessig bleibt.
MARKER_AUTO_OFF_THRESHOLD = 5000
# Tick-Intervall fuer den blinkenden "Recording"-Indikator.
RECORDING_TICK_MS = 500
if sys.platform.startswith("linux"):
    RECORDING_GLYPHS = ("*", "o")
else:
    RECORDING_GLYPHS = ("\u25CF", "\u25CB")  # ● / ○

# Breite des Start-/Fortsetzen-Buttons (ttk: Zeichen), einheitlich zu „Pausieren“.
RECORDING_START_BUTTON_WIDTH = 12
RECORDING_START_LABEL = "Starten"
RECORDING_RESUME_LABEL = "Fortsetzen"
