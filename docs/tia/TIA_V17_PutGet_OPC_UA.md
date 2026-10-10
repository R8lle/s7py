# TIA Portal V17 — Put/Get und OPC UA für s7py

Gilt für **TIA Portal V17** mit typischer S7-1500-Firmware **≤ V3.0**.

Abläufe wie bei [V16](TIA_V16_PutGet_OPC_UA.md); Menüpfade unverändert „klassisch“.  
Bei projektierter FW **≥ V3.1** eher [V19](TIA_V19_PutGet_OPC_UA.md) beachten.

Nach Änderungen: **kompilieren** → **in Gerät laden** → CPU **RUN**.

---

## 1. Put/Get freigeben (Snap7)

1. Gerätesicht → CPU anklicken
2. **Eigenschaften** → **Schutz** → **Verbindungsmechanismen**
3. Aktivieren: **Zugriff mit PUT/GET-Kommunikation von Remote-Partner zulassen**
4. Zugriffsstufe mindestens **Lesen** / **Vollzugriff** (nicht „Kein Zugriff“)
5. Laden

Hinweis: Ab S7-1500-FW ~V2.0 ist Put/Get oft standardmäßig **aus**.

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
- Unter **Benutzer-Authentifizierung**: **Gast** aktivieren **oder** Benutzer/Passwort anlegen

Optional: „Zusätzliche Benutzerverwaltung über Security-Einstellungen des Projekts“ (falls im Projekt genutzt).

### Browse / Read

In der OPC-UA-Benutzerverwaltung der CPU dem Gast bzw. User **Browse** und **Read** geben (soweit getrennt parametrierbar).

### Variablen

1. In den Variablen-/DB-Eigenschaften **Zugriff über OPC UA** erlauben
2. In s7py: Endpoint `opc.tcp://<IP>:4840` → *Datei → OPC UA Variablen…* → Browse

---

## Checkliste

- [ ] Put/Get aktiv, Zugriffsstufe ok
- [ ] DB Standard-Zugriff
- [ ] OPC-UA-Server + Lizenz
- [ ] Gast oder User; Browse/Read
- [ ] Variablen OPC-UA-fähig; CPU RUN

---

[← Übersicht](README.md) · [V16](TIA_V16_PutGet_OPC_UA.md) · [V18](TIA_V18_PutGet_OPC_UA.md)
