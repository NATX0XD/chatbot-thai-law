# -*- coding: utf-8 -*-
"""Turn a teacher's question into a cited answer, or into an honest refusal.

The refusal path matters more than the answer path, and more here than it did
before. This corpus is ten documents of the Teachers Council -- the professional
ethics of educators and the procedure for judging breaches of them -- and
nothing else in Thai law. A teacher asking about dismissal, about pay, about
their licence application, or about civil-service discipline is asking a real
question that this system cannot answer, and the ones that sit closest to the
corpus are the ones most likely to be answered wrongly.

Five guards, catching five different failures:

  1. find_gap -- the question is about law the corpus does not hold. These score
     *high*, because the retriever finds real, on-topic text; only a rule that
     knows what is missing can catch them. "ข้าราชการครูทำผิดวินัยร้ายแรงมีโทษ
     อะไร" reaches cosine 0.655 against ethics regulations that say nothing
     about civil-service discipline.
  2. the cosine gate -- nothing in the corpus resembles the question at all.
  3. find_gap_in_answer -- the *answer* wandered into missing law even though the
     question did not name it.
  4. unsupported_laws -- the answer names an instrument that was never supplied.
  5. impossible_citations -- the answer cites a rule number the instrument does
     not have, or attaches the wrong unit word to it, or points at a sub-item
     outside the block it names. A wrong name is visible to the reader; "ตามข้อ
     23" when the rule is ข้อ 13 is not. Checked against the corpus rather than
     the retrieved set, because that is a fact about the documents.

None of them spends an LLM call except the last three, which read what the model
already wrote. The model is never asked whether it should have answered.

What a guard does when it fires changed after the sixth acceptance run. Refusing
was costing answers to questions the corpus answers well: the tester's words were
that a correct catch "still leaves the user with nothing". So a guard that fires
now writes down what is wrong and the writer gets one more turn with that note in
front of it -- see inspect and REPAIR. Only if the second attempt is still wrong
does the refusal stand. The note is specific ("ข้อ 14 ใช้คำว่า พึง แต่คำตอบเขียนว่า
ต้อง"), because a general instruction to be careful is what six rounds of prompt
edits already were, and it did not hold.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

from app.config import settings
from app.coverage import answer_beyond_corpus as find_gap_in_answer, find_gap
from app.flex import answer_message
from app.llm import LLMUnavailable, complete
from app.refuse import compose as compose_refusal
from app.retriever import Hit, get_retriever
from app.smalltalk import route as smalltalk_route
from app.support import (
    Corpus as SupportIndex, cited_rules, correct_modals, impossible_citations,
    misattributed_citations, modal_mismatches, points_elsewhere,
    unsupported_claims)
from app.verify import unsupported_laws

log = logging.getLogger(__name__)

DISCLAIMER = ("ℹ️ ข้อมูลเบื้องต้นจากข้อบังคับคุรุสภาและพระราชบัญญัติสภาครูฯ "
              "ไม่ใช่คำวินิจฉัยของคุรุสภาและไม่ใช่คำปรึกษาทางกฎหมาย "
              f"อ้างจากตัวบทที่ประกาศถึง {settings.corpus_as_of} "
              "ก่อนดำเนินการใด ๆ ควรตรวจสอบฉบับปัจจุบันที่ ksp.or.th/laws")

SCOPE = ("คลังนี้มีเฉพาะจรรยาบรรณวิชาชีพทางการศึกษา ได้แก่ ข้อบังคับคุรุสภา "
         "ว่าด้วยจรรยาบรรณของวิชาชีพ แบบแผนพฤติกรรมตามจรรยาบรรณ "
         "การพิจารณาการประพฤติผิดจรรยาบรรณ การอุทธรณ์คำวินิจฉัย "
         "และพระราชบัญญัติสภาครูและบุคลากรทางการศึกษา")

OUT_OF_SCOPE = (
    "ยังตอบคำถามนี้ไม่ได้ครับ เพราะไม่พบตัวบทที่เกี่ยวข้องในคลังข้อมูล\n\n"
    f"{SCOPE}\n\n"
    "ลองถามใหม่ให้ตรงกับเรื่องเหล่านี้ เช่น จรรยาบรรณห้าด้านของครู "
    "พฤติกรรมที่พึงประสงค์และไม่พึงประสงค์ โทษทางจรรยาบรรณ "
    "การร้องเรียน การสอบสวน หรือการอุทธรณ์"
)

FABRICATED = (
    "ยังตอบคำถามนี้ไม่ได้ครับ\n\n"
    "ระบบร่างคำตอบโดยอ้างถึง {laws} ซึ่งไม่มีอยู่ในคลังข้อมูล จึงตรวจสอบความถูกต้อง"
    "ไม่ได้ ผมเลยไม่ส่งคำตอบนั้นให้ เพราะข้อมูลกฎหมายที่ผิดอันตรายกว่าการไม่ตอบ\n\n"
    "แนะนำให้ดูตัวบทฉบับเต็มที่ ksp.or.th/laws หรือติดต่อคุรุสภาโดยตรงครับ"
)

MISCITED = (
    "ยังตอบคำถามนี้ไม่ได้ครับ\n\n"
    "ระบบร่างคำตอบโดยอ้างถึง {sections} ซึ่งไม่ตรงกับตัวบทที่ค้นเจอ "
    "ผมเลยไม่ส่งคำตอบนั้นให้ เพราะเลขข้อที่ผิดจะพาไปอ่านกฎคนละข้อ\n\n"
    "ลองถามใหม่ให้เจาะจงขึ้น หรือดูตัวบทฉบับเต็มที่ ksp.or.th/laws ครับ"
)

REPAIR = """
คำตอบที่คุณเพิ่งเขียนมีข้อผิดพลาดที่ตรวจพบจากการเทียบกับตัวบทโดยตรง ดังนี้

{problems}

