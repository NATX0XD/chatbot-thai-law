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
        if old.startswith("fig-"):
            os.remove(os.path.join(OUT_DIR, old))

    doc = pymupdf.open(PDF_PATH)
    pages: dict[int, tuple] = {}
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
        image = Image.open(io.BytesIO(png)).convert("RGB")
        w, h = image.size
        crop = image.crop((int(box[0] * w), int(box[1] * h),
                           int(box[2] * w), int(box[3] * h)))
        name = f"fig-{chapter}-{figure}.jpg"
        crop.save(os.path.join(OUT_DIR, name), "JPEG", quality=JPEG_QUALITY,
                  optimize=True)
        index[number] = {"file": name, "page": page, "caption": info["caption"],
                         "width": crop.size[0], "height": crop.size[1]}

    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=1)
    size = sum(os.path.getsize(os.path.join(OUT_DIR, v["file"])) for v in index.values())
    print(f"{len(index)} รูปจาก {len(wanted)} คำบรรยาย -> {OUT_DIR} "
          f"({size / 1e6:.1f} MB)")
    print(f"ดัชนี -> {INDEX_PATH}")
    if missed:
        print(f"หาไม่เจอ {len(missed)} รูป: {', '.join(missed)}")


if __name__ == "__main__":
    main()
