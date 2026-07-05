#!/usr/bin/env python3
"""OPC-UA-Verbindung im Terminal testen.

Aufruf aus dem s7py-Verzeichnis:
  ../.venv/bin/python opcua_diagnose.py
  ../.venv/bin/python opcua_diagnose.py --all
  ../.venv/bin/python opcua_diagnose.py opc.tcp://10.0.0.1:4840 --user U --password P
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from asyncua import ua
from asyncua.sync import Client

from s7py.db import load_opcua_security_config, merge_opcua_security_config
from s7py.opcua_connect import (
    NONE_POLICY_URI,
    OpcUaSecurityConfig,
    _apply_client_identity,
    _apply_none_policy,
    _endpoint_summary,
    _policy_class_for_uri,
    _server_offers_none_policy,
    connect_opcua_sync_client,
    select_endpoint,
)

CONNECT_TIMEOUT_S = 15
TEST_NODE = 'ns=3;s="SnapDB"."Count"'


@dataclass
class TestResult:
    name: str
    status: str  # OK | FEHLER | UEBERSPRUNGEN
    detail: str = ""


def _policy_name(endpoint: Any) -> str:
    uri = str(getattr(endpoint, "SecurityPolicyUri", "") or "")
    return uri.rsplit("#", 1)[-1] if uri else "?"


def _mode_name(endpoint: Any) -> str:
    return getattr(getattr(endpoint, "SecurityMode", None), "name", "?")


def _read_test_value(client: Client) -> str:
    try:
        val = client.get_node(TEST_NODE).read_value()
        return f"Lesen {TEST_NODE}: {val!r}"
    except Exception as exc:
        return f"Verbunden, Lesen fehlgeschlagen: {type(exc).__name__}: {exc}"


def _run_test(name: str, fn: Callable[[], str]) -> TestResult:
    try:
        detail = fn()
        return TestResult(name, "OK", detail)
    except Exception as exc:
        return TestResult(name, "FEHLER", f"{type(exc).__name__}: {exc}")


def _client(url: str) -> Client:
    return Client(url, timeout=CONNECT_TIMEOUT_S)


def _disconnect_quiet(client: Client | None) -> None:
    if client is None:
        return
    try:
        client.disconnect()
    except Exception:
        pass


def _connect_secure(
    url: str,
    endpoint: Any,
    *,
    cert_path: str,
    key_path: str,
    security: OpcUaSecurityConfig,
    identity: str,
) -> str:
    """identity: 'anonymous' | 'username'"""
    client = _client(url)
    try:
        policy_cls = _policy_class_for_uri(str(endpoint.SecurityPolicyUri or ""))
        if policy_cls is None:
            raise RuntimeError(f"Unbekannte Policy: {endpoint.SecurityPolicyUri}")
        if identity == "username":
            if not security.has_credentials():
                raise RuntimeError("Kein Benutzer konfiguriert")
            _apply_client_identity(client, security)
        client.set_security(
            policy_cls,
            cert_path,
            key_path,
            None,
            endpoint.ServerCertificate,
            endpoint.SecurityMode,
        )
        client.connect()
        return _read_test_value(client)
    finally:
        _disconnect_quiet(client)


def run_all_tests(
    url: str,
    sec: OpcUaSecurityConfig,
    endpoints: list[Any],
) -> list[TestResult]:
    results: list[TestResult] = []

    results.append(
        TestResult(
            "0. Server-Endpoints",
            "INFO",
            f"{len(endpoints)} Endpoint(s), Policy None: "
            f"{'ja' if _server_offers_none_policy(endpoints) else 'NEIN'}",
        )
    )
    for i, ep in enumerate(endpoints, 1):
        results.append(
            TestResult(f"   Endpoint {i}", "INFO", _endpoint_summary(ep))
        )

    # --- Weg A: Anonym Schnellversuch ---
    def test_anon_quick() -> str:
        c = _client(url)
        try:
            c.connect()
            return _read_test_value(c)
        finally:
            _disconnect_quiet(c)

    results.append(_run_test("1. Anonym — Schnellverbindung (ohne Endpoint-Auswahl)", test_anon_quick))

    # --- Weg A2: s7py anonym ---
    def test_s7py_anon() -> str:
        anon = OpcUaSecurityConfig()
        client, info = connect_opcua_sync_client(url, security=anon)
        try:
            return info.log_message() + " | " + _read_test_value(client)
        finally:
            _disconnect_quiet(client)

    results.append(_run_test("2. s7py — anonym (voller Connect-Flow)", test_s7py_anon))

    # --- Weg C: User/Pass + Policy None ---
    def test_s7py_user_none() -> str:
        if not sec.has_credentials():
            raise RuntimeError("Kein Benutzer in Config/Argumenten")
        if not _server_offers_none_policy(endpoints):
            raise RuntimeError("Server bietet keine Policy None")
        client, info = connect_opcua_sync_client(url, security=sec)
        try:
            return info.log_message() + " | " + _read_test_value(client)
        finally:
            _disconnect_quiet(client)

    if not sec.has_credentials():
        results.append(
            TestResult("3. s7py — Benutzer/Passwort + Policy None", "UEBERSPRUNGEN", "Kein Benutzer")
        )
    elif not _server_offers_none_policy(endpoints):
        results.append(
            TestResult(
                "3. s7py — Benutzer/Passwort + Policy None",
                "UEBERSPRUNGEN",
                "Policy None am Server nicht verfuegbar",
            )
        )
    else:
        results.append(_run_test("3. s7py — Benutzer/Passwort + Policy None", test_s7py_user_none))

    # --- Weg C ohne None: nur User/Pass ---
    def test_s7py_user_only() -> str:
        client, info = connect_opcua_sync_client(url, security=sec)
        try:
            return info.log_message() + " | " + _read_test_value(client)
        finally:
            _disconnect_quiet(client)

    if not sec.has_credentials():
        results.append(
            TestResult("4. s7py — nur Benutzer/Passwort (ohne Zertifikat)", "UEBERSPRUNGEN", "Kein Benutzer")
        )
    else:
        results.append(
            _run_test("4. s7py — nur Benutzer/Passwort (ohne Zertifikat)", test_s7py_user_only)
        )

    # --- Weg B: konfiguriertes Client-Zertifikat ---
    def test_s7py_with_config_certs() -> str:
        if not sec.has_certs():
            raise RuntimeError("Kein Zertifikat in s7py_db.json")
        client, info = connect_opcua_sync_client(url, security=sec)
        try:
            return info.log_message() + " | " + _read_test_value(client)
        finally:
            _disconnect_quiet(client)

    if sec.has_certs():
        label = "5. s7py — Benutzer/Passwort + Zertifikat aus s7py_db.json"
        if sec.has_credentials():
            results.append(_run_test(label, test_s7py_with_config_certs))
        else:
            def test_certs_anon() -> str:
                csec = OpcUaSecurityConfig(
                    client_cert=sec.client_cert,
                    client_key=sec.client_key,
                    client_key_password=sec.client_key_password,
                )
                client, info = connect_opcua_sync_client(url, security=csec)
                try:
                    return info.log_message() + " | " + _read_test_value(client)
                finally:
                    _disconnect_quiet(client)

            results.append(_run_test("5. s7py — Zertifikat aus s7py_db.json (anonym)", test_certs_anon))
    else:
        results.append(
            TestResult(
                "5. s7py — Zertifikat aus s7py_db.json",
                "UEBERSPRUNGEN",
                "opcua_client_cert/key nicht konfiguriert",
            )
        )

    # --- Manuell: None-Endpoint anonym / User ---
    none_eps = [
        ep
        for ep in endpoints
        if str(getattr(ep, "SecurityPolicyUri", "") or "") == NONE_POLICY_URI
    ]
    if none_eps:
        ep = none_eps[0]

        def test_none_anon_manual() -> str:
            c = _client(url)
            try:
                _apply_none_policy(c, ep)
                c.connect()
                return _read_test_value(c)
            finally:
                _disconnect_quiet(c)

        results.append(
            _run_test("6. Manuell — Policy None, anonym", test_none_anon_manual)
        )

        if sec.has_credentials():

            def test_none_user_manual() -> str:
                c = _client(url)
                try:
                    _apply_none_policy(c, ep)
                    _apply_client_identity(c, sec)
                    c.connect()
                    return _read_test_value(c)
                finally:
                    _disconnect_quiet(c)

            results.append(
                _run_test("7. Manuell — Policy None, Benutzer/Passwort", test_none_user_manual)
            )
    else:
        results.append(
            TestResult("6. Manuell — Policy None, anonym", "UEBERSPRUNGEN", "Kein None-Endpoint")
        )
        results.append(
            TestResult(
                "7. Manuell — Policy None, Benutzer/Passwort",
                "UEBERSPRUNGEN",
                "Kein None-Endpoint",
            )
        )

    # --- Gesicherte Endpoints: selbstsigniertes Zertifikat ---
    secure_eps = [
        ep
        for ep in endpoints
        if str(getattr(ep, "SecurityPolicyUri", "") or "") != NONE_POLICY_URI
        and _policy_class_for_uri(str(ep.SecurityPolicyUri or "")) is not None
    ]

    if not secure_eps:
        results.append(
            TestResult(
                "8+. Gesicherte Endpoints",
                "UEBERSPRUNGEN",
                "Keine unterstuetzten Secure-Policies",
            )
        )
        return results

    with tempfile.TemporaryDirectory(prefix="s7py_opcua_all_") as tmp:
        key = Path(tmp) / "client_key.pem"
        cert = Path(tmp) / "client_cert.der"
        host = url.split("//")[1].split(":")[0] if "//" in url else "localhost"
        gen = _client(url)
        try:
            gen.setup_self_signed_certificate(key, cert, host_name=host)
        finally:
            _disconnect_quiet(gen)
        cert_s, key_s = str(cert), str(key)

        n = 8
        for ep in secure_eps:
            label_base = f"{_policy_name(ep)} / {_mode_name(ep)}"
            pname = f"{n}. Secure anonym — {label_base} (selbstsign. Zert.)"

            def make_anon_secure(e: Any = ep) -> Callable[[], str]:
                def _t() -> str:
                    return _connect_secure(
                        url,
                        e,
                        cert_path=cert_s,
                        key_path=key_s,
                        security=sec,
                        identity="anonymous",
                    )

                return _t

            results.append(_run_test(pname, make_anon_secure()))
            n += 1

            if sec.has_credentials():
                pname_u = f"{n}. Secure User/Pass — {label_base} (selbstsign. Zert.)"

                def make_user_secure(e: Any = ep) -> Callable[[], str]:
                    def _t() -> str:
                        return _connect_secure(
                            url,
                            e,
                            cert_path=cert_s,
                            key_path=key_s,
                            security=sec,
                            identity="username",
                        )

                    return _t

                results.append(_run_test(pname_u, make_user_secure()))
                n += 1

    return results


def _print_results(results: list[TestResult]) -> int:
    ok = sum(1 for r in results if r.status == "OK")
    fail = sum(1 for r in results if r.status == "FEHLER")
    skip = sum(1 for r in results if r.status == "UEBERSPRUNGEN")
    print()
    print("=" * 70)
    print("ZUSAMMENFASSUNG")
    print("=" * 70)
    for r in results:
        if r.status == "INFO":
            print(f"  {r.name}: {r.detail}")
            continue
        mark = {"OK": "+", "FEHLER": "X", "UEBERSPRUNGEN": "-"}.get(r.status, "?")
        print(f"  [{mark}] {r.name}")
        if r.detail:
            for line in r.detail.split(" | "):
                print(f"       {line}")
    print()
    print(f"Ergebnis: {ok} OK, {fail} FEHLER, {skip} uebersprungen")
    return 0 if ok > 0 else (2 if fail > 0 else 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="OPC-UA-Diagnose fuer s7py")
    parser.add_argument("endpoint", nargs="?", default="", help="opc.tcp://IP:4840")
    parser.add_argument("--user", default="", help="Benutzer")
    parser.add_argument("--password", default=None, help="Passwort")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Alle Verbindungswege testen (anonym, User/Pass, Zertifikat, Secure)",
    )
    parser.add_argument("--verbose", action="store_true", help="Traceback bei Fehlern")
    args = parser.parse_args()

    base = load_opcua_security_config()
    url = (args.endpoint or "").strip()
    if not url:
        from s7py.db import load_opcua_endpoint

        url = load_opcua_endpoint()
    if not url:
        print("Kein Endpoint — Argument oder opcua_endpoint in s7py_db.json setzen.")
        return 1

    sec = merge_opcua_security_config(
        username=args.user or base.username,
        password=args.password if args.password is not None else base.password,
    )

    print("=" * 70)
    print("s7py OPC-UA Terminal-Diagnose" + (" — ALLE WEGE" if args.all else ""))
    print("=" * 70)
    print(f"Endpoint:   {url}")
    print(f"Benutzer:   {sec.username!r}")
    print(
        f"Passwort:   {'(gesetzt, ' + str(len(sec.password)) + ' Zeichen)' if sec.password else '(leer)'}"
    )
    print(f"Zertifikat: {'ja — ' + sec.client_cert if sec.has_certs() else 'nein'}")
    print(f"Timeout:    {CONNECT_TIMEOUT_S}s pro Versuch")
    print()

    try:
        probe = _client(url)
        endpoints = probe.connect_and_get_server_endpoints()
        _disconnect_quiet(probe)
    except Exception as exc:
        print(f"Server nicht erreichbar: {type(exc).__name__}: {exc}")
        if args.verbose:
            traceback.print_exc()
        return 1

    if args.all:
        try:
            results = run_all_tests(url, sec, endpoints)
            return _print_results(results)
        except Exception as exc:
            print(f"Testlauf abgebrochen: {exc}")
            if args.verbose:
                traceback.print_exc()
            return 1

    print("--- Endpoints vom Server ---")
    print(f"Anzahl: {len(endpoints)}")
    for i, ep in enumerate(endpoints, 1):
        print(f"  {i}. {_endpoint_summary(ep)}")
    print(f"Policy None: {'ja' if _server_offers_none_policy(endpoints) else 'NEIN'}")
    chosen = select_endpoint(endpoints, sec)
    print(
        f"s7py Auswahl: {_endpoint_summary(chosen) if chosen else 'kein passender Endpoint'}"
    )
    print()
    print("--- s7py connect_opcua_sync_client ---")
    print("(Alle Wege testen: opcua_diagnose.py --all)")
    try:
        client, info = connect_opcua_sync_client(url, security=sec)
        print("ERFOLG")
        print(info.log_message())
        _disconnect_quiet(client)
        return 0
    except Exception as exc:
        print(f"FEHLGESCHLAGEN: {exc}")
        if args.verbose:
            traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
