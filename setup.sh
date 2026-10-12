#!/usr/bin/env bash
# s7py portable: virtuelle Umgebung anlegen und Abhaengigkeiten installieren.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

MIN_PY=3.11

version_ge() {
    python3 - "$MIN_PY" <<'PY'
import sys
need = tuple(int(x) for x in sys.argv[1].split("."))
ver = sys.version_info[: len(need)]
sys.exit(0 if ver >= need else 1)
PY
}

if ! command -v python3 >/dev/null 2>&1; then
    echo "Fehler: python3 nicht gefunden."
    echo "Bitte Python ${MIN_PY}+ installieren (z. B. https://www.python.org/downloads/)."
    exit 1
fi

if ! version_ge; then
    echo "Fehler: Python ${MIN_PY}+ erforderlich, gefunden: $(python3 --version)"
    exit 1
fi

if [[ ! -d .venv ]]; then
    echo "Erstelle virtuelle Umgebung in .venv ..."
    python3 -m venv .venv
else
    echo "Virtuelle Umgebung .venv existiert bereits."
fi

if [[ -f ../.venv/bin/activate ]] && [[ "${S7PY_FORCE_LOCAL_VENV:-}" != "1" ]]; then
    echo ""
    echo "Hinweis: Workspace-venv unter ../.venv gefunden."
    echo "  Empfohlen (eine venv fuer ganz VSC_Snap7):  ../setup-s7py.sh"
    echo "  Lokale s7py/.venv erzwingen:               S7PY_FORCE_LOCAL_VENV=1 ./setup.sh"
    echo ""
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"

echo ""
echo "s7py ist eingerichtet."
echo "  Starten:  ./run.sh"
echo "  Oder:     source .venv/bin/activate  &&  s7py"
echo "  Tests:    ./test.sh"
echo ""
echo "Hinweis: python-snap7 3.0 ist reines Python — keine libsnap7 noetig."
echo "Netzwerkzugriff auf die SPS (Port 102) muss auf dem Ziel-Rechner moeglich sein."
