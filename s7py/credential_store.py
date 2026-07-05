"""Verschluesselte Speicherung sensibler Config-Werte (OPC-UA-Passwoerter)."""

from __future__ import annotations

import os
from pathlib import Path

from s7py.constants import APP_DIR

ENC_PREFIX = "enc:v1:"
KEY_FILE = APP_DIR / ".s7py_key"

OPCUA_PASSWORD_ENC_KEY = "opcua_password_enc"
OPCUA_PASSWORD_PLAIN_KEY = "opcua_password"
OPCUA_CLIENT_KEY_PASSWORD_ENC_KEY = "opcua_client_key_password_enc"
OPCUA_CLIENT_KEY_PASSWORD_PLAIN_KEY = "opcua_client_key_password"


def _fernet():
    from cryptography.fernet import Fernet

    if KEY_FILE.is_file():
        key = KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except OSError:
            pass
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    """Klartext fuer die JSON-Config verschluesseln."""
    if not plain:
        return ""
    token = _fernet().encrypt(plain.encode("utf-8"))
    return ENC_PREFIX + token.decode("ascii")


def decrypt_secret(stored: str) -> str:
    """Gespeicherten Wert entschluesseln (inkl. Legacy-Klartext)."""
    value = str(stored or "")
    if not value:
        return ""
    if value.startswith(ENC_PREFIX):
        token = value[len(ENC_PREFIX) :].encode("ascii")
        return _fernet().decrypt(token).decode("utf-8")
    return value


def load_stored_secret(config: dict, *, plain_key: str, enc_key: str) -> str:
    """Verschluesselten oder Legacy-Klartext-Wert aus der Config lesen."""
    enc = str(config.get(enc_key, "") or "")
    if enc:
        try:
            return decrypt_secret(enc)
        except Exception:
            return ""
    return str(config.get(plain_key, "") or "")


def store_secret_in_config(
    config: dict,
    *,
    plain_key: str,
    enc_key: str,
    value: str,
) -> None:
    """Wert verschluesselt speichern und Klartext-Schluessel entfernen."""
    secret = value or ""
    if secret:
        config[enc_key] = encrypt_secret(secret)
    else:
        config.pop(enc_key, None)
    config.pop(plain_key, None)


def migrate_plaintext_secrets(config: dict) -> bool:
    """Legacy-Klartext in der Config verschluesseln. True wenn geaendert."""
    changed = False
    for plain_key, enc_key in (
        (OPCUA_PASSWORD_PLAIN_KEY, OPCUA_PASSWORD_ENC_KEY),
        (OPCUA_CLIENT_KEY_PASSWORD_PLAIN_KEY, OPCUA_CLIENT_KEY_PASSWORD_ENC_KEY),
    ):
        plain = str(config.get(plain_key, "") or "")
        if not plain:
            if plain_key in config:
                config.pop(plain_key, None)
                changed = True
            continue
        if not config.get(enc_key):
            config[enc_key] = encrypt_secret(plain)
            changed = True
        config.pop(plain_key, None)
        changed = True
    return changed
