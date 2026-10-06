# -*- coding: utf-8 -*-
"""Answer from the networking textbook.

The corpus is คู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น (รหัสวิชา 2204-2003), cut
into passages by ingest/extract_book.py. A passage has no rule number to check
a citation against the way the Council's regulations did, so this path holds
the answer to the book by other means, the same ones app/articles.py uses:

  the citation is copied   the model writes [2]; the chapter and the page come
                           from record 2. It never types a page number itself.
  figures are computed     every number in the answer must be printed in the
                           passages it was shown -- 100 เมตร, 802.11g, 16 Mbps
                           are exactly what a model fills in from memory.
  uncited lines are held   a line with no pointer has to be made of the
  to the passages          passages' own words.
  pictures are not chosen  the figures shown are captioned in the passages
  by the model             the model was given, and picked by how much of the
                           caption the question is about.

A question the book does not cover is refused, naming the nearest sections. The
cosine gate catches what is not about networking at all; a networking question
the book never reaches (IPv6, VLAN) passes that gate, and is caught by the model
saying it has nothing and by the guards above when it does not say so.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.articles import (DEGENERATE_RUN, NO_ANSWER, POINTER,
                          REPEATED_CITE, THAI_DIGITS, WORD, ArticleIndex)
from app.bm25_lite import BM25Lite
from app.config import PROCESSED_DIR, settings
from app.corpus_store import open_corpus
from app.embed import get_embedder
from app.llm import LLMUnavailable, complete
from app.retriever import Hit
from app.thai_tokenize import word_tokenize

log = logging.getLogger(__name__)

BOOK = "คู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น"
FIGURES_PATH = os.path.join(PROCESSED_DIR, "figures_network.json")
FIGURES_URL = "/static/figures/"
TOP_K = 6
MAX_FIGURES = 2
FIGURE_COVER = 0.5
FIGURE_NEAR_BEST = 0.9
# words that ask rather than name; they say nothing about which figure is meant
ASKING = frozenset((
    "คือ", "อะไร", "บ้าง", "อย่างไร", "ยังไง", "ทำไม", "เท่าใด", "เท่าไร", "เท่าไหร่",
    "หรือไม่", "ไหม", "มี", "กี่", "แบบ", "ชนิด", "ของ", "และ", "หรือ", "ที่", "ใน",
    "การ", "เป็น", "ได้", "ให้", "กับ", "จาก", "ครับ", "ค่ะ", "ช่วย", "อธิบาย", "หน่อย",
    "รูป", "ภาพ", "แสดง", "ตัวอย่าง"))

DISCLAIMER = (f"ℹ️ สรุปจากหนังสือ{BOOK} (รหัสวิชา 2204-2003) "
              "ใช้ทบทวนบทเรียน ควรอ่านเนื้อหาเต็มในหนังสือตามหน้าที่อ้างประกอบ")

EMPTY = "พิมพ์คำถามเรื่องเครือข่ายคอมพิวเตอร์มาได้เลยครับ"

OUT_OF_SCOPE = (
    "คำถามนี้อยู่นอกเนื้อหาของหนังสือที่ผมใช้ตอบครับ\n\n"
    f"ผมตอบได้เฉพาะเรื่องในหนังสือ{BOOK} เช่น ประเภทของเครือข่าย แบบจำลอง OSI "
    "สายสัญญาณและสื่อกลางไร้สาย อุปกรณ์เครือข่าย โทโปโลยี อีเทอร์เน็ต "
    "การเข้าหัวสายแลน และการตั้งค่าเวิร์กกรุ๊ปบน Windows\n\n"
    "ลองถามใหม่ให้ตรงกับเรื่องเหล่านี้ได้เลยครับ")

UNANSWERED = (
    "เรื่องนี้ผมหาคำตอบที่ยืนยันกับหนังสือไม่ได้ จึงไม่ตอบ เพราะไม่อยากเดาครับ "
    "อาจเป็นเรื่องที่หนังสือเล่มนี้ไม่ได้อธิบายไว้ หรือลองถามให้เจาะจงขึ้นได้ครับ")

SYSTEM_PROMPT = f"""คุณคือผู้ช่วยทบทวนบทเรียนวิชาเครือข่ายคอมพิวเตอร์เบื้องต้น สำหรับนักเรียนระดับ ปวช. ตอบผ่านแอปแชท LINE

คุณจะได้รับคำถาม และข้อความจากหนังสือ{BOOK}ที่ค้นมาให้ แต่ละชิ้นมีหมายเลข [1] [2] ...

