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

The cosine gate refuses what is not about networking at all. A networking
question the book never reaches (IPv6, VLAN) passes that gate; the guards above
keep it from being answered as if the book had said it, and it is then answered
from the model's own knowledge under a fixed label saying exactly that. The
same label separates anything the model adds to an answer the book does give.
What is the book's and what is the model's never share a line.
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
# Step photographs: from how many of the cited passages, and how many at most.
# LINE shows them in one carousel, which holds twelve.
PHOTO_PASSAGES = 2
MAX_PHOTOS = 8
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

# --- the things people say that are not a question the book answers ---
#
# Read from the first hour of real traffic: "จากหนังสือมีทั้งหมดกี่บทครับ",
# "คุณเป็นใคร", "อยากรู้เพิ่มเติมอีก". Each got the fixed refusal above, word
# for word, and none of them is off the subject -- the first is about the book
# itself, the second about the bot, the third goes on from the last answer.

# A question about the book rather than about networks. Answered from the
# corpus by counting, not by the model: see about_the_book.
ABOUT_BOOK = re.compile(
    r"กี่บท|สารบัญ|มีบทอะไร|บทไหนบ้าง|แต่ละบท|"
    r"(?:หนังสือ|เล่มนี้|วิชานี้|เนื้อหา).{0,20}(?:มีอะไรบ้าง|เรื่องอะไร|เกี่ยวกับอะไร|สอนอะไร|"
    r"ชื่ออะไร|เล่มไหน|อะไรบ้าง)|(?:ใช้|ตอบจาก|อ้างอิง).{0,10}หนังสือ(?:อะไร|เล่มไหน)")

# A message that only makes sense after the one before it.
FOLLOW_UP = re.compile(
    r"เพิ่มเติม|เพิ่มอีก|อีกหน่อย|อีกนิด|ต่ออีก|ต่อเลย|เล่าต่อ|ขยายความ|ละเอียดกว่านี้|"
    r"ละเอียดขึ้น|ยกตัวอย่าง|ขอตัวอย่าง|สรุปสั้น|สั้น ?ๆ|ง่าย ?ๆ|ไม่เข้าใจ|งง|"
    r"หมายความว่า(?:ไง|ยังไง|อย่างไร)|แล้ว.{0,25}(?:ล่ะ|ละ|หล่ะ)|^(?:ทำไม|ยังไง|อย่างไร|เช่น)"
    r"(?:ล่ะ|ครับ|คะ|ค่ะ|\s)*$|^(?:แล้ว|และ|ส่วน|อันนี้|อันนั้น|มัน|ข้อ)|มีรูปไหม|ขอรูป")
MAX_FOLLOW_UP = 60

CHAT_FALLBACK = OUT_OF_SCOPE
MAX_CHAT = 500
CHAT_PROMPT = f"""คุณคือผู้ช่วยทบทวนวิชาเครือข่ายคอมพิวเตอร์เบื้องต้น สำหรับนักเรียนระดับ ปวช. คุยผ่านแอปแชท LINE
คุณตอบคำถามจากหนังสือ{BOOK} (รหัสวิชา 2204-2003) ซึ่งมีเรื่องประเภทของเครือข่าย แบบจำลอง OSI
สายสัญญาณและสื่อกลางไร้สาย อุปกรณ์เครือข่าย โทโปโลยี อีเทอร์เน็ต การเข้าหัวสายแลน
และการตั้งค่าเวิร์กกรุ๊ป บัญชีผู้ใช้ สิทธิ์ การแชร์ไฟล์และเครื่องพิมพ์บน Windows

ข้อความต่อไปนี้ของนักเรียนไม่ใช่คำถามที่หาคำตอบในหนังสือได้ ให้ตอบกลับสั้น ๆ 1-3 ประโยค เป็นธรรมชาติเหมือนคนคุยกัน

- ถ้าเป็นการทักทาย ถามว่าคุณคือใคร หรือชวนคุย ให้ตอบรับสั้น ๆ แล้วชวนถามเรื่องในวิชา
- ถ้าข้อความกำกวม ไม่รู้ว่าถามเรื่องอะไร ให้ถามกลับว่าอยากรู้เรื่องไหน พร้อมยกหัวข้อในวิชา 2-3 หัวข้อ
- ถ้าเป็นเรื่องอื่นที่ไม่ใช่เครือข่ายคอมพิวเตอร์ ให้บอกสุภาพ ๆ ว่าช่วยได้เฉพาะวิชานี้ แล้วชวนถามเรื่องในวิชา
  ห้ามตอบเนื้อหาของเรื่องนั้นแม้แต่บางส่วน ห้ามให้ข้อมูล ตัวเลข สูตร หรือคำแนะนำในเรื่องนั้น
- ห้ามอธิบายเนื้อหาวิชาเครือข่ายในข้อความนี้ ถ้านักเรียนอยากรู้ ให้ชวนถามเป็นคำถามมา
- ห้ามใช้ ** ## เขียนเป็นข้อความธรรมดา ลงท้ายด้วย ครับ ห้ามขึ้นต้นด้วยคำว่า ขออภัย"""

