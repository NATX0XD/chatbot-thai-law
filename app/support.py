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

The third check does not block, and after the sixth acceptance run it no longer
has to. What it finds goes into the repair turn in app/answer.py -- the writer is
told which rule and which mistake, and writes the answer again. A false positive
there costs one wasted call; a false positive that refused an answer cost the
user the answer. app/config.py can still make it block, and the flag rate on
correct answers is the thing to measure before doing that.

Two extensions the sixth round asked for, both here:

  * the claim is read on *both* sides of the citation. Reading only backwards is
    what kept this off: the writer puts the sentence after the citation as often
    as before it, and five of twelve correct answers were flagged for it.
  * a claim that cites a sub-item is compared against that sub-item, not the
    whole rule, which is the only way a wrong sub-item number is visible -- the
    words are all in the rule either way.

And one check that is not about citations at all: conviction_on_thin_evidence,
for answers that rule on conduct no rule mentions.
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
# "ต้อง" is an obligation whose breach is punishable; "พึง" is one that is not.
# The corpus is careful about which it uses and the writer is not.
MUST = re.compile(r"ต้อง(?!การ)")
SHOULD = re.compile(r"พึง")
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


def _block_for(text: str, markers: list[str]) -> str | None:
    """The part of a rule a pointer like "(ข)(๑)" actually points at.

    Returns None when the pointer lands nowhere. Narrowing matters twice over:
    it is how "(ก)(๕)" is caught -- ข้อ 8 ของข้อบังคับฯ 2550 lists two desirable
    behaviours under (ก) and five undesirable ones under (ข), so looking for
    "(๕)" anywhere in the rule finds it while the pointer means nothing -- and it
    is what lets a claim be compared against the sub-item it cites rather than
    against the whole rule, which is how a wrong sub-item number gets noticed.
    """
    letters = [m for m in markers if m in LETTERS]
    numbers = [m for m in markers if m not in LETTERS]

    if letters:
        start = text.find(f"({letters[0]})")
        if start < 0:
            return None
        after = text[start + 3:]
        ends = [after.find(f"({other})") for other in LETTERS
                if other != letters[0] and f"({other})" in after]
        text = after[:min([e for e in ends if e >= 0], default=len(after))]

    for number in numbers:
        found = next((text.find(form) for form in _forms(number)
                      if form in text), -1)
        if found < 0:
            return None
        text = text[found:]
        # up to whichever numbered item comes next, whatever its number
        rest = text[1:]
        ends = [rest.find(form) for n in range(1, 30)
                for form in _forms(str(n)) if form in rest]
        if ends:
            text = text[:1 + min(ends)]
    return text


def _missing_sub_item(markers: list[str], candidates: list[dict]) -> str | None:
    if not markers:
        return None
    for rec in candidates:
        if _block_for(rec["text"], markers) is not None:
            return None
    return "".join(f"{m})(" for m in markers)[:-2]


def _rarest(words: list[str], corpus: "Corpus") -> set[str]:
    # words that only appear because an instrument was named are not part of the
    # claim: "สภาครูและบุคลากรทางการศึกษา" says nothing about what the sentence
    # asserts, and it is rare enough to crowd out the words that do
    distinctive = [w for w in words
                   if w in corpus.distinctive and w not in corpus.name_words]
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

        self.name_words = {w for name in self.names for w in _content(name)}

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


def _windows(answer: str, span: tuple[int, int],
             others: list[tuple[int, int]]) -> list[str]:
    """The sentences a citation could be attached to: the one in front of it and
    the one behind it.

    Reading only what came before was what kept this check switched off. The
    writer puts the sentence on either side -- "ครูต้องไม่ดูหมิ่นศิษย์ (ข้อ 7)"
    and "(ข้อ 7) ครูต้องไม่ดูหมิ่นศิษย์" are both common -- and five of twelve
    correct answers were flagged because the text in front was either empty or
    belonged to the previous citation.

    Both windows stop at the nearest line, bullet or bracket, and at the nearest
    other citation, so one citation's sentence is never read as another's.

    A citation inside brackets is stepped over completely, name and all. Reading
    the name as the claim was the first false positive the repair turn produced,
    and it was expensive: "(พ.ร.บ.สภาครูและบุคลากรทางการศึกษา 2546 มาตรา 50)" was
    compared against มาตรา 50 on the words สภา and บุคลากร, which the section
    does not use, and a correct answer -- the five duties, counted right -- was
    rewritten into a wrong one that counted three.
    """
    start, end = span
    open_at, close_at = _brackets(answer, span)

    edges = [m.end() for m in CLAIM_EDGE.finditer(answer, 0, open_at)]
    left = max([e for e in edges if e <= open_at], default=0)
    left = max([left] + [b for _, b in others if b <= open_at])

    edges = [m.start() for m in CLAIM_EDGE.finditer(answer, close_at)]
    right = min([e for e in edges if e >= close_at], default=len(answer))
    right = min([right] + [a for a, _ in others if a >= close_at])

    return [answer[left:open_at], answer[close_at:right]]


