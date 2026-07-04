# s7py — Backlog

Geplante Erweiterungen (noch nicht umgesetzt).

---

## OPC UA: Benutzer und Passwort (ohne Client-Zertifikat)

**Status:** geplant  
**Kontext:** TIA Portal erlaubt OPC-UA-Anmeldung per Username/Password — getrennt von Security Policy und Client-Zertifikat.

### Hintergrund

- **Security Policy** (None, Basic256Sha256, …) = Verschlüsselung des Kanals  
- **User Identity** (Anonymous, Username/Password, Zertifikat) = Anmeldung  
- Kombination oft möglich: **Policy None + User/PW** → kein Client-Zertifikat nötig  
- s7py unterstützt heute: Anonymous + optional Client-Zertifikat (`opcua_client_cert` / `opcua_client_key` in `s7py_db.json`)

### Geplante Umsetzung

1. Config: `opcua_username`, `opcua_password` in `s7py_db.json`  
2. UI: optionale Felder in der Verbindungszeile (nur bei Protokoll OPC UA)  
3. Connect: asyncua `set_user()` / `set_password()` vor `connect()`  
4. Endpoint-Auswahl: Endpoint mit **UserName**-Token bevorzugen (nicht nur Anonymous)  
5. Doku: Abschnitt in [TIA_OPCUA_S7-1500.md](TIA_OPCUA_S7-1500.md) ergänzen  

### Referenz asyncua

- `client.set_user(username)`  
- `client.set_password(password)`  
- alternativ URL: `opc.tcp://user:pass@host:4840`
