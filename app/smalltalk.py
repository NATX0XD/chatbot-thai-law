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

from app.config import settings

CAPABILITIES = (
    "ผมตอบคำถามเรื่องจรรยาบรรณวิชาชีพทางการศึกษา จากข้อบังคับคุรุสภาฉบับจริง "
    "และอ้างเลขข้อให้ทุกครั้งเพื่อให้ตรวจสอบต่อได้ครับ\n\n"
    "ถามได้เลย เช่น\n"
    "• จรรยาบรรณวิชาชีพครูมีกี่ด้าน อะไรบ้าง\n"
    "• ครูด่านักเรียนหน้าชั้นผิดจรรยาบรรณไหม\n"
    "• ครูนินทาเพื่อนครูผิดข้อไหน\n"
    "• ครูผิดจรรยาบรรณมีโทษอะไรบ้าง\n"
    "• อยากร้องเรียนครู ต้องทำยังไง\n"
    "• ถูกวินิจฉัยว่าผิดจรรยาบรรณ อุทธรณ์ได้ภายในกี่วัน\n\n"
    "คลังมีข้อบังคับคุรุสภา 9 ฉบับ ว่าด้วยจรรยาบรรณของวิชาชีพ แบบแผนพฤติกรรม "
    "การพิจารณาการประพฤติผิด และการอุทธรณ์ พร้อมพระราชบัญญัติสภาครูและบุคลากร"
    "ทางการศึกษา พ.ศ. 2546\n\n"
    "สิ่งที่ผมยังตอบไม่ได้ คือเรื่องที่ไม่ใช่จรรยาบรรณ เช่น วินัยข้าราชการครู "
    "การขอและต่อใบอนุญาต เงินเดือนและสัญญาจ้าง ภาษี หรือคดีอาญาและคดีแพ่ง "
    "เพราะคลังไม่มีตัวบทเหล่านั้น ผมจะบอกตรง ๆ ไม่เดาให้ครับ"
)

GREETING = "สวัสดีครับ 👋\n\n" + CAPABILITIES

# The rich menu's middle cell sends the exact string "ตัวอย่างคำถาม", so this is
# what a tap on it produces. Grouped by topic and longer than the six lines in
# CAPABILITIES, otherwise the cell would just repeat the welcome message. The
# same questions back the web chat's ตัวอย่างคำถาม panel. Each one was run against
# the deployed bot and came back with a section from an act that governs it, so
# tapping one never lands on a refusal -- a menu of examples that get refused is
# worse than no menu at all.
EXAMPLES = (
    "ตัวอย่างคำถามที่ผมตอบได้จริง ก็อปแล้วส่งมาได้เลยครับ\n\n"
    "📘 จรรยาบรรณห้าด้าน\n"
    "• จรรยาบรรณวิชาชีพครูมีกี่ด้าน อะไรบ้าง\n"
    "• จรรยาบรรณต่อตนเองของครูคืออะไร\n"
    "• ครูต้องพัฒนาตัวเองด้านไหนบ้าง\n\n"
    "🧑\u200d🏫 ครูกับศิษย์\n"
    "• ครูด่านักเรียนหน้าชั้นผิดจรรยาบรรณไหม\n"
    "• ครูเอาความลับของนักเรียนไปเล่าให้คนอื่นฟังได้ไหม\n"
    "• ครูเรียกเงินจากผู้ปกครองเพื่อให้ลูกได้เกรดดีผิดข้อไหน\n\n"
    "🤝 ครูกับเพื่อนร่วมวิชาชีพ\n"
    "• ครูนินทาเพื่อนครูผิดจรรยาบรรณไหม\n"
    "• ครูโยนความผิดให้เพื่อนครูผิดข้อไหน\n\n"
    "🏘️ ครูกับสังคม\n"
    "• จรรยาบรรณต่อสังคมของครูคืออะไร\n"
    "• เศรษฐกิจพอเพียงเกี่ยวอะไรกับจรรยาบรรณครู\n\n"
    "⚖️ โทษและกระบวนการ\n"
    "• ครูผิดจรรยาบรรณมีโทษอะไรบ้าง\n"
    "• พักใช้ใบอนุญาตได้นานสุดกี่ปี\n"
    "• อยากร้องเรียนครูที่ประพฤติผิดจรรยาบรรณ ต้องทำยังไง\n"
    "• อุทธรณ์คำวินิจฉัยได้ภายในกี่วัน"
)

THANKS = "ยินดีครับ ถามเพิ่มได้ตลอดเลย"

# Politeness particles and punctuation that can trail a bare greeting.
TAIL = r"(?:ครับ|คร้าบ|ค่ะ|คะ|ค๊า|จ้า|จ้ะ|ฮะ|นะ|น้า|ๆ|\s|!|~|\.)*"

# Greetings and thanks are anchored to the *whole* message. Someone who writes
# "สวัสดีครับ อยากถามเรื่องเลิกจ้าง" is asking a real question with a polite
# opener, and must reach the retrieval pipeline rather than get a canned hello.
# Capability phrases need no anchor -- they are unambiguous wherever they appear.
#
# The two rich menu cells are matched first and anchored to the whole message:
# they are literal strings LINE sends on a tap, and "ถามกฎหมาย" as free text
# would otherwise be caught by the capability pattern below.
ROUTES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(rf"^ตัวอย่างคำถาม{TAIL}$"), EXAMPLES),
    (re.compile(rf"^ถามกฎหมาย{TAIL}$"), CAPABILITIES),
    (re.compile(rf"^(?:ขอบคุณ|ขอบใจ|thank you|thanks|thank|thx){TAIL}$", re.I), THANKS),
    (re.compile(rf"^(?:สวัสดี|หวัดดี|ดี|hello|hi|hey|ทัก){TAIL}$", re.I), GREETING),
    (re.compile(r"(ทำอะไรได้|ช่วยอะไรได้|ตอบอะไรได้|ถามอะไรได้|เก่งอะไร|"
                r"คุณคือใคร|คุณคืออะไร|นี่คืออะไร|บอทอะไร|ใช้ยังไง|ใช้งานยังไง|"
                r"^help$|^ช่วยเหลือ$|^เริ่ม$|^start$|^เมนู$|^\?+$)", re.I), CAPABILITIES),
)


