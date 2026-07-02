#!/usr/bin/env bash
# Baut s7py.app mit PyInstaller (standalone, ohne Terminal/venv).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -f ../.venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source ../.venv/bin/activate
elif [[ -f .venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
else
    echo "Keine venv gefunden. Bitte ../setup-s7py.sh oder ./setup.sh ausfuehren."
    exit 1
fi

python -m pip install --upgrade pip
pip install -e ".[build]"

ICON_PNG="${ROOT}/assets/s7py-robot-icon.png"
ICON_ICNS="${ROOT}/assets/s7py.icns"
if [[ -f "${ICON_PNG}" ]]; then
    ICONSET="$(mktemp -d /tmp/s7py-pyi-icon-XXXXXX).iconset"
    cleanup_iconset() { rm -rf "${ICONSET%.iconset}" "${ICONSET}" 2>/dev/null || true; }
    trap cleanup_iconset EXIT
    for size in 16 32 128 256 512; do
        sips -z "${size}" "${size}" "${ICON_PNG}" --out "${ICONSET}/icon_${size}x${size}.png" >/dev/null
        sips -z $((size * 2)) $((size * 2)) "${ICON_PNG}" --out "${ICONSET}/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "${ICONSET}" -o "${ICON_ICNS}"
fi

pyinstaller --noconfirm --clean s7py-macos.spec

APP="${ROOT}/dist/s7py.app"
if [[ -d "${APP}" ]]; then
    xattr -cr "${APP}" 2>/dev/null || true
    echo ""
    echo "Build fertig:"
    echo "  ${APP}"
    echo ""
    echo "Daten (Config, SQLite, Log): ~/Library/Application Support/s7py/"
    echo "Hinweis: python-snap7 3.0 ist reines Python — keine libsnap7 noetig."
    echo "Netzwerkzugriff auf die SPS (Port 102) muss auf dem Ziel-Mac moeglich sein."
else
    echo "Abbruch: ${APP} wurde nicht erstellt."
    exit 1
fi
