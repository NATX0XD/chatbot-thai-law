# -*- coding: utf-8 -*-
"""Catch answers that cite laws we never showed the model.

Real failure this exists to stop. A user asked about a friend shoplifting. The
retriever, having no criminal code to find, returned พ.ร.บ.ระบบการชำระเงิน มาตรา 48
at cosine 0.588 -- above the gate but unrelated. The model ignored the context it
was given, fell back on its own memory, and produced:

    "มีความผิดฐานลักทรัพย์ตามประมวลกฎหมายอาญา มาตรา 335 ... โทษจำคุกไม่เกิน 5 ปี
     (พ.ร.บ. ว่าด้วยการกระทำผิดเกี่ยวกับทรัพย์สิน พ.ศ. ...)"

ประมวลกฎหมายอาญา is not in the corpus, and the second act does not exist at all.
Confident, specific, and fabricated -- the worst possible output from a legal bot.

Prompt instructions did not prevent it and keyword rules cannot enumerate every
way to say "steal". So the answer is checked against the evidence after the fact:
every law it names must be one we actually put in front of it.
"""
from __future__ import annotations

import re

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# A title ends where the sentence resumes. Without this the trailing-token window
# swallows the conjunction and the *next* law with it, so a fabricated citation
# hides inside a legitimate one:
#   "ตาม พ.ร.บ.การทวงถามหนี้ 2558 ม.9 และประมวลกฎหมายแพ่งและพาณิชย์"
# matched as a single title and passed, because it started with a real act.
# Words that open a clause. A title cannot contain them, and letting the
# trailing-token window swallow one turns half a sentence into a law name:
# "พระราชบัญญัติฉบับเดียวกัน คือ ประกอบด้วยจรรยาบรรณต่อตนเอง..." was reported as
# a statute the corpus does not hold, and a correct answer was thrown away.
STOP = (r"(?!และ|หรือ|ตาม|กับ|ซึ่ง|โดย|เพื่อ|แต่|จึง|ที่|ใน|มาตรา|ม\."
        r"|คือ|ได้แก่|เช่น|ประกอบด้วย|หมายความว่า|กำหนด|ระบุ|บัญญัติ)")
# A single space or tab, never a newline. With \s the window ran past the end
# of a line and swallowed the next bullet point into the "law name", so the
# refusal message quoted half a paragraph back at the user.
TAIL = rf"(?:[ \t]+{STOP}[^\s(),]+){{0,6}}"

# How a law gets named in an answer: a code, an act in long or short form, or a
# regulation of the Teachers Council.
#
# The Council's instruments need their own shape, and a loose one is worse than
# none. "ข้อบังคับ" is this corpus's everyday noun -- an ordinary sentence says
# "ข้อบังคับไม่ได้ระบุว่า...", "ข้อบังคับฉบับนี้มีผลใช้บังคับ...", "ข้อบังคับ
# ที่เกี่ยวข้อง" -- and a pattern that reads those as titles rejected twelve of
# fifty correct answers in acceptance testing, including the one asking which
# regulation is currently in force.
#
# What separates a citation from the noun is punctuation Thai does not usually
# use: a real title has a space after ข้อบังคับคุรุสภา, or runs straight into
# ว่าด้วย. Prose glues the next word on instead. That is the whole distinction,
# and NAMED below adds a second condition -- the span must carry a year or the
# word ว่าด้วย -- so that "ข้อบังคับคุรุสภา กำหนดว่า..." cannot slip through.
SHORT_TAIL = rf"(?:[ \t]+{STOP}[^\s(),]+){{0,4}}"
COUNCIL = (
    rf"ข้อบังคับ[^\s(),]*ว่าด้วย[^\s(),]*{SHORT_TAIL}"
    rf"|ข้อบังคับ(?:คุรุสภา|ฯ)[ \t]+{STOP}[^\s(),]+{SHORT_TAIL}"
    rf"|ประกาศคณะกรรมการคุรุสภา[^\s(),]*{SHORT_TAIL}"
)

LAW_MENTION = re.compile(
    r"(ประมวลรัษฎากร"
    r"|ประมวลกฎหมาย[ก-๙]+(?:และ[ก-๙]+)?"
    rf"|{COUNCIL}"
    rf"|พระราชบัญญัติ[^\s(),]*{TAIL}"
    rf"|พระราชกำหนด[^\s(),]*{TAIL}"
    rf"|พ\.?\s?ร\.?\s?บ\.?\s?[^\s(),]*{TAIL}"
    rf"|พ\.?\s?ร\.?\s?ก\.?\s?[^\s(),]*{TAIL})"
)

