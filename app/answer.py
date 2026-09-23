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
  5. unsupported_sections -- the answer cites a rule number that is not in the
     evidence, or attaches the wrong unit word to it. A wrong name is visible to
     the reader; "ตามข้อ 23" when the rule is ข้อ 13 is not.

None of them spends an LLM call except the last three, which read what the model
already wrote. The model is never asked whether it should have answered.
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
from app.verify import unsupported_laws, unsupported_sections

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

SYSTEM_PROMPT = """คุณคือผู้ช่วยให้ข้อมูลเรื่องจรรยาบรรณวิชาชีพทางการศึกษา สำหรับครูและผู้ปกครอง ตอบผ่านแอปแชท LINE

ขอบเขต
คลังข้อมูลมีเฉพาะข้อบังคับคุรุสภาและพระราชบัญญัติสภาครูและบุคลากรทางการศึกษา พ.ศ. 2546
ไม่มีกฎหมายแรงงาน อาญา แพ่ง ภาษี และไม่มีวินัยข้าราชการครูตาม พ.ร.บ.ระเบียบข้าราชการครูฯ
จรรยาบรรณวิชาชีพกับวินัยข้าราชการเป็นคนละเรื่องกัน ห้ามตอบปนกัน

เนื้อหา
1. ตอบจากตัวบทที่ให้มาเท่านั้น ห้ามใช้ความรู้อื่น
2. ทุกข้อความที่เป็นสาระ ต้องอ้างที่มาในวงเล็บ โดยคัดลอกชื่อที่กำกับหน้าตัวบทแต่ละชิ้นมาทั้งบรรทัด
   เช่น (ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 7) หรือ (พ.ร.บ.สภาครูและบุคลากรทางการศึกษา 2546 มาตรา 54)
   ห้ามย่อชื่อเอง ห้ามสลับชื่อข้ามฉบับ และห้ามเปลี่ยนคำว่า "ข้อ" เป็น "มาตรา" หรือกลับกัน
   ข้อบังคับคุรุสภาใช้คำว่า "ข้อ" พระราชบัญญัติใช้คำว่า "มาตรา" ข้อบังคับไม่มีมาตรา
3. ห้ามแต่งเลขข้อหรือเลขมาตรา ถ้าไม่แน่ใจเลขข้อ ให้อธิบายโดยไม่ใส่เลข
4. ถ้าตัวบทไหนมีคำว่า (ยกเลิกแล้ว) กำกับอยู่ ห้ามอ้างเป็นกฎที่ใช้อยู่
   ให้ใช้ฉบับที่ไม่ได้ถูกยกเลิก และบอกผู้ใช้ได้ว่าฉบับเก่าถูกยกเลิกไปแล้ว
5. ถ้าตัวบทไม่พอจะตอบ บอกตรง ๆ ว่าตัวบทไม่ได้เขียนเรื่องนี้ไว้ ห้ามเดา
   โดยเฉพาะคำถามที่ถามหาตัวเลข เช่น จำนวนชั่วโมงอบรม ถ้าตัวบทไม่ได้กำหนดไว้ ให้บอกว่าไม่ได้กำหนด
6. ถ้าถูกขอให้ช่วยหลบเลี่ยงการถูกร้องเรียนหรือการสอบสวน ให้ปฏิเสธ
   แล้วอธิบายกระบวนการและสิทธิชี้แจงตามตัวบทแทน
7. อธิบายด้วยภาษาที่คนทั่วไปเข้าใจ ห้ามคัดลอกตัวบทมาทั้งดุ้น
8. ถ้ามีตัวเลขสำคัญ เช่น จำนวนวัน จำนวนคน ให้ระบุเป็นเลขอารบิก

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


def build_context(hits: list[Hit]) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        blocks.append(f"[{i}] {h.citation}\n{h.rec['text']}")
    return "\n\n".join(blocks)


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

    # the answer may drift into law the corpus does not hold without ever naming
    # it as a citation -- social security explained out of labour law is the case
    # this was written for. Checked before the citation guard because a leak of
    # this kind cites nothing wrong; there is simply nothing behind what it says.
    strayed = find_gap_in_answer(text)
    if strayed:
        log.warning("REFUSED answer-side gap=%s | %r", strayed.topic, question[:80])
        return Answer(text=await phrase_refusal(question, strayed), hits=hits,
                      in_scope=False, error="answer beyond corpus")

    citations = [h.citation for h in hits]
    # last line of defence: the model may ignore the context and answer from its
    # own memory. If it names a law we never supplied, the answer is fabricated.
    invented = unsupported_laws(text, citations)
    if invented:
        log.warning("HALLUCINATION blocked %s | %r", invented, question[:80])
        return Answer(text=FABRICATED.format(laws=", ".join(invented[:2])),
                      hits=hits, in_scope=False, error="unsupported citations")

    # the number matters as much as the name. An answer can cite the right
    # regulation and the wrong rule inside it, which reads as correct and sends
    # the reader to text that does not say what they were told it says.
    miscited = unsupported_sections(text, citations, [h.rec["text"] for h in hits])
    if miscited:
        log.warning("MISCITED %s | %r", miscited, question[:80])
        return Answer(text=MISCITED.format(sections=", ".join(miscited[:3])),
                      hits=hits, in_scope=False, error="unsupported sections")

    return Answer(text=tidy_for_chat(text), citations=citations, hits=hits)
