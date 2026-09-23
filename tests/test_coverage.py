# -*- coding: utf-8 -*-
"""The line around the corpus: what is inside it, and what only looks inside.

This corpus is ten documents about the professional ethics of educators. The
questions worth testing are not the obviously unrelated ones -- the cosine gate
handles those -- but the ones that are about teachers, retrieve real regulations,
and still cannot be answered from what is here.

No index is needed for any of this: coverage is decided from the question text
alone, before retrieval runs, which is the whole point of it.
"""
import pytest

from app.coverage import ETHICS, GAPS, answer_beyond_corpus, find_gap

# (question, a word that has to appear in the refusal so the user learns where
#  the answer actually lives)
NEAR_MISSES = [
    # civil-service discipline: a separate body of rules, a separate procedure,
    # and separate penalties. Confusing the two is the worst thing this bot
    # could do to a teacher.
    ("ข้าราชการครูทำผิดวินัยร้ายแรงมีโทษอะไรบ้าง", "ระเบียบข้าราชการครู"),
    ("ครูโดนตัดเงินเดือนเพราะมาสาย ถูกต้องไหม", "ระเบียบข้าราชการครู"),
    ("ผิดวินัยกับผิดจรรยาบรรณต่างกันยังไง", "ระเบียบข้าราชการครู"),
    # the Council's own regulations, just not these ten
    ("ขอใบอนุญาตประกอบวิชาชีพครูต้องใช้เอกสารอะไรบ้าง", "ใบอนุญาต"),
    ("ต่ออายุใบอนุญาตครูค่าธรรมเนียมเท่าไหร่", "ใบอนุญาต"),
    # about a teacher, about employment
    ("โรงเรียนหักเงินเดือนครูอัตราจ้างได้ไหม", "คุ้มครองแรงงาน"),
    ("ครูอัตราจ้างถูกเลิกจ้างได้ค่าชดเชยไหม", "คุ้มครองแรงงาน"),
    # a teacher's job, not a legal question
    ("ช่วยเขียนแผนการสอนคณิตศาสตร์ ป.4 ให้หน่อย", "หลักสูตร"),
    ("อยากเลื่อนวิทยฐานะต้องทำอะไรบ้าง", "หลักสูตร"),
    # named instruments that are not here
    ("พ.ร.บ.คอมพิวเตอร์ มาตรา 14 เขียนว่าอะไร", "ตัวบท"),
    ("พระราชบัญญัติการศึกษาแห่งชาติ พ.ศ. 2542 ว่าอย่างไร", "ตัวบท"),
    # ordinary law, no teacher in sight
    ("เงินเดือน 40,000 ต้องเสียภาษีเท่าไหร่", "รัษฎากร"),
    ("ลักทรัพย์มีโทษจำคุกกี่ปี", "อาญา"),
    ("อยากหย่ากับสามี ต้องมีเหตุอะไรบ้าง", "แพ่ง"),
]


@pytest.mark.parametrize("question,expected", NEAR_MISSES)
def test_out_of_scope_questions_are_refused_with_a_pointer(question, expected):
    gap = find_gap(question)
    assert gap is not None, f"{question!r} ไม่มีกฎดัก"
    message = gap.message()
    assert expected in message, f"{question!r} -> {message[:120]}"
    assert gap.where, "a refusal has to say where to go instead"


IN_SCOPE = [
    "จรรยาบรรณวิชาชีพครูมีกี่ด้าน อะไรบ้าง",
    "จรรยาบรรณต่อตนเองของครูคืออะไร",
    "ครูด่านักเรียนหน้าชั้นผิดจรรยาบรรณไหม",
    "ครูนินทาเพื่อนครูผิดข้อไหน",
    "ครูมีชู้ผิดจรรยาบรรณไหม",
    "ครูผิดจรรยาบรรณมีโทษอะไรบ้าง",
    "พักใช้ใบอนุญาตได้นานสุดกี่ปี",
    "อยากร้องเรียนครูที่ประพฤติผิดจรรยาบรรณ ต้องทำยังไง",
    "อุทธรณ์คำวินิจฉัยได้ภายในกี่วัน",
    "คณะอนุกรรมการสอบสวนมีกี่คน",
    "ครูเรียกเงินจากผู้ปกครองผิดข้อไหน",
    "เศรษฐกิจพอเพียงเกี่ยวอะไรกับจรรยาบรรณครู",
]