UNANSWERED = (
    "เรื่องนี้ผมหาคำตอบที่ยืนยันกับหนังสือไม่ได้ จึงไม่ตอบ เพราะไม่อยากเดาครับ "
    "อาจเป็นเรื่องที่หนังสือเล่มนี้ไม่ได้อธิบายไว้ หรือลองถามให้เจาะจงขึ้นได้ครับ")

# The model may add what the book does not say, under this word on a line of
# its own. Everything above it is held to the book by the guards below;
# everything under it is the model's own knowledge and is printed under a
# label, written here and not by the model, that says so.
SUPPLEMENT_MARK = "เสริม:"
SUPPLEMENT_LINE = re.compile(r"(?m)^\s*(?:ส่วน)?เสริม\s*[:：]\s*")
SUPPLEMENT_LABEL = ("💡 เสริมจากความรู้ทั่วไปของ AI (ส่วนนี้ไม่ได้มาจากหนังสือ "
                    "ควรตรวจกับครูผู้สอนหรือแหล่งอื่นประกอบ)")
MODEL_NOTICE = ("เรื่องนี้หนังสือคู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้นไม่ได้อธิบายไว้ "
                "คำตอบต่อไปนี้มาจากความรู้ทั่วไปของ AI ไม่ได้มาจากหนังสือ "
                "ควรตรวจกับครูผู้สอนหรือแหล่งอื่นประกอบ")
# When a draft was thrown out by a guard rather than by the model saying the
# book has nothing: the book may cover this, so the notice does not say it
# does not -- only that this answer could not be held to it.
UNVERIFIED_NOTICE = ("ผมยืนยันคำตอบเรื่องนี้กับหนังสือคู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้นไม่ได้ "
                     "คำตอบต่อไปนี้มาจากความรู้ทั่วไปของ AI ไม่ได้มาจากหนังสือ "
                     "ควรตรวจกับครูผู้สอนหรือเปิดหนังสือตามหัวข้อท้ายคำตอบประกอบ")
MODEL_DISCLAIMER = ("ℹ️ คำตอบนี้มาจากความรู้ทั่วไปของ AI ไม่ได้อ้างอิงหนังสือ "
                    "อาจคลาดเคลื่อนหรือไม่เป็นปัจจุบัน")
MAX_SUPPLEMENT = 900

