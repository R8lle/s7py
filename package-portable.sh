#!/usr/bin/env bash
# Erzeugt ein ZIP-Archiv zum Kopieren auf einen anderen Mac (ohne .venv).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

NAME="s7py-portable"
STAMP="$(date +%Y%m%d)"
OUT_DIR="${ROOT}/dist"
ARCHIVE="${OUT_DIR}/${NAME}-${STAMP}.zip"

mkdir -p "$OUT_DIR"

zip -r "$ARCHIVE" . \
    -x '*.venv/*' \
    -x '.venv/*' \
    -x '*/__pycache__/*' \
    -x '__pycache__/*' \
    -x '*.pyc' \
    -x 'dist/*' \
    -x '*.log' \
    -x 's7py_db.json' \
    -x '*.db' \
    -x '*.db-wal' \
    -x '*.db-shm' \
    -x '.DS_Store' \
    -x '*/.DS_Store'

echo ""
echo "Portable Paket erstellt:"
echo "  $ARCHIVE"
echo ""
echo "Auf dem Ziel-Mac:"
echo "  1. Archiv entpacken"
echo "  2. cd s7py"
echo "  3. ./setup.sh   (Mac/Linux)  oder  setup.bat  (Windows)"
echo "  4. ./run.sh     (Mac/Linux)  oder  run.bat    (Windows)"
