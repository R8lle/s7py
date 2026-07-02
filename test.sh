#!/usr/bin/env bash
# s7py-Tests (nach ./setup.sh in s7py/.venv).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f .venv/bin/activate ]]; then
    echo "Virtuelle Umgebung fehlt. Bitte zuerst: ./setup.sh"
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python -m pytest "$@"
