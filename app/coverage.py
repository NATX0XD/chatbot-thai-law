# -*- coding: utf-8 -*-
"""Deterministic detection of questions this corpus cannot answer.

Similarity scores cannot catch these. A question whose governing text is missing
still retrieves a real, on-topic section -- to the retriever that looks exactly
like a successful search, and the model then writes a confident answer out of a
regulation that does not contain the rule. Only a rule that knows what is absent
can stop it.

This corpus is narrow on purpose: ten documents of the Teachers Council, 324
rules in all, about the professional ethics of educators. Everything else in Thai
law is absent. That inverts the job of this module. It used to list the few gaps
in a corpus of 733 acts; it now has to hold a line around a small island, and the
dangerous questions are the ones standing just offshore:

    ข้าราชการครูทำผิดวินัยร้ายแรงมีโทษอะไร   cosine 0.655, well above the gate
    ขอใบอนุญาตประกอบวิชาชีพครูใช้เอกสารอะไร   the Council, the wrong regulation
    โรงเรียนหักเงินเดือนครูได้ไหม            about a teacher, not about ethics

All three are about teachers, all three retrieve plausible text, and none of
them can be answered from what is here. Professional discipline (จรรยาบรรณ) and
civil-service discipline (วินัย) in particular are two separate bodies of rules
with two separate procedures and two separate sets of penalties, and confusing
them is the single most likely way this bot could mislead a teacher.

So each rule below names the law that does govern the question, and says where
to go. A refusal that explains which instrument the answer lives in is worth
more than a refusal that just says no.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


KSP = ("แนะนำให้ติดต่อคุรุสภา ksp.or.th หรือสายด่วน 02 280 6366 "
       "หรือดูตัวบทฉบับเต็มที่ ksp.or.th/laws")
LAWYER = ("แนะนำให้ดูตัวบทที่ krisdika.go.th หรือปรึกษาทนายความ "
          "หรือติดต่อสภาทนายความ สายด่วน 1167 สำหรับคำปรึกษาเบื้องต้นฟรี")
REVENUE = ("แนะนำให้ดูที่กรมสรรพากร rd.go.th หรือสายด่วน 1161 "
           "ซึ่งมีเครื่องคำนวณภาษีและคู่มือการยื่นแบบให้ด้วย")
LABOUR = ("แนะนำให้ติดต่อกรมสวัสดิการและคุ้มครองแรงงาน labour.go.th "
          "หรือสายด่วน 1506 กด 3")
OBEC = ("แนะนำให้ปรึกษาต้นสังกัดหรือสำนักงานเขตพื้นที่การศึกษา "
        "หรือดูตัวบทที่ krisdika.go.th")


# Vocabulary that only a question about this corpus uses. It decides whether a
# softer rule below applies: "ผิดจรรยาบรรณแล้วติดคุกไหม" is a fair question about
# what the Council can and cannot do, and refusing it as a criminal-law question
# because it contains the word คุก would be wrong. "ลักทรัพย์ติดคุกกี่ปี", with
# no ethics word anywhere, is a criminal-law question and has to be refused.
ETHICS = re.compile(
    "จรรยาบรรณ|คุรุสภา|แบบแผนพฤติกรรม|ประพฤติผิด|มาตรฐานวิชาชีพ"
    "|วิชาชีพทางการศึกษา|พักใช้ใบอนุญาต|เพิกถอนใบอนุญาต|ตักเตือน|ภาคทัณฑ์"
    "|อุทธรณ์คำวินิจฉัย|คณะกรรมการมาตรฐานวิชาชีพ"
)


@dataclass(frozen=True)
class Gap:
    topic: str
    code: str
    pattern: re.Pattern
    # a refusal is more useful when it says where to go instead
    where: str = LAWYER
    # A hard rule fires even when the question is worded in ethics vocabulary,
    # because the two bodies of law overlap in wording and differ in substance --
    # civil-service discipline is the case this exists for. A soft rule defers to
    # the ethics vocabulary, so that a question about what the Council may do is
    # not mistaken for a question about the criminal code.
    hard: bool = True

    def message(self) -> str:
        return (
            f"คำถามนี้อยู่ในเรื่อง{self.topic} ซึ่งกำกับโดย{self.code}\n\n"
            f"คลังข้อมูลของระบบมีเฉพาะจรรยาบรรณวิชาชีพทางการศึกษาตามข้อบังคับคุรุสภา "
            f"ยังไม่มี{self.code} ผมจึงตอบไม่ได้ และจะไม่เดาให้ครับ\n\n"
            f"{self.where}"
        )


def _p(*words: str) -> re.Pattern:
    # case-insensitive so that a user who types a law's name in Latin letters
    # gets the same informative refusal as one who types it in Thai
    return re.compile("|".join(words), re.I)


# Ordered. The first match wins, so the rules that separate this corpus from its
# nearest neighbours come before the ones that rule out unrelated law entirely.
GAPS: tuple[Gap, ...] = (
    # The closest neighbour and the most dangerous. A teacher who breaks the
    # rules can face two proceedings at once -- one under the Council's ethics
    # regulations, which this corpus holds, and one under the civil-service
    # discipline law, which it does not. The penalties differ: the Council can
    # suspend or revoke a licence, an employer can dismiss. Answering a วินัย
    # question out of จรรยาบรรณ text would tell a teacher the wrong thing about
    # their job.
    Gap("วินัยข้าราชการครู ซึ่งเป็นคนละเรื่องกับจรรยาบรรณวิชาชีพ",
        "พระราชบัญญัติระเบียบข้าราชการครูและบุคลากรทางการศึกษา พ.ศ. 2547",
        _p("ผิดวินัย", "วินัยร้ายแรง", "วินัยไม่ร้ายแรง", "โทษทางวินัย",
           "วินัยข้าราชการ", "ทางวินัย", "ก\\.ค\\.ศ", "กคศ",
           "ปลดออก", "ไล่ออก", "ให้ออกจากราชการ", "ตัดเงินเดือน", "ลดขั้นเงินเดือน"),
        where=OBEC),
    # Also the Council, also ksp.or.th, also a regulation -- just not one of the
    # ten that were ingested. Being right about the agency makes this easier to
    # answer wrongly, not harder.
    Gap("การขอและต่ออายุใบอนุญาตประกอบวิชาชีพ",
        "ข้อบังคับคุรุสภาว่าด้วยใบอนุญาตประกอบวิชาชีพ ซึ่งไม่ได้อยู่ในคลังนี้",
        _p("ขอใบอนุญาต", "ขอรับใบอนุญาต", "ต่อใบอนุญาต", "ต่ออายุใบอนุญาต",
           "ขึ้นทะเบียนใบอนุญาต", "ใบอนุญาตหมดอายุ", "ตั๋วครู",
           "ค่าธรรมเนียม", "สมัครสอบ", "ทดสอบสมรรถนะ", "คุณสมบัติผู้ขอ"),
        where=KSP),
    Gap("การจ้างงาน ค่าจ้าง และสวัสดิการ",
        "พระราชบัญญัติคุ้มครองแรงงาน พ.ศ. 2541",
        _p("ค่าชดเชย", "เลิกจ้าง", "สัญญาจ้าง", "อัตราจ้าง", "ลูกจ้าง", "นายจ้าง",
           "หักเงินเดือน", "ค่าจ้าง", "ค่าล่วงเวลา", "โอที", "ลาคลอด", "วันลา",
           "ประกันสังคม", "ผู้ประกันตน"),
        where=LABOUR),
    Gap("ภาษี", "ประมวลรัษฎากร",
        _p("ภาษี", "vat", "แวต", "ลดหย่อน", "ยื่นแบบ", "ภ\\.ง\\.ด"),
        where=REVENUE),
    Gap("ความผิดอาญาและโทษทางอาญา", "ประมวลกฎหมายอาญา",
        _p("ลักทรัพย์", "ฉ้อโกง", "ยักยอก", "หมิ่นประมาท", "ทำร้ายร่างกาย",
           "จำคุก", "ติดคุก", "ปรับกี่บาท", "แจ้งความ", "ประกันตัว", "คดีอาญา"),
        hard=False),
    Gap("ครอบครัว มรดก สัญญา และหนี้", "ประมวลกฎหมายแพ่งและพาณิชย์",
        _p("หย่า", "สมรส", "มรดก", "พินัยกรรม", "สัญญาเช่า", "กู้ยืม", "ค้ำประกัน",
           "ทวงหนี้", "ดอกเบี้ย"), hard=False),
    Gap("วิธีพิจารณาความและการบังคับคดี",
        "ประมวลกฎหมายวิธีพิจารณาความแพ่งและความอาญา",
        _p("บังคับคดี", "ยึดทรัพย์", "อายัดเงินเดือน", "ฟ้องศาล", "ขึ้นศาล",
           "พนักงานสอบสวน", "อัยการ", "รอลงอาญา"), hard=False),
    # Named instruments that are not in the corpus at all. A question that names
    # a law by name is the one the model is most tempted to answer from memory.
    Gap("กฎหมายฉบับที่คลังนี้ไม่มี", "ตัวบทฉบับนั้น",
        _p(r"พ\.?ร\.?บ\.?คอมพิวเตอร์", "พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์",
           r"พ\.?ร\.?บ\.?คุ้มครองข้อมูล", "pdpa", "ประมวลกฎหมายที่ดิน",
           "พระราชบัญญัติการศึกษาแห่งชาติ", r"พ\.?ร\.?บ\.?การศึกษาแห่งชาติ")),
    # Not a legal question at all. These score low and the cosine gate would
    # usually catch them, but a request phrased in school vocabulary sits close
    # enough to the corpus to clear it.
    Gap("การจัดการเรียนการสอน ซึ่งไม่ใช่คำถามกฎหมาย",
        "หลักสูตรและแนวปฏิบัติของต้นสังกัด",
        _p("แผนการสอน", "แผนการจัดการเรียนรู้", "ใบงาน", "ข้อสอบ", "สื่อการสอน",
           "เขียนวิจัยในชั้นเรียน", "วิทยฐานะ", "ว\\s*ฐ", "เลื่อนวิทยฐานะ"),
        where=OBEC),
)


def find_gap(question: str) -> Gap | None:
    """Return the first known gap this question falls into, if any."""
    ethics = bool(ETHICS.search(question))
    for gap in GAPS:
        if not gap.hard and ethics:
            continue
        if gap.pattern.search(question):
            return gap
    return None


# Subject matter that exists only in law this corpus does not hold. Matching the
# *question* is not enough: a question can be phrased entirely in ethics words
# and still be answered with civil-service content, because the model knows the
# topic and the retrieved sections look close enough to write from. This reads
# the finished answer instead.
BEYOND_CORPUS = (
    (re.compile("ระเบียบข้าราชการครู|วินัยข้าราชการ|ก\\.ค\\.ศ|ปลดออก|ไล่ออกจากราชการ"),
     "วินัยข้าราชการครู", "พระราชบัญญัติระเบียบข้าราชการครูและบุคลากรทางการศึกษา", OBEC),
    # The citation form only. ข้อ 7 ของข้อบังคับฯ 2568 really does say that an
    # investigating subcommittee is a public official "ตามประมวลกฎหมายอาญา", so
    # naming the code in passing is quoting the corpus, not leaving it. Naming a
    # section of it is not.
    (re.compile(r"ประมวลกฎหมาย(?:อาญา|แพ่ง[ก-๙]*|วิธีพิจารณา[ก-๙]*)\s*(?:มาตรา|ม\.)\s*[๐-๙0-9]"),
     "ประมวลกฎหมาย", "ประมวลกฎหมายฉบับนั้น", LAWYER),
    (re.compile("คุ้มครองแรงงาน|ประกันสังคม"),
     "กฎหมายแรงงานและประกันสังคม", "พระราชบัญญัติคุ้มครองแรงงานและกฎหมายประกันสังคม",
     LABOUR),
    (re.compile("ประมวลรัษฎากร|ภาษีเงินได้"),
     "ภาษี", "ประมวลรัษฎากร", REVENUE),
)


def answer_beyond_corpus(answer: str) -> Gap | None:
    """A gap the *answer* wandered into, even though the question did not name it."""
    for pattern, topic, code, where in BEYOND_CORPUS:
        if pattern.search(answer):
            return Gap(topic, code, pattern, where)
    return None
