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

A fourth check was tried here and removed. It refused to let an answer convict
when BM25 after query expansion was below 10, on the theory that no rule used
the words the question used. Round seven measured it: three false positives on
questions the corpus answers well, and it did not fire on the case it was
written for. The reason is structural, not a threshold. This corpus writes at a
high level -- อบายมุข, สิ่งเสพติด, สิ่งแวดล้อม -- and teachers ask about เหล้า,
ขยะ, การพนัน. Nine in-domain cases have the conduct word absent from the corpus
and covered by a broader term. Word overlap measures vocabulary, not coverage,
and no threshold separates them.
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
# the word an instrument's name starts with. One of these between the name we
# matched and the citation means the citation belongs to an instrument we failed
# to recognise, not to the one we found.
INSTRUMENT = re.compile(r"พ\.ร\.บ\.|พระราชบัญญัติ|ข้อบังคับ|ประกาศ|ระเบียบ|กฎกระทรวง")
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
# "พฤติกรรมที่ไม่พึงประสงค์" is a heading in ข้อบังคับฯ 2550, not an obligation.
# Matching the พึง inside it told a user "ข้อ 7 ใช้คำว่า ต้อง แต่คำตอบเขียนว่า
# พึง" about an answer that never wrote พึง -- a false statement, shipped.
SHOULD = re.compile(r"พึง(?!ประสงค์)")
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


def _lettered_blocks(text: str, letter: str | None) -> list[str]:
    """The lettered blocks a pointer could mean.

    With a letter, one block. Without one, every block there is -- because a
    pointer like "ข้อ 6 (๖)" is *ambiguous*, not wrong. ข้อ 6 ของข้อบังคับฯ 2550
    has both "(ก)(๖) เลือกใช้หลักวิชาที่ถูกต้อง" and "(ข)(๖) ใช้หลักวิชาการที่ไม่
    ถูกต้อง ... เกิดความเสียหาย", and reading only the first made the checker
    report a correct prohibition as unsupported. The tester found that one; I had
    reported it as a real catch.
    """
    if letter is not None:
        start = text.find(f"({letter})")
        if start < 0:
            return []
        after = text[start + 3:]
        ends = [after.find(f"({other})") for other in LETTERS
                if other != letter and f"({other})" in after]
        return [after[:min([e for e in ends if e >= 0], default=len(after))]]

    starts = sorted(text.find(f"({other})") for other in LETTERS
                    if f"({other})" in text)
    if not starts:
        return [text]
    bounds = starts + [len(text)]
    return [text[bounds[i]:bounds[i + 1]] for i in range(len(starts))]


def _blocks_for(text: str, markers: list[str]) -> list[str]:
    """Every part of a rule the pointer could be naming. Empty means nowhere.

    Narrowing matters twice over: it is how "(ก)(๕)" is caught -- ข้อ 8 ของ
    ข้อบังคับฯ 2550 lists two desirable behaviours under (ก) and five undesirable
    ones under (ข), so looking for "(๕)" anywhere in the rule finds it while the
    pointer means nothing -- and it is what lets a claim be compared against the
    sub-item it cites rather than against the whole rule.
    """
    letters = [m for m in markers if m in LETTERS]
    numbers = [m for m in markers if m not in LETTERS]
    blocks = _lettered_blocks(text, letters[0] if letters else None)

    # "(ข)(๑)(๒)" names two items under (ข), not an item inside an item. Each
    # number is looked for in the lettered block on its own; nesting them made
    # the checker refuse a correct answer that cited two sub-items at once.
    narrowed = []
    for number in numbers:
        for block in blocks:
            found = next((block.find(form) for form in _forms(number)
                          if form in block), -1)
            if found < 0:
                continue
            block = block[found:]
            # up to whichever numbered item comes next, whatever its number
            rest = block[1:]
            ends = [rest.find(form) for n in range(1, 30)
                    for form in _forms(str(n)) if form in rest]
            narrowed.append(block[:1 + min(ends)] if ends else block)
    return narrowed if numbers else blocks


