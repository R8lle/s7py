# s7py

Open-Source-Desktop-Werkzeug, um Messwerte einer Siemens-SPS zu lesen, lokal in **SQLite** zu speichern und als **Live-Diagramm** zu verfolgen.

Unterstützte Protokolle:

- **Snap7** (ISO-on-TCP, Port 102)
- **OPC UA** (optional, mit `asyncua`)

Keine Cloud-Pflicht: Konfiguration und Messdaten bleiben auf dem Rechner.

## Voraussetzungen

- Python 3.11 oder neuer
- Netzwerkzugriff auf die SPS
- Für OPC UA: `pip install -e ".[opcua]"` (bzw. Extra beim Setup)

`python-snap7` 3.x ist **reines Python** — keine separate Snap7-DLL oder `libsnap7` nötig.

## Schnellstart

```bash
cd s7py
./setup.sh    # Mac/Linux: venv + pip install -e ".[dev]"
./run.sh
```

```bat
setup.bat     # Windows
run.bat
```

Im Programm: Protokoll wählen → Verbindungswerte → **Verbinden** → **Start**.

Hilfe im Menü *Hilfe* (Taste **F1** für die Schnellhilfe). Quellen: [s7py/help/kurzanleitung.md](s7py/help/kurzanleitung.md) und [s7py/help/anleitung.md](s7py/help/anleitung.md). OPC UA an S7-1500: [docs/TIA_OPCUA_S7-1500.md](docs/TIA_OPCUA_S7-1500.md).

## Tests

```bash
./test.sh
```

Windows (nach `setup.bat`, venv aktiv):

```bat
.venv\Scripts\activate
python -m pytest
```

## Lokale Konfiguration

`s7py_db.json` speichert **lokal** letzte DB-Pfade, SPS-/OPC-UA-Parameter, Schema und Fenstergeometrien. Die Datei steht in `.gitignore` und wird nicht ins Repository gepackt.

Pfade werden relativ zum s7py-Ordner abgelegt. Vorlage: [`s7py_db.json.example`](s7py_db.json.example).

## Portable Paket / Build

| Ziel | Befehl | Ergebnis |
|------|--------|----------|
| ZIP (Mac/Linux) | `./package-portable.sh` | Quellarchiv zum Entpacken + `setup.sh` |
| ZIP (Windows) | `package-portable.bat` | Quellarchiv zum Entpacken + `setup.bat` |
| Windows-EXE | `build-windows.bat` | `dist\s7py\s7py.exe` (PyInstaller) |
| macOS-App | `./build-macos-pyinstaller.sh` | `.app`-Bundle (PyInstaller) |

Beim Paketieren den Build festschreiben:

```bash
python -m s7py.about --stamp
```

## Lizenz

s7py steht unter der [MIT License](LICENSE).

Lizenzen der eingebundenen Bibliotheken: [LICENSE_THIRD_PARTY.txt](LICENSE_THIRD_PARTY.txt) und im Programm unter *Hilfe → Info und Lizenzen*.
