# -*- coding: utf-8 -*-
"""How the networking textbook is cut into passages."""
from ingest import extract_book as ex
from ingest import extract_figures as fig

LONG = ("สายคู่บิดเกลียวประกอบด้วยสายทองแดงที่หุ้มด้วยฉนวนพลาสติกแล้วนำมาบิดเกลียวกันเป็นคู่ "
        "เพื่อลดสัญญาณรบกวนจากภายนอก นิยมใช้กับเครือข่ายท้องถิ่นและระบบโทรศัพท์ตามบ้านเรือนทั่วไป "
        "เพราะมีราคาถูกและติดตั้งง่ายกว่าสายชนิดอื่น")

SOURCE = f"""# คู่มือเรียน

<!-- หน้า 2 -->

คำนำที่ไม่ใช่เนื้อหาของบทเรียนและต้องไม่ถูกอ่านเข้ามาในคลัง

<!-- หน้า 7 -->

สารบัญ

สื่อกลางส่งข้อมูล . 40

ชนิดของสื่อกลางส่งข้อมูล .41 การติดตั้งด้วย Windows 7 .. 45

สรุปท้ายบทที่ 2..

<!-- หน้า 39 -->

## บทที่ 2 ช่องทางการสื่อสาร

จุดประสงค์เชิงพฤติกรรม

1. บอกข้อดีและข้อเสียของสื่อกลางส่งข้อมูลแบบมีสายชนิดต่างๆ ได้

2. อธิบายรายละเอียดเกี่ยวกับส่วนประกอบเครือข่ายได้

<!-- หน้า 40 -->

สื่อกลางส่งข้อมูล

{LONG}

<!-- หน้า 41 -->

ชนิดของสื่อกลางส่งข้อมูล

1. สายคู่บิดเกลียว {LONG}

ฉนวนหุ้ม

สายทองแดง o‡++t

รูปที่ 2.3 สายคู่บิดเกลียว

<!-- หน้า 42 -->

ข้อดี

• เป็นสายสัญญาณที่มีราคาถูก

CONNEC »

การติดตั้งด้วย Windows 7

{LONG}

สรุปท้ายบทที่ 2

{LONG}

แบบทดสอบประเมินผลการเรียนรู้

1. สายคู่บิดเกลียวมีข้อดีอย่างไร จงอธิบายมาให้เข้าใจพอสังเขปตามที่ได้เรียนมาในบทนี้

<!-- หน้า 291 -->

บรรณานุกรม

ยืน ภู่วรวรรณ. เทคนิคการเดินสายสัญญาณเครือข่ายคอมพิวเตอร์. กรุงเทพฯ : ซีเอ็ดยูเคชั่น, 2539.
"""


def rows():
    return list(ex.records(SOURCE.split("\n")))


def text_of(found):
    return "\n".join(r["text"] for r in found)


def test_front_matter_and_contents_are_not_read():
    assert "คำนำ" not in text_of(rows())
    assert "สารบัญ" not in text_of(rows())


def test_exercises_and_bibliography_are_dropped():
    body = text_of(rows())
    assert "จงอธิบาย" not in body
    assert "ภู่วรวรรณ" not in body


def test_the_objectives_list_is_dropped():
    assert "บอกข้อดีและข้อเสีย" not in text_of(rows())


def test_headings_come_from_the_table_of_contents():
    headings = list(dict.fromkeys(r["heading"] for r in rows()))
    assert headings == ["สื่อกลางส่งข้อมูล", "ชนิดของสื่อกลางส่งข้อมูล",
                        "การติดตั้งด้วย Windows 7", "สรุปท้ายบทที่ 2"]


def test_a_heading_with_a_digit_in_it_is_not_cut_at_the_digit():
    assert "การติดตั้งด้วยWindows" in ex.read_contents(SOURCE.split("\n"))


def test_a_word_inside_an_entry_is_not_a_heading():
    contents = ex.read_contents(SOURCE.split("\n"))
    assert not ex.is_heading("ข้อมูล", contents)
    assert ex.is_heading("สื่อกลางส่งข้อมูล", contents)


def test_labels_from_inside_a_figure_are_dropped_and_its_caption_kept():
    body = text_of(rows())
    assert "ฉนวนหุ้ม" not in body
    assert "o‡++t" not in body
    assert "รูปที่ 2.3 สายคู่บิดเกลียว" in body


def test_lines_with_no_thai_are_dropped():
    assert "CONNEC" not in text_of(rows())


def test_a_bullet_stays_with_the_label_above_it():
    chunk = next(r for r in rows() if "ข้อดี" in r["text"])
    assert "• เป็นสายสัญญาณที่มีราคาถูก" in chunk["text"]
    assert "1. สายคู่บิดเกลียว" in chunk["text"]


def test_a_record_knows_its_chapter_its_pages_and_its_figures():
    chunk = next(r for r in rows() if "รูปที่ 2.3" in r["text"])
    assert chunk["chapter"] == 2
    assert chunk["chapter_title"] == "ช่องทางการสื่อสาร"
    assert (chunk["page_from"], chunk["page_to"]) == (41, 42)
    assert chunk["figures"] == ["2.3"]
    assert chunk["id"].startswith("net-2-")


def test_a_long_section_breaks_before_a_paragraph_never_before_a_bullet():
    held = [(1, LONG)] * 4 + [(1, "• " + "ก" * 30)] + [(2, LONG)] * 4
    parts = list(ex.chunks(held))
    assert len(parts) > 1
    assert all(not text.startswith("•") for _, _, text in parts)
    assert all(len(text) <= ex.MAX_CHUNK + ex.SHORT_TAIL for _, _, text in parts)


def test_a_short_tail_joins_the_chunk_before_it():
    held = [(1, LONG)] * 4 + [(2, "10. คลิกปุ่ม Close")]
    parts = list(ex.chunks(held))
    assert parts[-1][2].endswith("10. คลิกปุ่ม Close")
    assert parts[-1][1] == 2


def test_captions_are_listed_with_their_page():
    found = fig.captions(SOURCE.split("\n"))
    assert found == {"2.3": {"page": 41, "caption": "สายคู่บิดเกลียว"}}


def test_a_figure_is_what_lies_between_the_caption_and_the_text_above():
    # (text, left, top, width, height) as shares of the page
    lines = [
        ("ย่อหน้าเต็มบรรทัดของเนื้อหา", 0.10, 0.10, 0.80, 0.02),
        ("ป้ายในรูป", 0.40, 0.25, 0.10, 0.02),
        ("รูปที่ 2.3 สายคู่บิดเกลียว", 0.30, 0.50, 0.40, 0.02),
        ("ย่อหน้าถัดไปเต็มบรรทัด", 0.10, 0.60, 0.80, 0.02),
    ]
    left, top, right, bottom = fig.locate(lines, "2", "3")
    assert 0.12 <= top < 0.25, "starts under the paragraph, above the label"
    assert 0.45 < bottom <= 0.50, "stops above the caption"
    assert left < 0.11 and right > 0.89


def test_a_caption_with_no_room_above_it_gives_no_figure():
    lines = [("ย่อหน้าเต็มบรรทัดของเนื้อหา", 0.10, 0.46, 0.80, 0.02),
             ("รูปที่ 2.3 สายคู่บิดเกลียว", 0.30, 0.50, 0.40, 0.02)]
    assert fig.locate(lines, "2", "3") is None
    assert fig.locate(lines, "2", "30") is None
