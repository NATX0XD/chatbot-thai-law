# -*- coding: utf-8 -*-
"""Answer from the journal articles when the rules are not what was asked for.

The Council's regulations say what a teacher must and must not do. They do not
say what จิตวิญญาณความเป็นครู is, how ไตรสิกขา is applied to the five duties, or
what a survey of teachers in one district found -- and those are questions the
people this bot is for do ask. Fourteen journal articles cover them, in a corpus
and an index of their own (ingest/extract_articles.py explains why they are not
simply added to the rules).

This module decides when a question belongs to the articles, and writes the
answer when it does. Three things hold it to the same standard as the rule path:

  the route is measured   `python -m ingest.calibrate_articles` prints the
                          scores the two thresholds below were read from.
  the citation is copied  the model writes [2]; the author and year come from
                          record 2. It never types a name or a year itself.
  the label is fixed      every answer opens with a sentence, written here and
                          not by the model, saying it rests on an article and is
                          not a rule anyone can be held to.

A question that is not routed here is answered exactly as it was before this
module existed. One that is routed here and cannot be answered well is refused
here, naming the articles that came closest. It is not handed back to the rule
path: the rules scored lower on it, and when that was tried the rule path
answered a question about a survey's findings by reciting ข้อ 7.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.bm25_lite import BM25Lite
from app.config import settings
from app.corpus_store import open_corpus
from app.llm import LLMUnavailable, complete
from app.numbers import unsupported_figures
from app.retriever import Hit, SearchResult
from app.thai_tokenize import word_tokenize

log = logging.getLogger(__name__)

# Read from `python -m ingest.calibrate_articles`, 172 probes, 2026-10-04:
#
#                                  n   best article cosine   article minus rule
#   answerable from the rules    118     0.396 – 0.763        -0.318 … +0.074
#   written from the articles     39     0.671 – 0.840        +0.021 … +0.343
#   not a question for this bot    6     0.345 – 0.428        (rules refuse these)
#
# The 118 include the sixty acceptance questions the reported results rest on.
#
# Every one of the sixteen article questions also clears the rule corpus's own
# gate -- each is about a teacher's ethics, and so is every regulation -- which
# is why "fall back when the rules refuse" would never have fired for them.
# The absolute score does not separate the two groups either; the difference
# does, because an article that merely quotes a rule scores no higher than the
# rule itself.
#
# MARGIN was first set at 0.05 and sent two acceptance questions to the
# articles, "จรรยาบรรณต่อวิชาชีพกำหนดไว้ว่าอย่างไร" among them -- a question
# about the rule, answered with somebody's reading of it. At 0.08 none of the
# 118 moves. The closest sits at +0.074, which is not much room. The article
# questions MARGIN alone leaves behind are picked up by the two narrower
# tests in route(), each of which needs something more than the score.
#
# Every article probe was written by the developer from the articles
# themselves. That is thin and flattering, and all three numbers should be
# re-read once the testers' real questions are in data/eval/.
MIN_ARTICLE_SIM = 0.55
MARGIN = 0.08

RESEARCH_WORDS = ("งานวิจัย", "ผลวิจัย", "ผลการวิจัย", "บทความ", "กลุ่มตัวอย่าง",
                  "ผลการศึกษา")
NEAR_MARGIN = 0.02
QUESTION_WORDS = frozenset((
    "อะไร", "บ้าง", "ใคร", "อย่างไร", "ยังไง", "ทำไม", "เท่าใด", "เท่าไร",
    "เท่าไหร่", "หรือไม่", "เมื่อใด", "เมื่อไร", "เมื่อไหร่", "หมายถึง", "แบบไหน"))
TOP_K = 6
ABSTRACT = "บทคัดย่อ"
MAX_ABSTRACT = 2
UNLABELLED_ABSTRACT = 3
MIN_BODY_CHARS = 80

NOTICE = ("เรื่องนี้ไม่ได้เขียนไว้ในข้อบังคับคุรุสภาโดยตรง คำตอบต่อไปนี้สรุปจากบทความวิชาการ "
          "จึงเป็นความเห็นหรือผลการศึกษาของผู้เขียนบทความ ไม่ใช่กฎที่ใช้บังคับ")

UNANSWERED = ("เรื่องนี้ไม่ได้เขียนไว้ในข้อบังคับคุรุสภาโดยตรง ระบบพบบทความวิชาการที่เกี่ยวข้อง "
              "แต่ข้อความที่ค้นได้ไม่พอจะสรุปคำตอบได้อย่างมั่นใจ จึงไม่ขอสรุป")

DISCLAIMER = ("ℹ️ สรุปจากบทความในวารสารวิชาการ ไม่ใช่ตัวบทของข้อบังคับคุรุสภา "
              "และไม่ใช่คำวินิจฉัยของคุรุสภา ควรอ่านบทความฉบับเต็มก่อนนำไปอ้างอิง")

SYSTEM_PROMPT = """คุณคือผู้ช่วยสรุปบทความวิชาการเรื่องจรรยาบรรณและจริยธรรมของครู ตอบผ่านแอปแชท LINE

