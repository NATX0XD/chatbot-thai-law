# -*- coding: utf-8 -*-
"""Handle the things people say to a bot that are not questions about the law.

Found from real LINE traffic: "สวัสดี" scored 0.445 and "คุณทำอะไรได้บ้าง" scored
0.512, so both fell through the cosine gate and got the out-of-scope refusal --
a wall of text about missing civil and criminal codes. Technically the guard did
its job; from the user's side the bot answered a greeting with a legal disclaimer.

Greetings and capability questions are routed here instead, before any retrieval
happens. Nothing in this module calls the model.
"""
from __future__ import annotations

import re

CAPABILITIES = (
    "ผมตอบคำถามกฎหมายไทยจากตัวบทพระราชบัญญัติจริง และอ้างเลขมาตราให้ทุกครั้ง "
    "เพื่อให้ตรวจสอบต่อได้ครับ\n\n"
    "ถามได้เลย เช่น\n"
    "• ถูกเลิกจ้าง ทำงานมา 5 ปี ได้ค่าชดเชยเท่าไหร่\n"
    "• ลาพักร้อนได้กี่วัน ลาคลอดได้กี่วัน\n"
    "• นายจ้างไม่จ่ายค่าจ้าง ต้องทำยังไง\n"
    "• เจ้าหนี้โทรทวงหนี้ตอนดึก ผิดกฎหมายไหม\n"
    "• บริษัทเก็บข้อมูลส่วนตัวต้องขอความยินยอมไหม\n"
    "• ซื้อของออนไลน์แล้วของไม่ตรงปก ร้องเรียนที่ไหน\n\n"
    "สิ่งที่ผมยังตอบไม่ได้ คือเรื่องที่อยู่ในประมวลกฎหมายแพ่งและพาณิชย์และประมวลกฎหมายอาญา "
    "ได้แก่ เช่าบ้าน มัดจำ กู้ยืม ค้ำประกัน ครอบครัว มรดก หมิ่นประมาท ฉ้อโกง "
    "เพราะคลังข้อมูลยังไม่มีตัวบทเหล่านั้น ผมจะบอกตรง ๆ ไม่เดาให้ครับ"
)

GREETING = "สวัสดีครับ 👋\n\n" + CAPABILITIES

THANKS = "ยินดีครับ ถามเพิ่มได้ตลอดเลย"

# Politeness particles and punctuation that can trail a bare greeting.
TAIL = r"(?:ครับ|คร้าบ|ค่ะ|คะ|ค๊า|จ้า|จ้ะ|ฮะ|นะ|น้า|ๆ|\s|!|~|\.)*"

# Greetings and thanks are anchored to the *whole* message. Someone who writes
# "สวัสดีครับ อยากถามเรื่องเลิกจ้าง" is asking a real question with a polite
# opener, and must reach the retrieval pipeline rather than get a canned hello.
# Capability phrases need no anchor -- they are unambiguous wherever they appear.
ROUTES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(rf"^(?:ขอบคุณ|ขอบใจ|thank you|thanks|thank|thx){TAIL}$", re.I), THANKS),
    (re.compile(rf"^(?:สวัสดี|หวัดดี|ดี|hello|hi|hey|ทัก){TAIL}$", re.I), GREETING),
    (re.compile(r"(ทำอะไรได้|ช่วยอะไรได้|ตอบอะไรได้|ถามอะไรได้|เก่งอะไร|"
                r"คุณคือใคร|คุณคืออะไร|นี่คืออะไร|บอทอะไร|ใช้ยังไง|ใช้งานยังไง|"
                r"^help$|^ช่วยเหลือ$|^เริ่ม$|^start$|^เมนู$|^\?+$)", re.I), CAPABILITIES),
)


def route(question: str) -> str | None:
    """Return a canned reply for conversational input, or None to carry on."""
    q = question.strip()
    if not q:
        return None
    for pattern, reply in ROUTES:
        if pattern.search(q):
            return reply
    return None
