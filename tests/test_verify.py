# -*- coding: utf-8 -*-
"""Fabricated-citation detection.

The first case is verbatim from production: the bot told a user their friend had
committed ลักทรัพย์ under ประมวลกฎหมายอาญา มาตรา 335 and cited an act that does
not exist, while the only context it had been given was an unrelated payments act.
"""
import pytest

from app.verify import invented_dates, unsupported_laws

# the model pointing back at the act it was handed, rather than naming a new one
SELF_REFERENCES = [
    "ตาม พ.ร.บ.นี้ มาตรา 20 ผู้บริโภคมีสิทธิได้รับความปลอดภัย",
    "ตามพระราชบัญญัตินี้ ผู้บริโภคมีสิทธิได้รับข่าวสารที่ถูกต้อง",
    "ตาม พ.ร.บ.ดังกล่าว ผู้บริโภคร้องเรียนได้",
    "ตามประมวลกฎหมายนี้ ผู้ใดลักทรัพย์ต้องระวางโทษ",
]

FAKE_ANSWER = (
    "เพื่อนของคุณมีความผิดฐานลักทรัพย์ตามประมวลกฎหมายอาญา มาตรา 335 "
    "ซึ่งมีโทษจำคุกไม่เกิน 5 ปี หรือปรับไม่เกิน 100,000 บาท "
    "(พ.ร.บ. ว่าด้วยการกระทำผิดเกี่ยวกับทรัพย์สิน พ.ศ. 2560)"
)
PAYMENTS_CONTEXT = ["พระราชบัญญัติระบบการชำระเงิน พ.ศ. 2560 มาตรา 48"]


def test_the_production_hallucination_is_caught():
    flagged = unsupported_laws(FAKE_ANSWER, PAYMENTS_CONTEXT)
    assert any("ประมวลกฎหมายอาญา" in f for f in flagged)
    assert any("ทรัพย์สิน" in f for f in flagged)


@pytest.mark.parametrize("answer,context", [
    # short form of a supplied act
    ("ได้ค่าชดเชย 180 วัน (พ.ร.บ.คุ้มครองแรงงาน 2541 ม.118)",
     ["พระราชบัญญัติคุ้มครองแรงงาน พ.ศ. 2541 มาตรา 118"]),
    # full form of a supplied act
    ("ตามพระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 มาตรา 19 ต้องขอความยินยอม",
     ["พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 มาตรา 19"]),
    # cross-referencing another section of the same supplied act
    ("ดู ม.122 ประกอบ ม.118 (พ.ร.บ.คุ้มครองแรงงาน 2541)",
     ["พระราชบัญญัติคุ้มครองแรงงาน พ.ศ. 2541 มาตรา 118"]),
    # a refusal names no law at all
    ("ข้อมูลที่มีไม่พอจะตอบคำถามนี้ครับ",
     ["พระราชบัญญัติคุ้มครองแรงงาน พ.ศ. 2541 มาตรา 5"]),
])
def test_legitimate_answers_are_not_flagged(answer, context):
    assert unsupported_laws(answer, context) == []


def test_a_fake_law_hiding_behind_a_real_one_is_caught():
    """The trailing-token window used to swallow the conjunction and the next
    title with it, so a fabricated code rode along inside a valid citation."""
    answer = "ตาม พ.ร.บ.การทวงถามหนี้ 2558 ม.9 และประมวลกฎหมายแพ่งและพาณิชย์ ม.420"
    flagged = unsupported_laws(answer, ["พระราชบัญญัติการทวงถามหนี้ พ.ศ. 2558 มาตรา 9"])
    assert flagged == ["ประมวลกฎหมายแพ่งและพาณิชย์"]