เขียนคำตอบใหม่ทั้งหมดโดยแก้ข้อผิดพลาดข้างต้น ใช้ได้เฉพาะตัวบทที่ให้ไว้เท่านั้น
ห้ามเพิ่มการอ้างอิงข้อหรือมาตราใหม่ที่ไม่ได้อยู่ในคำตอบเดิม แก้เฉพาะจุดที่ระบุไว้ข้างบน
ส่วนที่เหลือของคำตอบให้คงไว้ตามเดิม ห้ามตัดรายการที่ตัวบทกำหนดไว้ออก
ถ้าข้อที่อ้างไม่ได้เขียนเรื่องที่ถามไว้ ให้บอกตามตรงว่าตัวบทไม่ได้เขียนเรื่องนี้ไว้
แล้วอธิบายว่าข้อที่ใกล้เคียงที่สุดพูดถึงอะไร ดีกว่าอ้างข้อที่ไม่ตรง
ตอบเฉพาะคำตอบใหม่ ไม่ต้องอธิบายว่าแก้อะไร"""

SYSTEM_PROMPT = """คุณคือผู้ช่วยให้ข้อมูลเรื่องจรรยาบรรณวิชาชีพทางการศึกษา สำหรับครูและผู้ปกครอง ตอบผ่านแอปแชท LINE

ขอบเขต
คลังข้อมูลมีเฉพาะข้อบังคับคุรุสภาและพระราชบัญญัติสภาครูและบุคลากรทางการศึกษา พ.ศ. 2546
ไม่มีกฎหมายแรงงาน อาญา แพ่ง ภาษี และไม่มีวินัยข้าราชการครูตาม พ.ร.บ.ระเบียบข้าราชการครูฯ
จรรยาบรรณวิชาชีพกับวินัยข้าราชการเป็นคนละเรื่องกัน ห้ามตอบปนกัน
ข้อบังคับคุรุสภามีหลายฉบับและแต่ละฉบับเป็นคนละเรื่อง ต้องดูชื่อเรื่องหลังคำว่า ว่าด้วย ทุกครั้ง
ฉบับว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณ คือฉบับที่ใช้ดำเนินการเรื่องร้องเรียนและวินิจฉัยโทษ
ฉบับว่าด้วยการอุทธรณ์คำวินิจฉัย เป็นคนละฉบับ ใช้เฉพาะขั้นอุทธรณ์ ห้ามนำมาตอบแทนกัน

เนื้อหา
1. ตอบจากตัวบทที่ให้มาเท่านั้น ห้ามใช้ความรู้อื่น
2. ทุกข้อความที่เป็นสาระ ต้องอ้างที่มาด้วยเลขในวงเล็บเหลี่ยมของตัวบทที่ให้มา เช่น [1] [3]
   ห้ามพิมพ์ชื่อกฎหมาย เลขข้อ หรือเลขมาตราเอง ระบบจะเติมชื่อและเลขที่ถูกต้องให้เองจาก [เลข] ที่คุณใส่
   ถ้าจะอ้างอนุข้อด้วย ให้เขียนต่อท้ายเลขในวงเล็บเหลี่ยม เช่น [2](ข)(๓)
   ตัวอย่าง: "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ [2](ข)(๓)"
3. ถ้าไม่แน่ใจว่าข้อความอยู่ในตัวบทชิ้นไหน ให้อธิบายโดยไม่ใส่เลขในวงเล็บเหลี่ยม
   ห้ามเดาว่าเป็นชิ้นไหน เพราะเลขที่ใส่จะถูกแปลงเป็นเลขข้อจริง
4. ถ้าตัวบทไหนมีคำว่า (ยกเลิกแล้ว) กำกับอยู่ ห้ามอ้างเป็นกฎที่ใช้อยู่
   ให้ใช้ฉบับที่ไม่ได้ถูกยกเลิก และบอกผู้ใช้ได้ว่าฉบับเก่าถูกยกเลิกไปแล้ว
   ตัวบทชิ้นใดไม่มีคำว่า (ยกเลิกแล้ว) กำกับ แปลว่ายังใช้บังคับอยู่
   ห้ามบอกว่าถูกยกเลิก และห้ามไล่รายชื่อสถานะของทุกฉบับ ให้ตอบเฉพาะฉบับที่ถาม
   ถ้าคำถามระบุชื่อเรื่องของข้อบังคับ เช่น "ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณ"
   ต้องตอบจากตัวบทที่ชื่อเรื่องตรงกัน ห้ามตอบด้วยข้อบังคับเรื่องอื่น
   เช่น ห้ามตอบด้วยข้อบังคับว่าด้วยการอุทธรณ์คำวินิจฉัย ซึ่งเป็นคนละเรื่องกัน
   ถ้าตัวบทไหนมีบรรทัด (ข้อนี้ถูกยกเลิกและแทนที่แล้วโดย ...) ห้ามตอบตามข้อความของข้อนั้น
   ให้หาข้อความของฉบับแก้ไขในตัวบทที่ให้มา แล้วตอบตามฉบับแก้ไข พร้อมบอกว่าแก้ไขเมื่อใด
5. ถ้าตัวบทไม่พอจะตอบ บอกตรง ๆ ว่าตัวบทไม่ได้เขียนเรื่องนี้ไว้ ห้ามเดา
   โดยเฉพาะคำถามที่ถามหาตัวเลข เช่น จำนวนชั่วโมงอบรม ถ้าตัวบทไม่ได้กำหนดไว้ ให้บอกว่าไม่ได้กำหนด
   ห้ามเติมเงื่อนไข ระยะเวลา หรือขั้นตอนที่ตัวบทไม่ได้เขียน แม้จะฟังดูสมเหตุสมผลก็ตาม
