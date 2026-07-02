"""Tests fuer OPC-UA-Fehlerklassifizierung."""

import importlib.util

import pytest

from s7py.opcua_import import (
    OpcUaConnectionError,
    OpcUaDependencyError,
    asyncua_is_installed,
    format_opcua_connect_error,
    import_opcua_client_class,
    wrap_opcua_connect_error,
)


class TestOpcUaImport:
    def test_asyncua_is_installed_false_when_missing(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        assert asyncua_is_installed() is False

    def test_dependency_error_when_package_missing(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        with pytest.raises(OpcUaDependencyError) as exc_info:
            import_opcua_client_class()
        message = str(exc_info.value)
        assert "nicht installiert" in message
        assert "pip install asyncua" in message

    def test_connection_refused_is_not_dependency_error(self):
        exc = ConnectionRefusedError(61, "Connection refused")
        message = format_opcua_connect_error(exc, "opc.tcp://192.168.0.10:4840")
        assert "nicht erreichbar" in message
        assert "192.168.0.10:4840" in message
        assert "asyncua" not in message.lower()
        assert "nicht installiert" not in message

    def test_timeout_is_not_dependency_error(self):
        exc = TimeoutError("timed out")
        message = format_opcua_connect_error(exc, "opc.tcp://127.0.0.1:4840")
        assert "nicht erreichbar" in message
        assert "asyncua" not in message.lower()

    def test_wrap_opcua_connect_error(self):
        exc = OSError("[Errno 61] Connection refused")
        wrapped = wrap_opcua_connect_error(exc, "opc.tcp://127.0.0.1:4840")
        assert isinstance(wrapped, OpcUaConnectionError)
        assert "nicht erreichbar" in str(wrapped)

    @pytest.mark.skipif(not asyncua_is_installed(), reason="asyncua nicht installiert")
    def test_import_client_when_asyncua_present(self):
        client_cls = import_opcua_client_class()
        assert client_cls is not None
