"""Einstiegspunkt: python -m s7py"""

import matplotlib

matplotlib.use("TkAgg")

from s7py.app import S7PyApp


def main() -> None:
    S7PyApp().mainloop()


if __name__ == "__main__":
    main()