6. ตัวบทแต่ละชิ้นมีบรรทัด "(อยู่ใน หมวด ... > ส่วนที่ ...)" กำกับ ให้อ่านก่อนตอบเสมอ
   ข้อบังคับแบบแผนพฤติกรรม 2550 เขียนจรรยาบรรณห้าด้านซ้ำสี่รอบ รอบละหนึ่งประเภทผู้ประกอบวิชาชีพ
   คือ ครู ผู้บริหารสถานศึกษา ผู้บริหารการศึกษา และศึกษานิเทศก์
   ถ้าคำถามถามถึงครู ห้ามตอบด้วยข้อของผู้บริหารหรือศึกษานิเทศก์
   ถ้าคำถามไม่ได้ระบุว่าเป็นผู้ประกอบวิชาชีพประเภทใด ให้ตอบด้วยข้อของครูเป็นหลัก
   จะบอกเพิ่มได้ว่าประเภทอื่นมีข้อทำนองเดียวกัน แต่ข้อหลักที่ยกมาต้องเป็นของครู
7. ถ้ามีทั้งข้อบังคับจรรยาบรรณ 2556 และแบบแผนพฤติกรรม 2550 ให้ยึด 2556 เป็นตัวหลักที่วางหลัก
   แล้วใช้ 2550 เป็นตัวอย่างพฤติกรรมประกอบ
8. ถ้าคำถามถามจำนวน เช่น มีกี่ข้อ มีกี่อย่าง ให้นับจากตัวบทที่ให้มาเท่านั้น
   และถ้ารายการในตัวบทมีหลายข้อ ต้องยกให้ครบทุกข้อ ห้ามตัดทิ้ง
9. ถ้าถูกขอให้ช่วยหลบเลี่ยงการถูกร้องเรียนหรือการสอบสวน ให้ปฏิเสธ
   แล้วอธิบายกระบวนการและสิทธิชี้แจงตามตัวบทแทน
10. อธิบายด้วยภาษาที่คนทั่วไปเข้าใจ ห้ามคัดลอกตัวบทมาทั้งดุ้น
11. ถ้ามีตัวเลขสำคัญ เช่น จำนวนวัน จำนวนคน ให้ระบุเป็นเลขอารบิก
12. ห้ามเขียนคำหรือวลีเดิมซ้ำติดกันหลายครั้ง ถ้าไม่มีอะไรจะเขียนต่อแล้วให้จบคำตอบ
13. คำว่า "ต้อง" กับ "พึง" ในตัวบทมีน้ำหนักต่างกัน ต้องคัดลอกมาให้ตรงตามที่ตัวบทใช้
    ห้ามเปลี่ยน "พึง" เป็น "ต้อง" หรือกลับกัน
14. ถ้าจะอ้างอนุข้อหรือวรรค เช่น (ก) (ข) (๑) ต้องแน่ใจว่าข้อความนั้นอยู่ในอนุข้อนั้นจริง
    ถ้าไม่แน่ใจ ให้อ้างเฉพาะเลขข้อ ดีกว่าอ้างอนุข้อผิด
    ห้ามเขียนช่วงอนุข้อ เช่น (๑)-(๕) ถ้าไม่ได้ยกมาครบทุกอนุข้อในช่วงนั้น
15. เวลาอ้างตัวบทชิ้นใด ให้บอกด้วยว่าเรื่องนั้นอยู่ในด้านหรือหมวดใด เช่น "จรรยาบรรณต่อผู้รับบริการ"
    บอกเป็นชื่อด้านหรือชื่อหมวดเท่านั้น ห้ามพิมพ์เลขข้อนำหน้า เลขข้อระบบจะเติมให้เอง
16. ถ้าคำถามระบุประเภทผู้ประกอบวิชาชีพ เช่น ผู้บริหารสถานศึกษา ผู้บริหารการศึกษา ศึกษานิเทศก์
    ต้องตอบด้วยข้อของประเภทนั้นโดยตรง ไม่ใช่ข้อทั่วไปหรือข้อของครู
17. ถ้าคำถามเปรียบเทียบสองกลุ่ม ให้ยกตัวบทของทั้งสองกลุ่มมาวางคู่กัน
18. ถ้าคำถามถามถึงคำว่า "ต้อง" หรือ "พึง" ให้เทียบกับข้ออื่นข้างเคียงด้วยว่าใช้คำใด
19. ทุกขั้นตอนของกระบวนการที่อธิบาย ต้องมีเลขในวงเล็บเหลี่ยมกำกับ ถ้าไม่มีตัวบทรองรับ อย่าเขียนขั้นตอนนั้น
20. "กล่าวหา" กับ "กล่าวโทษ" ในตัวบทเป็นคนละสิทธิ และผู้มีสิทธิเป็นคนละกลุ่มกัน
    ต้องแยกอธิบายตามที่ตัวบทเขียน ห้ามรวมเป็นเรื่องเดียวกันหรือสรุปว่า "ทุกคนมีสิทธิ"
    เช่นเดียวกับคำว่า "อาจ" กับ "ต้อง" ตัวบทที่เขียนว่า อาจ คือทำก็ได้ไม่ทำก็ได้
    ห้ามเขียนเป็นข้อบังคับ และตัวบทที่เขียนว่า ต้อง ห้ามเขียนให้กลายเป็นทางเลือก
21. ถ้าคำถามถามว่า "โทษ" มีกี่อย่าง ให้แยกให้ชัดว่าการยกข้อกล่าวหาคือการวินิจฉัยว่าไม่ผิด
    จึงไม่ใช่โทษ ส่วนที่เป็นโทษคือรายการที่เหลือ ให้ตอบจำนวนตามที่นับได้จากตัวบทจริง

