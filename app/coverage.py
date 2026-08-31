# -*- coding: utf-8 -*-
"""Deterministic detection of questions this corpus cannot answer.

Similarity scores cannot catch these. A question whose governing text is missing
still retrieves a real, on-topic Act -- to the retriever that looks exactly like a
successful search, and the model then writes a confident answer out of a statute
that does not contain the rule. Only a rule that knows what is absent can stop it.

The set of gaps shrank when the two substantive codes were added to the corpus:
questions about tenancy, inheritance, divorce, loans, theft and defamation now
retrieve the section that governs them. What is still missing is the procedural
codes -- ป.วิ.แพ่ง and ป.วิ.อาญา -- and พ.ร.บ.ประกันสังคม, which do not appear in
any open dataset the project could find. พ.ร.บ.คอมพิวเตอร์ was in that list until
it was rebuilt from the Royal Gazette transcriptions on Wikisource; see
ingest/extract_computer_act.py.

That makes the surviving rules a line between substance and procedure. The
criminal code defines theft and its penalty; it says nothing about how to file a
report, how bail is granted, or how a judgment is enforced. Patterns therefore
target procedural vocabulary (แจ้งความ, ประกันตัว, บังคับคดี) and deliberately no
longer touch the substantive words (ลักทรัพย์, มรดก, หย่า) that used to be here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


LAWYER = ("แนะนำให้ดูตัวบทที่ krisdika.go.th หรือปรึกษาทนายความ "
          "หรือติดต่อสภาทนายความ สายด่วน 1167 สำหรับคำปรึกษาเบื้องต้นฟรี")
REVENUE = ("แนะนำให้ดูที่กรมสรรพากร rd.go.th หรือสายด่วน 1161 "
           "ซึ่งมีเครื่องคำนวณภาษีและคู่มือการยื่นแบบให้ด้วย")
SOCIAL_SECURITY = (
    "แนะนำให้ดูที่สำนักงานประกันสังคม sso.go.th หรือสายด่วน 1506\n\n"
    "ถ้าคำถามของคุณมีเรื่องกฎหมายแรงงานปนอยู่ด้วย เช่น ค่าชดเชย วันลา หรือค่าล่วงเวลา "
    "ลองถามแยกเฉพาะส่วนนั้น ผมตอบส่วนนั้นได้ครับ")


@dataclass(frozen=True)
class Gap:
    topic: str
    code: str
    pattern: re.Pattern
    # a refusal is more useful when it says where to go instead; the default is
    # the bar association, but a tax question belongs at the revenue department
    where: str = LAWYER

    def message(self) -> str:
        return (
            f"คำถามนี้อยู่ในเรื่อง{self.topic} ซึ่งกำกับโดย{self.code}\n\n"
            f"คลังข้อมูลของระบบยังไม่มี{self.code} ผมจึงตอบไม่ได้ และจะไม่เดาให้ครับ\n\n"
            f"{self.where}"
        )


def _p(*words: str) -> re.Pattern:
    # case-insensitive so that a user who types "hack" in Latin letters gets the
    # same informative refusal as one who types "แฮก". Without it the question
    # fell through to the generic "ไม่พบตัวบทที่เกี่ยวข้อง", which tells the user
    # nothing about *why*.
    return re.compile("|".join(words), re.I)


# Six groups were removed when ประมวลกฎหมายแพ่งและพาณิชย์ (1,827 มาตรา) and
# ประมวลกฎหมายอาญา (443 มาตรา) entered the corpus: tenancy, inheritance, family,
# loans and guarantees, substantive criminal offences, and tort. Those questions
# now retrieve the governing section instead of a refusal.
#
# What remains absent is the *procedural* codes and two Acts, so the rules that
# survive draw a line the corpus really has: the criminal code says what theft is
# and what it is punished with, but says nothing about how to report it, how bail
# works, or how a judgment gets enforced.
GAPS: tuple[Gap, ...] = (
    Gap("วิธีพิจารณาคดีอาญา", "ประมวลกฎหมายวิธีพิจารณาความอาญา",
        _p("แจ้งความ", "ลงบันทึกประจำวัน", "ประกันตัว", "ขอประกันตัว",
           "ปล่อยชั่วคราว", "ปล่อยตัวชั่วคราว", "วางหลักประกัน", "หลักทรัพย์ประกัน",
           "ฝากขัง", "หมายจับ", "หมายค้น", "พนักงานสอบสวน", "ชั้นสอบสวน",
           "สั่งฟ้อง", "สั่งไม่ฟ้อง", "อัยการ", "ยื่นฟ้องคดีอาญา",
           "ศาลจะตัดสิน", "รอลงอาญา", "โอกาสชนะคดี")),
    Gap("วิธีพิจารณาคดีแพ่งและการบังคับคดี", "ประมวลกฎหมายวิธีพิจารณาความแพ่ง",
        _p("บังคับคดี", "หมายบังคับคดี", "ยึดทรัพย์", "อายัดเงินเดือน",
           "อายัดทรัพย์", "ขายทอดตลาด", "เจ้าพนักงานบังคับคดี")),
    # The corpus holds nine tax Acts -- สรรพสามิต, ที่ดินและสิ่งปลูกสร้าง, ป้าย,
    # การรับมรดก and more -- but not ประมวลรัษฎากร, which is where income tax, VAT
    # and withholding actually live. That combination is the dangerous one: asked
    # "เรื่องภาษี" the retriever returned พ.ร.บ.ภาษีการรับมรดก ม.31 and answered
    # about a 1.5% surcharge, which is real law and almost certainly not the law
    # the asker meant. So the rule names the code and points at the right agency.
    Gap("ภาษีเงินได้ ภาษีมูลค่าเพิ่ม และภาษีหัก ณ ที่จ่าย", "ประมวลรัษฎากร",
        _p("ภาษีเงินได้บุคคล", "ภาษีเงินได้นิติบุคคล", "ภาษีนิติบุคคล",
           "ภาษีมูลค่าเพิ่ม", "vat", "แวต", "ภาษีหัก ณ ที่จ่าย", "หักภาษี ณ ที่จ่าย",
           "ลดหย่อนภาษี", "ยื่นภาษี", "ยื่นแบบภาษี", "ภ\\.ง\\.ด", "ภพ\\.30",
           "เสียภาษีเท่าไหร่", "เสียภาษีเท่าไร", "คำนวณภาษี", "ภาษีเงินเดือน"),
        where=REVENUE),
    # The widest of the rules, and the one adversarial testing forced open. The
    # corpus has พ.ร.บ.คุ้มครองแรงงาน, which sits close to every social-security
    # concept in embedding space, so "ถูกเลิกจ้างได้เงินทดแทนกรณีว่างงานเดือนละ
    # เท่าไหร่" retrieved confident labour-law text, cleared the gate, cited real
    # sections -- and the model filled the gap with a benefit figure that exists
    # in no Thai law. Every defence passed while the answer was invented, so the
    # vocabulary here has to cover how people describe the benefits, not just the
    # name of the fund.
    Gap("ประกันสังคม", "พระราชบัญญัติประกันสังคม พ.ศ. 2533",
        _p("ประกันสังคม", "ผู้ประกันตน", "สปส", "มาตรา 33", "มาตรา 39", "มาตรา 40",
           "เงินสมทบ", "ส่งสมทบ", "ว่างงาน", "เงินชราภาพ", "บำนาญชราภาพ",
           "สงเคราะห์บุตร", "ทุพพลภาพ", "เงินทดแทนกรณี", "กองทุนประกันสังคม"),
        where=SOCIAL_SECURITY),
    # พ.ร.บ.ว่าด้วยความผิดอันเกิดจากการใช้เช็ค พ.ศ. 2534 is not in the source
    # dataset. Without it the retriever falls back to ป.พ.พ. ลักษณะเช็ค, which is
    # civil, and the bot told a tester that a bounced cheque "ฟ้องอาญาไม่ได้" --
    # advice that could cost someone a criminal claim.
    Gap("ความผิดจากการใช้เช็ค", "พระราชบัญญัติว่าด้วยความผิดอันเกิดจากการใช้เช็ค พ.ศ. 2534",
        _p("เช็คเด้ง", "เช็คคืน", "เงินในบัญชีไม่พอ", "สั่งจ่ายเช็ค", "ธนาคารปฏิเสธการจ่ายเงิน")),
)


def find_gap(question: str) -> Gap | None:
    """Return the first known gap this question falls into, if any."""
    for gap in GAPS:
        if gap.pattern.search(question):
            return gap
    return None


# Subject matter that exists only in law this corpus does not hold. Matching the
# *question* is not enough: a question can be phrased entirely in labour-law
# words and still be answered with social-security content, because the model
# knows the topic and the retrieved sections look close enough to write from.
# Two leaks found in testing did exactly that -- one invented an unemployment
# benefit of 1,000 baht a month and attached it to พ.ร.บ.คุ้มครองแรงงาน, the
# other explained where to claim maternity money from the social security fund.
# Neither cited a law it had not been given, so app/verify.py had nothing to
# catch. This reads the finished answer instead.
BEYOND_CORPUS = (
    (re.compile("ประกันสังคม|ผู้ประกันตน|กองทุนประกันสังคม|เงินสมทบ"),
     "ประกันสังคม", "พระราชบัญญัติประกันสังคม พ.ศ. 2533", SOCIAL_SECURITY),
    (re.compile("ประมวลรัษฎากร|ภาษีเงินได้บุคคล|ภาษีเงินได้นิติบุคคล|"
                "ภาษีมูลค่าเพิ่ม|หักภาษี ณ ที่จ่าย|ภาษีหัก ณ ที่จ่าย"),
     "ภาษีตามประมวลรัษฎากร", "ประมวลรัษฎากร", REVENUE),
    (re.compile(r"ประมวลกฎหมายวิธีพิจารณา|ป\.วิ\.อาญา|ป\.วิ\.แพ่ง"),
     "วิธีพิจารณาความ", "ประมวลกฎหมายวิธีพิจารณาความ", LAWYER),
)


def answer_beyond_corpus(answer: str) -> Gap | None:
    """A gap the *answer* wandered into, even though the question did not name it."""
    for pattern, topic, code, where in BEYOND_CORPUS:
        if pattern.search(answer):
            return Gap(topic, code, pattern, where)
    return None
