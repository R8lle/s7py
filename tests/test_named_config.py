"""Tests fuer benannte Konfigurationen unter APP_DIR/configs/."""

from __future__ import annotations

import json

import pytest


def test_sanitize_config_name_basic():
    from s7py.named_config import sanitize_config_name

    assert sanitize_config_name("  Linie 1  ") == "Linie 1"
    assert sanitize_config_name("Werk-A_OPC") == "Werk-A_OPC"


def test_sanitize_config_name_strips_unsafe():
    from s7py.named_config import sanitize_config_name

    assert sanitize_config_name("a/b\\c:d*") == "abcd"
    with pytest.raises(ValueError):
        sanitize_config_name("///")


def test_save_load_roundtrip(tmp_path, monkeypatch):
    from s7py.named_config import (
        ACTIVE_CONFIG_NAME_KEY,
        list_named_configs,
        load_named_config,
        save_named_config,
    )

    monkeypatch.setattr("s7py.constants.APP_DIR", tmp_path)

    payload = {
        "plc_transport": "opcua",
        "opcua_endpoint": "opc.tcp://10.0.0.1:4840",
        "plc_structure_opcua": {"block_name": "Demo", "items": []},
        "last_database": "demo.db",
    }
    path = save_named_config("Anlage Ost", payload)
    assert path.is_file()
    assert path.parent.name == "configs"
    assert path.name == "Anlage Ost.json"

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert "meta" in stored
    assert stored["meta"]["name"] == "Anlage Ost"
    assert stored["plc_transport"] == "opcua"

    name, body = load_named_config("Anlage Ost")
    assert name == "Anlage Ost"
    assert ACTIVE_CONFIG_NAME_KEY in body
    assert body["plc_transport"] == "opcua"
    assert "meta" not in body

    listed = list_named_configs()
    assert len(listed) == 1
    assert listed[0][0] == "Anlage Ost"
    assert listed[0][1] == path


def test_overwrite_keeps_latest(tmp_path, monkeypatch):
    from s7py.named_config import load_named_config, save_named_config

    monkeypatch.setattr("s7py.constants.APP_DIR", tmp_path)
    save_named_config("Test", {"v": 1})
    save_named_config("Test", {"v": 2, "plc_transport": "snap7"})
    _name, body = load_named_config("Test")
    assert body["v"] == 2
    assert body["plc_transport"] == "snap7"


def test_rename_and_delete(tmp_path, monkeypatch):
    from s7py.named_config import (
        delete_named_config,
        list_named_configs,
        load_named_config,
        rename_named_config,
        save_named_config,
    )

    monkeypatch.setattr("s7py.constants.APP_DIR", tmp_path)
    save_named_config("Alt", {"plc_transport": "snap7", "x": 1})
    new_path = rename_named_config("Alt", "Neu")
    assert new_path.name == "Neu.json"
    assert not (tmp_path / "configs" / "Alt.json").exists()
    name, body = load_named_config("Neu")
    assert name == "Neu"
    assert body["x"] == 1

    save_named_config("Andere", {"y": 2})
    with pytest.raises(FileExistsError):
        rename_named_config("Neu", "Andere")

    delete_named_config("Neu")
    assert [item[0] for item in list_named_configs()] == ["Andere"]