GENERAL_PROMPT = f"""คุณคือผู้ช่วยสอนวิชาเครือข่ายคอมพิวเตอร์ สำหรับนักเรียนระดับ ปวช. ตอบผ่านแอปแชท LINE

คำถามต่อไปนี้ไม่มีคำตอบในหนังสือเรียนของนักเรียน ให้ตอบจากความรู้ทั่วไปของคุณ

กติกา
1. ตอบเฉพาะเรื่องเครือข่ายคอมพิวเตอร์ การสื่อสารข้อมูล และการใช้งานคอมพิวเตอร์บนเครือข่าย
   ถ้าคำถามไม่ใช่เรื่องเหล่านี้ ให้ตอบเพียงว่า {NO_ANSWER}
2. เขียนเฉพาะสิ่งที่มั่นใจ ถ้าไม่แน่ใจ หรือเป็นข้อมูลที่เปลี่ยนตามเวลา เช่น ราคา รุ่นล่าสุด ให้บอกตรง ๆ ว่าไม่แน่ใจ
3. ห้ามอ้างเลขบทหรือเลขหน้าของหนังสือ และห้ามใส่หมายเลข [1] [2]
4. เขียนภาษาไทยที่นักเรียนอ่านเข้าใจง่าย เริ่มด้วยคำตอบตรง ๆ ไม่เกิน 10 บรรทัด
5. ห้ามใช้ ** ## หรือตาราง ใช้ • นำหน้ารายการได้ ลงท้ายประโยคสุดท้ายด้วยคำว่า ครับ"""

SYSTEM_PROMPT = f"""คุณคือผู้ช่วยทบทวนบทเรียนวิชาเครือข่ายคอมพิวเตอร์เบื้องต้น สำหรับนักเรียนระดับ ปวช. ตอบผ่านแอปแชท LINE

คุณจะได้รับคำถาม และข้อความจากหนังสือ{BOOK}ที่ค้นมาให้ แต่ละชิ้นมีหมายเลข [1] [2] ...

กติกา
1. ตอบจากข้อความที่ให้มาเท่านั้น ห้ามเติมจากความรู้เดิม แม้จะมั่นใจว่าถูก
   เหตุผล ตัวอย่าง หรือคำอธิบายที่ข้อความไม่ได้เขียนไว้ ห้ามปนอยู่ในคำตอบส่วนนี้
2. ทุกประโยคที่เป็นเนื้อหา ต้องลงท้ายด้วยหมายเลขของชิ้นที่ใช้ เช่น [1] หรือ [2]
   ห้ามเขียนเลขบทหรือเลขหน้าเอง ระบบจะใส่ให้จากหมายเลขชิ้น
3. ตัวเลข ชื่อมาตรฐาน ชื่อเมนู และชื่อปุ่ม ให้คัดตามข้อความที่ให้มาทุกตัวอักษร ห้ามเปลี่ยน ห้ามเติมค่าที่ไม่ได้เขียนไว้
4. ถ้าเป็นขั้นตอนหรือรายการที่หนังสือใส่เลขลำดับไว้ ให้เรียงตามหนังสือและคงเลขลำดับเดิม ห้ามข้าม ห้ามเพิ่ม ห้ามสลับ
5. ถ้าข้อความที่ให้มาไม่ได้ตอบคำถาม ให้ตอบเพียงว่า {NO_ANSWER} ห้ามตอบจากความรู้เดิม
6. เขียนภาษาไทยที่นักเรียนอ่านเข้าใจง่าย เริ่มด้วยคำตอบตรง ๆ 1-2 ประโยค แล้วขยายเท่าที่จำเป็น ไม่เกิน 12 บรรทัด
7. ห้ามใช้ ** ## หรือตาราง เพราะแสดงผลไม่ได้ ใช้ • นำหน้ารายการได้
8. ลงท้ายประโยคสุดท้ายของคำตอบด้วยคำว่า ครับ ถ้าต้องเรียกตัวเองให้ใช้คำว่า ผม
9. ห้ามเขียนบรรทัดปิดท้ายที่ไม่ใช่เนื้อหา เช่น บอกว่าสรุปให้แล้ว หรืออธิบายว่าเข้าใจคำถามอย่างไร
10. ส่วนเสริม ใช้เฉพาะเมื่อคำถามถามสิ่งที่ข้อความจากหนังสือไม่ได้ตอบจริง ๆ เช่น ถามเหตุผลแต่หนังสือบอกแค่วิธีทำ
    หรือถามถึงเทคโนโลยีที่หนังสือไม่ได้กล่าวถึง คำถามส่วนใหญ่หนังสือตอบครบแล้ว และต้องไม่มีส่วนเสริม
    ห้ามใช้ส่วนเสริมเพื่อขยายความ ยกตัวอย่าง หรือสรุปซ้ำสิ่งที่หนังสือตอบไว้แล้ว
    ถ้าต้องมี ให้ขึ้นบรรทัดใหม่ เขียนคำว่า {SUPPLEMENT_MARK} ไว้บรรทัดเดียว แล้วเขียนต่อจากนั้นไม่เกิน 4 บรรทัด
    ไม่ต้องใส่หมายเลขชิ้น เขียนเฉพาะสิ่งที่มั่นใจ ถ้าไม่แน่ใจให้บอกว่าไม่แน่ใจ
    ถ้าหนังสือไม่ได้ตอบคำถามเลย ให้เขียน {NO_ANSWER} แล้วตามด้วยส่วนเสริมได้"""

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
    "อย่างไรก็ตาม", "นอกจากนี้", "โดยสรุป", "ทั้งหมด", "เท่านี้", "เพียง", "คำตอบ", "หนังสือ", "ระบุ", "อธิบาย"))
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
        # uncaptioned step photographs, by the page they are printed on
        self.photos: dict[int, list[dict]] = {}
        if os.path.exists(FIGURES_PATH):
            with open(FIGURES_PATH, encoding="utf-8") as handle:
                everything = json.load(handle)
            for key, info in everything.items():
                if info.get("kind") == "photo":
                    self.photos.setdefault(info["page"], []).append({**info, "key": key})
                else:
                    self.figures[key] = info
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
        log.info("book ready: %d chunks, %d figures, %d step photos",
                 len(_index.corpus), len(_index.figures),
                 sum(len(v) for v in _index.photos.values()))
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


