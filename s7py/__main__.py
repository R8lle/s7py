"""Einstiegspunkt: python -m s7py"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--selftest":
        from s7py.selftest import run_selftest

        report = args[1] if len(args) > 1 else "selftest.txt"
        raise SystemExit(run_selftest(report))

    # macOS-.app: LAN-Privacy-Dialog frueh anstossen (sonst Errno 65 ohne Eintrag).
    try:
        from s7py.macos_local_network import (
            is_frozen_macos_app,
            trigger_local_network_privacy_alert,
        )

        if is_frozen_macos_app():
            trigger_local_network_privacy_alert()
    except Exception:
        pass

    import matplotlib

    matplotlib.use("TkAgg")

    try:
        from s7py.app import S7PyApp

        S7PyApp().mainloop()
    except Exception as exc:  # noqa: BLE001 - Startfehler sichtbar machen
        import traceback

        msg = f"s7py Start fehlgeschlagen: {exc}\n{traceback.format_exc()}"
        print(msg, file=sys.stderr)
        try:
            from s7py.constants import APP_DIR

            crash = APP_DIR / "crash.log"
            crash.write_text(msg, encoding="utf-8")
            print(f"Details: {crash}", file=sys.stderr)
        except Exception:
            pass
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
