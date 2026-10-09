# s7py – Bedienungsanleitung

s7py ist ein Desktop-Werkzeug, um Prozesswerte einer Siemens-SPS zu lesen, in einer lokalen SQLite-Datenbank zu speichern und als Live-Diagramm zu verfolgen. Unterstützte Protokolle: **Snap7** (ISO-on-TCP) und **OPC UA**.

## Installation und Start

### Fertige Pakete (empfohlen)

Python und Bibliotheken sind **im Paket enthalten** — nichts separat installieren, keine Kommandozeile nötig.

| System | Datei | Vorgehen |
|--------|--------|----------|
| Windows | `s7py-*-setup.exe` | Doppelklick, Assistent folgen |
| macOS | `s7py-*-macos.dmg` | Öffnen, App nach Programme ziehen |

Download: [GitHub Releases](https://github.com/R8lle/s7py/releases).

Danach s7py starten → Protokoll wählen → verbinden → **Start**.

### Hinweis für Entwickler

Aus dem Quellcode wird mit Python 3.11+ gebaut (venv, PyInstaller). Das betrifft nur den Build-Rechner. Die fertige App bringt ihre Laufzeitumgebung mit; Endanwender sehen davon nichts.

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

- **SPS-IP**: Adresse der CPU.
- **Rack / Slot**: typisch Rack 0, Slot 1 bei S7-1200/1500 (je nach Hardware prüfen).
- **SPS-DB**: Nummer des Datenbausteins, aus dem gelesen wird.
- Port **102** muss erreichbar sein.

### Variablen

*Datei → Snap7 Variablen…*

- TIA-Datenbaustein importieren oder Zeilen manuell anlegen.
- Spalten: Name, Datentyp, Byte.Bit, Aktiv.
- **Count**-Feld: steigender Zähler in der SPS; bei Lücken warnt die Oberfläche.
- Speichern aktualisiert die lokale Konfiguration und kann die SQLite-Struktur anpassen.

## OPC UA

### Verbindung

- Endpoint im Format `opc.tcp://host:4840`.
- Optional Benutzer/Passwort (werden lokal verschlüsselt abgelegt).
- Bei aktivierter Zugriffssteuerung in TIA: Rolle mit **Browse** und **Read**, danach Hardware und Software laden.
- Ausführlich: `docs/TIA_OPCUA_S7-1500.md` im Projekt.

### Variablen

*Datei → OPC UA Variablen (manuell)…*

- Name, Typ, NodeId, SQLite (einzeln abwählbar), optional Spalte **Gruppe**.
- Browse-Dialog (`…` in der Zeile): gleiche Anmeldung wie die Hauptverbindung.
  - **NodeId uebernehmen**: eine Variable in die aktuelle Zeile.
  - **Unterbaum uebernehmen**: alle Variable-Knoten rekursiv unter dem markierten Ordner/Strukturknoten; erscheinen als Gruppe (gemeinsames Label).
- **X**: eine Zeile löschen. **Gruppe loeschen**: alle Zeilen derselben Import-Gruppe.

## Datenbank und Diagramm

- Eine SQLite-Datei pro Messreihe; Pfad in der Bedienleiste.
- Beim Schemawechsel: bestehende DB migrieren oder neue leere DB anlegen.
- Diagramm liest aus SQLite (nicht direkt aus dem Live-Puffer); Aktualisierung einstellbar.
- Kurven: bei wenigen Variablen Checkboxen in der Bedienleiste; ab 6 plotbaren Feldern Button **Kurven …** mit Auswahlliste (Standard: alle aus). Nur aktivierte Kurven werden gezeichnet und in der Legende gezeigt.
- Tabellenfenster: letzte N Zeilen oder gesamte Tabelle (bei sehr großen DBs Nachfrage).
- Wartung: alte Zeilen behalten/kürzen, Tabelle leeren, VACUUM.

## Gespeicherte Konfiguration

Datei `s7py_db.json` (Entwicklung: Projektordner; gebündelte App: Anwendungsdaten des Benutzers):

- letzte Datenbank und SPS-/OPC-UA-Parameter
- Snap7- und OPC-UA-Schema getrennt
- Abfrageintervall, Diagramm-Aktualisierung, Auto-Reconnect
- Fenstergeometrien

Die Datei gehört nicht ins Repository.

## Diagnose

- Meldungsbox und `s7py.log` (rotierend).
- *Hilfe → Info und Lizenzen*: Version, Build, Systemangaben kopieren.
- Count-Lücken: Abfrageintervall verringern oder SPS-Last prüfen.
- Verbindungsabbrüche: Auto-Reconnect in der Bedienleiste.
- OPC UA „verbunden, aber Objects leer“: Browse/Read in TIA-Zugriffssteuerung und Server-Interface prüfen.

## Lizenz

s7py steht unter der MIT License. Fremdkomponenten: siehe *Hilfe → Info und Lizenzen* und `LICENSE_THIRD_PARTY.txt`.
