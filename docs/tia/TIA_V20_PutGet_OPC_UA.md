# TIA Portal V20 — Put/Get und OPC UA für s7py

Gilt für **TIA Portal V20** (inkl. Updates). Basis wie [V19](TIA_V19_PutGet_OPC_UA.md) (UMAC).

Neu gegenüber V19:

- ab CPU-FW **V4.0**: optionale **zentrale** Benutzerverwaltung (UMC)
- ab **V20 Update 3** + FW **V4.0**: Editor **Zugriffssteuerung beim OPC UA-Server** (Browse/Read pro Namensraum)

Nach Änderungen: **kompilieren** → **in Gerät laden** → CPU **RUN**.

---

## 1. Put/Get freigeben (Snap7)

### Kernschritt

1. Gerätesicht → CPU anklicken
2. **Eigenschaften** → **Schutz & Security** → **Verbindungsmechanismen**
3. Aktivieren: **Zugriff mit PUT/GET-Kommunikation von Remote-Partner zulassen**
4. Zugriffsstufe mindestens **Lesen** / **Vollzugriff** (nicht „Kein Zugriff“)
5. Laden

### Wenn die Checkbox ausgegraut ist (FW ≥ V3.1)

Wie in [V19](TIA_V19_PutGet_OPC_UA.md) Abschnitt 1:

- **Schnelltest:** Zugriffssteuerung deaktivieren → Put/Get setzen → laden
- **Dauerbetrieb:** Rolle mit **HMI-Zugriff**, **Anonymous**/User zuweisen → Put/Get aktivieren

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

- Test: Policy **None** / Mode **None**
- Produktion: z. B. Basic256Sha256 + Zertifikat (siehe [TIA_OPCUA_S7-1500.md](../TIA_OPCUA_S7-1500.md))

### Benutzer (FW ≥ V3.1, UMAC)

1. **Security-Einstellungen → Benutzer und Rollen**
2. Rolle mit Funktionsrecht **OPC UA-Server-Zugriff**
3. Benutzer bzw. **Anonymous** zuweisen
4. Laden

### Browse / Read feingranular (FW ≥ V4.0, TIA V20 Update 3+)

Wenn verbunden, aber Baum leer oder keine Werte:

1. Projektnavigation → PLC → **OPC UA-Kommunikation → Zugriffssteuerung beim OPC UA-Server**
2. Für **Anonymous** und/oder **AuthenticatedUser** in den Namensräumen **Browse** und **Read** setzen
3. Laden

Ohne diesen Editor (ältere FW): Rechte über UMAC-Rolle wie in [V19](TIA_V19_PutGet_OPC_UA.md).

### Variablen

1. In den Variablen-/DB-Eigenschaften **Zugriff über OPC UA** erlauben
2. In s7py: Endpoint `opc.tcp://<IP>:4840` → *Datei → OPC UA Variablen…* → Browse

---

## Checkliste

- [ ] Put/Get aktiv (ggf. nach Rolle/Anonymous)
- [ ] DB Standard-Zugriff
- [ ] OPC-UA-Server + Lizenz + Policy
- [ ] UMAC-Rolle mit OPC UA-Server-Zugriff
- [ ] Bei FW ≥ V4.0: Browse/Read im Namensraum-Editor
- [ ] Variablen OPC-UA-fähig; CPU RUN

---

[← Übersicht](README.md) · [V19](TIA_V19_PutGet_OPC_UA.md) · [V21](TIA_V21_PutGet_OPC_UA.md)