def drop_unsupported_numbers(draft: str, hits: list[BookHit], context: str = ""
                             ) -> tuple[str, list[str]]:
    """Take out each line that states a number the passages do not print.

    The line, not the whole answer: a draft of eight sound lines used to be
    thrown away for one "1000" in the ninth, and the question then went to the
    model's own knowledge although the book had answered it. `context` is
    what else the number may rightly come from -- the question, and on a
    follow-up the answer already given, whose numbers were checked then.
    """
    kept, removed = [], []
    for line in draft.split("\n"):
        bad = unsupported_numbers(line, hits, context)
        if bad:
            removed.append(bad[0])
        else:
            kept.append(line)
    return "\n".join(kept), removed


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


def pick_figures(question: str, cited: list[BookHit], shown: list[BookHit],
                 figures: dict[str, dict], weight=None,
                 photos: dict[int, list[dict]] | None = None) -> list[dict]:
    """The pictures to put under this answer. None of this is asked of the model.

    Captioned figures ("รูปที่ 2.3") come from the passages the answer cites,
    and from the other passages it was shown in the same chapter. Not from
    another chapter: asked how to crimp a LAN plug, the answer cited chapter 4
    and was given the coaxial cable of chapter 3, whose caption also says
    "เข้าหัว". A figure is kept when its caption and the question are about the
    same thing:

      each shared word counts by its rarity in the book (`weight`), so that
      "สาย", which every cable's caption has, does not put the coaxial cable
      under an answer about สายคู่บิดเกลียว;
      the shared words must cover half of the caption or half of the question;
      and a figure behind the best one is dropped: the bus topology's
      caption differs from the star's by one word, and that word is the
      question.

    Step photographs have no caption to compare, only the step printed above
    them. They are shown for the pages of the passages the answer cites first,
    in the book's order -- the steps the answer has just listed.
    """
    weight = weight or (lambda word: 1.0)

    def content(text: str) -> set[str]:
        return {w for w in word_tokenize(text.translate(THAI_DIGITS), keep_whitespace=False)
                if len(w) >= 2 and WORD.search(w) and w not in ASKING}

    def mass(words: set[str]) -> float:
        return sum(weight(w) for w in words)

    def entry(number: str, info: dict) -> dict:
        return {"number": number, "caption": info["caption"], "page": info["page"],
                "kind": info.get("kind", "figure"), "url": FIGURES_URL + info["file"],
                "width": info["width"], "height": info["height"]}

    asked = content(question)
    chapters = {h.rec["chapter"] for h in cited}
    near = cited + [h for h in shown if h not in cited and h.rec["chapter"] in chapters]
    scored = []
    for order, hit in enumerate(near):
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
    scored.sort(key=lambda s: s[:3])
    best = -scored[0][0] if scored else 0.0
    seen, out = set(), []
    for negative, _, number, info in scored:
        if number in seen or -negative < FIGURE_NEAR_BEST * best:
            continue
        seen.add(number)
        out.append(entry(number, info))
    out = out[:MAX_FIGURES]

    steps: list[dict] = []
    for hit in cited[:PHOTO_PASSAGES]:
        for page in range(hit.rec["page_from"], hit.rec["page_to"] + 1):
            for info in (photos or {}).get(page, []):
                if info not in steps:
                    steps.append(info)
    if len(steps) > MAX_PHOTOS:
        # too many to show: keep the steps the question is about, then the first
        ranked = sorted(range(len(steps)), key=lambda i: (
            -mass(asked & content(steps[i]["caption"])), i))[:MAX_PHOTOS]
        steps = [steps[i] for i in sorted(ranked)]
    return out + [entry(info["key"], info) for info in steps]


