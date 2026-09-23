# -*- coding: utf-8 -*-
"""Check that each citation supports the sentence it is attached to.

app/verify.py asks whether the answer names a law the corpus holds. That is a
question about *provenance*, and four rounds of acceptance testing showed it is
the wrong question to stop at. It rejected correct answers -- one refusal said
พ.ร.บ.สภาครูฯ 2546 "ไม่มีอยู่ในคลังข้อมูล" about an act with ninety-two records
in the corpus, because that act had not been retrieved for that particular
question -- while the answers that were actually wrong sailed through, since
every instrument they named was real.

What was wrong about them was the pairing. The tester's word-for-word examples:

    มาตรฐานวิชาชีพมี 5 ด้าน (พ.ร.บ.สภาครูฯ 2546 มาตรา 50)
        มาตรา 50 is the five duties of ethics; มาตรา 49 is the three standards
    ครูใช้หลักวิชาผิด ... (ข้อบังคับฯ จรรยาบรรณ 2556 ข้อ 10)
        ข้อ 10 does not contain the word หลักวิชา, or anything near it
    ... เรื่องสิ่งแวดล้อม (ข้อบังคับฯ จรรยาบรรณ 2556 ข้อ 9)
        ข้อ 9 is about treating pupils equally

In each one the claim and the cited text share no distinctive word at all. So
this module asks the other question -- is the claim supported by the text it
points at -- and answers it from the corpus rather than from the retrieved set,
because a citation can be checked whether or not it was handed over.

Three checks, cheapest first:

  1. the rule exists       ข้อ 99 of a regulation with 24 rules does not
  2. the sub-item exists   "(ก)(๕)" where (ก) has two items does not
  3. the claim overlaps    zero shared distinctive words means the sentence is
                           about something else

Distinctive is measured against the corpus: a word in more than a sixth of the
records carries no information here, because ครู, วิชาชีพ and จรรยาบรรณ are in
almost every rule.

OFF BY DEFAULT, and it stays off until the third check earns its place. On the
twelve probes in tests/test_support.py the first two checks are silent on every
correct answer and catch four of the five known-wrong pairings, but the third
fires on five of twelve answers a human reads as correct -- because the claim it
compares is taken from the words *before* the citation, and the writer routinely
puts the sentence after it instead. Blocking at that rate would cost more than
the wrong citations do. app/config.py turns it on; until then it logs, which is
how the data to fix the window gets collected.
"""
from __future__ import annotations

import re
from collections import Counter

from app.thai_tokenize import word_tokenize

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 7 (ข)(๓))" -- the unit
# and number are the anchor, the instrument name is looked up behind them.
CITATION = re.compile(r"(ข้อ|มาตรา)\s*([๐-๙0-9]{1,3}(?:/[๐-๙0-9]{1,3})?)(?![๐-๙0-9])"
                      r"((?:\s*\([ก-ฮ๐-๙0-9]{1,3}\))*)")
SUB_ITEM = re.compile(r"\(([ก-ฮ๐-๙0-9]{1,3})\)")
# how far back to look for the instrument the citation belongs to
NAME_WINDOW = 90
# where a claim starts: the previous line, bullet, or closing bracket
CLAIM_EDGE = re.compile(r"[\n•]|\)\s")
MIN_CLAIM_WORDS = 6
COMMON_SHARE = 1 / 6
# how many of the claim's rarest words have to be looked for in the cited rule
KEY_WORDS = 3
LETTERS = "กขคฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ"


def _missing_sub_item(markers: list[str], candidates: list[dict]) -> str | None:
    """A pointer like "(ก)(๕)" has to land inside the lettered block it names.

    Looking for "(๕)" anywhere in the rule is not enough: ข้อ 8 ของข้อบังคับฯ
    2550 lists two desirable behaviours under (ก) and five undesirable ones
    under (ข), so "(ก)(๕)" points at nothing while every marker in it exists.
    """
    letters = [m for m in markers if m in LETTERS]
    numbers = [m for m in markers if m not in LETTERS]
    for text in (rec["text"] for rec in candidates):
        blocks = [text]
        if letters:
            start = text.find(f"({letters[0]})")
            if start < 0:
                continue
            after = text[start + 3:]
            ends = [after.find(f"({other})") for other in LETTERS
                    if other != letters[0] and f"({other})" in after]
            cut = min([e for e in ends if e >= 0], default=len(after))
            blocks = [after[:cut]]
        if all(any(f"({n})" in block for block in blocks) for n in numbers):
            return None
    return "".join(f"{m})(" for m in markers)[:-2] if markers else None


