"""Erzeugt packaging/build/s7py.ico aus assets/s7py-robot-icon.png."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "assets" / "s7py-robot-icon.png"
OUT_DIR = ROOT / "packaging" / "build"
OUT = OUT_DIR / "s7py.ico"


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    side = min(src.size)
    left = (src.width - side) // 2
    top = (src.height - side) // 2
    square = src.crop((left, top, left + side, top + side))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    square.save(
        OUT,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"wrote {OUT} ({square.size[0]}x{square.size[1]})")


if __name__ == "__main__":
    main()
