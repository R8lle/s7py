# OPC UA in TIA Portal — S7-1500 für s7py

Schritt-für-Schritt-Anleitung, um eine **S7-1500** per **OPC UA** mit **s7py** zu verbinden.

Gültig für TIA Portal (V17/V18/V19). Menübezeichnungen können je nach Sprache leicht abweichen.

---

## Übersicht: drei Wege

| Weg | Aufwand | Einsatz |
|-----|---------|---------|
| **A — ohne Zertifikat, anonym** | gering | Test, Entwicklung |
| **C — Benutzer/Passwort** | gering | Gast deaktiviert, Policy None |
| **B — mit Zertifikat** | höher | Produktion, abgesicherte Anlage |

Empfehlung: zuerst **Weg A** testen, bei Login-Pflicht **Weg C**, fuer Dauerbetrieb **Weg B**.

---

## Voraussetzungen

- TIA Portal mit geöffnetem Projekt (S7-1500)
- SPS und PC mit s7py im gleichen Netzwerk
- Projekt kompiliert, Hardware-Konfiguration in die SPS geladen
- In s7py: OPC UA nutzen (in den fertigen Windows-/macOS-Paketen bereits enthalten; Entwickler: Extra `opcua`)

---

# Weg A: ohne Zertifikat (Testbetrieb)

## 1. OPC-UA-Server aktivieren

1. TIA Portal öffnen → Projekt wählen
2. **Gerätesicht** → CPU der S7-1500 anklicken
3. Unten **Eigenschaften** → Register **„OPC UA“**
4. **„OPC UA-Server aktivieren“** aktivieren
5. **Port** notieren (Standard: **4840**)
6. Projekt **speichern** und **in Gerät laden**

## 2. Security Policy „None“ erlauben

1. CPU → **Eigenschaften** → **OPC UA** → Bereich **Sicherheit**
2. **SecurityPolicy „None“** aktivieren  
   (URI: `http://opcfoundation.org/UA/SecurityPolicy#None`)
3. Unverschlüsselten Modus (**Security Mode: None**) zulassen

> Ohne diese Einstellung meldet s7py oft: `BadSecurityPolicyRejected`

## 3. Anonymen Zugriff erlauben

1. Im selben OPC-UA-Bereich: **Benutzerauthentifizierung**
2. **Anonym** aktivieren (Testbetrieb ohne Login)
3. **Benutzername und Kennwort** nur aktivieren, wenn die Anlage Login verlangt
   (siehe **Weg C**)

## 4. Projekt laden und SPS starten

1. **Gesamtes Projekt** in die SPS laden (Hardware + Software)
2. SPS auf **RUN**
3. Kurz warten, bis der OPC-UA-Server bereit ist

## 5. Endpoint-Adresse für s7py

Typische Adresse:

```text
opc.tcp://192.168.0.10:4840
```

- `192.168.0.10` → IP der SPS (**Online** → zur SPS verbinden → Gerätediagnose → Ethernet)
- `4840` → OPC-UA-Port aus Schritt 1

In s7py:

1. Protokoll **OPC UA** wählen
2. Endpoint eintragen
3. **Verbinden**

## 6. Variablen für OPC UA freigeben

OPC UA arbeitet mit **NodeIds**, nicht mit DB-Byte-Adressen wie Snap7.

1. Im TIA-Projekt die gewünschten Variablen/DB-Elemente öffnen
2. In den Eigenschaften **OPC-UA-Zugriff** erlauben (z. B. „Über OPC UA zugreifbar“ / symbolischer Zugriff)
3. NodeIds ermitteln — z. B. mit **UaExpert** oder über den OPC-UA-Browser in s7py

In s7py: **Datei → OPC UA Variablen (manuell)...**

- NodeIds eintragen oder pro Zeile **...** (Server durchsuchen) nutzen
- Speichern

---

# Weg C: Benutzer und Passwort (ohne Client-Zertifikat)

Fuer Anlagen, in denen **Gast/anonym deaktiviert** ist, aber **Security Policy „None"**
erlaubt bleibt.

## 1. TIA Portal

1. CPU → **Eigenschaften** → **OPC UA** → **Server** → **Sicherheit**
2. **SecurityPolicy „None"** aktivieren (wie Weg A, Schritt 2)
3. Unter **Benutzerauthentifizierung**:
   - **„Benutzername und Kennwort aktivieren"**
   - optional **Gast/anonym deaktivieren**
4. In **Benutzerverwaltung** Benutzer anlegen (Passwort gemaess TIA-Regeln)
5. Projekt laden, SPS auf **RUN**

## 2. s7py

1. Protokoll **OPC UA** waehlen
2. Endpoint: `opc.tcp://<IP>:4840`
3. **Benutzer** und **Passwort** eintragen (werden in `s7py_db.json` gespeichert)
4. **Verbinden**

