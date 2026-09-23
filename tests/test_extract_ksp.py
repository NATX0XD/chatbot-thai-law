# -*- coding: utf-8 -*-
"""The parse in ingest/extract_ksp.py: headings, sections, duties, chunking.

Fixtures are short extracts typed the way the PDFs deliver them -- one visual
line per line, the gazette masthead sitting wherever a page happened to break.
That shape is the whole difficulty, so it is what the tests feed in.
"""
import pytest

from ingest.extract_ksp import (
    CATEGORIES,
    DOCS,
    MAX_CHUNK,
    body_lines,
    category_of,
    chunk,
    is_noise,
    paragraphs,
    units,
)

# ข้อบังคับฯ 2556, the document the five duties come from
ETHICS_2556 = """
                                              หน้า ๗๒
เล่ม ๑๓๐ ตอนพิเศษ ๑๓๐ ง                     ราชกิจจานุเบกษา                          ๔ ตุลาคม ๒๕๕๖
        ข้อ ๖ ผู้ประกอบวิชาชีพทางการศึกษา ต้องประพฤติตนตามจรรยาบรรณของวิชาชีพ
และแบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพ
                                                หมวด ๑
                                        จรรยาบรรณต่อตนเอง

        ข้อ ๗ ผู้ประกอบวิชาชีพทางการศึกษา ต้องมีวินัยในตนเอง พัฒนาตนเองด้านวิชาชีพ
บุคลิกภาพ และวิสัยทัศน์ ให้ทันต่อการพัฒนาทางวิทยาการ เศรษฐกิจ สังคม และการเมืองอยู่เสมอ
                                          หมวด ๒
                                    จรรยาบรรณต่อวิชาชีพ

        ข้อ ๘ ผู้ประกอบวิชาชีพทางการศึกษา ต้องรัก ศรัทธา ซื่อสัตย์สุจริต รับผิดชอบต่อวิชาชีพ
"""

# ข้อบังคับฯ 2550, where the same five duties are ส่วนที่ inside a หมวด
BEHAVIOUR_2550 = """
                                                หมวด ๑
                            แบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพครู

                                                ส่วนที่ ๑
                                         จรรยาบรรณต่อตนเอง

         ข้อ ๕ ครูต้องมีวินัยในตนเอง พัฒนาตนเองด้านวิชาชีพ โดยต้องประพฤติและละเว้น
ตามแบบแผนพฤติกรรม ดังตัวอย่างต่อไปนี้
         (ก) พฤติกรรมที่พึงประสงค์
         (๑) ประพฤติตนเหมาะสมกับสถานภาพและเป็นแบบอย่างที่ดี
         (๒) ประพฤติตนเป็นแบบอย่างที่ดีในการดำเนินชีวิตตามประเพณี
"""


def sections(text, unit="ข้อ"):
    return {number: (body, chapters) for number, body, chapters in units(text, unit)}


# --- dropping the page furniture ---------------------------------------------


def test_the_masthead_never_reaches_the_text():
    kept = "\n".join(body_lines(ETHICS_2556))
    for junk in ("ราชกิจจานุเบกษา", "หน้า ๗๒", "ตอนพิเศษ"):
        assert junk not in kept


def test_the_signature_block_is_cut_off():
    text = "ข้อ ๑ เรียกว่าข้อบังคับนี้\nประกาศ ณ วันที่ ๑๙ กันยายน พ.ศ. ๒๕๕๖\nไพฑูรย์ สินลารัตน์"
    kept = "\n".join(body_lines(text))
    assert "ไพฑูรย์" not in kept
    assert "ข้อ ๑" in kept


@pytest.mark.parametrize("line", ["๑๓ ๐ ข เ- 1 ข ๓๑๓ ๓", "า 0", "บ ๐", "=๑%=% ๓๓"])
def test_ocr_speckle_is_dropped(line):
    assert is_noise(line)


@pytest.mark.parametrize("line", [
    "ข้อ ๗ ผู้ประกอบวิชาชีพทางการศึกษา ต้องมีวินัยในตนเอง",
    "(๑) ประพฤติตนเหมาะสมกับสถานภาพ",
    "จรรยาบรรณต่อตนเอง",
])
def test_real_text_is_not_mistaken_for_speckle(line):
    assert not is_noise(line)


# --- finding the sections -----------------------------------------------------


def test_every_section_is_found_with_its_heading():
    found = sections(ETHICS_2556)
    assert set(found) == {"6", "7", "8"}
    assert found["7"][1] == ["หมวด 1 จรรยาบรรณต่อตนเอง"]
    assert found["8"][1] == ["หมวด 2 จรรยาบรรณต่อวิชาชีพ"]
    # ข้อ 6 comes before the first หมวด and belongs to none of them
    assert found["6"][1] == []


def test_a_section_keeps_the_lines_that_wrapped():
    body = sections(ETHICS_2556)["7"][0]
    assert body.startswith("ผู้ประกอบวิชาชีพทางการศึกษา ต้องมีวินัยในตนเอง")
    assert body.endswith("และการเมืองอยู่เสมอ")


