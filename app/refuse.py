# -*- coding: utf-8 -*-
"""Let the model write the refusal, without letting it answer the question.

Every refusal used to be one fixed block of text. Ask two different questions
that fall in the same gap and you get the same four paragraphs word for word,
which reads like a form letter rather than an assistant that simply does not
have the material. A user seeing it twice in a row learns to stop reading it.

So the wording is written per question now. What does *not* move is the decision:
app/coverage.py and the cosine gate decide whether to refuse, by rule, before
this module is called. The model is handed a verdict and asked to phrase it. It
is never asked whether the bot should have answered -- that question stays where
it was, because a model is the wrong thing to ask about its own limits.

Because a refusal is still a message about law, it is checked before sending. A
refusal that quotes a section, names an act, or states an amount is not a
refusal; it is the guess this whole system exists to prevent, wearing an
apology. Anything that trips the check falls back to the fixed text, which is
duller but cannot be wrong.
"""
from __future__ import annotations

import logging
import re

from app.llm import LLMUnavailable, complete
from app.verify import LAW_MENTION, unsupported_laws

log = logging.getLogger(__name__)

SYSTEM = """คุณคือผู้ช่วยกฎหมายไทยที่กำลังบอกผู้ใช้ว่าตอบคำถามนี้ไม่ได้

เขียนคำตอบสั้น ๆ 2-4 ประโยค ภาษาพูดที่สุภาพและเป็นธรรมชาติ เหมือนคนช่วยจริง ๆ ไม่ใช่ข้อความอัตโนมัติ

สิ่งที่ต้องมี
1. บอกว่าเรื่องนี้อยู่ในกฎหมายอะไร โดยเรียกชื่อกว้าง ๆ ตามที่ระบุให้ ไม่ต้องลงรายละเอียด
2. บอกตรง ๆ ว่าคลังข้อมูลของคุณไม่มีตัวบทนั้น จึงไม่ตอบ เพราะไม่อยากเดา
3. ชี้ทางไปที่ที่ถามได้จริง ตามที่ระบุให้

ห้ามเด็ดขาด
- ห้ามตอบคำถามนั้นไม่ว่าบางส่วนหรือทั้งหมด
- ห้ามอ้างเลขมาตรา
- เอ่ยชื่อกฎหมายได้เฉพาะฉบับที่ระบุให้เท่านั้น ห้ามเอ่ยฉบับอื่น
- ห้ามบอกตัวเลข จำนวนเงิน จำนวนวัน หรือร้อยละ
- ห้ามคาดเดาว่ากฎหมายน่าจะเขียนว่าอย่างไร
- ห้ามใช้ ** ## หรือสัญลักษณ์จัดรูปแบบ เพราะแสดงผลไม่ได้
- ห้ามขึ้นต้นด้วยคำว่า ขออภัย หรือ ขอโทษ
- แทนตัวเองว่า ผม และลงท้ายว่า ครับ เสมอ

เขียนให้ต่างกันไปตามคำถามที่ได้รับ อย่าใช้ประโยคเดิมซ้ำ"""

# A refusal may name the law it is missing -- that is the useful part of it --
# but nothing else about the law. Section numbers and figures are the giveaway
# that it started answering.
FORBIDDEN = (
    re.compile(r"มาตรา\s*[๐-๙0-9]|ม\.\s*[๐-๙0-9]"),      # a section number
    re.compile(r"[๐-๙0-9][\d,\.]*\s*(บาท|วัน|เดือน|ปี|%|เปอร์เซ็นต์)"),  # an amount
    re.compile(r"ร้อยละ"),
)
MAX_CHARS = 700


def _unsafe(text: str, code: str) -> str | None:
    """The first reason this text may not be sent, if there is one.

    `code` is the law the refusal is allowed to name. Any other act mentioned is
    the model reaching for something it was not given, which is the same test
    app/verify.py runs on real answers -- reused here rather than reimplemented.
    """
    if not text or len(text) > MAX_CHARS:
        return "ว่างหรือยาวเกินไป"
    for pattern in FORBIDDEN:
        m = pattern.search(text)
        if m:
            return f"มีเนื้อหากฎหมาย: {m.group(0)[:40]!r}"
    others = unsupported_laws(text, [code]) if LAW_MENTION.search(code) else \
        [m for m in LAW_MENTION.findall(text)]
    if others:
        return f"เอ่ยกฎหมายฉบับอื่น: {others[0][:40]!r}"
    return None


async def compose(question: str, topic: str, code: str, where: str,
                  fallback: str) -> str:
    """Phrase a refusal that has already been decided. Falls back on any doubt."""
    user = (f"คำถามของผู้ใช้\n{question}\n\n"
            f"เรื่องนี้อยู่ในหมวด {topic}\n"
            f"เรียกชื่อกฎหมายแบบกว้าง ๆ ได้ว่า {code}\n"
            f"ที่ที่ผู้ใช้ควรไปถามต่อ\n{where}")
    try:
        text = (await complete(SYSTEM, user)).strip()
    except LLMUnavailable as exc:
        log.info("refusal fell back to fixed text: %s", exc)
        return fallback

    reason = _unsafe(text, code)
    if reason:
        log.warning("refusal rejected (%s), using fixed text | %r", reason, text[:120])
        return fallback
    return text
