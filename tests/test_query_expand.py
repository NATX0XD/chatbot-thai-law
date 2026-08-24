# -*- coding: utf-8 -*-
"""The glossary is the highest-leverage and most fragile part of retrieval, so it
gets tested on both sides: it must fire on plain speech, and it must stay quiet
when the user already speaks statute."""
import pytest

from app.query_expand import expand


@pytest.mark.parametrize("question,expected_term", [
    ("โดนไล่ออก ได้เงินไหม", "การเลิกจ้าง"),
    ("เจ้านายให้ออกกะทันหัน", "ค่าชดเชย"),
    ("ลาพักร้อนกี่วัน", "วันหยุดพักผ่อนประจำปี"),
    ("ท้องอยู่ ลาได้กี่วัน", "ลาเพื่อคลอดบุตร"),
    ("เจ้าหนี้โทรทวงตอนดึก", "การทวงถามหนี้"),
    ("คนทวงหนี้ไปบอกที่ทำงาน", "เปิดเผยความเป็นหนี้แก่ผู้อื่น"),
    ("ทำโอทีได้เงินเท่าไหร่", "ค่าล่วงเวลา"),
    ("นายจ้างหักเงินเดือนได้ไหม", "การหักค่าจ้าง"),
    ("ซื้อของออนไลน์ของไม่ตรงปก", "ผู้บริโภค"),
    ("ขอลบข้อมูลส่วนตัวได้ไหม", "สิทธิขอให้ลบข้อมูลส่วนบุคคล"),
    ("เมาแล้วขับโทษอะไร", "ขับรถในขณะเมาสุรา"),
    ("เจ็บจากงาน ใครจ่าย", "เงินทดแทน"),
])
def test_colloquial_gets_legal_vocabulary(question, expected_term):
    query, added = expand(question)
    assert expected_term in " ".join(added), f"{question!r} -> {added}"
    assert query.startswith(question), "the user's own words must stay first"


@pytest.mark.parametrize("question", [
    "สูตรทำต้มยำกุ้ง",
    "พรุ่งนี้ฝนตกไหม",
])
def test_unrelated_questions_are_untouched(question):
    query, added = expand(question)
    assert added == []
    assert query == question


def test_statutory_phrasing_is_not_padded_with_duplicates():
    """Someone who already wrote "ค่าชดเชย" should not have it appended again."""
    query, added = expand("เลิกจ้างแล้วได้ค่าชดเชยเท่าไหร่")
    assert "ค่าชดเชย" not in added
    assert query.count("ค่าชดเชย") == 1


def test_expansion_is_additive_never_substitutive():
    original = "โดนไล่ออก ได้เงินไหม"
    query, added = expand(original)
    assert original in query, "the original wording must survive for BM25"
    assert len(query) > len(original)
