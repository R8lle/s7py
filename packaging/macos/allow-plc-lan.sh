#!/usr/bin/env bash
# macOS 15+: behebt Errno 65 fuer SPS-LANs, wenn die App-Freigabe „Lokales Netzwerk“
# nicht greift (kein Eintrag in den Systemeinstellungen).
# Braucht Admin-Passwort und einen Neustart.
set -euo pipefail

sudo defaults write com.apple.network.local-network AllowedEthernetLocalNetworkAddresses -array \
  "10.0.0.0/8" \
  "192.168.0.0/16" \
  "172.16.0.0/12"
sudo defaults write com.apple.network.local-network AllowedWiFiLocalNetworkAddresses -array \
  "10.0.0.0/8" \
  "192.168.0.0/16" \
  "172.16.0.0/12"

echo "Gesetzt. Bitte Mac jetzt neu starten, dann s7py erneut verbinden."