เนื้อหา
1. ตอบจากข้อความบทความที่ให้มาเท่านั้น ห้ามใช้ความรู้อื่น
2. ทุกประโยคที่เป็นสาระ ต้องลงท้ายด้วยเลขในวงเล็บเหลี่ยมของข้อความที่ใช้ เช่น [1] [3]
   ห้ามพิมพ์ชื่อผู้เขียน ชื่อบทความ ชื่อวารสาร หรือปีเอง ระบบจะเติมให้จาก [เลข] ที่คุณใส่
3. ข้อความเหล่านี้เป็นบทความ ไม่ใช่ข้อบังคับ ห้ามเขียนว่าครู "ต้อง" ทำสิ่งใดตามกฎ
   ห้ามอ้างเลขข้อหรือเลขมาตราของข้อบังคับหรือกฎหมายใด แม้บทความจะเขียนไว้
   ให้เขียนว่าเป็นสิ่งที่บทความเสนอ หรือสิ่งที่งานวิจัยนั้นพบ
4. ผลวิจัยเป็นของกลุ่มตัวอย่างในงานนั้นเท่านั้น ถ้ายกผลวิจัยมา ต้องบอกว่าศึกษากับใครหรือที่ใด
   ตามที่ข้อความเขียนไว้ ห้ามสรุปว่าเป็นจริงกับครูทั่วไป
5. ตัวเลขทุกตัวต้องคัดจากข้อความที่ให้มา ห้ามคำนวณหรือประมาณเอง
6. ระดับผลการประเมิน เช่น มากที่สุด มาก ปานกลาง ดีมาก ดี ให้คัดคำตามข้อความที่ให้มา
   ห้ามเปลี่ยนเป็นคำอื่น เช่น ห้ามเขียน "ระดับสูง" แทน "ระดับมาก" และถ้ามีค่าเฉลี่ยกำกับให้ยกมาด้วย
7. ถ้าข้อความที่ให้มาไม่ตอบคำถาม ให้ตอบเพียงคำว่า ไม่มีข้อมูลพอ ห้ามเดา

รูปแบบสำหรับหน้าจอแชท
- ย่อหน้าแรกคือคำตอบตรง ๆ 1-2 ประโยค
- เว้นบรรทัดว่าง แล้วอธิบายสั้น ๆ ถ้ามีหลายประเด็นให้ขึ้นบรรทัดใหม่ นำหน้าด้วย •
- ความยาวรวมไม่เกิน 10 บรรทัด
- ห้ามใช้ ** __ ## หรือสัญลักษณ์ markdown ใด ๆ ห้ามทวนคำถาม ห้ามพูดถึงตัวระบบ"""

POINTER = re.compile(r"\s*\[(\d{1,2})\]")
RULE_NUMBER = re.compile(r"(?:มาตรา|ข้อ(?!มูล|เสนอ|ความ|สรุป|ค้นพบ|คำถาม|จำกัด|สังเกต))\s*[๐-๙0-9]")
# "สมชาย ใจดี (2559)" is how the source list names an article; inside a sentence
# the same thing is written "(สมชาย ใจดี, 2559)"
INLINE_YEAR = re.compile(r" \((\d{4})\)$")
REPEATED_CITE = re.compile(r"( \([^()]+\))(?:\1)+")
NAMES_A_LAW = re.compile(r"ข้อบังคับ|พระราชบัญญัติ|พ\.ร\.บ\.|คุรุสภา|ประกาศ|กฎหมาย")
WORD = re.compile(r"[\u0e00-\u0e7fA-Za-z]")
NO_ANSWER = "ไม่มีข้อมูลพอ"
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
DEGENERATE_RUN = re.compile(r"(.{2,40}?)\1{9,}")


