# TIA Portal V21 — Put/Get und OPC UA für s7py

Gilt für **TIA Portal V21**. Inhaltlich wie [V20](TIA_V20_PutGet_OPC_UA.md); Menüs unter **Schutz & Security** und der OPC-UA-Zugriffssteuerungs-Editor sind der aktuelle Stand.

Je nach **CPU-Firmware**:

- **≤ V3.0** — Put/Get/Benutzer eher wie [V18](TIA_V18_PutGet_OPC_UA.md); OPC-UA-User in den CPU-Eigenschaften
- **≥ V3.1** — UMAC (dieses Dokument); Funktionsrecht **OPC UA-Server-Zugriff**
- **≥ V4.0** — UMAC, optional UMC; zusätzlich Editor **Zugriffssteuerung beim OPC UA-Server** (Browse/Read)

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

**Schnelltest:** Unter **Schutz & Security → Zugriffssteuerung** die Zugriffssteuerung deaktivieren → Put/Get setzen → laden.

**Dauerbetrieb:**

1. **Security-Einstellungen → Benutzer und Rollen**
2. Rolle anlegen (z. B. `PutGet`) mit Runtime-Recht **HMI-Zugriff**
3. **Anonymous** oder User der Rolle zuweisen
4. Put/Get aktivieren → laden

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
- Produktion: restriktive Policy + Zertifikat (siehe [TIA_OPCUA_S7-1500.md](../TIA_OPCUA_S7-1500.md))

### Benutzer (UMAC)

1. **Schutz & Security → Zugriffssteuerung** aktiv
2. **Security-Einstellungen → Benutzer und Rollen**
3. Rolle mit Funktionsrecht **OPC UA-Server-Zugriff**
4. Benutzer anlegen oder **Anonymous** für Gast
5. In s7py User/Passwort eintragen, wenn kein Anonymous

### Browse / Read (FW ≥ V4.0)

1. Projektnavigation → PLC → **OPC UA-Kommunikation → Zugriffssteuerung beim OPC UA-Server**
2. Für **Anonymous** und/oder **AuthenticatedUser**: **Browse** und **Read** in den Namensräumen
3. Laden

Ohne Browse/Read: s7py verbindet oft, der Baum bleibt leer.

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

[← Übersicht](README.md) · [V20](TIA_V20_PutGet_OPC_UA.md) · [s7py OPC-UA-Details](../TIA_OPCUA_S7-1500.md)
