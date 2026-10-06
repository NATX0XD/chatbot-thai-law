# -*- coding: utf-8 -*-
"""Turn the networking textbook into the corpus the bot answers from.

  data/raw/network/network-basics.md  ->  data/processed/corpus_network.jsonl

The source is the OCR of คู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น (รหัสวิชา
2204-2003), seven chapters. It marks two things only: `## บทที่ N` where a
chapter opens and `<!-- หน้า N -->` where a page of the PDF does. Everything
else -- which short line is a section heading, where the exercises begin -- is
read off the book's own table of contents and its fixed chapter layout.

What is dropped, and why:

  everything before บทที่ 1   cover, imprint, preface and the table of contents.
                               The contents page names every topic in the book
                               and explains none, so it would match every
                               question and answer nothing.
  แบบทดสอบ to chapter end      the exercises. They are questions with no
                               answers printed, worded exactly like what a
                               student types, so they would take the top seats
                               from the passage that does answer.
  จุดประสงค์เชิงพฤติกรรม        the list of objectives a chapter opens with. Like
                               the contents page, it names each topic of the
                               chapter and says nothing about any of them.
  บรรณานุกรม                    other people's books.
  lines with no Thai in them   what OCR makes of a screenshot: "CONNEC »".

A chunk never crosses a section heading, and inside a section it breaks before
a paragraph or a numbered item, never before a bullet: "ข้อดี" followed by four
bullets says nothing about which cable it praises once it is cut loose from the
paragraph above it.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import PROCESSED_DIR, RAW_DIR  # noqa: E402

SOURCE_PATH = os.path.join(RAW_DIR, "network", "network-basics.md")
OUT_PATH = os.path.join(PROCESSED_DIR, "corpus_network.jsonl")

SOURCES_PATH = os.path.join(PROCESSED_DIR, "corpus_network_SOURCES.md")

BOOK = "คู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น"

SOURCES = """# ที่มาของ corpus_network.jsonl และรูปใน web/figures

ไฟล์นี้สร้างโดย `python -m ingest.extract_book` ห้ามแก้ด้วยมือ

`corpus_network.jsonl` คือข้อความจากหนังสือเล่มเดียว และรูปใน `web/figures/`
ตัดมาจากหนังสือเล่มเดียวกัน

| | |
|:---|:---|
| ชื่อหนังสือ | คู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น (รหัสวิชา 2204-2003) |
| ผู้เรียบเรียง | ฝ่ายตำราวิชาการคอมพิวเตอร์ |
| ผู้จัดพิมพ์ | บริษัท ซีเอ็ดยูเคชั่น จำกัด (มหาชน) กรุงเทพฯ พ.ศ. 2557 |
| Barcode (e-book) | 9786160842926 |

ลิขสิทธิ์ของข้อความและรูปทั้งหมดเป็นของบริษัท ซีเอ็ดยูเคชั่น จำกัด (มหาชน)
ผู้จัดทำ repository นี้ไม่ได้เป็นเจ้าของ และไม่ได้อ้างสิทธิ์ใดในเนื้อหา

นำมาใช้ที่นี่เพื่อการศึกษา เป็นคลังข้อมูลของแชตบอตในปริญญานิพนธ์ ไม่ได้ใช้เพื่อการค้า
ทุกคำตอบของบอทระบุบทและหน้าของหนังสือกำกับไว้ ผู้เรียนควรอ่านจากหนังสือฉบับเต็ม

เจ้าของลิขสิทธิ์ที่ไม่ประสงค์ให้ใช้ แจ้งผ่าน Issues ของ repository นี้ได้ จะนำออกให้