รูปแบบสำหรับหน้าจอแชท
- ย่อหน้าแรกคือคำตอบตรง ๆ 1-2 ประโยค ต้องอ่านจบแล้วได้คำตอบทันที
- เว้นบรรทัดว่าง แล้วอธิบายเหตุผลสั้น ๆ พร้อมอ้างข้อหรือมาตรา
- ถ้ามีขั้นตอนที่ทำต่อได้ ให้ขึ้นบรรทัดใหม่แต่ละข้อ นำหน้าด้วย 1. 2. 3.
- ถ้ามีหลายกรณี ให้ขึ้นบรรทัดใหม่แต่ละกรณี นำหน้าด้วย •
- ความยาวรวมไม่เกิน 12 บรรทัด

ข้อห้ามเรื่องรูปแบบ เพราะ LINE แสดงข้อความธรรมดาเท่านั้น
- ห้ามใส่วงเล็บเหลี่ยม [ ] ในคำตอบเด็ดขาด
- ห้ามใช้ ** __ ## ``` หรือสัญลักษณ์ markdown ใด ๆ เพราะจะแสดงเป็นตัวอักษรดิบ
- ห้ามใส่หัวข้อกำกับ เช่น คำตอบ: หรือ คำอธิบาย: ให้เขียนเป็นเนื้อความต่อเนื่อง
- ห้ามขึ้นต้นด้วยการทวนคำถาม
- ห้ามพูดถึงตัวระบบ เช่น ข้อความถูกตัดทอน หรือ ข้อจำกัดของ LINE ผู้ใช้ไม่ต้องรู้เรื่องนี้

