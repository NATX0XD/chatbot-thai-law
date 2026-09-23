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

# A title ends where the sentence resumes. Without this the trailing-token window
# swallows the conjunction and the *next* law with it, so a fabricated citation
# hides inside a legitimate one:
#   "ตาม พ.ร.บ.การทวงถามหนี้ 2558 ม.9 และประมวลกฎหมายแพ่งและพาณิชย์"
# matched as a single title and passed, because it started with a real act.
STOP = r"(?!และ|หรือ|ตาม|กับ|ซึ่ง|โดย|เพื่อ|แต่|จึง|ที่|ใน|มาตรา|ม\.)"
# A single space or tab, never a newline. With \s the window ran past the end
# of a line and swallowed the next bullet point into the "law name", so the
# refusal message quoted half a paragraph back at the user.
TAIL = rf"(?:[ \t]+{STOP}[^\s(),]+){{0,6}}"

# how a law gets named in an answer: a code, or an act in long or short form, or
# -- since the corpus became the Teachers Council's -- a regulation or a notice
# it issued. Those two had to be added because they are what a fabricated
# citation in this domain would look like: the model knows คุรุสภา issues
# ข้อบังคับ, so inventing "ข้อบังคับคุรุสภาว่าด้วยมาตรฐานวิชาชีพ" is the easy
# mistake, and without them here nothing would have noticed.
LAW_MENTION = re.compile(
    r"(ประมวลรัษฎากร"
    r"|ประมวลกฎหมาย[ก-๙]+(?:และ[ก-๙]+)?"
    rf"|ข้อบังคับ[^\s(),]*{TAIL}"
    rf"|ประกาศคณะกรรมการ[^\s(),]*{TAIL}"
    rf"|พระราชบัญญัติ[^\s(),]*{TAIL}"
    rf"|พระราชกำหนด[^\s(),]*{TAIL}"
    rf"|พ\.?\s?ร\.?\s?บ\.?\s?[^\s(),]*{TAIL}"
    rf"|พ\.?\s?ร\.?\s?ก\.?\s?[^\s(),]*{TAIL})"
)

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
SELF_REF = re.compile(r"^(?:ประมวล)?(?:นี้|ดังกล่าว|ฉบับนี้|ข้างต้น|เดียวกัน)")
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


def unsupported_laws(answer: str, citations: list[str]) -> list[str]:
    """Laws named in the answer that were not among the retrieved sections.

    Matching is prefix-based in both directions: the model may shorten
    "พระราชบัญญัติคุ้มครองแรงงาน พ.ศ. 2541" to "พ.ร.บ.คุ้มครองแรงงาน", and it may
    also name only the first words of a long title.
    """
    allowed = allowed_names(citations)
    if not allowed:
        return []
    bad = []
    for raw in LAW_MENTION.findall(answer):
        name = normalise(raw)
        if len(name) < 4:
            continue
        if SELF_REF.match(name):
            continue
        if _names_the_same_law(name, allowed):
            continue
        if raw.strip() not in bad:
            bad.append(raw.strip())
    return bad


# how short a name may be and still be matched by containment. Codes normalise
# to very short names -- ประมวลกฎหมายอาญา becomes "อาญา" -- and four characters
# inside a long title is a coincidence waiting to happen, so those must match
# exactly instead.
MIN_CONTAINS = 6


def _names_the_same_law(name: str, allowed: set[str]) -> bool:
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


# A citation is a unit word and a number: "ข้อ 7", "มาตรา 54". Both are checked,
# because in this corpus the unit word carries meaning -- ข้อบังคับคุรุสภา
# numbers its rules as ข้อ and only the Act uses มาตรา, so "มาตรา 7 ของ
# ข้อบังคับ" is a citation to something that does not exist.
SECTION_MENTION = re.compile(r"(ข้อ|มาตรา)\s*([๐-๙0-9]+(?:/[๐-๙0-9]+)?)")
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _pairs(text: str) -> set[tuple[str, str]]:
    return {(unit, number.translate(THAI_DIGITS))
            for unit, number in SECTION_MENTION.findall(text)}


def unsupported_sections(answer: str, citations: list[str],
                         texts: list[str]) -> list[str]:
    """Rule numbers the answer cites that are nowhere in the evidence.

    Two sources count as evidence: the citations of the sections that were
    retrieved, and the cross-references inside their text -- ข้อ 16 ของ
    ข้อบังคับฯ 2568 refers to ข้อ 12, and an answer that follows the reference is
    reading the corpus, not inventing.

    This is the check that stops the failure a reader cannot detect. A wrong act
    name is visible; "ตามข้อ 23" when the rule is ข้อ 13 reads exactly like a
    correct citation and sends the reader to the wrong rule.
    """
    allowed = set()
    for source in list(citations) + list(texts):
        allowed |= _pairs(source)
    if not allowed:
        return []

    bad = []
    for unit, number in _pairs(answer):
        if (unit, number) in allowed:
            continue
        item = f"{unit} {number}"
        if item not in bad:
            bad.append(item)
    return bad