# ---------------------------------------------------------------------------
# The same four replies for the networking textbook. The constants above are
# the Teachers Council bot's and are served when DATASET=ksp.

NETWORK_CAPABILITIES = (
    "ผมช่วยทบทวนวิชาเครือข่ายคอมพิวเตอร์เบื้องต้น (รหัสวิชา 2204-2003) "
    "ตอบจากหนังสือคู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น บอกบทและหน้าให้ทุกครั้ง "
    "และแนบรูปจากหนังสือให้เมื่อมีรูปประกอบครับ\n\n"
    "ถามได้เลย เช่น\n"
    "• สายคู่บิดเกลียวคืออะไร มีข้อดีข้อเสียอย่างไร\n"
    "• แบบจำลอง OSI มีกี่ชั้น อะไรบ้าง\n"
    "• โทโปโลยีแบบดาวต่างจากแบบบัสอย่างไร\n"
    "• เครือข่ายแบบเวิร์กกรุ๊ปต่างจากแบบโดเมนอย่างไร\n"
    "• ขั้นตอนการเข้าหัวสายแลน RJ-45 มีอะไรบ้าง\n\n"
    "หนังสือมี 7 บท ตั้งแต่พื้นฐานการสื่อสารข้อมูล สื่อกลางและอุปกรณ์เครือข่าย "
    "โทโปโลยีและเครือข่ายท้องถิ่น ไปจนถึงการตั้งค่าเวิร์กกรุ๊ป บัญชีผู้ใช้ สิทธิ์ "
    "และการแชร์ไฟล์กับเครื่องพิมพ์บน Windows\n\n"
    "เรื่องที่หนังสือเล่มนี้ไม่ได้เขียนไว้ ผมจะบอกตรง ๆ ว่าไม่มี ไม่เดาให้ครับ"
)

NETWORK_GREETING = "สวัสดีครับ 👋\n\n" + NETWORK_CAPABILITIES

NETWORK_EXAMPLES = (
    "ตัวอย่างคำถามที่ผมตอบได้จากหนังสือ ก็อปแล้วส่งมาได้เลยครับ\n\n"
    "🌐 พื้นฐานเครือข่าย\n"
    "• เครือข่ายคอมพิวเตอร์คืออะไร\n"
    "• แบบจำลอง OSI มีกี่ชั้น อะไรบ้าง\n"
    "• เครือข่าย LAN MAN WAN ต่างกันอย่างไร\n\n"
    "🔌 สื่อกลางและอุปกรณ์\n"
    "• สายคู่บิดเกลียวคืออะไร มีข้อดีข้อเสียอย่างไร\n"
    "• สายใยแก้วนำแสงมีข้อดีอะไรบ้าง\n"
    "• ฮับกับสวิตช์ต่างกันอย่างไร\n\n"
    "🕸️ โทโปโลยีและแลน\n"
    "• โทโปโลยีแบบดาวมีข้อดีข้อเสียอะไร\n"
    "• CSMA/CD ทำงานอย่างไร\n\n"
    "🖥️ ภาคปฏิบัติบน Windows\n"
    "• ขั้นตอนการเข้าหัวสายแลน RJ-45 มีอะไรบ้าง\n"
    "• เครือข่ายแบบเวิร์กกรุ๊ปต่างจากแบบโดเมนอย่างไร\n"
    "• การแมปไดรฟ์คืออะไร"
)

NETWORK_ROUTES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(rf"^ตัวอย่างคำถาม{TAIL}$"), NETWORK_EXAMPLES),
    (re.compile(rf"^ถามเรื่องเครือข่าย{TAIL}$"), NETWORK_CAPABILITIES),
    (ROUTES[2][0], THANKS),
    (ROUTES[3][0], NETWORK_GREETING),
    (ROUTES[4][0], NETWORK_CAPABILITIES),
    # Asked on the first morning and refused as off the subject: "คุณเป็นใคร",
    # "คุณรู้เรื่องอะไรบ้าง". Only for this bot -- in a question about the law
    # "เป็นใคร" is part of the question.
    (re.compile(r"^(?:คุณ|เธอ|นาย|บอท|น้อง|พี่|นี่)?\s*(?:เป็น|คือ)\s*(?:ใคร|อะไร|บอทอะไร)"
                r"|(?:คุณ|บอท)?\s*(?:รู้|ตอบ|สอน|ช่วย|ถาม)(?:ได้)?(?:เรื่อง)?อะไร(?:ได้)?บ้าง"
                r"|รู้เรื่องอะไร|ถามอะไรดี|ไม่รู้จะถามอะไร"), NETWORK_CAPABILITIES),
)


def capabilities() -> str:
    return NETWORK_CAPABILITIES if settings.dataset == "network" else CAPABILITIES


def greeting() -> str:
    return NETWORK_GREETING if settings.dataset == "network" else GREETING


def route(question: str) -> str | None:
    """Return a canned reply for conversational input, or None to carry on."""
    q = question.strip()
    if not q:
        return None
    for pattern, reply in (NETWORK_ROUTES if settings.dataset == "network" else ROUTES):
        if pattern.search(q):
            return reply
    return None