def nearest(hits: list[BookHit]) -> list[str]:
    return list(dict.fromkeys(h.citation for h in hits))[:3]


def unanswered(hits: list[BookHit], reason: str):
    """A refusal that names the nearest sections and claims nothing else."""
    from app.answer import Answer   # answer.py imports this module

    listing = "\n".join(f"• {c}" for c in nearest(hits))
    return Answer(text=f"{UNANSWERED}\n\nหัวข้อที่ใกล้เคียงที่สุดในหนังสือ\n{listing}",
                  citations=nearest(hits), hits=hits, in_scope=False,
                  source="book", error=reason)


def split_supplement(raw: str) -> tuple[str, str]:
    """(what the model says the book says, what it adds of its own)."""
    mark = SUPPLEMENT_LINE.search(raw)
    if not mark:
        return raw, ""
    return raw[:mark.start()].rstrip(), raw[mark.end():].strip()


def clean_supplement(extra: str) -> str:
    """The model's own addition, made safe to print: no pointer that would
    read as a reference to the book, no runaway text."""
    extra = closing_remarks(POINTER.sub("", extra)).strip()
    if not extra or NO_ANSWER in extra or DEGENERATE_RUN.search(extra):
        return ""
    if len(extra) > MAX_SUPPLEMENT:
        extra = extra[:MAX_SUPPLEMENT].rsplit("\n", 1)[0].rstrip() + " …"
    return extra


async def from_general_knowledge(question: str, hits: list[BookHit], extra: str,
                                 why: str):
    """Answer what the book does not, from the model's own knowledge, labelled.

    Reached only for a question that passed the gate -- it is about networking
    -- and that the book could not answer. The label is fixed text and comes
    first; there are no references and no figures, because none of this is the
    book's.
    """
    from app.answer import Answer, tidy_for_chat   # answer.py imports this module

    if not extra:
        try:
            extra = clean_supplement(await complete(
                GENERAL_PROMPT, f"คำถามของนักเรียน\n{question}"))
        except LLMUnavailable as exc:
            return unanswered(hits, f"llm unavailable: {exc}")
    if not extra:
        return unanswered(hits, why)
    log.info("ANSWERED FROM GENERAL KNOWLEDGE (%s) | %r", why, question[:70])
    if "nothing to say" in why:
        text = f"{MODEL_NOTICE}\n\n{tidy_for_chat(extra)}"
    else:
        # a guard, not the model, threw the draft out; point at the sections
        # where the book's own answer would be, if it has one
        listing = "\n".join(f"• {c}" for c in nearest(hits))
        text = (f"{UNVERIFIED_NOTICE}\n\n{tidy_for_chat(extra)}\n\n"
                f"หัวข้อที่ใกล้เคียงที่สุดในหนังสือ\n{listing}")
    return Answer(text=text, hits=hits, source="model", error=why)