# A Council instrument is only named when the span says which one: a year, or
# ว่าด้วย followed by the subject. Without this, the second alternative above
# still matches "ข้อบังคับคุรุสภา กำหนดว่า…".
NAMED = re.compile(r"ว่าด้วย|[๐-๙0-9]{4}")
COUNCIL_HEAD = re.compile(r"^(?:ข้อบังคับ|ประกาศคณะกรรมการ)")

NOISE = re.compile(r"(พ\.?\s?ศ\.?\s*[๐-๙0-9]*|มาตรา\s*[๐-๙0-9/()]*|ม\.\s*[๐-๙0-9/()]*"
                   # the unit word of a Council regulation, and the abbreviation
                   # mark that ends every shortened Thai title. Without these
                   # "ข้อบังคับฯ จรรยาบรรณ 2556 ข้อ 7" normalised to a name ending
                   # in "ข้อ7" and matched nothing, so every correct answer about
                   # the five duties was thrown away as fabricated.
                   r"|ข้อ\s*[๐-๙0-9/()]*|ฯ"
                   # a bare year, written without the พ.ศ. the pattern above needs.
                   # "พ.ร.บ.คอมพิวเตอร์ 2550" kept its 2550 and stopped matching
                   # the act it names, which blocked every answer citing it.
                   r"|(?<![๐-๙0-9])[๐-๙0-9]{4}(?![๐-๙0-9])"
                   r"|ฉบับ\s*Update.*|\(.*?\)|[\s\.\,\:\;\"“”\-–]+)")

# "ตาม พ.ร.บ.นี้", "ตามพระราชบัญญัตินี้", "ตามประมวลกฎหมายนี้", "พ.ร.บ.ดังกล่าว" --
# the model pointing back at a statute it was already given, not naming a new one.
# The pattern above reads them as titles, and a user watching the bot throw away a
# correct answer about สิทธิผู้บริโภค is how this was found: the reply cited
# พ.ร.บ.คุ้มครองผู้บริโภค correctly, then wrote "ตาม พ.ร.บ.นี้" and the guard
# blocked the whole thing as fabricated.
SELF_REF = re.compile(r"^(?:ประมวล)?(?:นี้|ดังกล่าว|ฉบับนี้|ฉบับเดิม|ฉบับเดียวกัน"
                      r"|ข้างต้น|เดียวกัน|ทั้งสองฉบับ|ดังกล่าวข้างต้น)")
# Every form of "this is a statute" is stripped, so only the distinguishing part
# of the name is compared. That includes ประมวลกฎหมาย, because the model calls
# ประมวลกฎหมายแพ่งและพาณิชย์ "พ.ร.บ.แพ่งและพาณิชย์" often enough that a correct
# answer about มรดก was thrown away for it -- the wrong word for the kind of
# statute is a naming slip, not an invented law.
ABBREV = (("พระราชบัญญัติ", ""), ("พระราชกำหนด", ""),
          ("พรบ", ""), ("พรก", ""), ("ประมวลกฎหมาย", ""),
          # "ข้อบังคับคุรุสภา ว่าด้วยจรรยาบรรณของวิชาชีพ" and "ข้อบังคับ
          # จรรยาบรรณของวิชาชีพ" name the same instrument
          ("ข้อบังคับ", ""), ("คุรุสภา", ""), ("ว่าด้วย", ""), ("ของวิชาชีพ", "วิชาชีพ"))


def normalise(name: str) -> str:
    """Reduce a law name to something comparable across long and short forms."""
    text = NOISE.sub("", name)
    for src, dst in ABBREV:
        text = text.replace(src, dst)
    return text.strip()


def allowed_names(citations: list[str]) -> set[str]:
    """Normalised names of every act we actually supplied as context."""
    out = set()
    for c in citations:
        n = normalise(c)
        if n:
            out.add(n)
    return out