def test_prose_after_a_rule_number_is_not_part_of_the_title():
    """The answer to "อบายมุขอยู่ในข้อใด" was refused for naming a law that does
    not exist. The law it named was ข้อ 7 ของข้อบังคับฯ 2556, which does: the
    span ran past the rule number and took the verb phrase with it, so what got
    compared against the corpus was "กล่าวถึงการมีวินัยในตนเองและพัฒนาตนเอง"."""
    answer = ("ข้อบังคับคุรุสภา 2556 ข้อ 7 กล่าวถึงการมีวินัยในตนเองและพัฒนาตนเอง")
    context = ["ข้อบังคับคุรุสภา ว่าด้วยจรรยาบรรณของวิชาชีพ พ.ศ. 2556 ข้อ 7"]
    assert unsupported_laws(answer, context) == []


def test_no_context_means_no_verdict():
    """With nothing retrieved there is nothing to check against; other guards
    handle that path, and flagging everything here would fire on refusal text."""
    assert unsupported_laws(FAKE_ANSWER, []) == []


@pytest.mark.parametrize("answer", SELF_REFERENCES)
def test_a_reference_back_to_the_supplied_act_is_not_a_fabrication(answer):
    """Found from a real reply the bot threw away.

    A user asked สิทธิผู้บริโภค คืออะไร. The answer cited พ.ร.บ.คุ้มครองผู้บริโภค
    correctly and then wrote "ตาม พ.ร.บ.นี้" -- which the pattern read as the name
    of a second, unknown statute, so the whole answer was blocked as fabricated.
    "นี้" and "ดังกล่าว" point back at the evidence, they do not name new law.
    """
    cited = ["พระราชบัญญัติคุ้มครองผู้บริโภค พ.ศ. 2522 มาตรา 4"]
    assert unsupported_laws(answer, cited) == []


@pytest.mark.parametrize("answer", [
    "มรดกตกทอดแก่ทายาทโดยธรรม (พ.ร.บ.แพ่งและพาณิชย์ ม.1603)",
    "ตาม ป.พ.พ. ม.1603 มรดกตกทอดแก่ทายาท",
])
def test_a_code_called_by_the_wrong_kind_of_name_is_not_a_fabrication(answer):
    """Also from the running bot. Asked about มรดก, the model answered correctly
    from ประมวลกฎหมายแพ่งและพาณิชย์ but wrote 'พ.ร.บ.แพ่งและพาณิชย์'. Using the
    wrong word for what kind of statute it is misnames a real law; it does not
    invent one, and the answer it appeared in was right."""
    assert unsupported_laws(answer, ["ประมวลกฎหมายแพ่งและพาณิชย์ มาตรา 1603"]) == []


@pytest.mark.parametrize("answer", [
    "การเข้าถึงระบบโดยมิชอบมีโทษจำคุก (พ.ร.บ.คอมพิวเตอร์ 2550 ม.5)",
    "ตาม พ.ร.บ.คอมพิวเตอร์ พ.ศ. 2550 มาตรา 14 ต้องระวางโทษจำคุกไม่เกินห้าปี",
])
def test_an_act_known_by_a_short_name_is_not_a_fabrication(answer):
    """พ.ร.บ.คอมพิวเตอร์ is registered as ...ว่าด้วยการกระทำความผิดเกี่ยวกับ
    คอมพิวเตอร์, so a shared-prefix test compared 'คอมพิวเตอร์' against
    'ว่าด้วยการกระ' and blocked every answer that cited it. Adversarial testing
    found the whole act unusable while it sat in the index."""
    supplied = ["พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ พ.ศ. 2550 มาตรา 14"]
    assert unsupported_laws(answer, supplied) == []


def test_matching_by_containment_still_blocks_an_unrelated_code():
    """Containment is looser than a prefix, so the case that motivated the guard
    has to be re-checked: a code named in the answer but never supplied."""
    supplied = ["พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ พ.ศ. 2550 มาตรา 14"]
    assert unsupported_laws("ผิดฐานลักทรัพย์ตามประมวลกฎหมายอาญา ม.335", supplied) != []