def about_the_book(index: BookIndex) -> str:
    """What the book is and what its chapters are, counted from the corpus."""
    chapters: dict[int, dict] = {}
    for rec in index.corpus:
        row = chapters.setdefault(rec["chapter"], {
            "title": rec["chapter_title"], "first": rec["page_from"], "last": rec["page_to"]})
        row["last"] = max(row["last"], rec["page_to"])
    listing = "\n".join(f"บทที่ {n} {row['title']} (หน้า {row['first']}-{row['last']})"
                        for n, row in sorted(chapters.items()))
    return (f"ผมตอบจากหนังสือ{BOOK} รหัสวิชา 2204-2003 ของฝ่ายตำราวิชาการคอมพิวเตอร์ "
            f"ซีเอ็ดยูเคชั่น มีทั้งหมด {len(chapters)} บทครับ\n\n{listing}\n\n"
            "อยากทบทวนบทไหนหรือเรื่องไหน ถามมาได้เลยครับ")


def with_context(question: str, previous: str | None) -> str:
    """What to search for: the message itself, or -- when it only makes sense
    after the one before it ("อยากรู้เพิ่มเติมอีก", "แล้วข้อเสียล่ะ") -- the
    message with the earlier question behind it. The new words go first: they
    are what is being asked now, and the earlier question only says about what.
    """
    if previous and len(question) <= MAX_FOLLOW_UP and FOLLOW_UP.search(question):
        return f"{question} — {previous.strip()}"
    return question


async def chat_reply(question: str) -> str:
    """A short reply, written for this message, to something that is not a
    question for the book. The decision not to answer was made by the gate
    before this is called; the model only words it. Falls back on any doubt."""
    try:
        text = (await complete(CHAT_PROMPT, f"ข้อความของนักเรียน\n{question}")).strip()
    except LLMUnavailable as exc:
        log.info("chat reply fell back to fixed text: %s", exc)
        return CHAT_FALLBACK
    text = POINTER.sub("", text).replace("**", "").strip()
    if not text or len(text) > MAX_CHAT or DEGENERATE_RUN.search(text):
        log.info("chat reply rejected, using fixed text | %r", text[:80])
        return CHAT_FALLBACK
    return text


MAX_EARLIER = 1200
GOING_ON = ("\n\nนักเรียนได้คำตอบข้างล่างนี้ไปแล้วจากคำถามก่อนหน้า ห้ามเล่าซ้ำ และห้ามเริ่มอธิบายเรื่องเดิมใหม่ "
            "ตอบเฉพาะสิ่งที่คำถามตอนนี้ถาม ถ้าคำถามตอนนี้ขอให้เล่าเพิ่มโดยไม่เจาะจง "
            "ให้เล่าส่วนที่ข้อความจากหนังสือมีแต่คำตอบเดิมยังไม่ได้พูดถึง "
            "ถ้าข้อความจากหนังสือไม่มีอะไรเพิ่มแล้ว ให้บอกว่าหนังสืออธิบายไว้เท่านี้ "
            "แล้วใช้ส่วนเสริมได้\n\nคำตอบที่ให้ไปแล้ว\n")