@dataclass
class ArticleHit(Hit):
    @property
    def citation(self) -> str:
        """Who wrote it, when, what it is called and where it was printed."""
        r = self.rec
        return f"{r['short']} {r['title']} — {r['journal']}"


class ArticleIndex:
    """The article corpus with its vectors and its BM25 postings."""

    def __init__(self):
        self.corpus = open_corpus(settings.articles_path)
        self.vectors = np.load(settings.articles_vectors_path, mmap_mode="r")
        self.bm25 = BM25Lite(settings.articles_bm25_path, settings.articles_vocab_path)
        # Where each article's abstract sits, so it can be fetched without a
        # second search. See with_abstract.
        self.abstracts: dict[str, list[int]] = {}
        for i, rec in enumerate(self.corpus):
            if rec.get("heading", "").startswith(ABSTRACT):
                self.abstracts.setdefault(rec["sysid"], []).append(i)
        # Two of the fourteen print their abstract with no "บทคัดย่อ" above it.
        # There the opening passages stand in, which is where an abstract is.
        opening: dict[str, list[int]] = {}
        for i, rec in enumerate(self.corpus):
            if not rec.get("heading"):
                opening.setdefault(rec["sysid"], []).append(i)
        for sysid, first in opening.items():
            self.abstracts.setdefault(sysid, first[:UNLABELLED_ABSTRACT])
        for name, size in (("vectors", len(self.vectors)), ("bm25", self.bm25.n_docs)):
            if size != len(self.corpus):
                raise RuntimeError(
                    f"article index/corpus mismatch: {size} {name} vs "
                    f"{len(self.corpus)} chunks. Re-run ingest.build_article_index.")

    def search(self, question: str, vector: np.ndarray, top_k: int = TOP_K
               ) -> tuple[list[ArticleHit], float]:
        """The best passages for this question, and the best cosine among them."""
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            # the same spurious Accelerate warnings as app/retriever.py
            sims = np.asarray(self.vectors, dtype=np.float32) @ np.asarray(
                vector, dtype=np.float32)
        dense = [int(i) for i in np.argsort(-sims)[:settings.top_k_dense]]
        scores = self.bm25.get_scores(word_tokenize(question, keep_whitespace=False))
        sparse = [int(i) for i in np.argsort(-scores)[:settings.top_k_bm25]
                  if scores[i] > 0]
        fused: dict[int, float] = {}
        for ranking in (dense, sparse):
            for rank, idx in enumerate(ranking):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (settings.rrf_k + rank + 1)
        d_rank = {idx: r for r, idx in enumerate(dense)}
        b_rank = {idx: r for r, idx in enumerate(sparse)}
        order = sorted(fused, key=lambda i: -fused[i])[:top_k]
        hits = [ArticleHit(rec=self.corpus[i], rrf=fused[i],
                           dense_score=float(sims[i]), bm25_score=float(scores[i]),
                           dense_rank=d_rank.get(i), bm25_rank=b_rank.get(i))
                for i in order]
        return hits, float(sims[dense[0]])


    def with_abstract(self, hits: list[ArticleHit]) -> list[ArticleHit]:
        """Add the abstract of the article the best passage came from.

        The abstract is where a study states what it found, and it is written
        in the vocabulary of the whole study rather than of any one question.
        "ครูต้องการพัฒนาเรื่องใดเป็นลำดับแรก" retrieved the introduction, the
        objectives and the recommendations of the right article -- every
        passage that names the four areas -- and not the abstract, twelfth,
        which is the one that ranks them.
        """
        if not hits:
            return hits
        have = {h.rec["id"] for h in hits}
        extra = [ArticleHit(rec=self.corpus[i], rrf=0.0)
                 for i in self.abstracts.get(hits[0].rec["sysid"], [])[:UNLABELLED_ABSTRACT]]
        return hits + [h for h in extra if h.rec["id"] not in have]


_index: Optional[ArticleIndex] = None
_checked = False


def available() -> bool:
    return all(os.path.exists(p) for p in (
        settings.articles_path, settings.articles_vectors_path,
        settings.articles_bm25_path, settings.articles_vocab_path))