def _brackets(answer: str, span: tuple[int, int]) -> tuple[int, int]:
    """The bracket pair the citation sits in, or its own span if it sits bare."""
    start, end = span
    open_at = answer.rfind("(", 0, start)
    if open_at < 0 or ")" in answer[open_at:start]:
        return start, end
    close_at = answer.find(")", end)
    return open_at, (close_at + 1 if close_at >= 0 else end)


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

    spans = [m.span() for m in CITATION.finditer(answer)]
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

        others = [s for s in spans if s != match.span()]
        windows = [w for w in _windows(answer, match.span(), others)
                   if len(_content(w)) >= MIN_CLAIM_WORDS]
        if not windows:
            continue

        # the sub-item the citation points at, if it points at one: a claim that
        # belongs to (ข)(๓) and cites (ข)(๑) matches the rule and not the item,
        # which is the commonest wrong pointer the acceptance runs turn up
        texts = [_block_for(rec["text"], markers) or rec["text"]
                 for rec in candidates] if markers else \
                [rec["text"] for rec in candidates]

        supported = False
        for window in windows:
            # The rarest words the claim uses, not any word it uses. Sharing ครู
            # or วิชาชีพ with a rule proves nothing -- almost every rule has them
            # -- and a check that accepts that evidence never fires.
            # "หลักวิชาการ" appears in one rule, and a sentence built on it that
            # cites a different rule is citing the wrong one.
            keys = _rarest(_content(window), corpus)
            if not keys or any(keys & set(_content(text)) for text in texts):
                supported = True
                _modal(window, texts, unit, number, report)
                break
        if not supported:
            where = "อนุข้อที่ชี้" if markers else f"{unit} {number}"
            report(f"{where} ไม่มีข้อความรองรับประโยคที่อ้างถึง ({unit} {number})")

    return problems


# "ครูไปหาเสียงช่วยผู้สมัคร ส.ส. ผิดจรรยาบรรณไหม" -- a question that invites a
# verdict, and the regulations do not address it
VERDICT_ASKED = re.compile(r"ผิด(จรรยาบรรณ|ไหม|หรือไม่|มั้ย|รึเปล่า)|"
                           r"เข้าข่าย|ทำได้ไหม|ได้ไหม|ควรไหม")
VERDICT_GIVEN = re.compile(r"(ถือว่า|ถือเป็น|เข้าข่าย|จึง)\s*(การ)?(กระทำ)?ผิด|"
                           r"ผิดจรรยาบรรณ(?!ไหม|หรือไม่)|ละเมิดจรรยาบรรณ|"
                           r"เป็นการฝ่าฝืน|ขัด(ต่อ|กับ)จรรยาบรรณ|"
                           r"ฝ่าฝืนจรรยาบรรณ|ไม่พึงประสงค์ตามข้อ")
NOT_A_BREACH = re.compile(r"ไม่ได้เขียน|ไม่ได้กำหนด|ไม่มีข้อ|ไม่ได้ระบุ|"
                          r"ไม่ปรากฏ|ไม่ได้ห้าม|ไม่ถือว่าผิด|ไม่เข้าข่าย")
# Below this BM25 score, no rule uses the words the question uses -- see
# conviction_on_thin_evidence for how the number was picked.
THIN_EVIDENCE = 10.0


def conviction_on_thin_evidence(question: str, answer: str,
                                bm25_top: float) -> bool:
    """A verdict of "that breaks the code" with no rule that mentions the conduct.

    Six rounds of acceptance testing never moved this group with instructions.
    The standing example: a teacher canvassing for a parliamentary candidate. The
    regulations say nothing about it -- the political restrictions on civil
    servants live in an act this corpus does not hold -- and the answer convicts
    anyway, by reaching for ข้อ 15 about ยึดมั่นในระบอบประชาธิปไตย.

    The signal is BM25, not the dense score and not word overlap with the
    question. Word overlap is the wrong test in this corpus: users write ด่า and
    the rules write ดูหมิ่นเหยียดหยาม, which is what app/query_expand.py exists
    to bridge, so a question the corpus answers well can share no word with it.
    BM25 is measured *after* that bridge, and it separates cleanly where the
    dense score does not:

        conduct the rules address    ด่านักเรียน 35.9  นินทาเพื่อนครู 44.6
                                     เรียกเงิน 41.0    มีชู้ 23.9
                                     หลักวิชาผิด 11.9  (the lowest measured)
        conduct they do not          หาเสียงให้ ส.ส. 8.5   ขายประกัน 7.7
                                     ขับรถเร็ว 6.4        ย้อมผม 6.4
        dense, for both              0.52 -- 0.71, no separation at all

    This does not block. It adds a line to the repair turn, and the model still
    holds the evidence: if a rule really does cover the conduct it can keep the
    verdict. A false positive costs a sentence, not an answer.
    """
    if bm25_top >= THIN_EVIDENCE or not VERDICT_ASKED.search(question):
        return False
    verdicts = [m.start() for m in VERDICT_GIVEN.finditer(answer)]
    if not verdicts:
        return False
    # An answer that hedges and then convicts anyway is still convicting, and it
    # is the commoner shape: "ตัวบทไม่ได้ระบุชัดเจนว่าห้าม ... แต่ ... ถือว่าผิด
    # จรรยาบรรณ". Only a disclaimer that has the last word counts as one.
    hedges = [m.start() for m in NOT_A_BREACH.finditer(answer)]
    return not hedges or max(verdicts) > max(hedges)


def _modal(claim: str, texts: list[str], unit: str, number: str, report) -> None:
    """"พึง" and "ต้อง" are not the same obligation.

    ข้อ 14 says ผู้ประกอบวิชาชีพ *พึง* ช่วยเหลือเกื้อกูลซึ่งกันและกัน -- a duty
    the regulation states and does not punish. Answers that report it as "ต้อง"
    tell a teacher they can be disciplined for something the text does not say
    that about, and the tester has been catching it every round.
    """
    rules = " ".join(texts)
    if SHOULD.search(rules) and not MUST.search(rules) \
            and MUST.search(claim) and not SHOULD.search(claim):
        report(f"{unit} {number} ใช้คำว่า “พึง” แต่คำตอบเขียนว่า “ต้อง”")
    elif MUST.search(rules) and not SHOULD.search(rules) \
            and SHOULD.search(claim) and not MUST.search(claim):
        report(f"{unit} {number} ใช้คำว่า “ต้อง” แต่คำตอบเขียนว่า “พึง”")