คลังนี้มี {chapters} บท {chunks} ชิ้นข้อความ ไม่รวมสารบัญ แบบทดสอบท้ายบท และบรรณานุกรม
"""

# A chunk closes at the first paragraph break after SOFT_CHUNK and is cut at
# MAX_CHUNK whatever comes next.
SOFT_CHUNK = 700
MAX_CHUNK = 1400
MAX_HEADING = 80
PARAGRAPH = 150
# Shorter than this, a line sitting right above a figure caption is a label
# from inside the figure, and a section's last chunk is joined to the one
# before it.
FIGURE_LABEL = 100
SHORT_TAIL = 200
MIN_SECTION = 40

CHAPTER = re.compile(r"^## บทที่ (\d+)\s+(.+?)\s*$")
PAGE = re.compile(r"^<!-- หน้า (\d+) -->$")
CONTENTS = re.compile(r"^สารบัญ\s*$")
EXERCISES = re.compile(r"^แบบทดสอบ(?:ประเมิน|ประมวล)ผลการเรียนรู้\s*$")
BIBLIOGRAPHY = re.compile(r"^บรรณานุกรม\s*$")
OBJECTIVES = re.compile(r"^จุดประสงค์เชิงพฤติกรรม\s*$")
SUMMARY = re.compile(r"^สรุปท้ายบทที่\s*\d+\s*$")
# whole Thai block, not ก-ฮ: the leading vowels เ แ โ ใ ไ sit outside that range
THAI = re.compile(r"[฀-๿]")
NUMBERED = re.compile(r"^(?:\d{1,2}\.|ขั้นตอนที่\s*\d+)")
BULLET = re.compile(r"^[•\-–]\s")
CAPTION = re.compile(r"^(?:รูป|ตาราง)ที่\s*\d")
# Every figure a passage captions or points at ("ดังรูปที่ 1.6"), numbered the
# way ingest/extract_figures.py names the picture files.
FIGURE = re.compile(r"รูปที่\s*(\d+)\s*[.,]\s*(\d+)")
NOT_LETTERS = re.compile(r"[\s.…·:\d]+")
# What ends an entry in the table of contents: a dot leader, or the page number.
# No page is below 11, so "Windows 7" keeps its digit.
ENTRY_END = re.compile(r"(?:[.…]\s*){2,}\d*|\s[.…]?\s*\d{2,3}(?=\s|$)")


def key(text: str) -> str:
    """A line with its spacing, dot leaders and page numbers taken out."""
    return NOT_LETTERS.sub("", text)


def read_contents(lines: list[str]) -> set[str]:
    """Every entry of the table of contents, for recognising section headings."""
    start = next((i for i, l in enumerate(lines) if CONTENTS.match(l)), None)
    end = next((i for i, l in enumerate(lines) if CHAPTER.match(l)), None)
    if start is None or end is None or start >= end:
        raise SystemExit(f"หาสารบัญหรือบทที่ 1 ไม่เจอใน {SOURCE_PATH}")
    entries = {key(e) for line in lines[start + 1:end] for e in ENTRY_END.split(line)}
    entries.discard("")
    return entries


def is_heading(line: str, contents: set[str]) -> bool:
    """A section heading is a short line the table of contents lists as an entry.

    The whole entry, not part of one: "ข้อมูล" and "เครือข่าย" occur inside a
    dozen entries and are also what OCR leaves of a diagram's labels.
    """
    if len(line) > MAX_HEADING or NUMBERED.match(line) or BULLET.match(line) \
            or CAPTION.match(line):
        return False
    return bool(SUMMARY.match(line)) or key(line) in contents


def chapters(lines: list[str]):
    """Yield (number, title, [(page, line), ...]) with the exercises cut off."""
    current = None
    page = 0
    skipping = False
    objectives = False
    for raw in lines:
        line = raw.strip()
        turned = PAGE.match(line)
        if turned:
            page = int(turned.group(1))
            continue
        opened = CHAPTER.match(line)
        if opened:
            if current:
                yield current
            current = (int(opened.group(1)), opened.group(2), [])
            skipping = False
            continue
        if current is None or not line:
            continue
        if EXERCISES.match(line) or BIBLIOGRAPHY.match(line):
            skipping = True
        if OBJECTIVES.match(line):
            objectives = True
            continue
        if objectives:
            if NUMBERED.match(line):
                continue
            objectives = False
        if skipping or not THAI.search(line):
            continue
        if CAPTION.match(line):
            # The words printed inside a figure come out of OCR as loose short
            # lines just above its caption: "ดาวเทียม", "สถานีไมโครเวฟ".
            body = current[2]
            while body and len(body[-1][1]) < FIGURE_LABEL and not (
                    NUMBERED.match(body[-1][1]) or BULLET.match(body[-1][1])
                    or CAPTION.match(body[-1][1])):
                body.pop()
        current[2].append((page, line))
    if current:
        yield current


def sections(body: list[tuple[int, str]], contents: set[str]):
    """Yield (heading, [(page, line), ...]) for each section of one chapter."""
    heading, held = "", []
    for page, line in body:
        if is_heading(line, contents):
            if held:
                yield heading, held
            heading, held = line, []
            continue
        held.append((page, line))
    if held:
        yield heading, held


def starts_a_thought(line: str) -> bool:
    """Whether a chunk may begin here without losing what it is about."""
    if BULLET.match(line) or CAPTION.match(line):
        return False
    return bool(NUMBERED.match(line)) or len(line) >= PARAGRAPH


def split_long(line: str):
    """Cut one line longer than a chunk at a space, never mid-word."""
    while len(line) > MAX_CHUNK:
        cut = line.rfind(" ", MAX_CHUNK // 2, MAX_CHUNK)
        if cut == -1:
            cut = MAX_CHUNK
        yield line[:cut].strip()
        line = line[cut:].strip()
    if line:
        yield line


def chunks(held: list[tuple[int, str]]):
    """Yield (first page, last page, text) for one section."""
    groups: list[list[tuple[int, str]]] = []
    buffer: list[tuple[int, str]] = []
    size = 0
    for page, whole in held:
        for line in split_long(whole):
            full = size + len(line) > MAX_CHUNK
            ready = size >= SOFT_CHUNK and starts_a_thought(line)
            if buffer and (full or ready):
                groups.append(buffer)
                buffer, size = [], 0
            buffer.append((page, line))
            size += len(line) + 1
    if buffer:
        # "10. คลิกปุ่ม Close" on its own says nothing about what was closed
        if groups and size < SHORT_TAIL:
            groups[-1].extend(buffer)
        else:
            groups.append(buffer)
    for group in groups:
        text = "\n".join(line for _, line in group)
        if len(text) >= MIN_SECTION:
            yield group[0][0], group[-1][0], text


def records(lines: list[str]):
    contents = read_contents(lines)
    for number, title, body in chapters(lines):
        part = 0
        for heading, held in sections(body, contents):
            for first, last, text in chunks(held):
                part += 1
                yield {
                    "id": f"net-{number}-{part}",
                    "sysid": f"net-{number}",
                    "kind": "book",
                    "book": BOOK,
                    "chapter": number,
                    "chapter_title": title,
                    "heading": heading,
                    "page_from": first,
                    "page_to": last,
                    "part": part,
                    # the figures this chunk captions or refers to; app/book.py
                    # picks from them what to show under an answer
                    "figures": list(dict.fromkeys(
                        f"{a}.{b}" for a, b in FIGURE.findall(text))),
                    "text": text,
                    "n_chars": len(text),
                }
        if part == 0:
            raise SystemExit(f"บทที่ {number} ไม่เหลือข้อความหลังคัดกรอง")


def main() -> None:
    if not os.path.exists(SOURCE_PATH):
        raise SystemExit(f"ไม่พบไฟล์ต้นทาง {SOURCE_PATH}")
    with open(SOURCE_PATH, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    rows = list(records(lines))
    if not rows:
        raise SystemExit(f"ไม่พบบทใดเลยใน {SOURCE_PATH}")

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    per: dict[int, list[dict]] = {}
    for row in rows:
        per.setdefault(row["chapter"], []).append(row)
    for number, group in per.items():
        heads = len({r["heading"] for r in group})
        chars = sum(r["n_chars"] for r in group)
        print(f"บทที่ {number}  {len(group):3d} ชิ้น {heads:3d} หัวข้อ {chars:7,d} ตัวอักษร  "
              f"หน้า {group[0]['page_from']}-{group[-1]['page_to']}  "
              f"{group[0]['chapter_title']}")
    with open(SOURCES_PATH, "w", encoding="utf-8") as handle:
        handle.write(SOURCES.format(chapters=len(per), chunks=len(rows)))
    print(f"\n{len(per)} บท {len(rows):,} ชิ้น -> {OUT_PATH}")
    print(f"ที่มา -> {SOURCES_PATH}")
    print("ต่อไป: python -m ingest.build_book_index")


if __name__ == "__main__":
    main()