def get_index() -> Optional[ArticleIndex]:
    """The article index, or None when it has not been built on this machine.

    Absent is a state, not a fault: the files are not in the repository yet, so
    a server built from git runs on the rules alone. It is logged once, loudly,
    so nobody reads the missing answers as a bug. Present but inconsistent is a
    fault, and raises.
    """
    global _index, _checked
    if not _checked:
        _checked = True
        if available():
            _index = ArticleIndex()
            log.info("articles ready: %d chunks", len(_index.corpus))
        else:
            log.warning("ARTICLES OFF: %s or its index is missing -- answering "
                        "from the rules only", settings.articles_path)
    return _index


def beyond_the_rules(asked: str, index: ArticleIndex, rule_vocabulary) -> list[str]:
    """Words in the question that the articles use and no rule ever does.

    ตัวบ่งชี้, ราชภัฏ, ดิจิทัล: none of them occurs anywhere in the ten
    instruments, so whatever is being asked about them, the rules do not say
    it. Question words are left out -- "อะไร" and "บ้าง" are not in the rules
    either, and say nothing about the subject.
    """
    words = dict.fromkeys(word_tokenize(asked, keep_whitespace=False))
    return [w for w in words
            if len(w) >= 3 and w not in QUESTION_WORDS
            and w in index.bm25.term_id and w not in rule_vocabulary]


def route(question: str, rules: SearchResult, encode,
          rule_vocabulary=()) -> list[ArticleHit] | None:
    """The passages to answer from, if this question is one for the articles.

    `encode` is the rule retriever's own embedder, so both corpora are compared
    under one model and the service holds one client.
    """
    index = get_index()
    # a question that names ข้อ 7 wants ข้อ 7, whatever else resembles it
    if index is None or rules.exact_section:
        return None
    asked = question.translate(THAI_DIGITS)
    hits, best = index.search(asked, encode(asked))
    if best < MIN_ARTICLE_SIM:
        return None
    # Someone who asks what a study found has said which corpus they mean, the
    # same way naming ข้อ 7 does on the other side. None of the 108 rule
    # questions uses any of these words; "งานวิจัย...พบว่าจรรยาบรรณมีกี่
    # องค์ประกอบ กี่ตัวบ่งชี้" does, sat at +0.02, and was answered from
    # มาตรา 50 with the count of indicators left out.
    asks_for_research = any(word in asked for word in RESEARCH_WORDS)
    lead = best - rules.max_dense
    # A smaller lead is enough when the question is about something the rules
    # have no word for. Read from the same calibration run: among the 118 rule
    # questions, those using such a word lead by +0.004 at most, and those
    # leading by +0.02 or more use none. Both conditions together move none of
    # them, and bring in the four article questions MARGIN alone left behind.
    foreign = beyond_the_rules(asked, index, rule_vocabulary) if rule_vocabulary else []
    near = lead >= NEAR_MARGIN and bool(foreign)
    if rules.in_scope and not (asks_for_research or near or lead >= MARGIN):
        return None
    log.info("ARTICLES article=%.4f rules=%.4f foreign=%s top=%s | %r",
             best, rules.max_dense, foreign[:4], hits[0].rec["id"], question[:80])
    return index.with_abstract(hits)


def build_context(hits: list[ArticleHit]) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        head = f"[{i}] บทความเรื่อง {h.rec['title']}"
        if h.rec.get("heading"):
            head += f"\n    (อยู่ในหัวข้อ {h.rec['heading']})"
        blocks.append(f"{head}\n{h.rec['text']}")
    return "\n\n".join(blocks)


def resolve(text: str, hits: list[ArticleHit]) -> tuple[str, list[ArticleHit]]:
    """Swap each [n] for the author and year of passage n.

    A pointer to a passage that was never supplied is dropped rather than
    guessed at. Returns the passages actually cited, in the order first cited.
    """
    cited: list[ArticleHit] = []

    def swap(match: re.Match) -> str:
        n = int(match.group(1))
        if not 1 <= n <= len(hits):
            return ""
        hit = hits[n - 1]
        if hit not in cited:
            cited.append(hit)
        inline = INLINE_YEAR.sub(r", \1", hit.rec["short"])
        return f" ({inline})"

    text = POINTER.sub(swap, text)
    # "[1] [2]" from one article, or "[1][1]", would print the same name twice
    text = REPEATED_CITE.sub(r"\1", text)
    return "\n".join(line.rstrip() for line in text.split("\n")), cited


