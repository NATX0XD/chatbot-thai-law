# -*- coding: utf-8 -*-
"""An assessor's note, with the system's own names for things taken out.

The assessors wrote "ตรงกับ net-5-19 หน้า 209-211" and "ตรงกับ P19": a chunk id
of the corpus and a passage number of the review packet. Neither means
anything to someone reading the sheet with the book open. Each is replaced by
where it is in the book -- "หนังสือบทที่ 5 หน้า 209-211" -- looked up from the
corpus or the packet, not guessed. The coding files keep the assessors' words
as written; only what is shown is changed.
"""
from __future__ import annotations

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(BASE_DIR, "data", "processed", "corpus_network.jsonl")
EVAL = os.path.join(BASE_DIR, "data", "eval")

NAME = r"(?:net-\d+-\d+|P\d+)"
PAGES = r"[\d]+(?:\s*[\-–]\s*\d+)?"
MENTION = re.compile(
    rf"({NAME})(?:\s*ถึง\s*({NAME}))?"
    rf"(?:\s*\((?:บทที่\s*\d+\s*)?หน้า\s*({PAGES})\)|\s+หน้า\s*({PAGES}))?")
PACKET_HEAD = re.compile(r"^## (P\d+) — บทที่ (\d+) .*\(หน้า ([\d\-]+)\)\s*$", re.M)
LEFT_OVER = re.compile(NAME)

_chunks: dict[str, tuple[int, int, int]] | None = None


def chunks() -> dict[str, tuple[int, int, int]]:
    global _chunks
    if _chunks is None:
        with open(CORPUS, encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle]
        _chunks = {r["id"]: (r["chapter"], r["page_from"], r["page_to"]) for r in records}
    return _chunks


def packet_passages(round_no: int, part: int) -> dict[str, tuple[int, int, int]]:
    """Where each P-number of one review packet is in the book."""
    source = os.path.join(EVAL, f"network_review_packet_round{round_no}_{part}.md")
    if not os.path.exists(source):
        raise SystemExit(f"ไม่พบ {source}")
    with open(source, encoding="utf-8") as handle:
        found = PACKET_HEAD.findall(handle.read())
    out = {}
    for name, chapter, pages in found:
        first, _, last = pages.partition("-")
        out[name] = (int(chapter), int(first), int(last or first))
    return out


# what the project calls the book's text, in a reader's words
WORDS = (("ค้นคลังตำรา", "ค้นในหนังสือ"), ("คลังตำรา", "หนังสือ"), ("คลัง", "หนังสือ"))
REFERENCE = r"หนังสือบทที่ (\d+) หน้า (\d+)(?:-(\d+))?"
RUN = re.compile(rf"{REFERENCE}(?: {REFERENCE})+")


def together(match: re.Match) -> str:
    """"P3 P4 P5" comes out as three references in a row; when they are in one
    chapter they are read as the one span of pages they cover."""
    found = re.findall(REFERENCE, match.group(0))
    if len({chapter for chapter, _, _ in found}) != 1:
        return match.group(0)
    first = min(int(start) for _, start, _ in found)
    last = max(int(end or start) for _, start, end in found)
    return f"หนังสือบทที่ {found[0][0]} หน้า {first}" + (f"-{last}" if last != first else "")


def plain(note: str, passages: dict[str, tuple[int, int, int]] | None = None) -> str:
    known = {**chunks(), **(passages or {})}

    def where(match: re.Match) -> str:
        first, last, bracketed, bare = match.groups()
        if first not in known or (last and last not in known):
            raise SystemExit(f"หมายเหตุอ้าง {first} {last or ''} ซึ่งหาในหนังสือไม่เจอ: {note[:80]}")
        chapter, start, end = known[first]
        if last:
            end = known[last][2]
        stated = bracketed or bare
        pages = stated.replace("–", "-").replace(" ", "") if stated else (
            f"{start}-{end}" if end != start else str(start))
        return f"หนังสือบทที่ {chapter} หน้า {pages}"

    shown = RUN.sub(together, MENTION.sub(where, note))
    for ours, theirs in WORDS:
        shown = shown.replace(ours, theirs)
    if LEFT_OVER.search(shown):
        raise SystemExit(f"ยังมีชื่อภายในเหลืออยู่ในหมายเหตุ: {shown[:120]}")
    return shown