ข้อห้ามที่สำคัญที่สุด
ห้ามอ้างชื่อกฎหมายหรือข้อบังคับที่ไม่ได้อยู่ในตัวบทที่ให้มาเด็ดขาด แม้จะมั่นใจว่าจำได้ก็ตาม
ถ้าตัวบทที่ให้มาไม่ตรงกับคำถามเลย ให้ตอบเพียงว่าไม่มีข้อมูลพอ ห้ามตอบจากความรู้เดิม"""


@dataclass
class Answer:
    text: str
    citations: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    in_scope: bool = True
    error: str | None = None
    # what the guards found and what the repair turn did with it. Carried so a
    # reader of the API can check the mechanism instead of inferring it from a
    # diff against the previous run, which is how round seven had to be read.
    faults: list[str] = field(default_factory=list)
    repair: str = "not attempted"   # accepted | rejected | not attempted

    def for_line(self) -> str:
        """Plain-text form, used as a fallback and by callers that want one string."""
        body = self.text.strip()
        if len(body) > settings.max_answer_chars:
            body = body[:settings.max_answer_chars].rstrip() + " …"
        return f"{body}\n\n{DISCLAIMER}"

    def for_line_messages(self) -> list:
        """Text first, then the same answer as a card.

        Both are sent because they serve different readers: the text bubble is
        searchable, copyable and works on every client, while the card separates
        the cited sections from the prose so the reader can check them at a glance.
        Sending only the card would break copy-paste; only the text loses the
        structure the citations need.
        """
        body = self.text.strip()
        if len(body) > settings.max_answer_chars:
            body = body[:settings.max_answer_chars].rstrip() + " …"
        messages = [{"type": "text", "text": f"{body}\n\n{DISCLAIMER}"}]
        if self.citations:
            messages.append(answer_message(body, self.citations,
                                           in_scope=self.in_scope))
        return messages


MARKDOWN_BOLD = re.compile(r"\*{1,3}([^*\n]+)\*{1,3}")
MARKDOWN_HEAD = re.compile(r"(?m)^#{1,6}\s*")
TEMPLATE_BRACKET = re.compile(r"\[([^\]\n]{0,120})\]")
LABEL_PREFIX = re.compile(r"(?m)^\s*(คำตอบ|คำอธิบาย(ขยายความ)?|สรุป|ขั้นตอน)\s*[:：]\s*")
BLANK_RUN = re.compile(r"\n{3,}")


def tidy_for_chat(text: str) -> str:
    """Strip formatting LINE cannot render.

    The model is told not to emit these, and mostly obeys, but "mostly" shows up
    in someone's chat window as literal ** and [ ]. The first version of the
    prompt used a bracketed skeleton -- [คำตอบสั้น 1-3 ประโยค] -- and Typhoon
    copied the brackets through verbatim, so this net stays even though the
    prompt no longer invites it.
    """
    text = MARKDOWN_BOLD.sub(r"\1", text)
    text = MARKDOWN_HEAD.sub("", text)
    text = TEMPLATE_BRACKET.sub(r"\1", text)
    text = LABEL_PREFIX.sub("", text)
    text = text.replace("`", "")
    text = BLANK_RUN.sub("\n\n", text)
    return text.strip()


async def phrase_refusal(question: str, gap) -> str:
    """Word a coverage-rule refusal for this particular question."""
    return await compose_refusal(question, topic=gap.topic, code=gap.code,
                                 where=gap.where, fallback=gap.message())


# Whenever a duty is in play, the rules that state it come along. ข้อบังคับฯ
# 2556 หมวด 3 holds five of them, and retrieving one of the five is how
# "จรรยาบรรณต่อผู้รับบริการมีกี่ข้อ" came back as "1 ข้อ" twice over. Only
# ข้อบังคับฯ 2556 is pulled in this way: it is fifteen rules long, none of its
# chapters holds more than five, and it is the document that states the duties
# rather than illustrating them -- so the cost is bounded and the gain is that
# an answer always has the rule itself in front of it, not only an example.
STATES_THE_DUTIES = "ksp-2556"
# ข้อบังคับฯ 2550 repeats the five duties once per kind of practitioner. The
# chapter for ครู is the one almost every question means, and it is where the
# worked examples of good and bad conduct live, so it comes along too -- one
# extra rule per duty, not four.
ILLUSTRATES_THE_DUTIES = "ksp-2550"
FOR_TEACHERS = "วิชาชีพครู"


# The five duties as a reader writes them. None is a substring of another, so a
# question that names one names exactly one.
DUTY_NAMES = ("ต่อตนเอง", "ต่อวิชาชีพ", "ต่อผู้รับบริการ",
              "ต่อผู้ร่วมประกอบวิชาชีพ", "ต่อสังคม")


def duties_named(question: str) -> set[str]:
    """Which of the five the question asks about, by name.

    Retrieval cannot be relied on for this. The five duties are phrased almost
    identically and sit close together in embedding space, so a question about
    จรรยาบรรณต่อวิชาชีพ came back holding rules about ต่อตนเอง and
    ต่อผู้ร่วมประกอบวิชาชีพ and none about the one it asked for. The name is
    right there in the question; reading it is free and exact.
    """
    return {duty for duty in DUTY_NAMES if duty in question}


def with_chapter_siblings(hits: list[Hit], corpus, question: str = "") -> list[Hit]:
    """Add the rules that state, or illustrate, a duty that is in play."""
    # A duty the question names outright is the duty it is about. Only when it
    # names none is the duty inferred, and then from the best-ranked labelled
    # hit alone -- taking every duty that appeared anywhere in the results added
    # eight rules to a question about one of them.
    wanted = duties_named(question)
    if not wanted:
        ranked = [h.rec.get("ethics_category") for h in hits if h.rec.get("ethics_category")]
        wanted = {ranked[0]} if ranked else set()
    if not wanted:
        return hits
    have = {h.rec["id"] for h in hits}
    def belongs(rec) -> bool:
        if rec.get("ethics_category") not in wanted or rec["id"] in have:
            return False
        if rec["sysid"] == STATES_THE_DUTIES:
            return True
        chapters = rec.get("chapters") or []
        return (rec["sysid"] == ILLUSTRATES_THE_DUTIES
                and bool(chapters) and chapters[0].endswith(FOR_TEACHERS))

    return hits + [Hit(rec=rec, rrf=0.0) for rec in corpus if belongs(rec)]


def with_amendments(hits: list[Hit], corpus) -> list[Hit]:
    """Put the replacing rule beside any retrieved rule that was replaced.

    Marking the old rule as superseded is not enough on its own: the new text
    lives in a different document under a different number, and if it was not
    retrieved the model has nothing to answer from and falls back on the old
    one. ข้อ 7 ของข้อบังคับฯ 2549 and its replacement in ฉบับที่ 2 พ.ศ. 2569
    ข้อ 3 are the pair this exists for.
    """
    wanted = {h.rec["amended_by"] for h in hits if h.rec.get("amended_by")}
    if not wanted:
        return hits
    have = {h.rec["id"] for h in hits}
    extra = [rec for rec in corpus
             if rec["id"] not in have
             and f"{rec.get('short')} {rec.get('unit')} {rec['section']}" in wanted]
    return hits + [Hit(rec=rec, rrf=0.0) for rec in extra]


def order_for_reading(hits: list[Hit]) -> list[Hit]:
    """Put the regulation that states the duties first, ranking aside.

    ข้อบังคับฯ 2556 states each duty; ข้อบังคับฯ 2550 illustrates it with worked
    examples. An answer should rest on the first and quote the second, and the
    model follows whichever it reads first.
    """
    return sorted(hits, key=lambda h: h.rec["sysid"] != STATES_THE_DUTIES)


def build_context(hits: list[Hit]) -> str:
    """The retrieved rules, each under the headings it sits below.

    The headings are not decoration. ข้อบังคับฯ 2550 states the same five duties
    four times over, once per kind of practitioner, and its rules read
    "ศึกษานิเทศก์ พึง..." only in the first line -- so without the chapter above
    them an answer about a classroom teacher can be written out of the rule for
    a district administrator, which acceptance testing caught it doing.
    """
    blocks = []
    for i, h in enumerate(hits, start=1):
        head = f"[{i}] {h.citation}"
        chapters = h.rec.get("chapters") or []
        if chapters:
            head += "\n    (อยู่ใน " + " > ".join(chapters) + ")"
        # A rule can be replaced without its document being repealed. ข้อ 7 ของ
        # ข้อบังคับฯ 2549 still reads "สิบเอ็ดคน" in the corpus; ฉบับที่ 2 พ.ศ.
        # 2569 ข้อ 3 replaced it with nine, and the assessors caught the system
        # answering from the old text with no sign that it was old.
        if h.rec.get("amended_by"):
            head += (f"\n    (ข้อนี้ถูกยกเลิกและแทนที่แล้วโดย {h.rec['amended_by']} "
                     f"— ห้ามตอบตามข้อความข้างล่างนี้ ให้ใช้ข้อความของฉบับแก้ไข)")
        if h.rec.get("amends"):
            head += f"\n    (ข้อนี้เป็นข้อความที่ใช้แทน {h.rec['amends']})"
        blocks.append(f"{head}\n{h.rec['text']}")
    return "\n\n".join(blocks)


# The model occasionally collapses into repeating one short phrase -- "ข้อ 8
# ข้อ 8 ข้อ 8" for hundreds of characters, until the answer is cut off with no
# content in it at all. Two acceptance cases came back that way. Every guard
# below passes such an answer, because it cites nothing and claims nothing.
DEGENERATE_RUN = re.compile(r"(.{2,40}?)\1{9,}")


def looks_degenerate(text: str) -> bool:
    return bool(DEGENERATE_RUN.search(text))


_support: SupportIndex | None = None


def _support_index() -> SupportIndex:
    """Built once from the same corpus the retriever holds."""
    global _support
    if _support is None:
        _support = SupportIndex(list(get_retriever().corpus))
    return _support


# "[2](ข)(๓)" -- the model points at the second piece of evidence and, if it
# wants, at a sub-item inside it. Everything else about the citation is filled
# in from the record.
MARKER = re.compile(r"\[(\d{1,2})\]((?:\s*\([ก-ฮ๐-๙0-9]{1,3}\))*)")
THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
# the rule number a fault is about, so a repair may move that one and no other
NUMBER_IN_NOTE = re.compile(r"(?:ข้อ|มาตรา)\s*([๐-๙0-9]{1,3})")
# a rule number the model typed itself, which is the thing being taken away
TYPED_NUMBER = re.compile(r"(ข้อ|มาตรา)\s*([๐-๙0-9]{1,3})")
# "8(ข)(๓)" with the brackets around the index lost -- a pointer that failed to
# become a citation, and reads to a teacher as a rule number
BARE_POINTER = re.compile(r"(?<![๐-๙0-9])[๐-๙0-9]{1,2}(?:\s*\([ก-ฮ๐-๙0-9]{1,3}\))+")
# a whole hand-written citation: "(ข้อบังคับคุรุสภา ... ข้อ 99)". Removing only
# the number would leave the instrument's name dangling in an empty bracket.
TYPED_CITATION = re.compile(r"\([^()\[\]]*(?:ข้อ|มาตรา)\s*[๐-๙0-9]{1,3}[^()]*\)")


def resolve_citations(text: str, hits: list[Hit]) -> tuple[str, list[str]]:
    """Turn the model's [n] markers into real citations, and report the rest.

    Three assessor rounds measured the same thing three times: the answers are
    right and the numbers beside them are not. Across 180 judgements the
    dominant fault was a clause quoted correctly and attributed to the wrong
    ข้อ, most often to another profession's chapter of ข้อบังคับฯ 2550, which
    repeats the same five duties four times over. The model typed 266 rule
    numbers across 60 answers, and every one was a chance to get it wrong.

    So it no longer types them. It points at the evidence it was given, and the
    citation is assembled from that record -- instrument, unit, number and the
    chapter that says whose duty it is. A pointer is either in range or it is
    not; there is no wrong-but-plausible version of it.
    """
    # Numbers the model typed in prose are removed, not just reported. It still
    # narrates them -- "อยู่ในข้อ 7 จรรยาบรรณต่อตนเอง" -- and those are the ones
    # that are wrong, while the sentence around them is not. Deleting the number
    # leaves "อยู่ในจรรยาบรรณต่อตนเอง", which is true and still useful; keeping
    # it leaves a false statement a reader cannot check.
    # A typed number is deleted only when the evidence does not contain it.
    # Deleting every one of them was too blunt: the answer to "อยู่ในข้อใด"
    # became "อยู่ใน จรรยาบรรณต่อตนเอง", and a list came out as "ได้แก่ , 10,
    # 11, 12 และ 13" because only the first number carried the word ข้อ. What
    # matters is whether the number is one the model was shown, not who typed it.
    supplied = {(h.rec.get("unit", "มาตรา"), h.rec["section"]) for h in hits}

    def invented(match: re.Match) -> bool:
        return (match.group(1),
                match.group(2).translate(THAI_TO_ARABIC)) not in supplied

    mispointed: list[str] = []
    by_number = {(h.rec.get("unit", "มาตรา"), h.rec["section"]): h.rec["text"]
                 for h in hits}

    def wrong(match: re.Match) -> bool:
        """A number the model typed that the evidence has, attached to a
        sentence that rule does not carry.

        Keeping every number the evidence contained let this through: "การ
        เกี่ยวข้องกับอบายมุข ... อยู่ในข้อ 9" where ข้อ 9 is จรรยาบรรณต่อสังคม
        and the rule is ข้อ 5. The citation in brackets beside it was right, so
        nothing looked at the prose. Both assessors named this as the fault the
        citation check cannot see by construction.
        """
        rule = by_number.get((match.group(1),
                              match.group(2).translate(THAI_TO_ARABIC)))
        return rule is not None and points_elsewhere(
            _sentence_before(text, match.start()), rule, _support_index())

    def keep(match: re.Match) -> str:
        return "" if invented(match) or wrong(match) else match.group(0)

    stray = [m.group(0) for m in TYPED_NUMBER.finditer(MARKER.sub("", text))
             if invented(m) or wrong(m)]
    text = TYPED_CITATION.sub(
        lambda m: "" if any(invented(t) or wrong(t)
                            for t in TYPED_NUMBER.finditer(m.group(0)))
        else m.group(0), text)
    text = TYPED_NUMBER.sub(keep, text)
    text = BARE_POINTER.sub("", text)

    def swap(match: re.Match) -> str:
        index = int(match.group(1)) - 1
        if not 0 <= index < len(hits):
            return ""          # a pointer at evidence that was never supplied
        rec = hits[index].rec
        subs = "".join(match.group(2).split())
        sentence = _sentence_before(text, match.start())
        if points_elsewhere(sentence, rec["text"], _support_index()):
            mispointed.append(f"{hits[index].citation} "
                              f"ไม่มีข้อความรองรับประโยคที่ชี้มา")
        return f"({hits[index].citation}{subs}{_whose(rec)})"

    text = MARKER.sub(swap, text)
    return re.sub(r"[ \t]{2,}", " ", text), stray + mispointed


SENTENCE_EDGE = re.compile(r"[\n•]|[.!?]\s")


def _sentence_before(text: str, at: int) -> str:
    """The sentence a pointer sits at the end of."""
    edges = [m.end() for m in SENTENCE_EDGE.finditer(text, 0, at)]
    return text[(edges[-1] if edges else 0):at]


def _whose(rec: dict) -> str:
    """Which practitioner a rule of ข้อบังคับฯ 2550 belongs to.

    That regulation states the same five duties four times, once for ครู, once
    for each kind of administrator, and once for ศึกษานิเทศก์. Quoting one
    profession's rule for another was the single commonest fault the assessors
    found, so the profession is named in the citation rather than left to be
    inferred from a number.
    """
    if rec.get("sysid") != ILLUSTRATES_THE_DUTIES:
        return ""
    chapters = rec.get("chapters") or []
    head = chapters[0] if chapters else ""
    _, _, who = head.partition("ของวิชาชีพ")
    return f" หมวดของ{who.strip()}" if who.strip() else ""


@dataclass
class Fault:
    """Something wrong with a draft answer, and what to do about it.

    `note` goes to the writer in the repair turn, so it names the rule and the
    mistake rather than describing a category. `blocks` says whether the answer
    is withheld when the repair fails: structural mistakes block, because they
    are facts about the corpus; judgements about meaning do not, because they
    can be wrong and a wrong refusal costs more than a wrong side-citation.
    """
    note: str
    blocks: bool
    kind: str = ""
    gap: object = None
    # whether this fault is allowed to spend a model call. False means it is
    # recorded for the log and the API and nothing else.
    acts: bool = True
    # what the refusal names. The note is a sentence written for the model to
    # act on; dropping it into a refusal template produced "ระบบร่างคำตอบโดย
    # อ้างถึง คำตอบอ้าง ข้อบังคับฯ 2556 ไม่ได้ระบุ ... ซึ่งไม่มีอยู่ในคลังข้อมูล
    # ซึ่งไม่มีอยู่ในคลังข้อมูล", which is what a teacher actually received.
    subject: str = ""

    async def refuse(self, question: str, hits: list[Hit]) -> Answer:
        if self.gap is not None:
            return Answer(text=await phrase_refusal(question, self.gap),
                          hits=hits, in_scope=False, error=self.kind)
        template = FABRICATED if self.kind == "unsupported citations" else MISCITED
        named = self.subject or self.note
        return Answer(text=template.format(laws=named, sections=named),
                      hits=hits, in_scope=False, error=self.kind)


def inspect(text: str, hits: list[Hit]) -> list[Fault]:
    """Everything wrong with a draft, in one pass, so the repair turn sees it all.

    Reporting one fault at a time made the writer fix that one and break another,
    which is most of what the regression column of the acceptance runs was.
    """
    evidence = [h.rec["text"] for h in hits]
    faults: list[Fault] = []

    # the answer may drift into law the corpus does not hold without ever naming
    # it as a citation -- civil-service discipline explained out of the ethics
    # regulations is the case this was written for. It cites nothing wrong;
    # there is simply nothing behind what it says.
    strayed = find_gap_in_answer(text, evidence)
    if strayed:
        faults.append(Fault(
            f"คำตอบพูดถึง{strayed.topic} ซึ่งอยู่ใน{strayed.code} ไม่ได้อยู่ในคลังนี้",
            blocks=True, kind="answer beyond corpus", gap=strayed,
            subject=strayed.topic))

    # the model may answer from its own memory. Whether the instrument exists is
    # asked of the whole corpus -- a real regulation cited from memory can still
    # be checked, and refusing it as fabricated was costing correct answers.
    for law in unsupported_laws(text, _support_index().all_citations, evidence):
        faults.append(Fault(f"คำตอบอ้าง {law} ซึ่งไม่มีอยู่ในคลังข้อมูล",
                            blocks=True, kind="unsupported citations",
                            subject=law))

    # an answer can cite the right regulation and the wrong rule inside it, which
    # reads as correct and sends the reader to text that does not say what they
    # were told it says. Checked against the corpus rather than the retrieved
    # set: ข้อ 99 of a regulation with 24 rules does not exist either way.
    for problem in impossible_citations(text, _support_index()):
        faults.append(Fault(problem, blocks=True, kind="unsupported sections",
                            subject=problem))

    # the number is real, the instrument beside it is not the one that has it
    for problem in misattributed_citations(text, _support_index()):
        faults.append(Fault(problem, blocks=False, kind="misattributed"))

    # พึง against ต้อง is two words compared against the text that contains
    # them. It is the only part of the lexical pass that earned a call: over
    # rounds seven and eight it is the one true catch that turned into a
    # corrected answer.
    for problem in modal_mismatches(text, _support_index()):
        faults.append(Fault(problem, blocks=False, kind="modal mismatch"))

    # The overlap check is measured at 39% of answers with 68% of those wrong,
    # and it has two harms on record. It is recorded and not acted on: the log
    # is how its window gets fixed, and settings.claim_check_blocks is the
    # switch that would let it decide anything, still off.
    for problem in unsupported_claims(text, _support_index()):
        faults.append(Fault(problem, blocks=settings.claim_check_blocks,
                            kind="unsupported claims", acts=False))

    return faults


async def answer_question(question: str) -> Answer:
    question = (question or "").strip()
    if not question:
        return Answer(text="พิมพ์คำถามเกี่ยวกับกฎหมายมาได้เลยครับ", in_scope=False)

    # greetings and "what can you do" are not legal questions; without this they
    # score just under the gate and get answered with a legal disclaimer
    canned = smalltalk_route(question)
    if canned:
        log.info("SMALLTALK | %r", question[:60])
        return Answer(text=canned, in_scope=False)

    # layer 1: the codes this corpus is missing. Checked before retrieval, because
    # retrieval will happily return a plausible-looking but wrong act for these.
    gap = find_gap(question)
    if gap:
        log.info("REFUSED gap=%s | %r", gap.topic, question[:80])
        return Answer(text=await phrase_refusal(question, gap), in_scope=False)

    # retrieval is CPU-bound: encoding the query plus scoring 27k BM25 documents
    # takes long enough to stall every other request if run on the event loop
    result = await asyncio.to_thread(get_retriever().search, question)
    hits = result.hits
    # layer 2: nothing in the corpus is close enough to the question
    if not result.in_scope:
        log.info("REFUSED low-score dense=%.4f bm25=%.1f | %r",
                 result.max_dense, result.max_bm25, question[:80])
        text = await compose_refusal(
            question,
            topic="เรื่องที่อยู่นอกจรรยาบรรณวิชาชีพทางการศึกษา",
            code="กฎหมายฉบับอื่นที่ไม่ได้อยู่ในคลังนี้",
            where=("ลองถามใหม่ให้ตรงกับจรรยาบรรณวิชาชีพทางการศึกษา เช่น "
                   "จรรยาบรรณห้าด้าน พฤติกรรมที่พึงประสงค์และไม่พึงประสงค์ "
                   "โทษทางจรรยาบรรณ การร้องเรียน การสอบสวน หรือการอุทธรณ์ "
                   "หรือดูตัวบทเองที่ ksp.or.th/laws"),
            fallback=OUT_OF_SCOPE)
        return Answer(text=text, hits=hits, in_scope=False)

    log.info("ANSWERING dense=%.4f top=%s | %r",
             result.max_dense, hits[0].citation if hits else "-", question[:80])

    # Everything downstream reads this list, not the raw ranking: the guards
    # have to judge the answer against exactly what the model was shown, or
    # citing a rule that was added as a chapter sibling looks like an invention.
    corpus = get_retriever().corpus
    hits = order_for_reading(with_amendments(
        with_chapter_siblings(hits, corpus, question), corpus))
    user_prompt = (f"คำถามของประชาชน\n{question}\n\n"
                   f"ตัวบทที่ค้นได้\n{build_context(hits)}")
    try:
        text = await complete(SYSTEM_PROMPT, user_prompt)
    except LLMUnavailable as exc:
        # retrieval still worked, so hand back the sections rather than nothing
        listing = "\n\n".join(f"• {h.citation}\n{h.rec['text'][:400]}" for h in hits[:3])
        return Answer(
            text=("ระบบสรุปคำตอบไม่พร้อมใช้งานขณะนี้ "
                  f"แต่พบตัวบทที่เกี่ยวข้องดังนี้\n\n{listing}"),
            citations=[h.citation for h in hits],
            hits=hits, error=str(exc))

    if looks_degenerate(text):
        log.warning("DEGENERATE answer | %r", question[:80])
        listing = "\n\n".join(f"• {h.citation}\n{h.rec['text'][:400]}" for h in hits[:3])
        return Answer(
            text=("ระบบสรุปคำตอบผิดพลาดครั้งนี้ "
                  f"แต่พบตัวบทที่เกี่ยวข้องดังนี้\n\n{listing}"),
            citations=[h.citation for h in hits],
            hits=hits, error="degenerate answer")

    text, typed = resolve_citations(text, hits)
    if typed:
        log.info("TYPED NUMBERS %s | %r", typed[:3], question[:70])

    # Which of ต้อง and พึง a rule uses is a fact about the corpus, so it is
    # corrected here rather than asked for in the repair turn -- which was told
    # about it every round and shipped the wrong word anyway.
    text, modals = correct_modals(text, _support_index())
    if modals:
        log.info("MODALS FIXED %s | %r", modals[:2], question[:70])

    faults = inspect(text, hits)
    # Recorded, not acted on. The number has already been kept or removed by
    # the substitution, so there is nothing left for a rewrite to fix -- and
    # counting these as faults diluted the test that decides whether a rewrite
    # is an improvement: 19 of the 33 faults on rejected repairs were these.
    for number in dict.fromkeys(typed):
        faults.append(Fault(
            f"คำตอบพิมพ์ “{number}” เอง ให้ใช้เลขในวงเล็บเหลี่ยมของตัวบทแทน",
            blocks=False, kind="typed citation", acts=False))
    found = [f.note for f in faults]
    repair = "not attempted"
    if any(f.acts for f in faults):
        repair = "rejected"
        log.info("REPAIRING %s | %r", [f.note for f in faults][:3], question[:70])
        try:
            second = await complete(SYSTEM_PROMPT, user_prompt + REPAIR.format(
                problems="\n".join("- " + f.note for f in faults)))
        except LLMUnavailable:
            second = ""
        if second and not looks_degenerate(second):
            # the rewrite goes through the same substitution as the first draft.
            # It did not, and accepted repairs shipped with their pointers
            # unresolved -- "…ต่อจิตใจและอารมณ์ 2(ข)(๓)" reached a reader as a
            # rule number, in an answer the system had recorded as repaired.
            second, second_typed = resolve_citations(second, hits)
            left = inspect(second, hits)
            left += [Fault(note, blocks=False, kind="typed citation", acts=False)
                     for note in second_typed]
            # A repair has to earn its shorter fault list. Deleting the flagged
            # citation shortens it too, and round seven caught three answers
            # doing exactly that -- a provision cited correctly the round before,
            # replaced by a hedge. So the second draft must keep every rule the
            # first one cited, on top of having fewer faults.
            # The second draft must keep the citations nobody complained
            # about. Demanding an identical set made pointer repairs impossible
            # -- fixing a wrong pointer means pointing somewhere else, which
            # changes the set -- and 24 of 27 repairs were rejected for it.
            # Requiring only that nothing be lost is what let the answers get
            # padded two rounds ago, so the flagged citations, and only those,
            # may move.
            flagged = {n.translate(THAI_TO_ARABIC)
                       for f in faults for n in NUMBER_IN_NOTE.findall(f.note)}
            before = cited_rules(text, _support_index())
            after = cited_rules(second, _support_index())
            kept = (before - flagged) <= after
            acting = sum(f.acts for f in faults)
            if sum(f.acts for f in left) < acting and kept:
                log.info("REPAIRED %d -> %d | %r", acting,
                         sum(f.acts for f in left), question[:60])
                text, faults, repair = second, left, "accepted"
        blocking = next((f for f in faults if f.blocks), None)
        if blocking:
            log.warning("BLOCKED %s | %r", blocking.note, question[:80])
            answer = await blocking.refuse(question, hits)
            answer.faults, answer.repair = found, repair
            return answer

    return Answer(text=tidy_for_chat(text), faults=found, repair=repair,
                  citations=[h.citation for h in hits], hits=hits)
