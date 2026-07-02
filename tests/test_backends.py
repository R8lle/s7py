"""Tests fuer SPS-Backend-Abstraktion."""

from s7py.backends.factory import create_backend
from s7py.backends.snap7 import Snap7Backend
from s7py.backends.opcua import OpcUaBackend
from s7py.constants import PLC_TRANSPORT_OPCUA, PLC_TRANSPORT_SNAP7
from s7py.db import (
    load_plc_transport,
    normalize_plc_transport,
    save_plc_transport,
)


class TestPlcTransportConfig:
    def test_normalize_defaults_to_snap7(self):
        assert normalize_plc_transport(None) == PLC_TRANSPORT_SNAP7
        assert normalize_plc_transport("unknown") == PLC_TRANSPORT_SNAP7

    def test_normalize_opcua_aliases(self):
        assert normalize_plc_transport("opcua") == PLC_TRANSPORT_OPCUA
        assert normalize_plc_transport("OPC UA") == PLC_TRANSPORT_OPCUA

    def test_save_and_load(self, tmp_path, monkeypatch):
        cfg = tmp_path / "s7py_db.json"
        monkeypatch.setattr("s7py.db.DB_CONFIG_PATH", str(cfg))
        save_plc_transport(PLC_TRANSPORT_OPCUA)
        assert load_plc_transport() == PLC_TRANSPORT_OPCUA


class TestBackendFactory:
    def test_create_snap7(self):
        backend = create_backend(PLC_TRANSPORT_SNAP7)
        assert isinstance(backend, Snap7Backend)
        assert backend.transport == PLC_TRANSPORT_SNAP7

    def test_create_opcua(self):
        backend = create_backend(PLC_TRANSPORT_OPCUA)
        assert isinstance(backend, OpcUaBackend)
        assert backend.transport == PLC_TRANSPORT_OPCUA

    def test_snap7_status_detail(self):
        backend = Snap7Backend()
        text = backend.status_detail(
            "192.168.0.10", rack=0, slot=1, db_number=30
        )
        assert "192.168.0.10" in text
        assert "DB30" in text