กติกา
1. ตอบจากข้อความที่ให้มาเท่านั้น ห้ามเติมจากความรู้เดิม แม้จะมั่นใจว่าถูก
   ห้ามเพิ่มเหตุผล ตัวอย่าง ข้อเปรียบเทียบ ข้อสรุป หรือคำแนะนำที่ข้อความไม่ได้เขียนไว้ แม้จะเป็นความจริง
   ถ้าคำถามถามเหตุผลหรือรายละเอียดที่ข้อความไม่ได้บอก ให้ตอบเท่าที่ข้อความเขียน แล้วบอกว่าหนังสือไม่ได้อธิบายส่วนที่เหลือ
2. ทุกประโยคที่เป็นเนื้อหา ต้องลงท้ายด้วยหมายเลขของชิ้นที่ใช้ เช่น [1] หรือ [2]
   ห้ามเขียนเลขบทหรือเลขหน้าเอง ระบบจะใส่ให้จากหมายเลขชิ้น
3. ตัวเลข ชื่อมาตรฐาน ชื่อเมนู และชื่อปุ่ม ให้คัดตามข้อความที่ให้มาทุกตัวอักษร ห้ามเปลี่ยน ห้ามเติมค่าที่ไม่ได้เขียนไว้
4. ถ้าเป็นขั้นตอนหรือรายการที่หนังสือใส่เลขลำดับไว้ ให้เรียงตามหนังสือและคงเลขลำดับเดิม ห้ามข้าม ห้ามเพิ่ม ห้ามสลับ
5. ถ้าข้อความที่ให้มาไม่ได้ตอบคำถาม ให้ตอบเพียงว่า {NO_ANSWER} ห้ามตอบจากความรู้เดิม
6. เขียนภาษาไทยที่นักเรียนอ่านเข้าใจง่าย เริ่มด้วยคำตอบตรง ๆ 1-2 ประโยค แล้วขยายเท่าที่จำเป็น ไม่เกิน 12 บรรทัด
7. ห้ามใช้ ** ## หรือตาราง เพราะแสดงผลไม่ได้ ใช้ • นำหน้ารายการได้
8. ลงท้ายประโยคสุดท้ายของคำตอบด้วยคำว่า ครับ ถ้าต้องเรียกตัวเองให้ใช้คำว่า ผม
9. ห้ามเขียนบรรทัดปิดท้ายที่ไม่ใช่เนื้อหา เช่น บอกว่าสรุปให้แล้ว หรืออธิบายว่าเข้าใจคำถามอย่างไร"""

# every run of digits, with the decimals and the dotted parts of a standard's
# name kept on: 802.11, 2.4, 1,000
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)*")
LIST_MARK = re.compile(r"(?m)^\s*\d{1,2}[.)]\s")
STEP_MARK = re.compile(r"ขั้นตอนที่\s*\d{1,2}")
# Words an answer is held together with. None of them states anything about a
# network, so a line is not thrown away for using one: the first run dropped
# "ข้อดีของสายคู่บิดเกลียว ได้แก่" over "ได้แก่" and left seven bullets with
# nothing to say which were the advantages.
CONNECTIVES = frozenset((
    "ได้แก่", "ดังนี้", "ดังต่อไปนี้", "ต่อไปนี้", "ครับ", "สรุป", "ประกอบด้วย",
    "กล่าวคือ", "นั่นคือ", "ดังนั้น", "ส่วน", "สำหรับ", "รายละเอียด", "เช่น",
    "อย่างไรก็ตาม", "นอกจากนี้", "โดยสรุป", "ทั้งหมด", "คำตอบ", "หนังสือ", "ระบุ", "อธิบาย"))
# "ในทางกลับกัน เครือข่ายแบบโดเมน" above four bullets is what says whose
# bullets they are. A short uncited line directly above a list is kept on a
# narrower test than the rest: it may not bring a number or an English term
# the passages do not have.
LIST_ITEM = re.compile(r"^\s*(?:[•\-–]|\d{1,2}[.)])\s")
MAX_LIST_HEADING = 70
# The book path answers "กี่คู่" in one line; the eighty characters asked of an
# article summary would throw that away.
MIN_ANSWER = 20
# A line that is the model talking about itself rather than about networks:
# "ครับ", "ผมครับ", "ผมขอสรุปให้ครับ". See closing_remarks.
ABOUT_ITSELF = re.compile(r"^\s*(?:(?:นะ)?ครับ|ผม\S*.*)\s*$")
# Five references after one line is the model pointing at everything it was
# shown. The first two are the ones it reached for.
CITE_PILE = re.compile(r"((?: \(บทที่ \d+ หน้า [\d\-]+\)){2})(?: \(บทที่ \d+ หน้า [\d\-]+\))+")
REMINDER = ("\n\nคำตอบก่อนหน้านี้ไม่ได้ใส่หมายเลขชิ้น [1] [2] ท้ายประโยค จึงใช้ไม่ได้ "
            "ตอบใหม่โดยใส่หมายเลขชิ้นท้ายทุกประโยคที่เป็นเนื้อหา")
TRAILING_CITE = re.compile(r" \(บทที่ \d+ หน้า [\d\-]+\)$")
LATIN_TERM = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


@dataclass
class BookHit(Hit):
    @property
    def where(self) -> str:
        """'บทที่ 2 หน้า 42-43' -- the short form put inline in an answer."""
        r = self.rec
        pages = (f"{r['page_from']}" if r["page_from"] == r["page_to"]
                 else f"{r['page_from']}-{r['page_to']}")
        return f"บทที่ {r['chapter']} หน้า {pages}"

    @property
    def citation(self) -> str:
        r = self.rec
        head = f"บทที่ {r['chapter']} {r['chapter_title']}"
        topic = f"หัวข้อ {r['heading']} " if r.get("heading") else ""
        return f"{head} — {topic}({self.where.split(' ', 2)[2]})"


class BookIndex(ArticleIndex):
    """The textbook corpus with its vectors and its BM25 postings."""

    hit_class = BookHit

    def __init__(self):
        for path in (settings.book_path, settings.book_vectors_path,
                     settings.book_bm25_path, settings.book_vocab_path):
            if not os.path.exists(path):
                raise RuntimeError(
                    f"ไม่พบ {path} -- รัน python -m ingest.extract_book แล้ว "
                    "python -m ingest.build_book_index")
        self.corpus = open_corpus(settings.book_path)
        self.vectors = np.load(settings.book_vectors_path, mmap_mode="r")
        self.bm25 = BM25Lite(settings.book_bm25_path, settings.book_vocab_path)
        for name, size in (("vectors", len(self.vectors)), ("bm25", self.bm25.n_docs)):
            if size != len(self.corpus):
                raise RuntimeError(
                    f"book index/corpus mismatch: {size} {name} vs "
                    f"{len(self.corpus)} chunks. Re-run ingest.build_book_index.")
        self.embedder = None
        # Absent is a state: the book answers without its pictures. Logged once.
        self.figures: dict[str, dict] = {}
        if os.path.exists(FIGURES_PATH):
            with open(FIGURES_PATH, encoding="utf-8") as handle:
                self.figures = json.load(handle)
        else:
            log.warning("FIGURES OFF: %s is missing -- answers carry no pictures",
                        FIGURES_PATH)

    def encode(self, text: str) -> np.ndarray:
        if self.embedder is None:
            self.embedder = get_embedder()
        return self.embedder.encode(text)

    def rarity(self, word: str) -> float:
        """How much a word says about which passage is meant: its BM25 idf.
        A word the book never uses says nothing here."""
        i = self.bm25.term_id.get(word)
        return float(max(self.bm25.idf[i], 0.0)) if i is not None else 0.0

    def find(self, question: str, top_k: int = TOP_K) -> tuple[list[BookHit], float]:
        asked = question.translate(THAI_DIGITS)
        return self.search(asked, self.encode(asked), top_k)


_index: Optional[BookIndex] = None


def get_index() -> BookIndex:
    global _index
    if _index is None:
        _index = BookIndex()
        log.info("book ready: %d chunks, %d figures",
                 len(_index.corpus), len(_index.figures))
    return _index


def build_context(hits: list[BookHit]) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        head = f"[{i}] บทที่ {h.rec['chapter']} {h.rec['chapter_title']}"
        if h.rec.get("heading"):
            head += f"\n    (อยู่ในหัวข้อ {h.rec['heading']})"
        blocks.append(f"{head}\n{h.rec['text']}")
    return "\n\n".join(blocks)


def source_text(hits: list[BookHit]) -> str:
    return " ".join(f"{h.rec['chapter_title']} {h.rec.get('heading', '')} {h.rec['text']}"
                    for h in hits).translate(THAI_DIGITS)


def resolve(text: str, hits: list[BookHit]) -> tuple[str, list[BookHit]]:
    """Swap each [n] for the chapter and page of passage n.

    A pointer to a passage that was never supplied is dropped rather than
    guessed at. Returns the passages actually cited, in the order first cited.
    """
    cited: list[BookHit] = []

    def swap(match: re.Match) -> str:
        n = int(match.group(1))
        if not 1 <= n <= len(hits):
            return ""
        hit = hits[n - 1]
        if hit not in cited:
            cited.append(hit)
        return f" ({hit.where})"

    text = CITE_PILE.sub(r"\1", REPEATED_CITE.sub(r"\1", POINTER.sub(swap, text)))
    lines = [line.rstrip() for line in text.split("\n")]
    # Seven bullets from one page each end in the same reference. It is printed
    # once, on the last of them.
    for i in range(len(lines) - 1):
        here, after = TRAILING_CITE.search(lines[i]), TRAILING_CITE.search(lines[i + 1])
        if here and after and here.group(0) == after.group(0):
            lines[i] = lines[i][:here.start()]
    return "\n".join(lines), cited


def drop_ungrounded(draft: str, hits: list[BookHit], question: str = ""
                    ) -> tuple[str, list[str]]:
    """Remove every line that cites nothing and says something the passages do not.

    The same rule as app/articles.py: a line without a pointer is normal -- six
    steps copied out under one citation -- and it is also where the model adds
    what it remembers. So every word of three letters or more in such a line
    must occur in the passages; one that does not takes the line with it. The
    asker's own words and the connectives above are allowed.
    """
    source = source_text(hits) + " " + question.translate(THAI_DIGITS)
    lines = draft.split("\n")
    kept, dropped = [], []
    for i, line in enumerate(lines):
        if not line.strip() or POINTER.search(line):
            kept.append(line)
            continue
        plain = line.translate(THAI_DIGITS)
        following = next((l for l in lines[i + 1:] if l.strip()), "")
        if len(line.strip()) <= MAX_LIST_HEADING and LIST_ITEM.match(following) \
                and not LIST_ITEM.match(line):
            foreign = [t for t in NUMBER.findall(plain) + LATIN_TERM.findall(plain)
                       if t.lower() not in source.lower()]
        else:
            foreign = [w for w in word_tokenize(plain, keep_whitespace=False)
                       if len(w) >= 3 and WORD.search(w) and w not in CONNECTIVES
                       and w not in source]
        if foreign:
            dropped.append(f"{line.strip()[:60]} <- {foreign[0]}")
        else:
            kept.append(line)
    return "\n".join(kept), dropped


def closing_remarks(draft: str) -> str:
    """Take out the lines in which the model speaks of itself.

    "ผมขออธิบายเพิ่มเติมว่า", "ผมเข้าใจว่าคำถามต้องการ", "ผมขอสรุปว่า": read
    across the ninety-nine saved answers, a line that opens this way is either
    about the answer rather than the subject, or is where the model goes on
    from what the book says to what it knows. Either way the book's own
    statement is already in the lines around it.
    """
    lines = [line for line in draft.split("\n") if not ABOUT_ITSELF.match(line)]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


BOOK_ITEM = re.compile(r"(?m)^(\d{1,2})\.\s*(\S.*)$")
MARKER = re.compile(r"^\s*(?:[•\-–]|\d{1,2}[.)])\s*")
MIN_ITEM = 8
MIN_RUN = 3


def in_book_order(draft: str, hits: list[BookHit]) -> tuple[str, bool]:
    """Put a list back in the order, and under the numbers, the book prints.

    Asked how many layers the OSI model has, the model answered seven and then
    listed them with the third and fourth changed over -- every name right, the
    order wrong, and nothing in a word-by-word check to notice. The book
    numbers those layers, so the order is not the model's to choose: where
    three or more consecutive list lines are each a numbered item of the
    passages, they are sorted by the book's number and carry it.

    A line that matches two different numbers is left alone, and so is its run.
    """
    numbered: dict[str, set[int]] = {}
    for hit in hits:
        for number, text in BOOK_ITEM.findall(hit.rec["text"].translate(THAI_DIGITS)):
            numbered.setdefault(text.strip(), set()).add(int(number))

    def number_of(line: str) -> int | None:
        if not LIST_ITEM.match(line):
            return None
        item = POINTER.sub("", MARKER.sub("", line)).strip().translate(THAI_DIGITS)
        if len(item) < MIN_ITEM:
            return None
        found: set[int] = set()
        for text, numbers in numbered.items():
            if text.startswith(item) or item.startswith(text[:max(MIN_ITEM, len(item))]):
                found |= numbers
        return found.pop() if len(found) == 1 else None

    lines = draft.split("\n")
    changed = False
    start = 0
    while start < len(lines):
        end = start
        run = []
        while end < len(lines) and (n := number_of(lines[end])) is not None:
            run.append(n)
            end += 1
        if len(run) >= MIN_RUN and len(set(run)) == len(run):
            ordered = sorted(zip(run, lines[start:end]))
            rewritten = [f"{n}. {MARKER.sub('', line)}" for n, line in ordered]
            if rewritten != lines[start:end]:
                # a pointer rode on whichever line was last; it stays last
                tails = [POINTER.findall(line) for line in rewritten]
                if any(tails[:-1]) and not tails[-1]:
                    carried = "".join(f" [{t}]" for t in dict.fromkeys(
                        t for tail in tails for t in tail))
                    rewritten = [POINTER.sub("", line).rstrip() for line in rewritten]
                    rewritten[-1] += carried
                lines[start:end] = rewritten
                changed = True
        start = max(end, start + 1)
    return "\n".join(lines), changed


def unsupported_numbers(body: str, hits: list[BookHit], question: str = "") -> list[str]:
    """Numbers in the answer that are printed nowhere in the passages.

    List markers and "ขั้นตอนที่ 3" are the answer's own numbering, and a number
    the asker typed is theirs to repeat. A bare single digit is how prose
    counts ("มี 3 แบบ") and is let through, as app/numbers.py does.
    """
    known = set(NUMBER.findall(source_text(hits) + " " + question.translate(THAI_DIGITS)))
    known |= {n.replace(",", "") for n in known}
    bare = STEP_MARK.sub("", LIST_MARK.sub("", POINTER.sub("", body)))
    bad = []
    for number in NUMBER.findall(bare.translate(THAI_DIGITS)):
        number = number.rstrip(".,")
        if len(number) < 2 or number in known or number.replace(",", "") in known:
            continue
        if number not in bad:
            bad.append(number)
    return bad


def foreign_terms(body: str, hits: list[BookHit], question: str = "") -> list[str]:
    """English terms in the answer that neither the passages nor the question use.

    Logged, not acted on: it has not been measured against anyone's reading of
    the answers yet, and a guard goes in only after that.
    """
    known = (source_text(hits) + " " + question).lower()
    return list(dict.fromkeys(
        t for t in LATIN_TERM.findall(POINTER.sub("", body)) if t.lower() not in known))


def reject(body: str, hits: list[BookHit], question: str = "") -> str | None:
    """Why this draft may not be sent, if there is a reason. Reads the draft
    with its [n] pointers still in place."""
    bare = POINTER.sub("", body).strip()
    if NO_ANSWER in bare or len(bare) < MIN_ANSWER:
        return "model had nothing to say"
    if DEGENERATE_RUN.search(bare):
        return "degenerate repetition"
    if not any(1 <= int(n) <= len(hits) for n in POINTER.findall(body)):
        return "no passage cited"
    numbers = unsupported_numbers(body, hits, question)
    if numbers:
        return f"number not in the passages: {numbers[0]}"
    return None


def pick_figures(question: str, shown: list[BookHit], figures: dict[str, dict],
                 weight=None) -> list[dict]:
    """The pictures to put under this answer.

    Candidates are the figures captioned in the passages the model was shown,
    those it cited first. A figure is kept when its caption and the question
    are about the same thing, which is measured, not asked of the model:

      each shared word counts by its rarity in the book (`weight`), so that
      "สาย", which every cable's caption has, does not put the coaxial cable
      under an answer about สายคู่บิดเกลียว;
      the shared words must cover half of the caption or half of the question;
      and a figure behind the best one is dropped: the bus topology's
      caption differs from the star's by one word, and that word is the
      question.
    """
    weight = weight or (lambda word: 1.0)

    def content(text: str) -> set[str]:
        return {w for w in word_tokenize(text.translate(THAI_DIGITS), keep_whitespace=False)
                if len(w) >= 2 and WORD.search(w) and w not in ASKING}

    def mass(words: set[str]) -> float:
        return sum(weight(w) for w in words)

    asked = content(question)
    scored = []
    for order, hit in enumerate(shown):
        for number in hit.rec.get("figures", []):
            info = figures.get(number)
            if not info:
                continue
            words = content(info["caption"])
            score = mass(asked & words)
            if score <= 0:
                continue
            covered = max(score / mass(words), score / mass(asked))
            if covered >= FIGURE_COVER:
                scored.append((-score, order, number, info))
    if not scored:
        return []
    scored.sort(key=lambda s: s[:3])
    best = -scored[0][0]
    seen, out = set(), []
    for negative, _, number, info in scored:
        if number in seen or -negative < FIGURE_NEAR_BEST * best:
            continue
        seen.add(number)
        out.append({"number": number, "caption": info["caption"],
                    "page": info["page"], "url": FIGURES_URL + info["file"],
                    "width": info["width"], "height": info["height"]})
    return out[:MAX_FIGURES]


def nearest(hits: list[BookHit]) -> list[str]:
    return list(dict.fromkeys(h.citation for h in hits))[:3]


def unanswered(hits: list[BookHit], reason: str):
    """A refusal that names the nearest sections and claims nothing else."""
    from app.answer import Answer   # answer.py imports this module

    listing = "\n".join(f"• {c}" for c in nearest(hits))
    return Answer(text=f"{UNANSWERED}\n\nหัวข้อที่ใกล้เคียงที่สุดในหนังสือ\n{listing}",
                  citations=nearest(hits), hits=hits, in_scope=False,
                  source="book", error=reason)


async def answer(question: str):
    """An Answer written from the book, or a refusal if no draft holds up."""
    import asyncio

    from app.answer import Answer, tidy_for_chat   # answer.py imports this module

    index = get_index()
    hits, best = await asyncio.to_thread(index.find, question)
    if best < settings.book_min_sim:
        log.info("REFUSED low-score dense=%.4f | %r", best, question[:80])
        return Answer(text=OUT_OF_SCOPE, hits=hits, in_scope=False, source="book")
    log.info("ANSWERING dense=%.4f top=%s | %r", best, hits[0].rec["id"], question[:80])

    user = (f"คำถามของนักเรียน\n{question}\n\n"
            f"ข้อความจากหนังสือที่ค้นได้\n{build_context(hits)}")
    try:
        draft = await complete(SYSTEM_PROMPT, user)
    except LLMUnavailable as exc:
        # retrieval still worked, so hand back the passages rather than nothing
        listing = "\n\n".join(f"• {h.citation}\n{h.rec['text'][:400]}" for h in hits[:3])
        return Answer(
            text=("ระบบสรุปคำตอบไม่พร้อมใช้งานขณะนี้ "
                  f"แต่พบเนื้อหาที่เกี่ยวข้องในหนังสือดังนี้\n\n{listing}"),
            citations=nearest(hits), hits=hits, source="book", error=str(exc))

    raw = draft
    draft, ungrounded = drop_ungrounded(closing_remarks(raw), hits, question)
    reason = reject(draft, hits, question)
    if reason == "no passage cited" and NO_ANSWER not in raw:
        # The model answered and left every pointer off, which the provider
        # does now and then on a question it answers properly the next time.
        # Asked once more, and only for this: a draft dropped for a number the
        # book does not print is not given a second go at printing it.
        log.info("NO POINTERS, ASKING ONCE MORE | %r", question[:70])
        try:
            raw = await complete(SYSTEM_PROMPT, user + REMINDER)
        except LLMUnavailable as exc:
            return unanswered(hits, f"llm unavailable on retry: {exc}")
        draft, ungrounded = drop_ungrounded(closing_remarks(raw), hits, question)
        reason = reject(draft, hits, question)
    if ungrounded:
        log.info("UNGROUNDED LINES DROPPED %s | %r", ungrounded[:3], question[:70])
    if reason:
        log.info("BOOK ANSWER DROPPED (%s) | %r", reason, question[:80])
        return unanswered(hits, f"book draft dropped: {reason}")
    draft, reordered = in_book_order(draft, hits)
    if reordered:
        log.info("LIST PUT BACK IN BOOK ORDER | %r", question[:70])
    terms = foreign_terms(draft, hits, question)
    if terms:
        log.info("FOREIGN TERMS (logged only) %s | %r", terms[:5], question[:70])
    body, cited = resolve(draft, hits)
    return Answer(text=tidy_for_chat(body),
                  citations=list(dict.fromkeys(h.citation for h in cited)),
                  hits=hits, source="book",
                  figures=pick_figures(
                      question, cited + [h for h in hits if h not in cited],
                      index.figures, index.rarity))
