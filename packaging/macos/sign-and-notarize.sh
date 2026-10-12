#!/usr/bin/env bash
# Signiert s7py.app mit Developer ID (ein --deep-Lauf, kein per-Datei-Timestamp-Hammer).
# Notarisierung lokal: S7PY_NOTARY_PROFILE=<keychain-profil>
# Notarisierung CI:   S7PY_NOTARY_KEY / S7PY_NOTARY_KEY_ID / S7PY_NOTARY_ISSUER
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="${1:-$ROOT/dist/s7py.app}"
ENTITLEMENTS="$ROOT/packaging/macos/entitlements.plist"
IDENTITY="${S7PY_CODESIGN_IDENTITY:-Developer ID Application: Ralf Kauschus (Z2FRLAU83M)}"
NOTARY_PROFILE="${S7PY_NOTARY_PROFILE:-}"
NOTARY_KEY="${S7PY_NOTARY_KEY:-}"
NOTARY_KEY_ID="${S7PY_NOTARY_KEY_ID:-}"
NOTARY_ISSUER="${S7PY_NOTARY_ISSUER:-}"

notary_ready() {
  if [[ -n "$NOTARY_PROFILE" ]]; then
    return 0
  fi
  if [[ -n "$NOTARY_KEY" && -n "$NOTARY_KEY_ID" && -n "$NOTARY_ISSUER" ]]; then
    return 0
  fi
  return 1
}

notary_submit() {
  local artifact="$1"
  if [[ -n "$NOTARY_KEY" && -n "$NOTARY_KEY_ID" && -n "$NOTARY_ISSUER" ]]; then
    local key_file
    key_file="$(mktemp "${TMPDIR:-/tmp}/s7py-notary-XXXXXX.p8")"
    printf '%s' "$NOTARY_KEY" > "$key_file"
    echo "Notarisiere via App Store Connect API Key ..."
    if xcrun notarytool submit "$artifact" \
      --key "$key_file" \
      --key-id "$NOTARY_KEY_ID" \
      --issuer "$NOTARY_ISSUER" \
      --wait; then
      rm -f "$key_file"
    else
      rm -f "$key_file"
      return 1
    fi
  else
    echo "Notarisiere ($NOTARY_PROFILE) ..."
    xcrun notarytool submit "$artifact" --keychain-profile "$NOTARY_PROFILE" --wait
  fi
}

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

# Deep + Timestamp. Hardened Runtime wenn Notarisierung gewuenscht
# (S7PY_HARDENED_RUNTIME=1) — ohne Runtime klappt LAN-Privacy bei PyInstaller
# auf manchen macOS-Versionen zuverlaessiger.
SIGN_OPTS=(--force --deep --timestamp --entitlements "$ENTITLEMENTS" --sign "$IDENTITY")
if [[ "${S7PY_HARDENED_RUNTIME:-}" == "1" ]] || notary_ready; then
  SIGN_OPTS=(--force --deep --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$IDENTITY")
fi
codesign "${SIGN_OPTS[@]}" "$APP"

echo "Pruefe Signatur ..."
codesign --verify --deep --strict --verbose=2 "$APP"
echo "Signatur OK."

if notary_ready; then
  VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import s7py; print(s7py.__version__)" 2>/dev/null || echo "0.9.0")"
  ARCH="$(uname -m)"
  ZIP="$ROOT/dist/s7py-${VERSION}-macos-${ARCH}-notarize.zip"
  rm -f "$ZIP"
  ditto -c -k --keepParent "$APP" "$ZIP"
  notary_submit "$ZIP"
  xcrun stapler staple "$APP"
  echo "Notarisierung + Staple OK."
  rm -f "$ZIP"
else
  echo "Hinweis: Kein Notary-Profil/API-Key — nur signiert, nicht notariert."
fi
