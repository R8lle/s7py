# TIA Portal V19 — Put/Get und OPC UA für s7py

Gilt für **TIA Portal V19** mit S7-1500-Firmware **≥ V3.1** (lokale Benutzerverwaltung / **UMAC**).

Das ist der große Bruch zu V16–V18: Benutzer und Rechte liegen unter **Security-Einstellungen → Benutzer und Rollen**, nicht mehr nur in den OPC-UA-CPU-Eigenschaften.

Bei FW **≤ V3.0** im V19-Projekt eher die Abläufe von [V18](TIA_V18_PutGet_OPC_UA.md) nutzen.

Nach Änderungen: **kompilieren** → **in Gerät laden** → CPU **RUN**.

---

## 1. Put/Get freigeben (Snap7)

### Kernschritt

1. Gerätesicht → CPU anklicken
2. **Eigenschaften** → **Schutz & Security** → **Verbindungsmechanismen**
3. Aktivieren: **Zugriff mit PUT/GET-Kommunikation von Remote-Partner zulassen**
4. Zugriffsstufe mindestens **Lesen** / **Vollzugriff** (nicht „Kein Zugriff“)
5. Laden

### Wenn die Checkbox ausgegraut ist

**Schnelltest:** Unter **Schutz & Security → Zugriffssteuerung** die Zugriffssteuerung deaktivieren → Put/Get setzen → laden.

**Mit Zugriffssteuerung (empfohlen):**

1. **Security-Einstellungen → Benutzer und Rollen**
2. Rolle anlegen (z. B. `PutGet`)
3. Runtime-Rechte: mindestens **HMI-Zugriff** für die PLC
4. Benutzer **Anonymous** (oder eigenen User) der Rolle zuweisen
5. Put/Get-Checkbox aktivieren → laden

### Datenbausteine

- DB mit Zugriffstyp **Standard** (nicht optimiert) — Snap7 liest über Byte-Offsets
- In s7py: Protokoll **Snap7**, IP, Rack/Slot, SPS-DB → *Datei → Snap7 Variablen…*

---

## 2. OPC UA freigeben

### Server

1. CPU → **Eigenschaften** → **OPC UA** → **Server**
2. **OPC UA-Server aktivieren**, Port notieren (meist **4840**)
3. Runtime-Lizenz für OPC UA setzen
4. Laden

### Sicherheit (erster Test)

- Policy **None** / Mode **None** zulassen

### Benutzer (UMAC — neu gegenüber V18)

1. **Schutz & Security → Zugriffssteuerung** aktiv (Standard)
2. **Security-Einstellungen → Benutzer und Rollen**
3. Rolle mit Funktionsrecht **OPC UA-Server-Zugriff**
4. Benutzer anlegen und Rolle zuweisen
   - Gast-Betrieb: Benutzer **Anonymous** aktivieren und berechtigen
5. Laden

> „Gast-Authentifizierung“ nur in den alten OPC-UA-Dialogen (FW ≤ V3.0). Ab V3.1 = **Anonymous**.

### Variablen

1. In den Variablen-/DB-Eigenschaften **Zugriff über OPC UA** erlauben
2. In s7py: Endpoint `opc.tcp://<IP>:4840`, ggf. User/Passwort → *Datei → OPC UA Variablen…* → Browse
3. Browse leer → Rolle/Anonymous und **OPC UA-Server-Zugriff** prüfen

---

## Checkliste

- [ ] Put/Get aktiv (ggf. nach Rolle/Anonymous)
- [ ] DB Standard-Zugriff
- [ ] OPC-UA-Server + Lizenz + Policy
- [ ] UMAC-Rolle mit OPC UA-Server-Zugriff
- [ ] Variablen OPC-UA-fähig; CPU RUN

---

[← Übersicht](README.md) · [V18](TIA_V18_PutGet_OPC_UA.md) · [V20](TIA_V20_PutGet_OPC_UA.md)