@pytest.mark.parametrize("question", IN_SCOPE)
def test_the_rules_do_not_reach_into_the_corpus(question):
    gap = find_gap(question)
    assert gap is None, f"{question!r} ถูกบล็อกเป็น {gap.topic}"


def test_ethics_vocabulary_rescues_a_question_a_soft_rule_would_have_taken():
    """"ติดคุก" is criminal vocabulary and this is a fair question about it.

    Asking whether a breach of professional ethics can put someone in prison is
    asking what the Council can and cannot do. The answer is in มาตรา 54, which
    lists five outcomes and no imprisonment among them.
    """
    assert ETHICS.search("ผิดจรรยาบรรณแล้วติดคุกไหม")
    assert find_gap("ผิดจรรยาบรรณแล้วติดคุกไหม") is None
    # the same words without the ethics half are a criminal-law question
    assert find_gap("ลักทรัพย์แล้วติดคุกไหม") is not None


def test_a_hard_rule_fires_even_when_the_question_sounds_like_ethics():
    """Discipline and ethics overlap in wording and differ in substance."""
    question = "ครูประพฤติผิดจรรยาบรรณแล้วจะโดนวินัยร้ายแรงด้วยไหม"
    assert ETHICS.search(question), "the question does read as an ethics question"
    gap = find_gap(question)
    assert gap is not None and "ระเบียบข้าราชการครู" in gap.code


def test_every_rule_names_the_law_and_a_place_to_go():
    for gap in GAPS:
        assert gap.topic and gap.code
        assert gap.where, f"{gap.topic} ไม่ได้บอกว่าให้ไปถามที่ไหน"
        assert "จรรยาบรรณวิชาชีพทางการศึกษา" in gap.message(), \
            "the refusal has to state what this system does cover"


# --- the answer side --------------------------------------------------------


def test_an_answer_that_strays_into_civil_service_discipline_is_caught():
    strayed = answer_beyond_corpus(
        "ครูอาจถูกลงโทษตามระเบียบข้าราชการครู ตั้งแต่ตัดเงินเดือนจนถึงปลดออก")
    assert strayed is not None
    assert "ข้าราชการครู" in strayed.code


def test_quoting_the_corpus_own_reference_to_the_criminal_code_is_not_straying():
    """ข้อ 7 ของข้อบังคับฯ 2568 really does say this.

    "ให้อนุกรรมการสอบสวนเป็นเจ้าพนักงานตามประมวลกฎหมายอาญา" -- naming the code in
    passing is reading the corpus. Naming a section of it is not.
    """
    quoting = "ให้อนุกรรมการสอบสวนเป็นเจ้าพนักงานตามประมวลกฎหมายอาญา"
    assert answer_beyond_corpus(quoting) is None

    citing = "มีความผิดฐานลักทรัพย์ตามประมวลกฎหมายอาญา มาตรา 335"
    assert answer_beyond_corpus(citing) is not None


def test_repeating_a_phrase_from_the_evidence_is_not_straying():
    """ข้อ 71 ของข้อบังคับฯ 2568 lists an employer's order to dismiss as a ground
    for suspending a licence, so an answer repeating it is reading the corpus.

    Without this the rule meant to catch drift into the civil-service discipline
    act rejected the one question หมวด 13 exists to answer, and told the asker
    the corpus does not cover it -- worse than a technical refusal, because they
    believe it.
    """
    evidence = ["หน่วยงานต้นสังกัดมีคำสั่ง ปลดออกหรือไล่ออกหรือเลิกจ้าง"]
    quoting = "คุรุสภาพักใช้ใบอนุญาตได้เมื่อต้นสังกัดมีคำสั่งปลดออกหรือไล่ออก"
    assert answer_beyond_corpus(quoting, evidence) is None
    # the same words with no such section retrieved are still a leak
    assert answer_beyond_corpus(quoting, []) is not None


def test_an_ordinary_ethics_answer_passes_the_answer_side_check():
    ordinary = ("ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ "
                "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 7)")
    assert answer_beyond_corpus(ordinary) is None
