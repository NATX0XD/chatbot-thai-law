# -*- coding: utf-8 -*-
"""Turn the journal articles into a second corpus, kept apart from the rules.

  data/raw/articles/teacher-ethics.md  ->  data/processed/corpus_articles.jsonl

The source file holds one regulation (ข้อบังคับฯ 2556, already in corpus_ksp)
followed by fourteen journal articles. Only the articles are read here.

They go into their own corpus and their own index rather than into corpus_ksp
for three reasons. The articles are two and a half times the size of every
regulation put together and quote the regulations at length, so in one index
they would take the seats in the top eight that the rule itself needs. Nothing
in an article has a ข้อ number, so the citation machinery in app/answer.py has
nothing to check them against. And an article is somebody's reading of the
rules, not the rules: an answer has to say which of the two it rests on, and it
can only say so if the two never mix.

What is dropped, and why:

  the reference list   names and titles of other people's work; retrieving it
                       answers nothing and it matches every question about
                       จรรยาบรรณ on vocabulary alone
  English paragraphs   the abstract in translation and the author block; the
                       bot answers in Thai from Thai text
  short lines          the source flattens every table into one cell per line,
                       so "มาก", "4.51" and "0.000" arrive as paragraphs. A
                       number without its row and column is not a finding.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import PROCESSED_DIR, RAW_DIR  # noqa: E402

SOURCE_PATH = os.path.join(RAW_DIR, "articles", "teacher-ethics.md")
OUT_PATH = os.path.join(PROCESSED_DIR, "corpus_articles.jsonl")

MAX_CHUNK = 1000
MIN_PARAGRAPH = 60
SHORT_TAIL = 250
MIN_THAI_SHARE = 0.5

ARTICLES_START = re.compile(r"^# ส่วนที่ 2\b")
ARTICLE = re.compile(r"^## \[(G\d+)\]\s+(.+?)\s*$")
SOURCE_LINE = re.compile(r"^แหล่งที่มา:\s*(.+)$")
REFERENCES = re.compile(r"^(?:เอกสารอ้างอิง|บรรณานุกรม|references?)\s*$", re.I)
URL = re.compile(r"https?://\S+")
BUDDHIST_YEAR = re.compile(r"25[0-9]{2}")
MARKDOWN_ESCAPE = re.compile(r"\\([._*\-\[\]()#+!|>~`])")
# whole Thai block, not ก-ฮ: the leading vowels เ แ โ ใ ไ sit outside that range
THAI = re.compile(r"[\u0e00-\u0e7f]")
SUBMISSION_DATES = ("รับบทความ", "วันที่รับบทความ", "Received")
ENGLISH_TITLE = re.compile(r"\s*\([A-Za-z][^()]*\)\s*$")

# The headings a Thai research article is built from. A chunk carries the one
# it sits under, because "ร้อยละ 80" means something different under
# วิธีดำเนินการวิจัย than under ผลการวิจัย.
HEADINGS = ("บทคัดย่อ", "บทนำ", "วัตถุประสงค์", "กรอบแนวคิด", "สมมติฐาน",
            "วิธีดำเนินการวิจัย", "วิธีการวิจัย", "ระเบียบวิธีวิจัย",
            "ผลการวิจัย", "ผลการศึกษา", "อภิปรายผล", "สรุป", "บทสรุป",
            "องค์ความรู้", "ข้อเสนอแนะ")


def unescape(text: str) -> str:
    return MARKDOWN_ESCAPE.sub(r"\1", text).strip()


def thai_share(text: str) -> float:
    letters = [c for c in text if not c.isspace()]
    return len(THAI.findall(text)) / len(letters) if letters else 0.0


def heading_of(line: str) -> str | None:
    """The section heading this line is, if it is one."""
    if len(line) > 60:
        return None
    bare = line.lstrip("0123456789. ").strip()
    return bare if bare.startswith(HEADINGS) else None


def parse_source(line: str) -> dict:
    """Split the 'แหล่งที่มา:' line into who wrote it, where, and when."""
    fields = [unescape(f) for f in line.split(" · ")]
    url = next((URL.search(f).group(0) for f in fields if URL.search(f)), "")
    authors = fields[0]
    journal = fields[1] if len(fields) > 1 else ""
    years = BUDDHIST_YEAR.findall(journal)
    if not years:
        raise SystemExit(f"หาปี พ.ศ. ของบทความไม่เจอในบรรทัดแหล่งที่มา: {line[:120]}")
    return {"authors": authors, "journal": journal, "year": years[-1], "url": url}


def short_authors(authors: str) -> str:
    """'ปณิดา แก้วกัลยา และคณะ' -- the form a reader would look the article up by."""
    names = [re.sub(r"\s*\(.*$", "", n).strip() for n in authors.split(";")]
    names = [n for n in names if n]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} และ{names[1]}"
    return f"{names[0]} และคณะ"


def articles(lines: list[str]):
    """Yield (key, title, source line, body lines) for each article."""
    start = next((i for i, l in enumerate(lines) if ARTICLES_START.match(l)), None)
    if start is None:
        raise SystemExit(f"หาหัวข้อ '# ส่วนที่ 2' ไม่เจอใน {SOURCE_PATH}")
    current = None
    for line in lines[start + 1:]:
        head = ARTICLE.match(line)
        if head:
            if current:
                yield current
            current = [head.group(1), unescape(head.group(2)), None, []]
            continue
        if current is None:
            continue
        source = SOURCE_LINE.match(line)
        if source and current[2] is None:
            current[2] = source.group(1)
            continue
        current[3].append(line)
    if current:
        yield current


def passages(body: list[str]):
    """Yield (heading, paragraph) for the Thai prose of one article."""
    heading = ""
    for raw in body:
        line = unescape(raw)
        if not line:
            continue
        if REFERENCES.match(line):
            return
        found = heading_of(line)
        if found:
            heading = found
            continue
        if len(line) < MIN_PARAGRAPH or thai_share(line) < MIN_THAI_SHARE:
            continue
        # the journal's own bookkeeping, not anything the article says
        if line.startswith(SUBMISSION_DATES):
            continue
        yield heading, line


def split_long(text: str):
    """Cut a paragraph longer than a chunk at a space, never mid-word."""
    # A tail shorter than SHORT_TAIL stays with the text before it. Cutting at
    # exactly MAX_CHUNK left "ด้านความรักและศรัทธาในวิชาชีพครู ตามลำดับ" -- the
    # fourth item of a ranking -- as the opening line of the next chunk, and the
    # bot answered that it ranked first.
    while len(text) > MAX_CHUNK + SHORT_TAIL:
        cut = text.rfind(" ", int(MAX_CHUNK * 0.5), MAX_CHUNK)
        if cut == -1:
            cut = MAX_CHUNK
        yield text[:cut].strip()
        text = text[cut:].strip()
    if text:
        yield text


def chunks(body: list[str]):
    """Yield (heading, text), packing whole paragraphs up to MAX_CHUNK.

    A chunk never crosses a heading: the abstract and the findings of the same
    article say the same thing at different strengths, and a chunk holding the
    end of one and the start of the other reads as a single claim.
    """
    buffer: list[str] = []
    under = ""
    for heading, paragraph in passages(body):
        for piece in split_long(paragraph):
            size = sum(len(p) for p in buffer) + len(buffer)
            if buffer and (heading != under or size + len(piece) > MAX_CHUNK):
                yield under, "\n".join(buffer)
                buffer = []
            under = heading
            buffer.append(piece)
    if buffer:
        yield under, "\n".join(buffer)


def records(lines: list[str]):
    for key, title, source, body in articles(lines):
        if source is None:
            raise SystemExit(f"บทความ {key} ไม่มีบรรทัด 'แหล่งที่มา:'")
        meta = parse_source(source)
        thai_title = ENGLISH_TITLE.sub("", title)
        short = f"{short_authors(meta['authors'])} ({meta['year']})"
        count = 0
        for part, (heading, text) in enumerate(chunks(body), start=1):
            count += 1
            yield {
                "id": f"{key}-{part}",
                "sysid": key,
                "kind": "article",
                "title": thai_title,
                "short": short,
                "authors": meta["authors"],
                "journal": meta["journal"],
                "year": meta["year"],
                "source_url": meta["url"],
                "heading": heading,
                "part": part,
                "text": text,
                "n_chars": len(text),
            }
        if count == 0:
            raise SystemExit(f"บทความ {key} ไม่เหลือข้อความหลังคัดกรอง")


def main() -> None:
    if not os.path.exists(SOURCE_PATH):
        raise SystemExit(f"ไม่พบไฟล์ต้นทาง {SOURCE_PATH}")
    with open(SOURCE_PATH, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    rows = list(records(lines))
    if not rows:
        raise SystemExit(f"ไม่พบบทความใน {SOURCE_PATH}")

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    per: dict[str, list[dict]] = {}
    for row in rows:
        per.setdefault(row["sysid"], []).append(row)
    for key, group in per.items():
        chars = sum(r["n_chars"] for r in group)
        print(f"{key}  {len(group):3d} ชิ้น {chars:7,d} ตัวอักษร  "
              f"{group[0]['short']}  {group[0]['title'][:50]}")
    print(f"\n{len(per)} บทความ {len(rows):,} ชิ้น -> {OUT_PATH}")
    print("ต่อไป: python -m ingest.build_article_index")


if __name__ == "__main__":
    main()