def drop_ungrounded(draft: str, hits: list[ArticleHit]) -> tuple[str, list[str]]:
    """Remove every line that cites nothing and says something the passages do not.

    The prompt asks for a pointer on each sentence and the model gives one per
    list instead, so a line without a pointer is normal -- nine course topics
    copied out under one citation. It is also where the model adds what it
    remembers. Asked which principles govern ครองคน, it listed them correctly
    from the passage and then explained one from memory: "สังคหวัตถุ 4 ได้แก่
    ทาน สมถะ ปัญญา และวิริยะ", three of the four wrong, no pointer.

    So a line with no pointer has to be made of the passages' own words. Every
    word of three letters or more must occur in them; one that does not takes
    the whole line with it. Losing a correct line that was reworded is the
    price, and it is the cheaper mistake.
    """
    source = " ".join(f"{h.rec['title']} {h.rec.get('heading', '')} {h.rec['text']}"
                      for h in hits).translate(THAI_DIGITS)
    kept, dropped = [], []
    for line in draft.split("\n"):
        if not line.strip() or POINTER.search(line):
            kept.append(line)
            continue
        words = word_tokenize(line.translate(THAI_DIGITS), keep_whitespace=False)
        foreign = [w for w in words
                   if len(w) >= 3 and WORD.search(w) and w not in source]
        if foreign:
            dropped.append(f"{line.strip()[:60]} <- {foreign[0]}")
        else:
            kept.append(line)
    return "\n".join(kept), dropped


def reject(body: str, hits: list[ArticleHit]) -> str | None:
    """Why this draft may not be sent, if there is a reason. Reads the draft
    with its [n] pointers still in place."""
    bare = POINTER.sub("", body).strip()
    if NO_ANSWER in bare or len(bare) < MIN_BODY_CHARS:
        return "model had nothing to say"
    if DEGENERATE_RUN.search(bare):
        return "degenerate repetition"
    if not any(1 <= int(n) <= len(hits) for n in POINTER.findall(body)):
        return "no passage cited"
    # Only where the sentence is about a law. A questionnaire has ข้อ 1 too, and
    # an answer about a twenty-item scale was thrown away for saying so.
    for line in bare.split("\n"):
        numbered = RULE_NUMBER.search(line)
        if numbered and (numbered.group(0).startswith("มาตรา") or NAMES_A_LAW.search(line)):
            return f"cites a rule number: {numbered.group(0)!r}"
    figures = unsupported_figures(bare, [h.rec["text"] for h in hits])
    if figures:
        return f"figure not in the passages: {figures[0]}"
    return None


def unanswered(hits: list[ArticleHit], reason: str):
    """A refusal that names the nearest articles and claims nothing else."""
    from app.answer import Answer   # answer.py imports this module

    nearest = list(dict.fromkeys(h.citation for h in hits))[:3]
    listing = "\n".join(f"• {c}" for c in nearest)
    return Answer(text=f"{UNANSWERED}\n\nบทความที่ใกล้เคียงที่สุด\n{listing}",
                  citations=nearest, hits=hits, in_scope=False,
                  source="articles", error=reason)


async def write(question: str, hits: list[ArticleHit]):
    """An Answer built from these passages, or a refusal if no draft holds up."""
    from app.answer import Answer, tidy_for_chat   # answer.py imports this module

    user = (f"คำถามของประชาชน\n{question}\n\n"
            f"ข้อความจากบทความที่ค้นได้\n{build_context(hits)}")
    try:
        draft = await complete(SYSTEM_PROMPT, user)
    except LLMUnavailable as exc:
        log.info("article answer unavailable: %s", exc)
        return unanswered(hits, f"llm unavailable: {exc}")

    draft, ungrounded = drop_ungrounded(draft, hits)
    if ungrounded:
        log.info("UNGROUNDED LINES DROPPED %s | %r", ungrounded[:3], question[:70])
    reason = reject(draft, hits)
    if reason:
        log.info("ARTICLE ANSWER DROPPED (%s) | %r", reason, question[:80])
        return unanswered(hits, f"article draft dropped: {reason}")
    body, cited = resolve(draft, hits)
    citations = list(dict.fromkeys(h.citation for h in cited))
    return Answer(text=f"{NOTICE}\n\n{tidy_for_chat(body)}", citations=citations,
                  hits=hits, source="articles")
