# -*- coding: utf-8 -*-
"""Group etiquette and chat formatting.

Both were found from real LINE usage: the bot printed the prompt's bracket
skeleton into the chat, and it had no notion of a group at all -- it would have
answered every message posted and sent the reply to the wrong conversation.
"""
import pytest

from app.answer import tidy_for_chat
from app.line_bot import GROUP_TRIGGER, chat_target, strip_mention


# ----------------------------------------------------------------- formatting

def test_bracket_skeleton_is_removed():
    """Typhoon copied [คำตอบสั้น 1-3 ประโยค] from the old prompt verbatim."""
    out = tidy_for_chat("[คำตอบสั้น] ลูกจ้างต้องบอกล่วงหน้า")
    assert "[" not in out and "]" not in out
    assert "คำตอบสั้น ลูกจ้างต้องบอกล่วงหน้า" == out


def test_markdown_is_stripped_because_line_shows_it_raw():
    out = tidy_for_chat("ต้อง**บอกล่วงหน้า** ตาม `ม.17`\n\n## หัวข้อ")
    assert "*" not in out and "`" not in out and "#" not in out
    assert "บอกล่วงหน้า" in out


def test_label_prefixes_are_dropped():
    out = tidy_for_chat("คำตอบ: ได้ครับ\n\nคำอธิบาย: ตาม ม.17")
    assert not out.startswith("คำตอบ:")
    assert "คำอธิบาย:" not in out


def test_citations_in_round_brackets_survive():
    """Only the square-bracket skeleton goes; real citations must stay."""
    out = tidy_for_chat("ได้ครับ (พ.ร.บ.คุ้มครองแรงงาน 2541 ม.17)")
    assert "(พ.ร.บ.คุ้มครองแรงงาน 2541 ม.17)" in out


def test_excess_blank_lines_are_collapsed():
    assert tidy_for_chat("ก\n\n\n\n\nข") == "ก\n\nข"


# ----------------------------------------------------------------- groups

def test_reply_goes_to_the_group_not_the_asker():
    """Answering to userId would deliver a group question to a private chat."""
    assert chat_target({"type": "group", "groupId": "G1", "userId": "U9"}) == "G1"
    assert chat_target({"type": "room", "roomId": "R1", "userId": "U9"}) == "R1"
    assert chat_target({"type": "user", "userId": "U9"}) == "U9"


@pytest.mark.parametrize("text,should_trigger", [
    ("กฎหมาย ลาออกต้องบอกกี่วัน", True),
    ("กฎหมาย: ค่าชดเชยเท่าไหร่", True),
    ("บอท ช่วยดูหน่อย", True),
    ("วันนี้กินอะไรดี", False),
    ("เรื่องกฎหมายนี่ยากจัง", False),   # keyword must lead, not appear anywhere
])
def test_group_keyword_only_fires_at_the_start(text, should_trigger):
    assert bool(GROUP_TRIGGER.match(text)) is should_trigger


def test_mention_is_detected_and_removed():
    text = "@บอท ลาออกกี่วัน"
    message = {"mention": {"mentionees": [
        {"index": 0, "length": len("@บอท"), "isSelf": True}]}}
    cleaned, mentioned = strip_mention(message, text)
    assert mentioned
    assert cleaned == "ลาออกกี่วัน"


def test_message_without_a_mention_is_left_alone():
    cleaned, mentioned = strip_mention({}, "ลาออกกี่วัน")
    assert not mentioned
    assert cleaned == "ลาออกกี่วัน"


def test_mention_of_someone_else_does_not_count():
    message = {"mention": {"mentionees": [
        {"index": 0, "length": 5, "isSelf": False, "userId": "Uother"}]}}
    _, mentioned = strip_mention(message, "@somebody ช่วยด้วย")
    assert not mentioned