s7py ueberspringt bei gesetztem Benutzer den anonymen Schnellversuch und waehlt
einen Server-Endpoint mit **UserName**-Token.

Alternativ in `s7py_db.json` (nur Benutzername; Passwort ueber die GUI oder
wird verschluesselt als `opcua_password_enc` gespeichert):

```json
{
  "plc_transport": "opcua",
  "opcua_endpoint": "opc.tcp://192.168.0.10:4840",
  "opcua_username": "meinUser"
}
```

Das OPC-UA-Passwort wird nicht im Klartext in der JSON abgelegt, sondern mit
einem lokalen Schluessel in `s7py/.s7py_key` verschluesselt (`opcua_password_enc`).

> Bei Policy „None" kann das Passwort unverschluesselt uebertragen werden (asyncua
> warnt mit *Sending plain-text password*). Fuer Produktion: Weg B mit Zertifikat.

---

# Weg B: mit Client-Zertifikat

## 1. Server vorbereiten

1. OPC-UA-Server aktivieren (wie Weg A, Schritt 1)
2. Gewünschte **Security Policy** aktivieren, z. B. **Basic256Sha256**
3. **SignAndEncrypt** zulassen
4. Anonym **oder** Benutzer/Passwort konfigurieren
5. Projekt laden, SPS auf **RUN**

## 2. Client-Zertifikat am PC erzeugen

Am PC mit s7py (Terminal):

```bash
mkdir -p ~/s7py-opcua-certs
cd ~/s7py-opcua-certs

openssl genrsa -out client_key.pem 2048

openssl req -new -x509 -key client_key.pem -out client.der -outform DER -days 365 \
  -subj "/CN=s7py-client/O=MeineFirma/C=DE"
```

| Datei | Verwendung |
|-------|------------|
| `client.der` | öffentlicher Teil → in TIA importieren |
| `client_key.pem` | privater Schlüssel → nur in s7py, **nicht** weitergeben |

## 3. Client-Zertifikat in TIA vertrauenswürdig machen

1. TIA Portal → **Online** → mit SPS verbinden
2. CPU → **Eigenschaften** → **OPC UA** → **Zertifikate**
3. **Vertrauenswürdige Clients** / **Partnerzertifikate**
4. **Importieren** → `client.der` wählen
5. Zertifikat als **vertrauenswürdig** markieren
6. Änderungen **in Gerät laden**

## 4. s7py konfigurieren

In `s7py_db.json` (im s7py-Datenverzeichnis):

```json
{
  "plc_transport": "opcua",
  "opcua_endpoint": "opc.tcp://192.168.0.10:4840",
  "opcua_client_cert": "/Users/ihrname/s7py-opcua-certs/client.der",
  "opcua_client_key": "/Users/ihrname/s7py-opcua-certs/client_key.pem"
}
```

s7py neu starten → **Verbinden**.

Bei gesichertem Endpoint wählt s7py automatisch einen passenden Server-Endpoint, sofern das Zertifikat in TIA hinterlegt ist.

---

# Typische Fehler

| Meldung | Ursache | Lösung |
|---------|---------|--------|
| `BadSecurityPolicyRejected` | Policy „None“ nicht erlaubt | Weg A Schritt 2, oder Weg B mit Zertifikat |
| `Connection refused` | Server aus / falscher Port | SPS RUN, Port 4840, Firewall prüfen |
| Verbindung OK, keine Werte | Keine NodeIds | Variablen OPC-UA-fähig machen, Schema in s7py pflegen |
| `BadIdentityTokenRejected` / `BadUserAccessDenied` | Falscher Benutzer/Passwort | TIA-Benutzerverwaltung und s7py-Zugangsdaten pruefen |
| Zertifikat abgelehnt | Client nicht vertrauenswürdig | `client.der` in TIA importieren |
| `asyncua` fehlt | falsche Python-Umgebung | `python -m pip install asyncua` mit dem s7py-Interpreter |

---

# Checkliste

- [ ] OPC-UA-Server an der S7-1500 aktiviert
- [ ] Projekt geladen, SPS in **RUN**
- [ ] IP-Adresse der SPS bekannt
- [ ] Security Policy passend (None **oder** Zertifikat + Basic256Sha256)
- [ ] Anonym oder Benutzer/Passwort konfiguriert
- [ ] Endpoint in s7py: `opc.tcp://<IP>:4840`
- [ ] OPC-UA-Variablen mit NodeIds in s7py hinterlegt
- [ ] `asyncua` in der s7py-Python-Umgebung installiert

---

# Empfohlene Reihenfolge

1. **Weg A** — Verbindung ohne Zertifikat testen
2. Bei Login-Pflicht **Weg C** — Benutzer/Passwort in s7py
3. Optional **UaExpert** — Endpoints und NodeIds pruefen
4. **s7py** — Variablen anlegen und Werte lesen
5. **Weg B** — fuer Dauerbetrieb Zertifikate und restriktive Policies nutzen
