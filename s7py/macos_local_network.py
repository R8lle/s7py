"""macOS Lokales-Netzwerk: Privacy-Dialog anstossen (TN3179), ohne UI zu blockieren."""

from __future__ import annotations

import random
import socket
import sys
import time
from urllib.parse import urlparse


def is_frozen_macos_app() -> bool:
    return sys.platform == "darwin" and bool(getattr(sys, "frozen", False))


def trigger_local_network_privacy_alert() -> None:
    """UDP-connect auf Link-Local — loest den macOS-Dialog aus, ohne Traffic."""
    if not is_frozen_macos_app():
        return
    try:
        for host in _link_local_ipv4_targets() + _link_local_ipv6_targets():
            family = socket.AF_INET6 if ":" in str(host[0]) else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_DGRAM, 0)
            try:
                sock.settimeout(0.05)
                sock.connect(host)
            except OSError:
                pass
            finally:
                sock.close()
    except Exception:
        return


def opc_endpoint_host_port(endpoint_url: str) -> tuple[str, int]:
    raw = (endpoint_url or "").strip()
    if not raw:
        return "", 4840
    parsed = urlparse(raw if "://" in raw else f"opc.tcp://{raw}")
    return parsed.hostname or "", int(parsed.port or 4840)


def connect_with_local_network_retry(connect_fn, *, attempts: int = 2, delay_s: float = 0.8):
    """Kurzer Retry bei Errno 65 — kein langes Blockieren der UI."""
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return connect_fn()
        except Exception as exc:
            if not _is_errno_65(exc):
                raise
            last_exc = exc
            if attempt >= attempts:
                raise
            time.sleep(delay_s)
            trigger_local_network_privacy_alert()
    if last_exc:
        raise last_exc
    return None


def _is_errno_65(exc: BaseException) -> bool:
    root: BaseException | None = exc
    while root is not None:
        if isinstance(root, OSError) and (
            getattr(root, "errno", None) == 65
            or "no route to host" in str(root).lower()
        ):
            return True
        root = getattr(root, "__cause__", None) or getattr(root, "__context__", None)
    return False


def _link_local_ipv4_targets() -> list[tuple[str, int]]:
    targets: list[tuple[str, int]] = [("169.254.1.1", 9)]
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("1.1.1.1", 80))
            local_ip = probe.getsockname()[0]
        finally:
            probe.close()
        if local_ip and not local_ip.startswith("127."):
            parts = local_ip.split(".")
            if len(parts) == 4:
                targets.append((f"{parts[0]}.{parts[1]}.{parts[2]}.1", 9))
    except OSError:
        pass
    return targets


def _link_local_ipv6_targets() -> list[tuple]:
    out: list[tuple] = []
    try:
        for _ in range(2):
            host = "fe80::" + ":".join(f"{random.randint(0, 0xFFFF):x}" for _ in range(4))
            out.append((host, 9, 0, 0))
    except Exception:
        pass
    return out
