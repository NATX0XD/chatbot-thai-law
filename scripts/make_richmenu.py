# -*- coding: utf-8 -*-
"""Draw the LINE rich menu image in the bot's own colours.

Three cells, drawn rather than generated: a rich menu is rendered at roughly the
width of the chat column, so on a phone each cell is about 120 px wide. At that
size an illustration turns to mush and lettering has to be geometric, which is
why the icons here are primitives and the labels are one short Thai word each.

Colours come from assets/profile_c.png -- the maroon field is 80.7% of the logo
and the cream of the scales is 8.5% -- so the menu, the profile picture and the
web chat all read as one thing.

    python scripts/make_richmenu.py

Writes assets/richmenu/richmenu-2500.png (LINE's compact size) and a 1200 px
copy for the smaller layout. Both are well under LINE's 1 MB limit.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 2500, 843
SS = 3                                  # supersample the shapes, not the text
CELLS = 3

MAROON_TOP = (0x83, 0x26, 0x3A)
MAROON_BOT = (0x58, 0x17, 0x24)
CREAM = (0xF6, 0xE9, 0xD8)
INK = (0x5C, 0x19, 0x26)                # the "?" sitting on cream

FONT = "/System/Library/Fonts/Supplemental/SukhumvitSet.ttc"
BOLD, TEXT = 5, 2                       # face indexes inside the collection

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HERE, "assets", "richmenu")

MENU = [
    {"label": "ถามกฎหมาย", "caption": "พิมพ์คำถามได้เลย", "icon": "ask"},
    {"label": "ตัวอย่างคำถาม", "caption": "ไม่รู้จะเริ่มยังไง", "icon": "list"},
    {"label": "เปิดเว็บแชท", "caption": "อ่านตัวบทเต็ม", "icon": "web"},
]


def background() -> Image.Image:
    """Vertical maroon gradient, warmed slightly towards the middle cell."""
    top = np.array(MAROON_TOP, dtype=np.float32)
    bot = np.array(MAROON_BOT, dtype=np.float32)
    t = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None, None]
    grad = top + (bot - top) * t                      # (H, 1, 3)
    img = np.repeat(grad, W, axis=1)

    # a wide, shallow highlight behind the centre so the strip is not flat
    x = np.linspace(-1.0, 1.0, W, dtype=np.float32)[None, :, None]
    y = np.linspace(-1.0, 1.0, H, dtype=np.float32)[:, None, None]
    glow = np.exp(-(x * x * 1.6 + y * y * 0.9) * 1.4) * 14.0
    img = np.clip(img + glow, 0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGB")


def icon_ask(d: ImageDraw.ImageDraw, x: int, y: int, s: int) -> None:
    """A speech bubble with a question mark: the thing this bot actually does."""
    d.rounded_rectangle((x, y, x + 224 * s, y + 172 * s), radius=48 * s, fill=CREAM)
    d.polygon([(x + 52 * s, y + 154 * s), (x + 52 * s, y + 224 * s),
               (x + 122 * s, y + 162 * s)], fill=CREAM)


def icon_list(d: ImageDraw.ImageDraw, x: int, y: int, s: int) -> None:
    """Three bullets: a list of ready-made questions."""
    for row, width in enumerate((196, 152, 172)):
        cy = y + (18 + row * 66) * s
        d.ellipse((x, cy, x + 28 * s, cy + 28 * s), fill=CREAM)
        d.rounded_rectangle((x + 56 * s, cy + 2 * s,
                             x + (56 + width) * s, cy + 26 * s),
                            radius=12 * s, fill=CREAM)


def icon_web(d: ImageDraw.ImageDraw, x: int, y: int, s: int) -> None:
    """A screen: this cell opens the web chat instead of sending a message."""
    d.rounded_rectangle((x, y, x + 228 * s, y + 152 * s), radius=26 * s,
                        outline=CREAM, width=18 * s)
    for row, width in enumerate((132, 92)):
        top = y + (48 + row * 40) * s
        d.rounded_rectangle((x + 48 * s, top, x + (48 + width) * s, top + 20 * s),
                            radius=10 * s, fill=CREAM)
    d.rounded_rectangle((x + 100 * s, y + 152 * s, x + 128 * s, y + 186 * s), fill=CREAM)
    d.rounded_rectangle((x + 56 * s, y + 186 * s, x + 172 * s, y + 208 * s),
                        radius=11 * s, fill=CREAM)


ICONS = {"ask": (icon_ask, 224, 224),
         "list": (icon_list, 252, 178),
         "web": (icon_web, 228, 208)}

ICON_BOX = 224          # every icon is centred in a box this tall
ICON_TOP = 252          # where that box starts, in final pixels
LABEL_TOP = 528
CAPTION_TOP = 638


def draw_shapes(img: Image.Image) -> Image.Image:
    """Icons and dividers, drawn large and shrunk so the curves are smooth."""
    layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    for i in range(1, CELLS):
        x = round(W * i / CELLS) * SS
        d.rectangle((x - 2 * SS, 168 * SS, x + 1 * SS, (H - 168) * SS),
                    fill=CREAM + (54,))

    for i, item in enumerate(MENU):
        cx = (i + 0.5) * W / CELLS
        fn, iw, ih = ICONS[item["icon"]]
        x = round((cx - iw / 2) * SS)
        y = round((ICON_TOP + (ICON_BOX - ih) / 2) * SS)
        fn(d, x, y, SS)

    layer = layer.resize((W, H), Image.LANCZOS)
    img = img.convert("RGBA")
    img.alpha_composite(layer)
    return img.convert("RGB")


def draw_text(img: Image.Image) -> None:
    """Labels at final resolution -- downsampling glyphs only makes them soft."""
    d = ImageDraw.Draw(img)
    label_font = ImageFont.truetype(FONT, 82, index=BOLD)
    caption_font = ImageFont.truetype(FONT, 46, index=TEXT)

    # the "?" sits inside the bubble drawn by icon_ask, in maroon on cream
    mark_font = ImageFont.truetype(FONT, 108, index=BOLD)
    d.text((W / CELLS * 0.5, ICON_TOP + 86), "?", font=mark_font,
           fill=INK, anchor="mm")

    for i, item in enumerate(MENU):
        cx = (i + 0.5) * W / CELLS
        d.text((cx, LABEL_TOP), item["label"], font=label_font,
               fill=(255, 255, 255), anchor="ma")
        d.text((cx, CAPTION_TOP), item["caption"], font=caption_font,
               fill=(0xD8, 0xB6, 0xB9), anchor="ma")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    img = draw_shapes(background())
    draw_text(img)

    big = os.path.join(OUT_DIR, "richmenu-2500.png")
    img.save(big, optimize=True)
    small = os.path.join(OUT_DIR, "richmenu-1200.png")
    img.resize((1200, 405), Image.LANCZOS).save(small, optimize=True)

    for path in (big, small):
        print(f"{os.path.relpath(path, HERE)}  "
              f"{Image.open(path).size}  {os.path.getsize(path) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
