"""
Make the staff favicon: the Elyria logo mark in white on a rounded maroon square.
Run once, then commit the PNG:  poetry run python scripts/make_staff_favicon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "static/front/assets/logo-head.png"
TARGET = ROOT / "static/back/assets/images/favicon-staff.png"

SIZE = 180          # big enough for browsers and phone home screens
MAROON = (110, 20, 35, 255)
MARK = (255, 255, 255, 255)   # white; use (201, 162, 39, 255) for gold
PADDING = 0.18      # space around the mark, as a share of the size
RADIUS = 0.22       # corner rounding

# Rounded maroon square
icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(icon).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=int(SIZE * RADIUS), fill=MAROON)

# The logo mark, recoloured: keep its shape (alpha), paint it white
logo = Image.open(SOURCE).convert("RGBA")
logo = logo.crop(logo.getbbox())                       # trim empty edges
inner = int(SIZE * (1 - 2 * PADDING))
logo.thumbnail((inner, inner), Image.LANCZOS)
mark = Image.new("RGBA", logo.size, MARK)
mark.putalpha(logo.getchannel("A"))

icon.alpha_composite(mark, ((SIZE - logo.width) // 2, (SIZE - logo.height) // 2))
TARGET.parent.mkdir(parents=True, exist_ok=True)
icon.save(TARGET)
print(f"Saved {TARGET.relative_to(ROOT)}")