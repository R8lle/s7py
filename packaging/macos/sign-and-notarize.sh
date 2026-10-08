#!/usr/bin/env bash
# Signiert s7py.app mit Developer ID (ein --deep-Lauf, kein per-Datei-Timestamp-Hammer).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="${1:-$ROOT/dist/s7py.app}"
ENTITLEMENTS="$ROOT/packaging/macos/entitlements.plist"
IDENTITY="${S7PY_CODESIGN_IDENTITY:-Developer ID Application: Ralf Kauschus (Z2FRLAU83M)}"
NOTARY_PROFILE="${S7PY_NOTARY_PROFILE:-}"

if [[ ! -d "$APP" ]]; then
  echo "App fehlt: $APP" >&2
  exit 1
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "Entitlements fehlen: $ENTITLEMENTS" >&2
  exit 1
fi

echo "Signiere mit: $IDENTITY"
xattr -cr "$APP" 2>/dev/null || true

# Deep + Timestamp. Hardened Runtime nur wenn Notarisierung gewuenscht
# (S7PY_HARDENED_RUNTIME=1) — ohne Runtime klappt LAN-Privacy bei PyInstaller
# auf manchen macOS-Versionen zuverlaessiger.
SIGN_OPTS=(--force --deep --timestamp --entitlements "$ENTITLEMENTS" --sign "$IDENTITY")
if [[ "${S7PY_HARDENED_RUNTIME:-}" == "1" ]] || [[ -n "$NOTARY_PROFILE" ]]; then
  SIGN_OPTS=(--force --deep --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$IDENTITY")
fi
codesign "${SIGN_OPTS[@]}" "$APP"

echo "Pruefe Signatur ..."
codesign --verify --deep --strict --verbose=2 "$APP"
echo "Signatur OK."

if [[ -n "$NOTARY_PROFILE" ]]; then
  VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import s7py; print(s7py.__version__)" 2>/dev/null || echo "0.9.0")"
  ARCH="$(uname -m)"
  ZIP="$ROOT/dist/s7py-${VERSION}-macos-${ARCH}-notarize.zip"
  rm -f "$ZIP"
  ditto -c -k --keepParent "$APP" "$ZIP"
  echo "Notarisiere ($NOTARY_PROFILE) ..."
  xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$APP"
  echo "Notarisierung + Staple OK."
  rm -f "$ZIP"
else
  echo "Hinweis: S7PY_NOTARY_PROFILE nicht gesetzt — nur signiert, nicht notariert."
fi
