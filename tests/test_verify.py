# -*- coding: utf-8 -*-
"""Fabricated-citation detection.

The first case is verbatim from production: the bot told a user their friend had
committed ลักทรัพย์ under ประมวลกฎหมายอาญา มาตรา 335 and cited an act that does
not exist, while the only context it had been given was an unrelated payments act.
"""
import pytest

from app.verify import unsupported_laws

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


def test_no_context_means_no_verdict():
    """With nothing retrieved there is nothing to check against; other guards
    handle that path, and flagging everything here would fire on refusal text."""
    assert unsupported_laws(FAKE_ANSWER, []) == []
