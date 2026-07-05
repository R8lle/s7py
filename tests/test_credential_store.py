"""Tests fuer verschluesselte Credential-Speicherung."""

import json

from s7py.credential_store import (
    OPCUA_PASSWORD_ENC_KEY,
    OPCUA_PASSWORD_PLAIN_KEY,
    decrypt_secret,
    encrypt_secret,
    migrate_plaintext_secrets,
)


class TestCredentialStore:
    def test_encrypt_decrypt_roundtrip(self, tmp_path, monkeypatch):
        key_file = tmp_path / ".s7py_key"
        monkeypatch.setattr("s7py.credential_store.KEY_FILE", key_file)

        enc = encrypt_secret("geheim")
        assert enc.startswith("enc:v1:")
        assert decrypt_secret(enc) == "geheim"

    def test_migrate_plaintext_removes_opcua_password(self, tmp_path, monkeypatch):
        key_file = tmp_path / ".s7py_key"
        monkeypatch.setattr("s7py.credential_store.KEY_FILE", key_file)

        config = {"opcua_username": "user", "opcua_password": "secret"}
        assert migrate_plaintext_secrets(config) is True
        assert OPCUA_PASSWORD_PLAIN_KEY not in config
        assert OPCUA_PASSWORD_ENC_KEY in config
        assert decrypt_secret(config[OPCUA_PASSWORD_ENC_KEY]) == "secret"

    def test_save_opcua_credentials_no_plaintext(self, tmp_path, monkeypatch):
        from s7py import db as db_mod

        app = tmp_path / "app"
        app.mkdir()
        cfg = app / "s7py_db.json"
        key_file = app / ".s7py_key"
        monkeypatch.setattr(db_mod, "APP_DIR", app)
        monkeypatch.setattr(db_mod, "DB_CONFIG_PATH", str(cfg))
        monkeypatch.setattr("s7py.credential_store.KEY_FILE", key_file)

        db_mod.save_opcua_credentials("Awm1", "meinPasswort")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data["opcua_username"] == "Awm1"
        assert "opcua_password" not in data
        assert "opcua_password_enc" in data
        assert db_mod.load_opcua_password() == "meinPasswort"
