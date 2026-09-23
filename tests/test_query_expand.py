# -*- coding: utf-8 -*-
"""The glossary is the highest-leverage and most fragile part of retrieval, so it
gets tested on both sides: it must fire on plain speech, and it must stay quiet
when the user already speaks the language of the regulations."""
import pytest

from app.query_expand import expand


@pytest.mark.parametrize("question,expected_term", [
    # the words the regulations use, which nobody types
    ("ครูด่านักเรียนหน้าชั้น", "ดูหมิ่นเหยียดหยามศิษย์"),
    ("ครูตีเด็กได้ไหม", "ลงโทษศิษย์อย่างไม่เหมาะสม"),
    ("ครูเอาเรื่องของเด็กไปเล่าให้คนอื่นฟัง", "เปิดเผยความลับของศิษย์"),
    ("ครูนินทาเพื่อนครู", "วิพากษ์วิจารณ์ผู้ร่วมประกอบวิชาชีพ"),
    ("ครูกลั่นแกล้งเพื่อนร่วมงาน", "กลั่นแกล้งผู้ร่วมประกอบวิชาชีพ"),
    ("ครูโยนความผิดให้คนอื่น", "ปฏิเสธความรับผิดชอบ"),
    ("ครูลอกผลงานคนอื่น", "คัดลอกหรือนำผลงานของผู้อื่นมาเป็นของตน"),
    ("ครูเล่นการพนัน", "อบายมุข"),
    ("ครูรับเงินจากผู้ปกครอง", "เรียกรับหรือยอมรับผลประโยชน์จากการใช้ตำแหน่งหน้าที่โดยมิชอบ"),
    ("ครูต้องอบรมพัฒนาตัวเองไหม", "วินัยในตนเอง"),
    # the five outcomes nobody names, behind the one word everybody uses
    ("ครูผิดจรรยาบรรณมีโทษอะไรบ้าง", "เพิกถอนใบอนุญาต"),
    ("อยากร้องเรียนครู ทำยังไง", "การกล่าวหา"),
    ("ไม่ยอมรับคำวินิจฉัย ทำอะไรได้", "อุทธรณ์คำวินิจฉัย"),
    ("ผอ.โรงเรียนมีจรรยาบรรณอะไรบ้าง", "ผู้บริหารสถานศึกษา"),
])
def test_colloquial_gets_the_regulations_vocabulary(question, expected_term):
    query, added = expand(question)
    assert expected_term in " ".join(added), f"{question!r} -> {added}"
    assert query.startswith(question), "the user's own words must stay first"


def test_all_five_duties_are_named_when_the_question_asks_for_the_list():
    _query, added = expand("จรรยาบรรณวิชาชีพครูมีกี่ด้าน")
    for duty in ("ต่อตนเอง", "ต่อวิชาชีพ", "ต่อผู้รับบริการ",
                 "ต่อผู้ร่วมประกอบวิชาชีพ", "ต่อสังคม"):
        assert any(duty in term for term in added), f"{duty} missing from {added}"


def test_punishing_a_pupil_is_not_the_councils_own_penalties():
    """Both entries contain the word โทษ and they answer different questions.

    "ลงโทษนักเรียน" is about แบบแผนพฤติกรรม; the five outcomes in มาตรา 54 are
    about what happens to the teacher. Before the trigger was narrowed, asking
    whether a teacher may cane a pupil retrieved the penalty schedule instead.
    """
    _query, added = expand("ครูลงโทษนักเรียนด้วยการตีได้ไหม")
    assert "ลงโทษศิษย์อย่างไม่เหมาะสม" in added
    assert "เพิกถอนใบอนุญาต" not in added


@pytest.mark.parametrize("question", [
    "สูตรทำต้มยำกุ้ง",
    "พรุ่งนี้ฝนตกไหม",
])
def test_unrelated_questions_are_untouched(question):
    query, added = expand(question)
    assert added == []
    assert query == question


def test_statutory_phrasing_is_not_padded_with_duplicates():
    """Someone who already wrote "ศิษย์" should not have it appended again."""
    query, added = expand("ครูดูหมิ่นศิษย์ผิดจรรยาบรรณไหม")
    assert "ศิษย์" not in added
    assert query.count("ศิษย์") == 1


def test_expansion_is_additive_never_substitutive():
    original = "ครูด่านักเรียนหน้าชั้น"
    query, added = expand(original)
    assert original in query, "the original wording must survive for BM25"
    assert len(query) > len(original)
