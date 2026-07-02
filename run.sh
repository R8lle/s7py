#!/usr/bin/env bash
# s7py portable: Anwendung starten (nach ./setup.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
    echo "Virtuelle Umgebung fehlt. Bitte zuerst ausfuehren:"
    echo "  ./setup.sh"
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec s7py "$@"
