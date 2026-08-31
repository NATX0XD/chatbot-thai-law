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
           "ฝากขัง", "หมายจับ", "หมายค้น", "พนักงานสอบสวน", "ชั้นสอบสวน",
           "สั่งฟ้อง", "สั่งไม่ฟ้อง", "อัยการ", "ยื่นฟ้องคดีอาญา")),
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
    Gap("ประกันสังคม", "พระราชบัญญัติประกันสังคม พ.ศ. 2533",
        _p("ประกันสังคม", "ผู้ประกันตน", "มาตรา 33", "มาตรา 39", "มาตรา 40",
           "เงินชราภาพ", "เงินว่างงาน", "สปส")),
)


def find_gap(question: str) -> Gap | None:
    """Return the first known gap this question falls into, if any."""
    for gap in GAPS:
        if gap.pattern.search(question):
            return gap
    return None