def test_a_section_number_run_together_with_its_text_is_still_found():
    """The 2546 Act does this for every multiple of ten."""
    found = sections("มาตรา ๑๐คุรุสภาอาจมีรายได้ ดังนี้", unit="มาตรา")
    assert "10" in found
    assert found["10"][0].startswith("คุรุสภาอาจมีรายได้")


def test_only_the_document_own_unit_word_starts_a_section():
    """A regulation cites the Act it was issued under; that is not a section here."""
    text = "ข้อ ๑ ออกตามความใน\nมาตรา ๙ วรรคหนึ่ง แห่งพระราชบัญญัติสภาครูฯ"
    found = sections(text, unit="ข้อ")
    assert set(found) == {"1"}
    assert "มาตรา ๙" in found["1"][0]


def test_a_new_heading_ends_the_section_before_it():
    body = sections(ETHICS_2556)["6"][0]
    assert "หมวด" not in body
    assert "จรรยาบรรณต่อตนเอง" not in body


# --- the five duties ----------------------------------------------------------


def test_the_duty_comes_from_the_chapter_in_2556():
    found = sections(ETHICS_2556)
    assert category_of(found["7"][1]) == "ต่อตนเอง"
    assert category_of(found["8"][1]) == "ต่อวิชาชีพ"
    assert category_of(found["6"][1]) is None


def test_the_duty_comes_from_the_part_in_2550():
    """Here the หมวด names the practitioner and the ส่วนที่ names the duty."""
    _body, chapters = sections(BEHAVIOUR_2550)["5"]
    assert chapters == [
        "หมวด 1 แบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพครู",
        "ส่วนที่ 1 จรรยาบรรณต่อตนเอง",
    ]
    assert category_of(chapters) == "ต่อตนเอง"


def test_only_the_five_named_duties_count():
    assert category_of(["หมวด 1 บททั่วไป"]) is None
    assert category_of(["หมวด 4 บทกำหนดโทษ"]) is None
    assert category_of(["ส่วนที่ 2 คณะกรรมการคุรุสภา"]) is None


def test_the_five_duties_are_the_ones_the_brief_asked_for():
    assert CATEGORIES == (
        "ต่อตนเอง", "ต่อวิชาชีพ", "ต่อผู้รับบริการ",
        "ต่อผู้ร่วมประกอบวิชาชีพ", "ต่อสังคม",
    )


# --- laying out and splitting -------------------------------------------------


def test_listed_items_stay_apart_from_the_running_text():
    body = sections(BEHAVIOUR_2550)["5"][0]
    assert "\n\n(ก) พฤติกรรมที่พึงประสงค์" in body
    assert "\n\n(๑) ประพฤติตนเหมาะสม" in body
    # the rule itself is still one reflowed paragraph
    assert body.startswith("ครูต้องมีวินัยในตนเอง พัฒนาตนเองด้านวิชาชีพ โดยต้อง")


def test_a_short_section_is_left_whole():
    assert list(chunk("สั้นมาก")) == [("สั้นมาก", 0)]


def test_a_long_section_is_cut_on_an_item_edge():
    items = [f"({i}) ข้อความของพฤติกรรมที่ยาวพอสมควร {'ก' * 120}" for i in range(1, 25)]
    pieces = list(chunk("\n\n".join(items)))
    assert len(pieces) > 1
    for piece, _part in pieces:
        assert len(piece) <= MAX_CHUNK
        assert piece.startswith("(")


def test_chunk_parts_are_numbered_from_zero_and_lose_nothing():
    text = "\n\n".join(f"({i}) {'ก' * 200}" for i in range(1, 20))
    pieces = list(chunk(text))
    assert [part for _piece, part in pieces] == list(range(len(pieces)))
    joined = "".join(piece for piece, _part in pieces)
    assert joined.count("ก") == text.count("ก")


def test_paragraphs_collapses_the_wrap_but_keeps_the_break():
    out = paragraphs(["ครูต้องมีวินัย", "ในตนเองเสมอ", "(ก) พฤติกรรมที่พึงประสงค์"])
    assert out == "ครูต้องมีวินัย ในตนเองเสมอ\n\n(ก) พฤติกรรมที่พึงประสงค์"


# --- the document table -------------------------------------------------------


def test_every_document_is_listed_once_with_a_real_unit():
    keys = [doc.key for doc in DOCS]
    assert len(keys) == len(set(keys)) == 10
    for doc in DOCS:
        assert doc.unit in ("ข้อ", "มาตรา")
        assert doc.published[:4].isdigit() and len(doc.published) == 10
        assert doc.url.startswith("https://")


def test_only_the_act_is_numbered_by_มาตรา():
    by_unit = {doc.key for doc in DOCS if doc.unit == "มาตรา"}
    assert by_unit == {"act-2546"}
