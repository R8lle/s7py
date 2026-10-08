"""Einstiegspunkt: python -m s7py"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--selftest":
        from s7py.selftest import run_selftest

        report = args[1] if len(args) > 1 else "selftest.txt"
        raise SystemExit(run_selftest(report))

    import matplotlib

    matplotlib.use("TkAgg")

    from s7py.app import S7PyApp

    S7PyApp().mainloop()


if __name__ == "__main__":
    main()