def _missing_sub_item(markers: list[str], candidates: list[dict]) -> str | None:
    if not markers:
        return None
    for rec in candidates:
        if _blocks_for(rec["text"], markers):
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
        # A long rule is stored as several records and read here as one. Ten of
        # the 334 records are continuations, and dropping them cost an answer:
        # ข้อ 7 ของข้อบังคับฯ 2550 carries (ข)(๗) เรียกร้องผลตอบแทนจากศิษย์ in
        # its second piece, so the sub-item check reported the rule as having no
        # (๗) and refused an answer that had quoted it correctly.
        self.by_rule: dict[tuple[str, str, str], dict] = {}
        self.by_unit_number: dict[tuple[str, str], list[dict]] = {}
        for rec in sorted(records, key=lambda r: r.get("part", 0)):
            key = (rec["sysid"], rec.get("unit", "มาตรา"), rec["section"])
            if key in self.by_rule:
                self.by_rule[key]["text"] += "\n\n" + rec["text"]
                continue
            whole = dict(rec)
            self.by_rule[key] = whole
            self.by_unit_number.setdefault(
                (rec.get("unit", "มาตรา"), rec["section"]), []).append(whole)

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
                    best = (found, sysid, len(key))
        if best is None:
            return None
        # "...2568 ข้อ 46 และ พ.ร.บ.สภาครูฯ มาตรา 52" -- the short form matches no
        # name and carries no year, so the search fell back to the regulation
        # named earlier and reported มาตรา 52, which exists, as missing. An
        # instrument word standing between the two means we do not know which
        # instrument this citation belongs to, and not knowing is not a fault in
        # the answer.
        if INSTRUMENT.search(window[best[0] + best[2]:]):
            return None
        return best[1]


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
    That is why this one blocks and the other two do not.
    """
    return [note for kind, note in _walk(answer, corpus) if kind == "structural"]


def misattributed_citations(answer: str, corpus: Corpus) -> list[str]:
    """Citations whose number exists, but not in the instrument named beside it.

    Worth telling the writer about and not worth refusing over. Every time this
    has been allowed to block it has cost a correct answer instead of catching a
    wrong one: KSP-028, KSP-043, and two of the three wrongly refused questions
    in the assessor run, where มาตรา 51 and ข้อ 34 both exist and were both
    reported as missing because the name nearest them belonged to a different
    instrument.
    """
    return [note for kind, note in _walk(answer, corpus) if kind == "attribution"]


def modal_mismatches(answer: str, corpus: Corpus) -> list[str]:
    """Answers that turn a พึง into a ต้อง, or the other way round.

    Kept apart from unsupported_claims because the two were measured together
    and came out opposite. Over rounds seven and eight the overlap check fired
    28 times, 9 of them right, and exactly one of those nine -- a พึง reported
    as ต้อง -- turned into a corrected answer. This one compares two words
    against the text that contains them; there is no judgement about meaning in
    it, and it is the only part of the lexical pass allowed to cost a call.
    """
    return [note for kind, note in _walk(answer, corpus) if kind == "modal"]


def unsupported_claims(answer: str, corpus: Corpus) -> list[str]:
    """Citations whose text does not carry the sentence they are attached to.

    LOGGED, NOT ACTED ON. Round eight measured it at 39% of in-domain answers
    with 68% of those wrong, and the two harms it did are on record: a repair
    that deleted a correctly cited provision, and one that appended a line
    saying ข้อ 8 does not exist to an answer whose first sentence cited ข้อ 8
    correctly. A check that is wrong two times in three cannot be allowed to
    rewrite an answer. It stays because its false positives are the data for
    fixing it -- see ingest/flag_rate.py.
    """
    return [note for kind, note in _walk(answer, corpus) if kind == "overlap"]


def _walk(answer: str, corpus: Corpus) -> list[tuple[str, str]]:
    # keep the offsets usable: the pointer is blanked, not deleted, so the
    # claim window and the instrument lookup still measure the real distances
    answer = NESTED.sub(lambda m: m.group(1) + m.group(2)
                        + " " * (len(m.group(0)) - len(m.group(1)) - len(m.group(2))),
                        answer)
    problems: list[tuple[str, str]] = []

    def report(kind: str, message: str) -> None:
        if (kind, message) not in problems:
            problems.append((kind, message))

    spans = [m.span() for m in CITATION.finditer(answer)]
    for match in CITATION.finditer(answer):
        unit, raw_number, subs = match.groups()
        number = raw_number.translate(THAI_DIGITS)
        sysid = corpus.instrument_before(answer, match.start())

        if sysid:
            rec = corpus.by_rule.get((sysid, unit, number))
            if rec is None:
                # The number exists, just not under the instrument we think the
                # sentence named. Attribution is the unreliable half of this
                # check -- the writer shortens names, and three separate rounds
                # lost a correct answer to it -- so a mismatch here asks for a
                # rewrite and does not block. Only a number that exists nowhere
                # is a fact about the corpus.
                elsewhere = corpus.by_unit_number.get((unit, number))
                report("attribution" if elsewhere else "structural",
                       f"{unit} {number} ไม่ตรงกับเอกสารที่อ้างไว้ข้างหน้า"
                       if elsewhere else f"ไม่มี{unit} {number} ในตัวบทฉบับใดเลย")
                if not elsewhere:
                    continue
                candidates = elsewhere
            else:
                candidates = [rec]
        else:
            candidates = corpus.by_unit_number.get((unit, number), [])
            if not candidates:
                report("structural", f"ไม่มี{unit} {number} ในตัวบทฉบับใดเลย")
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
            report("structural", f"{unit} {number} ไม่มีอนุข้อ ({missing})")

        others = [s for s in spans if s != match.span()]
        windows = [w for w in _windows(answer, match.span(), others)
                   if len(_content(w)) >= MIN_CLAIM_WORDS]
        if not windows:
            continue

        # the sub-item the citation points at, if it points at one: a claim that
        # belongs to (ข)(๓) and cites (ข)(๑) matches the rule and not the item,
        # which is the commonest wrong pointer the acceptance runs turn up
        texts = [block for rec in candidates
                 for block in (_blocks_for(rec["text"], markers) or [rec["text"]])] \
            if markers else [rec["text"] for rec in candidates]

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
            report("overlap",
                   f"{where} ไม่มีข้อความรองรับประโยคที่อ้างถึง ({unit} {number})")

    return problems


def points_elsewhere(sentence: str, rule_text: str, corpus: "Corpus") -> bool:
    """Does this sentence belong to the rule it was pointed at?

    Once the model points at evidence instead of typing numbers, this check
    gets the signal it never had before: there is no doubt about which record a
    citation refers to, so an overlap of zero distinctive words is a wrong
    pointer rather than an attribution the checker could not resolve. The
    assessors' remaining wrong-ข้อ cases are all of this shape -- the text of
    2556 ข้อ 13 printed under a citation to 2568 ข้อ 51, faithfully labelled
    with a record that says nothing of the kind.

    Silent on short sentences, as always: there is nothing to compare.
    """
    words = _content(sentence)
    if len(words) < MIN_CLAIM_WORDS:
        return False
    keys = _rarest(words, corpus)
    return bool(keys) and not (keys & set(_content(rule_text)))


def cited_rules(answer: str, corpus: "Corpus") -> set[str]:
    """The rule numbers an answer cites that exist somewhere in the corpus.

    Used to stop a repair from "fixing" a flagged citation by deleting it. That
    shortens the fault list, so the accept rule passed it, and three answers in
    round seven lost a provision they had cited correctly in round six and
    gained a hedge in its place. An answer with no rule number cannot be checked
    by anyone -- which is the opposite of what these checks are for.

    Numbers only, not (unit, number): correcting "มาตรา 7" to "ข้อ 7" is exactly
    the repair the unit check asks for, and counting the unit word would make
    that read as losing one citation and inventing another.
    """
    found = set()
    for match in CITATION.finditer(answer):
        unit, raw_number, _ = match.groups()
        number = raw_number.translate(THAI_DIGITS)
        if corpus.by_unit_number.get((unit, number)) or any(
                corpus.by_unit_number.get((other, number))
                for other in ("ข้อ", "มาตรา")):
            found.add(number)
    return found


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
        report("modal", f"{unit} {number} ใช้คำว่า “พึง” แต่คำตอบเขียนว่า “ต้อง”")
    elif MUST.search(rules) and not SHOULD.search(rules) \
            and SHOULD.search(claim) and not MUST.search(claim):
        report("modal", f"{unit} {number} ใช้คำว่า “ต้อง” แต่คำตอบเขียนว่า “พึง”")
