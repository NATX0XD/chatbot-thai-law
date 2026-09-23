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
# the Buddhist year in an instrument's name, which identifies it on its own
YEAR = re.compile(r"25[0-9]{2}")
# "มาตรา 9 ข้อ ๑" is one citation and a pointer into it, not two citations. The
# writer keeps using ข้อ for sub-items even though the prompt asks for "(๑)",
# and reading the second half as a citation to ข้อ 1 rejected a correct answer
# about who sets the code of ethics.
NESTED = re.compile(
    r"((?:ข้อ|มาตรา)\s*[๐-๙0-9]{1,3}(?:/[๐-๙0-9]{1,3})?)"
    r"(\s*(?:วรรค\S*\s*)?)(?:ข้อ|มาตรา)\s*[๐-๙0-9]{1,3}(?:/[๐-๙0-9]{1,3})?")
# how far back to look for the instrument the citation belongs to
NAME_WINDOW = 90
# where a claim starts: the previous line, bullet, or closing bracket
CLAIM_EDGE = re.compile(r"[\n•]|\)\s")
MIN_CLAIM_WORDS = 6
COMMON_SHARE = 1 / 6
# how many of the claim's rarest words have to be looked for in the cited rule
KEY_WORDS = 3
LETTERS = "กขคฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ"


def _forms(marker: str) -> tuple[str, ...]:
    """A sub-item written either way. The rules use Thai numerals throughout and
    the writer is told to answer in Arabic ones, so "(๑)" and "(1)" are the same
    pointer -- comparing them literally reported ข้อ 12 as having no (1)."""
    arabic = marker.translate(THAI_DIGITS)
    thai = arabic.translate(str.maketrans("0123456789", "๐๑๒๓๔๕๖๗๘๙"))
    return tuple({f"({marker})", f"({arabic})", f"({thai})"})


def _has(text: str, marker: str) -> bool:
    return any(form in text for form in _forms(marker))


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
        if all(any(_has(block, n) for block in blocks) for n in numbers):
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

        self.all_citations = [
            f"{rec.get('short') or rec['act']} {rec.get('unit', 'มาตรา')} {rec['section']}"
            for rec in self.by_rule.values()]

        self.names = {}
        years: dict[str, set[str]] = {}
        for rec in records:
            for name in (rec.get("short"), rec.get("act")):
                if name:
                    self.names[name] = rec["sysid"]
                    for year in YEAR.findall(name):
                        years.setdefault(year, set()).add(rec["sysid"])
        # every instrument here carries a different year, so a bare "2550" names
        # one of them unambiguously. Kept only where that holds.
        self.by_year = {year: next(iter(ids)) for year, ids in years.items()
                        if len(ids) == 1}

        seen = Counter()
        for rec in records:
            seen.update(set(_content(rec["text"])))
        cutoff = max(2, int(len(records) * COMMON_SHARE))
        self.frequency = dict(seen)
        self.distinctive = {word for word, n in seen.items() if n <= cutoff}

    def instrument_before(self, text: str, at: int) -> str | None:
        """Which instrument the citation at `at` belongs to, if it says.

        The year is read alongside the names, and whichever sits closest to the
        citation wins. Names alone were not enough: the writer shortens them
        ("แบบแผนพฤติกรรม 2550" for a regulation the corpus calls ข้อบังคับคุรุสภา
        ว่าด้วยแบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพ พ.ศ. 2550), and a shortened
        name matches nothing, so the search kept walking back to whatever
        instrument was named earlier in the sentence and attributed the citation
        to that one. Round six blocked a correct answer that way -- ข้อ 8 (ข)(๑)
        of ข้อบังคับฯ 2550 read against ข้อ 8 of ข้อบังคับฯ 2556, which has no
        lettered blocks at all, and the refusal said the sub-item did not exist.
        """
        window = text[max(0, at - NAME_WINDOW):at]
        best = None
        for table in (self.names, self.by_year):
            for key, sysid in table.items():
                found = window.rfind(key)
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


def impossible_citations(answer: str, corpus: Corpus) -> list[str]:
    """Citations that point at nothing. Structural, so it cannot be wrong.

    A rule number the instrument does not have, a unit word that instrument
    never uses, a sub-item outside the block it names -- each is a fact about
    the corpus, checked against the corpus, with no judgement about meaning.
    That is why this one blocks and `unsupported_claims` does not.
    """
    return _walk(answer, corpus, lexical=False)


def unsupported_claims(answer: str, corpus: Corpus) -> list[str]:
    """Citations whose text does not carry the sentence they are attached to."""
    return _walk(answer, corpus, lexical=True)


def _walk(answer: str, corpus: Corpus, lexical: bool) -> list[str]:
    # keep the offsets usable: the pointer is blanked, not deleted, so the
    # claim window and the instrument lookup still measure the real distances
    answer = NESTED.sub(lambda m: m.group(1) + m.group(2)
                        + " " * (len(m.group(0)) - len(m.group(1)) - len(m.group(2))),
                        answer)
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
                if not lexical:
                    report(f"{unit} {number} ไม่มีอยู่ในเอกสารที่อ้าง")
                continue
            candidates = [rec]
        else:
            candidates = corpus.by_unit_number.get((unit, number), [])
            if not candidates:
                if not lexical:
                    report(f"ไม่มี{unit} {number} ในตัวบทฉบับใดเลย")
                continue

        markers = SUB_ITEM.findall(subs)
        missing = _missing_sub_item(markers, candidates)
        if missing and _missing_sub_item(
                markers, corpus.by_unit_number.get((unit, number), [])):
            # only when no instrument in the corpus has that sub-item under that
            # number. Attribution can still be wrong -- the writer's names are
            # not the corpus's -- and this check blocks the whole answer, so it
            # is worth the second read to make the claim one about the corpus
            # rather than about which instrument the sentence seemed to mean.
            report(f"{unit} {number} ไม่มีอนุข้อ ({missing})")
        if not lexical:
            continue

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