def _rarest(words: list[str], corpus: "Corpus") -> set[str]:
    distinctive = [w for w in words if w in corpus.distinctive]
    distinctive.sort(key=lambda w: corpus.frequency.get(w, 0))
    return set(distinctive[:KEY_WORDS])


class Corpus:
    """The corpus, indexed the three ways this module needs to read it."""

    def __init__(self, records: list[dict]):
        self.by_rule: dict[tuple[str, str, str], dict] = {}
        self.by_unit_number: dict[tuple[str, str], list[dict]] = {}
        for rec in records:
            if rec.get("part", 0):
                continue  # a later chunk of a long rule; part 0 opens it
            key = (rec["sysid"], rec.get("unit", "มาตรา"), rec["section"])
            self.by_rule[key] = rec
            self.by_unit_number.setdefault(
                (rec.get("unit", "มาตรา"), rec["section"]), []).append(rec)

        self.names = {}
        for rec in records:
            for name in (rec.get("short"), rec.get("act")):
                if name:
                    self.names[name] = rec["sysid"]

        seen = Counter()
        for rec in records:
            seen.update(set(_content(rec["text"])))
        cutoff = max(2, int(len(records) * COMMON_SHARE))
        self.frequency = dict(seen)
        self.distinctive = {word for word, n in seen.items() if n <= cutoff}

    def instrument_before(self, text: str, at: int) -> str | None:
        """Which instrument the citation at `at` belongs to, if it says."""
        window = text[max(0, at - NAME_WINDOW):at]
        best = None
        for name, sysid in self.names.items():
            found = window.rfind(name)
            if found >= 0 and (best is None or found > best[0]):
                best = (found, sysid)
        return best[1] if best else None


def _content(text: str) -> list[str]:
    """Words worth comparing: Thai, and long enough to mean something."""
    return [w for w in word_tokenize(text, keep_whitespace=False)
            if len(w) >= 3 and any("ก" <= c <= "ฮ" for c in w)]


def _claim_before(answer: str, at: int) -> str:
    """The sentence the citation is attached to."""
    edges = [m.end() for m in CLAIM_EDGE.finditer(answer, 0, at)]
    return answer[(edges[-1] if edges else 0):at]


def unsupported_claims(answer: str, corpus: Corpus) -> list[str]:
    """Citations whose text does not carry the sentence they are attached to."""
    problems: list[str] = []

    def report(message: str) -> None:
        if message not in problems:
            problems.append(message)

    for match in CITATION.finditer(answer):
        unit, raw_number, subs = match.groups()
        number = raw_number.translate(THAI_DIGITS)
        sysid = corpus.instrument_before(answer, match.start())

        if sysid:
            rec = corpus.by_rule.get((sysid, unit, number))
            if rec is None:
                report(f"{unit} {number} ไม่มีอยู่ในเอกสารที่อ้าง")
                continue
            candidates = [rec]
        else:
            candidates = corpus.by_unit_number.get((unit, number), [])
            if not candidates:
                report(f"ไม่มี{unit} {number} ในตัวบทฉบับใดเลย")
                continue

        missing = _missing_sub_item(SUB_ITEM.findall(subs), candidates)
        if missing:
            report(f"{unit} {number} ไม่มีอนุข้อ ({missing})")

        claim = _content(_claim_before(answer, match.start()))
        if len(claim) < MIN_CLAIM_WORDS:
            continue
        # The rarest words the claim uses, not any word it uses. Sharing ครู or
        # วิชาชีพ with a rule proves nothing -- almost every rule has them -- and
        # a check that accepts that evidence never fires. "หลักวิชาการ" appears
        # in one rule, and a sentence built on it that cites a different rule is
        # citing the wrong one.
        keys = _rarest(claim, corpus)
        if not keys:
            continue
        if not any(keys & set(_content(rec["text"])) for rec in candidates):
            report(f"{unit} {number} ไม่มีข้อความรองรับสิ่งที่เขียนไว้ข้างหน้า")

    return problems
