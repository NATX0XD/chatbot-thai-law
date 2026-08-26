# -*- coding: utf-8 -*-
"""The router must be greedy about greetings and shy about anything else: a canned
reply sent to a real legal question is worse than a slightly clumsy greeting."""
import pytest

from app.smalltalk import CAPABILITIES, EXAMPLES, GREETING, THANKS, route


@pytest.mark.parametrize("message,expected", [
    ("สวัสดี", GREETING),
    ("สวัสดีครับ", GREETING),
    ("หวัดดีจ้า", GREETING),
    ("hi", GREETING),
    ("Hello!", GREETING),
    ("ขอบคุณครับ", THANKS),
    ("thanks", THANKS),
    ("คุณทำอะไรได้บ้าง", CAPABILITIES),
    ("บอทนี้ใช้ยังไง", CAPABILITIES),
    ("help", CAPABILITIES),
    ("เมนู", CAPABILITIES),
    ("?", CAPABILITIES),
    # exactly what the rich menu cells send on a tap
    ("ถามกฎหมาย", CAPABILITIES),
    ("ตัวอย่างคำถาม", EXAMPLES),
])
def test_conversational_input_gets_a_canned_reply(message, expected):
    assert route(message) == expected


@pytest.mark.parametrize("message", [
    "โดนไล่ออก ได้เงินไหม",
    "มรดกแบ่งยังไง",
    "เจ้าหนี้ทวงหนี้ตี 1 ผิดไหม",
    # a polite opener in front of a real question must not swallow the question
    "สวัสดีครับ อยากถามเรื่องเลิกจ้าง",
    "ขอบคุณสำหรับข้อมูลเรื่องค่าชดเชย",
    # the menu labels are only canned replies when they are the whole message
    "ถามกฎหมายแรงงานหน่อย ลาป่วยได้กี่วัน",
    "ขอตัวอย่างคำถามเรื่องทวงหนี้",
])
def test_real_questions_reach_the_pipeline(message):
    assert route(message) is None


def test_menu_cells_say_different_things():
    """Two cells that answer identically are two cells pretending to be one."""
    assert route("ถามกฎหมาย") != route("ตัวอย่างคำถาม")


def test_capability_text_states_what_is_missing():
    """Users must learn the limits from the bot itself, not by getting it wrong."""
    for topic in ("มรดก", "เช่าบ้าน", "หมิ่นประมาท"):
        assert topic in CAPABILITIES
