# s7py

SPS-Daten per Snap7 lesen, in SQLite speichern und als Live-Diagramm anzeigen.

Neues Projekt auf Basis von [PySnap](https://github.com/R8lle/PySnap). PySnap bleibt unverändert;
hier entwickeln wir die nächste Generation — geplant sind u. a. OPC UA neben Snap7.

## Schnellstart (portable)

```bash
cd s7py
./setup.sh    # Mac/Linux: venv + pip install -e ".[dev]"
./run.sh
```

```bat
setup.bat     # Windows
run.bat
```

`setup.sh` erkennt eine Workspace-venv unter `../.venv` und weist darauf hin.

## Tests

```bash
./test.sh
```

Windows (nach `setup.bat`, venv aktiv):

```bat
.venv\Scripts\activate
python -m pytest
```

## Voraussetzungen

- Python 3.11 oder neuer
- Netzwerkzugriff auf die SPS (ISO-on-TCP, Port 102); Standard-IP in der GUI ist ein Platzhalter (`192.168.0.1`) — bitte anpassen
- `python-snap7` 3.0.0 ist **reines Python** — keine separate Snap7-DLL
  oder native `libsnap7` nötig (wird per `pip install` mitgeliefert)

## Lizenz

s7py steht unter der [MIT License](LICENSE).

Lizenzen der eingebundenen Bibliotheken (matplotlib, python-snap7): [LICENSE_THIRD_PARTY.txt](LICENSE_THIRD_PARTY.txt).

## Lokale Konfiguration

`s7py_db.json` speichert **lokal** letzte DB-Pfade, SPS-IP und Schema — die Datei steht in `.gitignore`
und wird **nicht** ins Repository oder portable ZIPs gepackt.

Beim Speichern werden Pfade relativ zum s7py-Ordner abgelegt (z. B. `s7py.db` statt
`/Users/.../s7py.db`). Als Vorlage dient [`s7py_db.json.example`](s7py_db.json.example).

## Portable Paket / Build

| Ziel | Befehl | Ergebnis |
|------|--------|----------|
| ZIP (Mac/Linux) | `./package-portable.sh` | Quellarchiv zum Entpacken + `setup.sh` |
| ZIP (Windows) | `package-portable.bat` | Quellarchiv zum Entpacken + `setup.bat` |
| Windows-EXE | `build-windows.bat` | `dist\s7py\s7py.exe` (PyInstaller) |
| macOS-App | `./build-macos-pyinstaller.sh` | `.app`-Bundle (PyInstaller) |
