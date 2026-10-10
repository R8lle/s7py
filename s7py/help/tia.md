# s7py – TIA Portal (Put/Get & OPC UA)

Was in **TIA Portal** an einer **S7-1500** freizuschalten ist, damit s7py per **Snap7 (Put/Get)** bzw. **OPC UA** zugreifen kann.

Die **projektierte CPU-Firmware** zählt mit: neues TIA + alte FW → eher die ältere Beschreibung nutzen.

Nach jeder Änderung: Projekt **kompilieren** → **in die CPU laden** → SPS auf **RUN**.

## Was sich je TIA-Version ändert

- **V16–V18** — Put/Get unter *Schutz*; OPC-UA-Benutzer in den CPU-Eigenschaften
- **V19** — Lokale Benutzerverwaltung (UMAC); Put/Get oft erst nach Rollen frei
- **V20–V21** — Wie V19; ab FW V4.0 zusätzlich OPC-UA-Namensraum-Rechte (Browse/Read)

## Put/Get freigeben (Snap7) — alle Versionen

Snap7 liest Datenbausteine über die S7-Kommunikation. Die CPU muss **Zugriff mit Put/Get von Remote-Partnern** erlauben — unabhängig von der Zugriffsstufe (beide müssen passen).

### V16–V18

1. Gerätesicht → CPU anklicken
2. **Eigenschaften** → **Schutz** → **Verbindungsmechanismen**
3. Aktivieren: **Zugriff mit PUT/GET-Kommunikation von Remote-Partner zulassen**
4. Zugriffsstufe mindestens **Lesen** / **Vollzugriff**
5. Laden

Hinweis: Ab S7-1500-FW ~V2.0 ist Put/Get oft standardmäßig **aus**.

### V19–V21

1. Gerätesicht → CPU
2. **Eigenschaften** → **Schutz & Security** → **Verbindungsmechanismen**
3. **Zugriff mit PUT/GET-Kommunikation von Remote-Partner zulassen**
4. Zugriffsstufe mindestens Lesen/Vollzugriff
5. Laden

Wenn die Checkbox **ausgegraut** ist (FW ≥ V3.1):

- **Schnelltest:** Unter *Schutz & Security → Zugriffssteuerung* die Zugriffssteuerung deaktivieren → Put/Get setzen → laden
- **Dauerbetrieb:** *Security-Einstellungen → Benutzer und Rollen* → Rolle mit **HMI-Zugriff** → Benutzer **Anonymous** (oder eigenen User) zuweisen → Put/Get aktivieren → laden

### Datenbausteine für Snap7

- DB mit Zugriffstyp **Standard** (nicht optimiert) — Snap7 liest über Byte-Offsets
- In s7py: Protokoll **Snap7**, IP, Rack/Slot, SPS-DB → *Datei → Snap7 Variablen…*

### Checkliste Put/Get

- Put/Get von Remote-Partner aktiv
- Zugriffsstufe erlaubt Lesen
- Ab FW V3.1: Zugriffssteuerung aus oder Rolle/Anonymous passend
- DB Standard-Zugriff
- Geladen, CPU RUN, Port **102** erreichbar

## OPC UA freigeben — alle Versionen

### Server einschalten

1. CPU → **Eigenschaften** → **OPC UA** → **Server**
2. **OPC UA-Server aktivieren**, Port notieren (meist **4840**)
3. Runtime-Lizenz für OPC UA setzen
4. Laden

### Sicherheit (erster Test)

- Test: Security Policy **None** / Mode **None**
- Login ohne Zertifikat: Policy None + Benutzer/Passwort
- Produktion: z. B. Basic256Sha256 + SignAndEncrypt + Zertifikat

### Benutzer und Browse/Read

**V16–V18 / FW ≤ V3.0**

1. **OPC UA → Server → Security → Benutzer-Authentifizierung**
2. **Gast** aktivieren oder Benutzer/Passwort anlegen
3. Dem Account **Browse** und **Read** geben
4. Laden

**V19–V21 / FW ≥ V3.1 (UMAC)**

1. **Schutz & Security → Zugriffssteuerung** aktiv
2. **Security-Einstellungen → Benutzer und Rollen**
3. Rolle mit Funktionsrecht **OPC UA-Server-Zugriff**
4. Benutzer anlegen oder **Anonymous** für Gast
5. Laden

Gast ab FW V3.1 = Benutzer **Anonymous** (nicht mehr nur „Gast-Authentifizierung“).

**V20 Update 3 / V21 + FW ≥ V4.0**

Zusätzlich, wenn der Browse-Baum leer bleibt:

1. Projektnavigation → PLC → **OPC UA-Kommunikation → Zugriffssteuerung beim OPC UA-Server**
2. Für **Anonymous** und/oder **AuthenticatedUser** in den Namensräumen **Browse** und **Read** setzen
3. Laden

### Variablen freigeben

1. DB-/PLC-Variable in TIA: Zugriff **über OPC UA** erlauben
2. In s7py: Endpoint `opc.tcp://<IP>:4840` → *Datei → OPC UA Variablen…* → Browse

### Checkliste OPC UA

- OPC-UA-Server aktiv, Runtime-Lizenz gesetzt
- Security Policy passend (zuerst oft None)
- Auth passend zur FW (Gast / Anonymous / User)
- Browse + Read vergeben
- Variablen OPC-UA-fähig
- Endpoint in s7py, CPU RUN

## Typische Fehler

- Snap7 Zugriff verweigert → Put/Get aus oder Zugriffsstufe
- Put/Get-Checkbox grau → UMAC / FW ≥ V3.1: Rolle oder Zugriffssteuerung
- Snap7 Daten falsch → optimierter DB (auf Standard stellen)
- `BadSecurityPolicyRejected` → Policy None fehlt
- Verbunden, Baum leer → kein Browse
- Browse ok, keine Werte → kein Read oder Variable nicht freigegeben
- `Connection refused` → Server aus, falsche IP/Port, Firewall (102 / 4840)

## Empfohlene Reihenfolge

1. TIA-Version und CPU-Firmware klären
2. Put/Get freigeben → in s7py **Snap7** testen
3. OPC-UA-Server + passende Auth → in s7py **OPC UA** testen
4. Browse/Read und Variablenfreigabe
5. Für Produktion Policies und Benutzer verschärfen

Weitere Details zu anonym / User / Zertifikat in s7py und den Einzelversionen im Projektordner unter `docs/tia/`.
