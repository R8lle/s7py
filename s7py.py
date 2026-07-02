"""s7py-Starter (delegiert an das Paket ``s7py``)."""

import matplotlib

matplotlib.use("TkAgg")

from s7py.__main__ import main

if __name__ == "__main__":
    main()
