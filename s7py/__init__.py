"""s7py — SPS lesen, SQLite speichern, Live-Diagramm."""

from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.9.0"
COPYRIGHT = "© 2026 R@lle (R8lle)"
LICENSE_NAME = "MIT License"

__all__ = ["S7PyApp", "__version__", "COPYRIGHT", "LICENSE_NAME"]

if TYPE_CHECKING:
    from s7py.app import S7PyApp as S7PyApp


def __getattr__(name: str):
    if name == "S7PyApp":
        from s7py.app import S7PyApp as app_cls

        return app_cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
