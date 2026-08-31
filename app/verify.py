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
TAIL = rf"(?:\s+{STOP}[^\s(),]+){{0,6}}"

# how a law gets named in an answer: a code, or an act in long or short form
LAW_MENTION = re.compile(
    r"(ประมวลรัษฎากร"
    r"|ประมวลกฎหมาย[ก-๙]+(?:และ[ก-๙]+)?"
    rf"|พระราชบัญญัติ[^\s(),]*{TAIL}"
    rf"|พระราชกำหนด[^\s(),]*{TAIL}"
    rf"|พ\.?\s?ร\.?\s?บ\.?\s?[^\s(),]*{TAIL}"
    rf"|พ\.?\s?ร\.?\s?ก\.?\s?[^\s(),]*{TAIL})"
)

NOISE = re.compile(r"(พ\.?\s?ศ\.?\s*[๐-๙0-9]*|มาตรา\s*[๐-๙0-9/()]*|ม\.\s*[๐-๙0-9/()]*"
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
          ("พรบ", ""), ("พรก", ""), ("ประมวลกฎหมาย", ""))


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
        if any(name.startswith(a[:12]) or a.startswith(name[:12]) for a in allowed):
            continue
        if raw.strip() not in bad:
            bad.append(raw.strip())
    return bad