def unsupported_laws(answer: str, citations: list[str],
                     evidence: list[str] | None = None) -> list[str]:
    """Laws named in the answer that the corpus does not hold.

    Matching is prefix-based in both directions: the model may shorten
    "พระราชบัญญัติคุ้มครองแรงงาน พ.ศ. 2541" to "พ.ร.บ.คุ้มครองแรงงาน", and it may
    also name only the first words of a long title.

    `citations` is every instrument in the corpus, not only the ones retrieved
    for this question. Asking "was this handed over?" instead of "does this
    exist?" produced a refusal saying พ.ร.บ.สภาครูฯ 2546 "ไม่มีอยู่ในคลังข้อมูล"
    about an act with ninety-two records in it, four rounds running.

    `evidence` is the text of those sections. A name that appears in the rules
    themselves is being quoted, not invented: ข้อ 64 ของข้อบังคับฯ 2568 contains
    the phrase "ข้อบังคับคุรุสภาว่าด้วยการอุทธรณ์คำสั่ง...", and an answer
    repeating it was thrown away for naming a law.
    """
    allowed = allowed_names(citations)
    if not allowed:
        return []
    # The same extractor, run over the sections themselves, and compared in the
    # same normalised form. Exact substring matching was not enough: มาตรา 49
    # says "ให้มีข้อบังคับว่าด้วยมาตรฐานวิชาชีพ" and the answer wrote
    # "ข้อบังคับคุรุสภา ว่าด้วยมาตรฐานวิชาชีพ", which is the same instrument
    # named the way people name it.
    quoted = allowed_names([m for text in (evidence or [])
                            for m in LAW_MENTION.findall(text)])
    bad = []
    for raw in LAW_MENTION.findall(answer):
        if COUNCIL_HEAD.match(raw.strip()) and not NAMED.search(raw):
            continue
        raw = _title_only(raw)
        year_only = YEAR_ONLY.match(raw)
        if year_only:
            if year_only.group(1).translate(THAI_DIGITS) in _years(citations):
                continue
            bad.append(raw[:year_only.end()].strip())
            continue
        name = normalise(raw)
        if len(name) < 4:
            continue
        if SELF_REF.match(name):
            continue
        if _names_the_same_law(name, allowed):
            continue
        if _names_the_same_law(name, quoted):
            continue
        if raw.strip() not in bad:
            bad.append(raw.strip())
    return bad


# how short a name may be and still be matched by containment. Codes normalise
# to very short names -- ประมวลกฎหมายอาญา becomes "อาญา" -- and four characters
# inside a long title is a coincidence waiting to happen, so those must match
# exactly instead.
MIN_CONTAINS = 6

# A title stops at its own rule number; whatever follows is the sentence, not
# the name. Without this cut "ข้อบังคับคุรุสภา 2556 ข้อ 7 กล่าวถึงการมีวินัย
# ในตนเองและพัฒนาตนเอง" was read as one law name, normalised to the verb phrase
# at the end of it, matched nothing in the corpus, and the answer to "อบายมุข
# อยู่ในข้อใด" was refused as citing a law that does not exist -- about ข้อ 7
# ของข้อบังคับฯ 2556, which does.
UNIT_NUMBER = re.compile(r"(?:ข้อ|มาตรา)\s*[๐-๙0-9]")


def _title_only(raw: str) -> str:
    cut = UNIT_NUMBER.search(raw)
    return raw[:cut.start()].strip() if cut else raw.strip()


# "ข้อบังคับคุรุสภา 2556" names a regulation by its year and says nothing about
# its subject, so everything after the year is the sentence. Matching it as a
# title turned "ข้อบังคับคุรุสภา 2556 ยืนยันว่าผู้บริหารสถานศึกษาเป็นผู้ประกอบ
# วิชาชีพทางการศึกษา" into a law name and refused the answer to "จรรยาบรรณนี้
# ใช้กับผู้อำนวยการโรงเรียนด้วยไหม", which the corpus answers plainly.
#
# The year is still checked, against the years of the instruments the corpus
# holds. A regulation of a year the Council never issued one in is invented;
# one of a year it did is the model naming a real document tersely.
# The head has to be the bare noun: a span that carries a subject after ว่าด้วย
# is a title and is checked as one. "ข้อบังคับคุรุสภาว่าด้วยมาตรฐานวิชาชีพ พ.ศ.
# 2556" is a real regulation this corpus does not hold, and a looser head let it
# through on the strength of its year.
YEAR_ONLY = re.compile(r"^(?:ข้อบังคับ(?:คุรุสภา|ฯ)|ประกาศคณะกรรมการคุรุสภา)[ \t]+"
                       r"(?:พ\.?[ \t]*ศ\.?[ \t]*)?([๐-๙0-9]{4})")


YEAR_IN_NAME = re.compile(r"(?<![0-9])(2[0-9]{3})(?![0-9])")


def _years(citations: list[str]) -> set[str]:
    """Every year an instrument in the corpus carries in its name."""
    return {y for c in citations
            for y in YEAR_IN_NAME.findall(c.translate(THAI_DIGITS))}


def _names_the_same_law(name: str, allowed: set[str]) -> bool:  # noqa: D401
    """Is `name` one of the acts we supplied, under any of the names people use?

    Containment rather than a shared prefix, because the everyday name of an act
    is often buried in the middle of its official one. พ.ร.บ.คอมพิวเตอร์ is
    registered as ...ว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์, so a prefix test
    compared "คอมพิวเตอร์" against "ว่าด้วยการกระ" and blocked every answer that
    cited it -- the whole act was unusable while sitting in the index.
    """
    if name in allowed:
        return True
    for a in allowed:
        short, long = (name, a) if len(name) <= len(a) else (a, name)
        if len(short) >= MIN_CONTAINS and short in long:
            return True
    return False
