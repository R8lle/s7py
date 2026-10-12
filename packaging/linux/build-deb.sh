#!/usr/bin/env bash
# Baut ein .deb aus dem PyInstaller-Ordner dist/s7py.
# Aufruf aus dem Projektroot: ./packaging/linux/build-deb.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

APP_DIR="${ROOT}/dist/s7py"
if [[ ! -x "${APP_DIR}/s7py" ]]; then
  echo "Fehlt: ${APP_DIR}/s7py — zuerst PyInstaller bauen." >&2
  exit 1
fi

VERSION="$(
  python -c 'import s7py; print(s7py.__version__)' 2>/dev/null \
  || python3 -c 'import s7py; print(s7py.__version__)' 2>/dev/null \
  || echo "0.0.0"
)"
ARCH_RAW="$(uname -m)"
case "${ARCH_RAW}" in
  x86_64|amd64) DEB_ARCH=amd64 ;;
  aarch64|arm64) DEB_ARCH=arm64 ;;
  *) DEB_ARCH="${ARCH_RAW}" ;;
esac

STAGE="${ROOT}/dist/deb-stage"
PKG_ROOT="${STAGE}/s7py_${VERSION}_${DEB_ARCH}"
rm -rf "${STAGE}"
mkdir -p \
  "${PKG_ROOT}/DEBIAN" \
  "${PKG_ROOT}/opt/s7py" \
  "${PKG_ROOT}/usr/bin" \
  "${PKG_ROOT}/usr/share/applications" \
  "${PKG_ROOT}/usr/share/icons/hicolor/256x256/apps" \
  "${PKG_ROOT}/usr/share/doc/s7py"

# App nach /opt/s7py
cp -a "${APP_DIR}/." "${PKG_ROOT}/opt/s7py/"

# Wrapper in PATH
cat > "${PKG_ROOT}/usr/bin/s7py" <<'EOF'
#!/bin/sh
exec /opt/s7py/s7py "$@"
EOF
chmod 755 "${PKG_ROOT}/usr/bin/s7py"

# Desktop-Eintrag
cp "${ROOT}/packaging/linux/s7py.desktop" "${PKG_ROOT}/usr/share/applications/s7py.desktop"

# Icon (falls PNG vorhanden)
ICON_SRC=""
for candidate in \
  "${ROOT}/assets/s7py-robot-icon.png" \
  "${ROOT}/assets/s7py.png" \
  "${ROOT}/packaging/linux/s7py.png"
do
  if [[ -f "${candidate}" ]]; then
    ICON_SRC="${candidate}"
    break
  fi
done
if [[ -n "${ICON_SRC}" ]]; then
  cp "${ICON_SRC}" "${PKG_ROOT}/usr/share/icons/hicolor/256x256/apps/s7py.png"
fi

# Doku
[[ -f "${ROOT}/LICENSE" ]] && cp "${ROOT}/LICENSE" "${PKG_ROOT}/usr/share/doc/s7py/"
[[ -f "${ROOT}/LICENSE_THIRD_PARTY.txt" ]] && cp "${ROOT}/LICENSE_THIRD_PARTY.txt" "${PKG_ROOT}/usr/share/doc/s7py/"
cat > "${PKG_ROOT}/usr/share/doc/s7py/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: s7py
Source: https://github.com/R8lle/s7py

Files: *
Copyright: s7py contributors
License: MIT
EOF

INSTALLED_SIZE="$(du -sk "${PKG_ROOT}/opt" | awk '{print $1}')"

cat > "${PKG_ROOT}/DEBIAN/control" <<EOF
Package: s7py
Version: ${VERSION}
Section: science
Priority: optional
Architecture: ${DEB_ARCH}
Installed-Size: ${INSTALLED_SIZE}
Maintainer: s7py <noreply@example.com>
Depends: libgl1 | libgl1-mesa-glx, libxkbcommon0, libfontconfig1, libx11-6, libxext6, libxrender1, libxft2, libxss1
Recommends: python3-tk, libtk8.6
Description: SPS-Messwerte lesen, SQLite speichern, Live-Diagramm
 s7py liest Prozesswerte einer Siemens-SPS (Snap7 oder OPC UA),
 speichert sie lokal in SQLite und zeigt ein Live-Diagramm.
 Python ist im Paket enthalten — kein separates Python noetig.
Homepage: https://github.com/R8lle/s7py
EOF

cat > "${PKG_ROOT}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "${PKG_ROOT}/DEBIAN/postinst"

# Verzeichnisse les-/ausfuehrbar; Dateirechte vom PyInstaller-Copy (cp -a) belassen.
find "${PKG_ROOT}/opt/s7py" -type d -exec chmod 755 {} \;
chmod 755 "${PKG_ROOT}/opt/s7py/s7py"

OUT="${ROOT}/dist/s7py_${VERSION}_${DEB_ARCH}.deb"
rm -f "${OUT}"
dpkg-deb --root-owner-group --build "${PKG_ROOT}" "${OUT}"
rm -rf "${STAGE}"

echo ""
echo "DEB fertig: ${OUT}"
echo "Installieren:  sudo apt install ./${OUT##*/}"
echo "  oder:        sudo dpkg -i ${OUT}"
echo "Starten:       s7py   (Menueeintrag oder Terminal)"
echo "Deinstallieren: sudo apt remove s7py"
