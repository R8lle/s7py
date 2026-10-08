# s7py – Bedienungsanleitung

s7py ist ein Desktop-Werkzeug, um Prozesswerte einer Siemens-SPS zu lesen, in einer lokalen SQLite-Datenbank zu speichern und als Live-Diagramm zu verfolgen. Unterstützte Protokolle: **Snap7** (ISO-on-TCP) und **OPC UA**.

## Installation und Start

Voraussetzung: **Python 3.11** oder neuer.

```bash
cd s7py
./setup.sh    # Mac/Linux: venv + Abhaengigkeiten
./run.sh
```

Windows: `setup.bat`, danach `run.bat`.

Optional OPC UA:

```bash
source .venv/bin/activate
pip install -e ".[opcua]"
```

Tests: `./test.sh`.

Portable ZIP und PyInstaller-Builds sind in der [README](../../README.md) beschrieben.

## Oberfläche

- **Protokoll**: Snap7 oder OPC UA (wechselt Felder und Datei-Menü).
- **Verbinden / Trennen**: SPS-Sitzung.
- **Start / Pause**: Hintergrund-Thread für zyklisches Lesen und Schreiben in SQLite.
- **Meldungen**: Status- und Diagnosetext unten; ausführlicheres Log in `s7py.log`.
- **Menü Datei**: Variablen-Editor, PNG-Export, Tabellenansicht, Datenbankwartung.
- **Menü Hilfe**: Schnellhilfe, Bedienungsanleitung, Info und Lizenzen.

Fenstergrößen und Positionen (Hauptfenster, Variablen, Tabelle) werden beim Schließen gemerkt.

## Snap7

### Verbindung

- **SPS-IP**: Adresse der CPU (Standardplatzhalter `192.168.0.1`).
- **Rack / Slot**: typisch Rack 0, Slot 1 bei S7-1200/1500 (je nach Hardware prüfen).
- **SPS-DB**: Nummer des Datenbausteins, aus dem gelesen wird.
- Port **102** muss erreichbar sein. `python-snap7` 3.x ist reines Python — keine separate `libsnap7`.

### Variablen

*Datei → Snap7 Variablen…*

- TIA-Datenbaustein importieren oder Zeilen manuell anlegen.
- Spalten: Name, Datentyp, Byte.Bit, Aktiv.
- **Count**-Feld: steigender Zähler in der SPS; bei Lücken warnt die Oberfläche.
- Speichern aktualisiert `s7py_db.json` und kann die SQLite-Struktur anpassen.

## OPC UA

### Verbindung

- Endpoint im Format `opc.tcp://host:4840`.
- Optional Benutzer/Passwort (werden lokal verschlüsselt in der Konfiguration abgelegt).
- Zertifikatsbetrieb: siehe TIA-Anleitung im Projekt unter `docs/TIA_OPCUA_S7-1500.md`.

### Variablen

*Datei → OPC UA Variablen (manuell)…*

- Name, Typ, NodeId, Aktiv.
- Browse-Dialog hilft beim Finden von Nodes am Server.
- Abhaengigkeit: Paket `asyncua` (`pip install -e ".[opcua]"`).

## Datenbank und Diagramm

- Eine SQLite-Datei pro Messreihe; Pfad in der Bedienleiste.
- Beim Schemawechsel: bestehende DB migrieren oder neue leere DB anlegen.
- Diagramm liest aus SQLite (nicht direkt aus dem Live-Puffer); Aktualisierung einstellbar.
- Tabellenfenster: letzte N Zeilen oder gesamte Tabelle (bei sehr großen DBs Nachfrage).
- Wartung: alte Zeilen behalten/kürzen, Tabelle leeren, VACUUM.

## Gespeicherte Konfiguration

Datei `s7py_db.json` im Anwendungsordner (Entwicklung: Projektroot; gebündelte App: nutzerspezifisches Datenverzeichnis):

- letzte Datenbank und SPS-/OPC-UA-Parameter
- Snap7- und OPC-UA-Schema getrennt
- Abfrageintervall, Diagramm-Aktualisierung, Auto-Reconnect
- Fenstergeometrien

Vorlage: `s7py_db.json.example`. Die Datei gehört nicht ins Repository.

## Diagnose

- Meldungsbox und `s7py.log` (rotierend).
- *Hilfe → Info und Lizenzen*: Version, Build, Systemangaben kopieren.
- Count-Lücken: Abfrageintervall verringern oder SPS-Last prüfen.
- Verbindungsabbrüche: Auto-Reconnect in der Bedienleiste.

## Lizenz

s7py steht unter der MIT License. Fremdkomponenten: siehe *Hilfe → Info und Lizenzen* und `LICENSE_THIRD_PARTY.txt`.
