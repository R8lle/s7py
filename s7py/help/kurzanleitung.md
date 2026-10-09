# s7py – Schnellhilfe

s7py liest Messwerte von einer Siemens-SPS (**Snap7** oder **OPC UA**), speichert sie in **SQLite** und zeigt sie als **Live-Diagramm**.

## Start

1. Programm starten (Windows: nach Setup; macOS: App aus dem DMG bzw. Programme).
2. **Protokoll** wählen: *Snap7* oder *OPC UA*.
3. Verbindungswerte eintragen (IP bzw. Endpoint, bei Bedarf Benutzer/Passwort).
4. **Verbinden** → **Start** für die Aufzeichnung.

## Snap7

1. **SPS-IP**, **Rack**, **Slot** und **SPS-DB** setzen.
2. Unter *Datei → Snap7 Variablen…* die Datenpunkte pflegen (TIA-Import oder manuell).
3. Pro Zeile steuert **Aktiv**, ob der Wert gelesen und in SQLite geschrieben wird.
4. **Verbinden**, dann **Start**.

## OPC UA

1. **OPC-UA-Endpoint** eintragen (z. B. `opc.tcp://192.168.0.1:4840`).
2. Bei Bedarf **Benutzer** und **Passwort** (wie in TIA angelegt).
3. Unter *Datei → OPC UA Variablen (manuell)…* NodeIds festlegen: Browse `…` → einzelne **NodeId uebernehmen** oder **Unterbaum uebernehmen** (Gruppe; einzeln per SQLite/`X` oder ganz per **Gruppe loeschen**).
4. **Verbinden**, dann **Start**.

Wenn der Browse-Baum leer bleibt: in TIA unter *OPC UA-Kommunikation → Zugriffssteuerung* **Browse** und **Read** für die Benutzerrolle setzen und laden.

Schritt-für-Schritt für TIA Portal (S7-1500): Dokument `docs/TIA_OPCUA_S7-1500.md` im Projektordner.

## Aufzeichnung und Diagramm

- **Start** / **Pause**: Aufzeichnung ein und aus (Verbindung bleibt bestehen).
- **Abfrage (ms)**: wie oft die SPS gelesen wird. Bei Count-Lücken Intervall verkürzen.
- Im Diagramm Kurven ein-/ausblenden (bei vielen Variablen: Button **Kurven …**, Standard alle aus; nur aktivierte erscheinen in der Legende). Umfang und Aktualisierung in der Bedienleiste.
- *Datei → Diagramm als PNG speichern…* exportiert die aktuelle Ansicht.

## Datenbank

- Pfad in der Bedienleiste; zuletzt genutzte Datei wird gemerkt.
- *Datei → Datenbank als Tabelle…* zeigt gespeicherte Zeilen.
- *Datei → Datenbank warten…* zum Kürzen, Leeren oder Vacuum.

## Gespeicherte Einstellungen

Lokal in `s7py_db.json`: letzte Datenbank, IP/Endpoint, Schema, Abfrageintervall, Fenstergrößen und -positionen.

Die ausführliche **Bedienungsanleitung** steht unter *Hilfe → Bedienungsanleitung* (Taste **F1** öffnet die Schnellhilfe).