async def answer(question: str, previous: str | None = None,
                 previous_answer: str | None = None):
    """An Answer written from the book, or a refusal if no draft holds up."""
    import asyncio

    from app.answer import Answer, tidy_for_chat   # answer.py imports this module

    index = get_index()
    if ABOUT_BOOK.search(question):
        log.info("ABOUT THE BOOK | %r", question[:60])
        return Answer(text=about_the_book(index), source="book")
    asked = question
    question = with_context(question, previous)
    if question != asked:
        log.info("FOLLOW-UP joined to %r | %r", (previous or "")[:50], asked[:50])
    hits, best = await asyncio.to_thread(index.find, question)
    if best < settings.book_min_sim:
        log.info("NOT A QUESTION FOR THE BOOK dense=%.4f | %r", best, question[:80])
        return Answer(text=await chat_reply(asked), hits=hits, in_scope=False,
                      source="book")
    log.info("ANSWERING dense=%.4f top=%s | %r", best, hits[0].rec["id"], question[:80])

    if question == asked:
        user = (f"คำถามของนักเรียน\n{question}\n\n"
                f"ข้อความจากหนังสือที่ค้นได้\n{build_context(hits)}")
    else:
        user = (f"คำถามก่อนหน้าของนักเรียน\n{previous}\n\n"
                f"คำถามตอนนี้ ซึ่งถามต่อจากคำถามก่อนหน้า\n{asked}\n\n"
                f"ข้อความจากหนังสือที่ค้นได้\n{build_context(hits)}")
        if previous_answer:
            user += GOING_ON + previous_answer[:MAX_EARLIER]
    try:
        draft = await complete(SYSTEM_PROMPT, user)
    except LLMUnavailable as exc:
        # retrieval still worked, so hand back the passages rather than nothing
        listing = "\n\n".join(f"• {h.citation}\n{h.rec['text'][:400]}" for h in hits[:3])
        return Answer(
            text=("ระบบสรุปคำตอบไม่พร้อมใช้งานขณะนี้ "
                  f"แต่พบเนื้อหาที่เกี่ยวข้องในหนังสือดังนี้\n\n{listing}"),
            citations=nearest(hits), hits=hits, source="book", error=str(exc))

    context = question if question == asked else f"{question} {previous_answer or ''}"

    def check(raw: str):
        kept, ungrounded = drop_ungrounded(closing_remarks(raw), hits, context)
        kept, numbers = drop_unsupported_numbers(kept, hits, context)
        if numbers:
            log.info("LINES WITH UNSUPPORTED NUMBERS DROPPED %s | %r",
                     numbers[:3], question[:70])
        why = reject(kept, hits, context)
        if why and numbers and NO_ANSWER not in kept:
            # nothing was left once those lines were out
            why = f"number not in the passages: {numbers[0]}"
        return kept, ungrounded, why

    raw, extra = split_supplement(draft)
    extra = clean_supplement(extra)
    draft, ungrounded, reason = check(raw)
    if reason == "no passage cited" and NO_ANSWER not in raw:
        # The model answered and left every pointer off, which the provider
        # does now and then on a question it answers properly the next time.
        # Asked once more, and only for this: a draft dropped for a number the
        # book does not print is not given a second go at printing it.
        log.info("NO POINTERS, ASKING ONCE MORE | %r", question[:70])
        try:
            raw, again = split_supplement(await complete(SYSTEM_PROMPT, user + REMINDER))
        except LLMUnavailable as exc:
            return unanswered(hits, f"llm unavailable on retry: {exc}")
        extra = clean_supplement(again) or extra
        draft, ungrounded, reason = check(raw)
    if ungrounded:
        log.info("UNGROUNDED LINES DROPPED %s | %r", ungrounded[:3], question[:70])
    if reason:
        log.info("BOOK ANSWER DROPPED (%s) | %r", reason, question[:80])
        # Nothing the model said could be held to the book. What it knows
        # besides is offered instead, under a notice saying where it is from.
        return await from_general_knowledge(
            question, hits, extra, f"book draft dropped: {reason}")
    draft, reordered = in_book_order(draft, hits)
    if reordered:
        log.info("LIST PUT BACK IN BOOK ORDER | %r", question[:70])
    terms = foreign_terms(draft, hits, question)
    if terms:
        log.info("FOREIGN TERMS (logged only) %s | %r", terms[:5], question[:70])
    body, cited = resolve(draft, hits)
    body = tidy_for_chat(body)
    if extra:
        log.info("SUPPLEMENTED FROM GENERAL KNOWLEDGE | %r", question[:70])
        body = f"{body}\n\n{SUPPLEMENT_LABEL}\n{tidy_for_chat(extra)}"
    return Answer(text=body,
                  citations=list(dict.fromkeys(h.citation for h in cited)),
                  hits=hits, source="book",
                  figures=pick_figures(question, cited, hits, index.figures,
                                       index.rarity, index.photos))
