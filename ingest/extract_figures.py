# -*- coding: utf-8 -*-
"""Cut the textbook's figures out of the scanned PDF, one file per caption.

  data/raw/network/network-basics.md   which figures exist, and on which page
  data/raw/network/network-basics.pdf  the scan those pages are read from
      -> web/figures/fig-2-3.jpg ...
         data/processed/figures_network.json

The PDF is a scan: every page is one picture, with no text layer and nothing
that says where a figure sits. What is known is the caption -- the corpus has
"รูปที่ 2.3 สายคู่บิดเกลียว" and the page it was read on -- so the page is read
again with the macOS Vision framework, this time keeping where each line is,
and the figure is taken to be whatever lies between the caption and the nearest
line of running text above it. Running text spans the column; the labels inside
a diagram do not, which is what tells the two apart.

A figure that cannot be found this way is left out and listed, not guessed at:
a wrong picture under an answer is worse than no picture.

The practical chapters print a photograph or a screenshot under each step and
caption none of them: "ขั้นตอนที่ 3 นำมาจัดเรียงสี" and then the picture of the
eight wires in order. Those are found from the page itself -- a block of ink
taller than any line of text, solid from top to bottom -- and are filed under
the step printed above them (photo-126-2.jpg, key "p126-2"). A block with no
numbered step above it is not kept: there is nothing to say what it shows.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import BASE_DIR, PROCESSED_DIR, RAW_DIR  # noqa: E402

SOURCE_PATH = os.path.join(RAW_DIR, "network", "network-basics.md")
PDF_PATH = os.path.join(RAW_DIR, "network", "network-basics.pdf")
OUT_DIR = os.path.join(BASE_DIR, "web", "figures")
INDEX_PATH = os.path.join(PROCESSED_DIR, "figures_network.json")

PAGE = re.compile(r"^<!-- หน้า (\d+) -->$")
CAPTION_LINE = re.compile(r"^รูปที่\s*\d")
# OCR sometimes runs two captions into one line; each ends where the next begins
CAPTION = re.compile(r"รูปที่\s*(\d+)\s*[.,]\s*(\d+)\s*(.*?)(?=\s*รูปที่\s*\d+\s*[.,]\s*\d|$)")
EXERCISES = re.compile(r"^แบบทดสอบ(?:ประเมิน|ประมวล)ผลการเรียนรู้\s*$")
# A caption ends where the next sentence was glued onto it by OCR.
MAX_CAPTION = 160

DPI = 130
JPEG_QUALITY = 78
# A line this wide, as a share of the text column, is running text.
BODY_LINE = 0.62
MIN_HEIGHT = 0.05     # of the page; anything flatter is not a figure
PAD = 0.008

# --- uncaptioned photographs and screenshots, all as shares of the page ---
PAPER = 250               # a pixel at least this bright is blank paper
MARGIN = (0.05, 0.93, 0.04, 0.96)   # top, bottom, left, right: page furniture
BLANK_ROWS = 0.004        # blank rows that end a band
COLUMN_GAP = 0.025        # blank columns that split a band
PHOTO_HEIGHT = 0.06
PHOTO_WIDTH = 0.15
SOLID = 0.85              # rows of the block that carry ink; text has gaps
DENSE = 0.30              # ink in the block; a paragraph is far below this
STEP = re.compile(r"^\s*(?:ขั้นตอนที่\s*\d+|\d{1,2}\s*[.)])")
MAX_STEP_TEXT = 220


def captions(lines: list[str]) -> dict[str, dict]:
    """Every figure the book captions: number -> page and caption text."""
    found: dict[str, dict] = {}
    page = 0
    for raw in lines:
        line = raw.strip()
        turned = PAGE.match(line)
        if turned:
            page = int(turned.group(1))
            continue
        if not (page and CAPTION_LINE.match(line)):
            continue
        for hit in CAPTION.finditer(line):
            number = f"{hit.group(1)}.{hit.group(2)}"
            found.setdefault(number, {"page": page,
                                      "caption": hit.group(3)[:MAX_CAPTION].strip()})
    return found


def read_lines(png: bytes) -> list[tuple[str, float, float, float, float]]:
    """(text, left, top, width, height) of every line, as shares of the page."""
    try:
        import Vision
        from Foundation import NSData
    except ImportError as exc:
        raise SystemExit("เรียก Vision ของ macOS ไม่ได้ "
                         "ติดตั้งด้วย pip install pyobjc-framework-Vision") from exc
    data = NSData.dataWithBytes_length_(png, len(png))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["th-TH", "en-US"])
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise SystemExit(f"Vision อ่านหน้าไม่ได้: {error}")
    out = []
    for obs in request.results() or []:
        best = obs.topCandidates_(1)
        if not best:
            continue
        box = obs.boundingBox()
        # Vision measures from the bottom-left corner
        top = 1.0 - (box.origin.y + box.size.height)
        out.append((str(best[0].string()), box.origin.x, top,
                    box.size.width, box.size.height))
    return sorted(out, key=lambda l: l[2])


def locate(lines, chapter: str, figure: str) -> tuple[float, float, float, float] | None:
    """(left, top, right, bottom) of the figure above this caption, or None."""
    if not lines:
        return None
    wanted = re.compile(rf"รูปที่\s*{chapter}\s*[.,]\s*{figure}(?!\d)")
    any_caption = re.compile(r"^\s*รูปที่\s*\d")
    # a line that opens with a caption, not a sentence pointing at the figure
    # ("ดังรูปที่ 2.3"); two captions can share one line
    at = next((i for i, l in enumerate(lines)
               if any_caption.match(l[0]) and wanted.search(l[0])), None)
    if at is None:
        return None
    left = min(l[1] for l in lines)
    right = max(l[1] + l[3] for l in lines)
    column = right - left
    bottom = lines[at][2]
    top = 0.04
    for text, x, y, w, h in reversed(lines[:at]):
        if y + h > bottom:
            continue    # beside the caption, not above it
        if w >= BODY_LINE * column or any_caption.match(text):
            top = y + h
            break
    if bottom - top < MIN_HEIGHT:
        return None
    return (max(0.0, left - PAD), max(0.0, top + PAD / 2),
            min(1.0, right + PAD), min(1.0, bottom - PAD / 2))


def runs(mask, gap: int) -> list[tuple[int, int]]:
    """Stretches where `mask` is on, joined across breaks no longer than `gap`."""
    found, start, last = [], None, None
    for i, on in enumerate(mask):
        if on:
            if start is None:
                start = i
            last = i
        elif start is not None and i - last > gap:
            found.append((start, last + 1))
            start = None
    if start is not None:
        found.append((start, last + 1))
    return found


def photo_blocks(gray) -> list[tuple[int, int, int, int]]:
    """(left, top, right, bottom) in pixels of each picture-like block on a page."""
    height, width = gray.shape
    ink = gray < PAPER
    top, bottom, left, right = MARGIN
    ink[:int(height * top)] = False
    ink[int(height * bottom):] = False
    ink[:, :int(width * left)] = False
    ink[:, int(width * right):] = False
    found = []
    for y0, y1 in runs(ink.sum(1) > 0, int(height * BLANK_ROWS)):
        if y1 - y0 < height * PHOTO_HEIGHT:
            continue
        band = ink[y0:y1]
        for x0, x1 in runs(band.sum(0) > 0, int(width * COLUMN_GAP)):
            if x1 - x0 < width * PHOTO_WIDTH:
                continue
            piece = band[:, x0:x1]
            inked = piece.sum(1).nonzero()[0]
            a, b = int(inked[0]), int(inked[-1]) + 1
            piece = piece[a:b]
            if b - a < height * PHOTO_HEIGHT:
                continue
            if (piece.sum(1) > 0).mean() < SOLID or piece.mean() < DENSE:
                continue
            found.append((x0, y0 + a, x1, y0 + b))
    return found


def step_above(lines, top: float) -> str:
    """The numbered step printed above a block, with the sentence under it."""
    above = [l for l in lines if l[2] + l[4] <= top + 0.005]
    at = next((i for i in range(len(above) - 1, -1, -1) if STEP.match(above[i][0])), None)
    if at is None:
        return ""
    # a caption between the step and the block means the block is that figure's
    if any(re.match(r"^\s*รูปที่\s*\d", l[0]) for l in above[at:]):
        return ""
    return " ".join(l[0].strip() for l in above[at:])[:MAX_STEP_TEXT].strip()


def inside(block, box, size) -> bool:
    """Whether most of a pixel block lies in a figure already cut (page shares)."""
    width, height = size
    x0, y0, x1, y1 = block
    bx0, by0, bx1, by1 = box[0] * width, box[1] * height, box[2] * width, box[3] * height
    w = max(0, min(x1, bx1) - max(x0, bx0))
    h = max(0, min(y1, by1) - max(y0, by0))
    return w * h > 0.5 * (x1 - x0) * (y1 - y0)


def main() -> None:
    for path in (SOURCE_PATH, PDF_PATH):
        if not os.path.exists(path):
            raise SystemExit(f"ไม่พบไฟล์ต้นทาง {path}")
    import pymupdf
    from PIL import Image

    with open(SOURCE_PATH, encoding="utf-8") as handle:
        wanted = captions(handle.read().split("\n"))
    if not wanted:
        raise SystemExit(f"ไม่พบคำบรรยายรูปใน {SOURCE_PATH}")

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in os.listdir(OUT_DIR):
        if old.startswith(("fig-", "photo-")):
            os.remove(os.path.join(OUT_DIR, old))

    doc = pymupdf.open(PDF_PATH)
    pages: dict[int, tuple] = {}
    taken: dict[int, list] = {}
    index: dict[str, dict] = {}
    missed: list[str] = []
    for number, info in wanted.items():
        page = info["page"]
        if not 1 <= page <= len(doc):
            missed.append(f"{number} (หน้า {page} ไม่มีใน PDF)")
            continue
        if page not in pages:
            png = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
            pages[page] = (png, read_lines(png))
        png, lines = pages[page]
        chapter, figure = number.split(".")
        box = locate(lines, chapter, figure)
        if box is None:
            missed.append(f"{number} (หน้า {page})")
            continue
        taken.setdefault(page, []).append(box)
        image = Image.open(io.BytesIO(png)).convert("RGB")
        w, h = image.size
        crop = image.crop((int(box[0] * w), int(box[1] * h),
                           int(box[2] * w), int(box[3] * h)))
        name = f"fig-{chapter}-{figure}.jpg"
        crop.save(os.path.join(OUT_DIR, name), "JPEG", quality=JPEG_QUALITY,
                  optimize=True)
        index[number] = {"file": name, "page": page, "caption": info["caption"],
                         "width": crop.size[0], "height": crop.size[1]}

    import numpy as np
    captioned = len(index)
    first = min(info["page"] for info in wanted.values())
    for page in range(first, len(doc) + 1):
        png = pages[page][0] if page in pages else \
            doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
        image = Image.open(io.BytesIO(png))
        blocks = [b for b in photo_blocks(np.asarray(image.convert("L")).copy())
                  if not any(inside(b, box, image.size) for box in taken.get(page, []))]
        if not blocks:
            continue
        if page not in pages:
            pages[page] = (png, read_lines(png))
        lines = pages[page][1]
        w, h = image.size
        for order, block in enumerate(blocks, start=1):
            step = step_above(lines, block[1] / h)
            if not step:
                continue
            pad = int(PAD * w)
            crop = image.convert("RGB").crop((max(0, block[0] - pad), max(0, block[1] - pad),
                                              min(w, block[2] + pad), min(h, block[3] + pad)))
            name = f"photo-{page}-{order}.jpg"
            crop.save(os.path.join(OUT_DIR, name), "JPEG", quality=JPEG_QUALITY,
                      optimize=True)
            index[f"p{page}-{order}"] = {
                "file": name, "page": page, "caption": step, "kind": "photo",
                "width": crop.size[0], "height": crop.size[1]}

    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=1)
    print(f"รูปประกอบขั้นตอนที่ไม่มีคำบรรยาย {len(index) - captioned} รูป")
    size = sum(os.path.getsize(os.path.join(OUT_DIR, v["file"])) for v in index.values())
    print(f"รูปที่มีคำบรรยาย {captioned} จาก {len(wanted)} -> {OUT_DIR} รวม {len(index)} รูป "
          f"({size / 1e6:.1f} MB)")
    print(f"ดัชนี -> {INDEX_PATH}")
    if missed:
        print(f"หาไม่เจอ {len(missed)} รูป: {', '.join(missed)}")


if __name__ == "__main__":
    main()
