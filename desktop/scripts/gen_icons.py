#!/usr/bin/env python3
"""Generate SztuCode brand icons (terminal prompt style, pure color).

Writes into desktop/src-tauri/icons/: 32x32.png, 128x128.png,
128x128@2x.png, icon.ico and a 1024px source icon.png.

Run: python desktop/scripts/gen_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
INK = (28, 35, 48, 255)  # #1c2330
BACK = (244, 246, 250, 255)  # #f4f6fa

OUT = Path(__file__).resolve().parent.parent / "src-tauri" / "icons"


def draw_terminal(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    # base: rounded square, dark
    d.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=210, fill=BACK)
    # window frame
    frame = [192, 208, 831, 815]
    d.rounded_rectangle(frame, radius=112, outline=INK, width=58)
    # title bar dots
    for cx in (296, 388, 480):
        d.ellipse([cx - 32, 288, cx + 32, 352], fill=(INK[0], INK[1], INK[2], 205))
    # paired rounded eyes
    d.rounded_rectangle([314, 405, 431, 580], radius=52, fill=INK)
    d.rounded_rectangle([489, 405, 606, 580], radius=52, fill=INK)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw_terminal(src)
    src.save(OUT / "icon.png")
    src.resize((256, 256), Image.LANCZOS).save(OUT / "128x128@2x.png")
    src.resize((128, 128), Image.LANCZOS).save(OUT / "128x128.png")
    src.resize((32, 32), Image.LANCZOS).save(OUT / "32x32.png")
    # Windows ICO with common sizes
    src.save(
        OUT / "icon.ico",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