@pytest.mark.parametrize("text,ok", [
    ("เรื่องนี้อยู่ในพระราชบัญญัติประกันสังคม พ.ศ. 2533 ซึ่งคลังของผมไม่มีครับ", True),
    ("ปกติได้เงินทดแทนเดือนละ 5,000 บาท แต่ผมไม่มีตัวบทครับ", False),
    ("ดูได้ที่มาตรา 33 ของกฎหมายฉบับนั้นครับ", False),
    ("ได้ประมาณร้อยละ 50 ของค่าจ้างครับ", False),
    ("เรื่องนี้อยู่ในพระราชบัญญัติประกันสังคม และประมวลกฎหมายแพ่งและพาณิชย์ครับ", False),
])
def test_a_refusal_may_name_its_missing_act_but_nothing_else(text, ok):
    """A refusal is still a message about law. It may say which act it lacks --
    that is the useful part -- but a section number, a figure, or a second act
    means it started answering, and the fixed text is used instead."""
    from app.refuse import _unsafe
    assert (_unsafe(text, "พระราชบัญญัติประกันสังคม พ.ศ. 2533") is None) is ok


@pytest.mark.parametrize("words,value", [
    ("สามสิบ", 30), ("หนึ่งแสน", 100_000), ("ยี่สิบเอ็ด", 21),
    ("หนึ่งร้อยยี่สิบ", 120), ("สองแสนห้าหมื่น", 250_000), ("สิบเอ็ด", 11),
])
def test_thai_number_words_parse(words, value):
    """Statutes spell figures out -- หนึ่งแสนบาท -- while answers use digits, so
    the two can only be compared once the statute side is expanded."""
    from app.numbers import words_to_int
    assert words_to_int(words) == value


def test_a_figure_absent_from_the_sections_is_reported():
    """The production failure: a real act, a real section, and a benefit figure
    that appears in no Thai law."""
    from app.numbers import unsupported_figures
    sections = ["ลูกจ้างซึ่งทำงานติดต่อกันครบหนึ่งร้อยยี่สิบวัน ให้จ่ายไม่น้อยกว่า"
                "ค่าจ้างอัตราสุดท้ายสามสิบวัน"]
    assert unsupported_figures("ได้ค่าชดเชย 30 วัน เมื่อทำงานครบ 120 วัน", sections) == []
    assert unsupported_figures("ได้เงินทดแทนเดือนละ 1,000 บาท", sections) == ["1,000 บาท"]


def test_a_date_no_rule_states_takes_its_line_with_it():
    """Asked which regulation is in force, the answer said "มีผลใช้บังคับตั้งแต่
    วันที่ 1 เมษายน พ.ศ. 2568". ข้อ 2 says "วันถัดจากวันประกาศในราชกิจจานุเบกษา"
    and no record carries that date. The model was given the words of the rules
    and nothing else, so there is nowhere else the date came from."""
    answer = ("ข้อบังคับคุรุสภา ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณ พ.ศ. 2568 "
              "คือฉบับที่ใช้อยู่ในปัจจุบัน\n\n"
              "ข้อบังคับฉบับนี้มีผลใช้บังคับตั้งแต่วันที่ 1 เมษายน พ.ศ. 2568 เป็นต้นไป")
    kept, dropped = invented_dates(
        answer, ["ข้อบังคับนี้ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศในราชกิจจานุเบกษา"])
    assert dropped == ["1 เมษายน 2568"]
    assert "1 เมษายน" not in kept
    assert "คือฉบับที่ใช้อยู่ในปัจจุบัน" in kept


def test_a_date_the_rules_do_state_is_kept():
    """Thai numerals in the rule, Arabic in the answer -- the same date."""
    answer = "ประกาศใช้เมื่อวันที่ 1 เมษายน พ.ศ. 2568"
    assert invented_dates(answer, ["ประกาศ ณ วันที่ ๑ เมษายน พ.ศ. ๒๕๖๘"]) == (answer, [])


def test_an_answer_that_is_nothing_but_a_bad_date_is_left_alone():
    """Dropping every line would leave the reader with an empty message, which
    is worse than a wrong date they can check against the citation beside it."""
    answer = "มีผลตั้งแต่วันที่ 1 เมษายน พ.ศ. 2568"
    assert invented_dates(answer, ["ไม่มีวันที่ในข้อนี้"]) == (answer, [])
