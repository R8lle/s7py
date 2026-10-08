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

**Windows:** Setup doppelklicken → Assistent folgen (optional Desktop-Verknüpfung).

**macOS:** DMG öffnen → `s7py.app` nach **Programme** ziehen → starten. Beim ersten Start ggf. unter *Systemeinstellungen → Datenschutz & Sicherheit* erlauben (unsignierte Builds).

Danach im Programm: Protokoll wählen → Verbindungswerte → **Verbinden** → **Start**.

Hilfe im Menü *Hilfe* (Taste **F1** für die Schnellhilfe). OPC UA an S7-1500: [docs/TIA_OPCUA_S7-1500.md](docs/TIA_OPCUA_S7-1500.md).

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

Lokale Einstellungen: `s7py_db.json` (in `.gitignore`). Vorlage: [`s7py_db.json.example`](s7py_db.json.example).

## Installer selbst bauen

| Ziel | Befehl / Aktion | Ergebnis |
|------|-----------------|----------|
| Windows-Setup | `build-windows.bat` oder Actions → **Windows-Paket** | `s7py-<version>-setup.exe` |
| macOS-DMG | `./build-macos-pyinstaller.sh` oder Actions → **macOS-Paket** | `s7py-<version>-macos-arm64.dmg` / `…-x86_64.dmg` |
| Linux-Tarball | Actions → **Linux-Paket** | `s7py-<version>-linux-x86_64.tar.gz` |
| Portable ZIP | `./package-portable.sh` / `package-portable.bat` | Quellarchiv (Python nötig) |

Build-Kennung: `python -m s7py.about --stamp`.

## Lizenz

s7py steht unter der [MIT License](LICENSE).

Lizenzen der eingebundenen Bibliotheken: [LICENSE_THIRD_PARTY.txt](LICENSE_THIRD_PARTY.txt) und im Programm unter *Hilfe → Info und Lizenzen*.
