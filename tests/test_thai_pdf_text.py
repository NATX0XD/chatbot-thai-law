# -*- coding: utf-8 -*-
"""The character tables and the quality gates in ingest/thai_pdf_text.py.

Every case here is a string, not a PDF. The tables are the part that can be
wrong in a way nothing downstream notices -- a missed tone mark leaves text that
still reads as Thai and still indexes, it just stops matching the query that
should have found it -- so they are pinned character by character against the
words they were read off in the source documents.
"""
import pytest

from ingest.thai_pdf_text import (
    LEGACY_EXTRA,
    MUST_CONTAIN,
    PUA_MAP,
    check,
    compose_sara_am,
    from_legacy,
    looks_legacy,
    normalize_pua,
    thai_ratio,
    tone_ratio,
)


# --- the PUA table ------------------------------------------------------------

# left column is what AngsanaUPC puts in the text layer, right is the word meant
PUA_WORDS = [
    (0xF701, "ปกป" + chr(0xF701) + "ด", "ปกปิด"),
    (0xF706, "ปกป" + chr(0xF706) + "อง", "ปกป้อง"),
    (0xF70A, "ผู" + chr(0xF70B) + "ร" + chr(0xF70A) + "วม", "ผู้ร่วม"),
    (0xF70B, "หน" + chr(0xF70B) + "า", "หน้า"),
    (0xF70E, "ประสงค" + chr(0xF70E), "ประสงค์"),
    (0xF710, "ป" + chr(0xF710) + "ญญา", "ปัญญา"),
    (0xF712, "เป" + chr(0xF712) + "น", "เป็น"),
]


@pytest.mark.parametrize("slot,broken,want", PUA_WORDS)
def test_pua_slot_matches_the_word_it_was_read_from(slot, broken, want):
    assert normalize_pua(broken) == want


def test_pua_table_covers_the_whole_shifted_range():
    """A slot we have not seen yet must still convert, not survive into the corpus."""
    for code in range(0xF700, 0xF71B):
        assert code in PUA_MAP, f"U+{code:04X} ไม่มีในตาราง"


def test_pua_table_only_maps_to_thai_marks():
    for code, char in PUA_MAP.items():
        assert "฀" <= char <= "๿", f"U+{code:04X} -> {char!r} ไม่ใช่อักษรไทย"


def test_normalize_pua_leaves_ordinary_thai_alone():
    assert normalize_pua("จรรยาบรรณของวิชาชีพ") == "จรรยาบรรณของวิชาชีพ"


# --- the legacy table ---------------------------------------------------------

# left column is what the 2546 Act's text layer gives, right is the real word
LEGACY_WORDS = [
    ("\xc0\u03c0\xe2\u201c", "หน้า"),
    ("\u2021\u2248\xe0\xa1", "เล่ม"),
    ("\xa1\u201c\xb5\u221a\u201c", "มาตรา"),
    ("\xa2\xe2\xd5\u222b\u2014\xdf\xa7\u2014\u222b", "ข้อบังคับ"),
    ("\xab\u2018\u2122\u201c\u2122\u2019\xe6", "วิชาชีพ"),
    ("\xa7\xff\u221a\xff\xa0\xbf\u201c", "คุรุสภา"),
    ("\xae\u221a\u221a\xac\u201c\u222b\u221a\u221a\u2265", "จรรยาบรรณ"),
]


@pytest.mark.parametrize("broken,want", LEGACY_WORDS)
def test_legacy_words_come_back_whole(broken, want):
    assert from_legacy(broken) == want


def test_legacy_recovers_the_quoted_definitions():
    """มาตรา 4 defines every term in quotes, and the quotes sit in custom slots."""
    assert from_legacy("\xe7\xb0\u221a\u2013\u2211\u221a\xab\xdf\xe9") == "“กระทรวง”"


def test_legacy_does_not_normalise_away_the_bytes_it_needs():
    """NFKC turns ™ into "TM" and NBSP into a space; ™ is ช and NBSP is ส."""
    assert from_legacy("™") == "ช"
    assert from_legacy("\xa0") == "ส"
    assert from_legacy("µ") == "ต"
    assert from_legacy("…") == "ษ"


def test_legacy_extra_covers_the_shifted_marks():
    for byte in (0x88, 0x89, 0x8A, 0x8B, 0x8C):
        assert LEGACY_EXTRA[byte] in "่้๊๋์"


def test_looks_legacy_separates_the_two_kinds_of_text_layer():
    assert looks_legacy("Àπâ“ " * 200)
    assert not looks_legacy("จรรยาบรรณของวิชาชีพ " * 200)
    # a short Latin run is a page number or a URL, not a whole document
    assert not looks_legacy("Page 12 of 30")


# --- the quality gates --------------------------------------------------------

GOOD = (
    "ข้อบังคับคุรุสภา ว่าด้วยจรรยาบรรณของวิชาชีพ พ.ศ. ๒๕๕๖ "
    "ผู้ประกอบวิชาชีพทางการศึกษา ต้องมีวินัยในตนเอง พัฒนาตนเองด้านวิชาชีพ "
    "บุคลิกภาพ และวิสัยทัศน์ ให้ทันต่อการพัฒนาทางวิทยาการ เศรษฐกิจ สังคม "
    "และการเมืองอยู่เสมอ"
)


def test_clean_text_passes_every_gate():
    assert check(GOOD) == []


def test_text_that_lost_its_tone_marks_is_caught():
    """This is the failure the other four gates cannot see."""
    stripped = GOOD.translate({ord(c): None for c in "่้๊๋็์"})
    problems = check(stripped)
    assert any("วรรณยุกต์" in p for p in problems)


def test_leftover_pua_is_caught():
    problems = check(GOOD + chr(0xF70B))
    assert any("PUA" in p for p in problems)


def test_sara_am_written_as_two_glyphs_is_joined():
    """Every one of these PDFs writes ำ as ํ followed by า, 648 times in all."""
    assert compose_sara_am("ดํา" + "เนิน") == "ดำเนิน"
    assert compose_sara_am("สม่ําเสมอ") == "สม่ำเสมอ"
    assert compose_sara_am("คําวินิจฉัย") == "คำวินิจฉัย"


def test_sara_am_left_undone_is_caught():
    """pythainlp splits ดําเนิน into two words, so BM25 stops matching."""
    problems = check(GOOD + " การดําเนินการ")
    assert any("ำ" in p for p in problems)


def test_control_characters_are_caught():
    problems = check(GOOD + "\x02\x03")
    assert any("ควบคุม" in p for p in problems)


def test_latin_heavy_text_is_caught():
    problems = check(GOOD + " Lorem ipsum dolor sit amet " * 40)
    assert any("อักษรไทย" in p for p in problems)


def test_text_without_any_keyword_is_caught():
    plain = "ผู้ประกอบการต้องมีวินัยในตนเอง พัฒนาตนเองให้ทันต่อการเปลี่ยนแปลงของสังคม"
    assert not any(word in plain for word in MUST_CONTAIN)
    problems = check(plain)
    assert any("คำหลัก" in p for p in problems)


def test_check_reports_every_problem_not_just_the_first():
    problems = check("Lorem ipsum \x02" + chr(0xF70B))
    assert len(problems) >= 3


def test_ratios_on_empty_text_do_not_divide_by_zero():
    assert thai_ratio("") == 0.0
    assert tone_ratio("") == 0.0
