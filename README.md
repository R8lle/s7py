# s7py

Open-Source-Desktop-Werkzeug, um Messwerte einer Siemens-SPS zu lesen, lokal in **SQLite** zu speichern und als **Live-Diagramm** zu verfolgen.

Unterstützte Protokolle:

- **Snap7** (ISO-on-TCP, Port 102)
- **OPC UA** (optional, mit `asyncua`)

Keine Cloud-Pflicht: Konfiguration und Messdaten bleiben auf dem Rechner.

## Installation (Endanwender)

Python und Abhängigkeiten sind in den Installern **mit eingebaut**. Sie brauchen kein Python zu installieren und keine Kommandozeile.

| System | Paket | Quelle |
|--------|--------|--------|
| **Windows** | `s7py-*-setup.exe` | [GitHub Releases](https://github.com/R8lle/s7py/releases) (`v*-windows`) |
| **macOS** | `s7py-*-macos.dmg` | [GitHub Releases](https://github.com/R8lle/s7py/releases) (`v*-macos`) |
| **Linux (Ubuntu/Debian)** | `s7py_*_amd64.deb` | [GitHub Releases](https://github.com/R8lle/s7py/releases) (`v*-linux`) |

**Windows:** Setup doppelklicken → Assistent folgen (optional Desktop-Verknüpfung).

**macOS:** DMG öffnen → `s7py.app` nach **Programme** ziehen → starten. Signierte/notarisierte ARM-Builds aus Actions brauchen keine Gatekeeper-Ausnahme; unsignierte Builds ggf. unter *Datenschutz & Sicherheit* erlauben.

**Linux (Ubuntu):** `.deb` herunterladen, dann:

```bash
sudo apt install ./s7py_*_amd64.deb
s7py
```

Deinstallieren: `sudo apt remove s7py`. Alternativ portables `*.tar.gz` entpacken und `./s7py` starten.

Danach im Programm: Protokoll wählen → Verbindungswerte → **Verbinden** → **Start**.

Hilfe im Menü *Hilfe* (Taste **F1** für die Schnellhilfe; TIA Put/Get & OPC UA als eigener Eintrag, PDF-Export im Hilfe-Fenster). Versionierte TIA-Notizen: [docs/tia/](docs/tia/README.md). OPC UA mit s7py im Detail: [docs/TIA_OPCUA_S7-1500.md](docs/TIA_OPCUA_S7-1500.md).

## Entwicklung (Quellcode)

Nur für Entwickler / Beitragende. Endanwender nutzen die Installer oben.

Voraussetzung zum Bauen aus dem Quellbaum: **Python 3.11+** (läuft nur lokal in einer venv; der Nutzer der fertigen App sieht davon nichts).

```bash
cd s7py
./setup.sh    # Mac/Linux: venv + pip install -e ".[dev,opcua]"
./run.sh
```

```bat
setup.bat     # Windows
run.bat
```

Tests: `./test.sh` bzw. `python -m pytest`.

`python-snap7` 3.x ist reines Python — keine separate Snap7-DLL nötig.

Lokale Einstellungen: `s7py_db.json` (in `.gitignore`). Benannte Profile unter `configs/*.json` (Menü *Datei*). Vorlage: [`s7py_db.json.example`](s7py_db.json.example).

## Installer selbst bauen

| Ziel | Befehl / Aktion | Ergebnis |
|------|-----------------|----------|
| Windows-Setup | `build-windows.bat` oder Actions → **Windows-Paket** | `s7py-<version>-setup.exe` |
| macOS-DMG (ARM) | Actions → **macOS-Paket** (Secrets: `MACOS_CERTIFICATE*`, `APPLE_API_*`) | `s7py-<version>-macos-arm64.dmg` |
| macOS-DMG (Intel) | lokal `./build-macos-pyinstaller.sh` auf Intel-Mac | `s7py-<version>-macos-x86_64.dmg` |
| Linux .deb + Tarball | Actions → **Linux-Paket** | `s7py_<version>_amd64.deb`, `s7py-<version>-linux-x86_64.tar.gz` |
| Portable ZIP | `./package-portable.sh` / `package-portable.bat` | Quellarchiv (Python nötig) |

Build-Kennung: `python -m s7py.about --stamp`.

## Lizenz

s7py steht unter der [MIT License](LICENSE).

Lizenzen der eingebundenen Bibliotheken: [LICENSE_THIRD_PARTY.txt](LICENSE_THIRD_PARTY.txt) und im Programm unter *Hilfe → Info und Lizenzen*.
