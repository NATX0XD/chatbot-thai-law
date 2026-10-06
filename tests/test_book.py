# -*- coding: utf-8 -*-
"""The textbook path: what it cites, what it refuses, which pictures it shows."""
import asyncio
import os

import pytest

from app import book
from app.answer import answer_question
from app.config import settings
from app.flex import BLUE, answer_bubble
from app.smalltalk import NETWORK_CAPABILITIES, NETWORK_EXAMPLES, NETWORK_GREETING, route

needs_index = pytest.mark.skipif(
    not (os.path.exists(settings.book_path) and os.path.exists(settings.book_vectors_path)),
    reason="index not built -- run ingest.extract_book then ingest.build_book_index")


def hit(text, chapter=2, pages=(42, 44), heading="ชนิดของสื่อกลางส่งข้อมูล", figures=()):
    return book.BookHit(rec={
        "id": f"net-{chapter}-1", "chapter": chapter,
        "chapter_title": "ช่องทางการสื่อสารและส่วนประกอบของเครือข่าย",
        "heading": heading, "page_from": pages[0], "page_to": pages[1],
        "figures": list(figures), "text": text}, rrf=0.0)


CABLE = hit("สายคู่บิดเกลียว ประกอบด้วยสายทองแดงที่หุ้มด้วยฉนวน นำมาบิดเกลียวกันเป็นคู่\n"
            "รูปที่ 2.3 สายคู่บิดเกลียว\nข้อดี\n• เป็นสายสัญญาณที่มีราคาถูก\n"
            "รูปที่ 2.5 สายโคแอกเชียล\nเชื่อมโยงได้ไกล 100 เมตร ตามมาตรฐาน 802.3",
            figures=("2.3", "2.5"))
FIGURES = {
    "2.3": {"file": "fig-2-3.jpg", "page": 42, "caption": "สายคู่บิดเกลียว",
            "width": 800, "height": 300},
    "2.5": {"file": "fig-2-5.jpg", "page": 43, "caption": "สายโคแอกเชียล",
            "width": 800, "height": 300},
}


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------- citations

def test_a_citation_names_chapter_section_and_pages():
    assert CABLE.citation == ("บทที่ 2 ช่องทางการสื่อสารและส่วนประกอบของเครือข่าย — "
                              "หัวข้อ ชนิดของสื่อกลางส่งข้อมูล (หน้า 42-44)")
    assert hit("x", pages=(42, 42)).where == "บทที่ 2 หน้า 42"


def test_a_pointer_becomes_the_chapter_and_page_of_its_passage():
    text, cited = book.resolve("สายมีราคาถูก [1]", [CABLE])
    assert text == "สายมีราคาถูก (บทที่ 2 หน้า 42-44)"
    assert cited == [CABLE]


def test_a_pointer_to_a_passage_never_supplied_is_dropped():
    text, cited = book.resolve("สายมีราคาถูก [7]", [CABLE])
    assert text == "สายมีราคาถูก" and cited == []


def test_bullets_from_one_page_print_the_reference_once():
    text, _ = book.resolve("• ราคาถูก [1]\n• ใช้ง่าย [1]\n• แพร่หลาย [1]", [CABLE])
    assert text.count("(บทที่ 2 หน้า 42-44)") == 1
    assert text.endswith("• แพร่หลาย (บทที่ 2 หน้า 42-44)")


# ---------------------------------------------------------------- guards

def test_a_number_the_passages_do_not_print_is_caught():
    assert book.unsupported_numbers("เชื่อมได้ไกล 185 เมตร [1]", [CABLE]) == ["185"]
    assert book.unsupported_numbers("ตามมาตรฐาน 802.11 [1]", [CABLE]) == ["802.11"]


def test_numbers_from_the_passage_or_the_question_are_allowed():
    assert book.unsupported_numbers("ไกล 100 เมตร ตามมาตรฐาน 802.3 [1]", [CABLE]) == []
    assert book.unsupported_numbers("ไม่ได้กล่าวถึง 802.11 [1]", [CABLE],
                                    "802.11 คืออะไร") == []


def test_list_numbering_and_small_counts_are_not_figures():
    draft = "มี 2 แบบ [1]\n1. แบบแรก [1]\n12. แบบสิบสอง [1]\nขั้นตอนที่ 14 ทำต่อ [1]"
    assert book.unsupported_numbers(draft, [CABLE]) == []


def test_a_draft_with_a_made_up_number_is_rejected():
    reason = book.reject("สายคู่บิดเกลียวเชื่อมโยงได้ไกลสุด 185 เมตร [1]", [CABLE])
    assert reason and "185" in reason


def test_a_draft_that_cites_nothing_is_rejected():
    assert book.reject("สายคู่บิดเกลียวเป็นสายสัญญาณที่มีราคาถูก", [CABLE]) == "no passage cited"


def test_the_model_saying_it_has_nothing_is_a_refusal():
    assert book.reject("ไม่มีข้อมูลพอ", [CABLE]) == "model had nothing to say"


def test_a_one_line_answer_is_long_enough():
    assert book.reject("สายคู่บิดเกลียวมีราคาถูก [1]", [CABLE]) is None


def test_an_uncited_line_with_words_from_outside_the_passages_is_dropped():
    draft = "สายคู่บิดเกลียวมีราคาถูก [1]\nสายชนิดนี้กันน้ำได้ดีเยี่ยม"
    kept, dropped = book.drop_ungrounded(draft, [CABLE])
    assert kept == "สายคู่บิดเกลียวมีราคาถูก [1]"
    assert len(dropped) == 1


def test_a_heading_above_a_list_survives_its_connectives():
    draft = "ในทางกลับกัน ข้อดีของสายคู่บิดเกลียว ได้แก่\n• เป็นสายสัญญาณที่มีราคาถูก [1]"
    kept, dropped = book.drop_ungrounded(draft, [CABLE])
    assert kept == draft and dropped == []


def test_a_heading_above_a_list_may_not_bring_its_own_term_or_number():
    draft = "ข้อดีของสาย CAT6 ได้แก่\n• เป็นสายสัญญาณที่มีราคาถูก [1]"
    kept, dropped = book.drop_ungrounded(draft, [CABLE])
    assert "CAT6" not in kept and len(dropped) == 1


def test_foreign_terms_are_reported_but_those_in_the_question_are_not():
    assert book.foreign_terms("ใช้ VLAN แบ่งเครือข่าย [1]", [CABLE]) == ["VLAN"]
    assert book.foreign_terms("ใช้ VLAN [1]", [CABLE], "VLAN คืออะไร") == []


# ------------------------------------------------------------ list order

LAYERS = hit("7. ชั้นสื่อสารการประยุกต์\n4. ชั้นสื่อสารเพื่อนำส่งข้อมูล\n"
             "3. ชั้นสื่อสารควบคุมเครือข่าย\n2. ชั้นสื่อสารเชื่อมต่อข้อมูล\n"
             "1. ชั้นสื่อสารทางกายภาพ\n"
             "1. ชั้นสื่อสารทางกายภาพ (Physical Layer) มีหน้าที่เกี่ยวข้องกับคุณลักษณะทางกายภาพ",
             chapter=1, pages=(21, 22))


def test_a_list_the_book_numbers_is_put_back_in_the_books_order():
    draft = ("แบบจำลอง OSI มี 7 ชั้น [1]\n• ชั้นสื่อสารทางกายภาพ\n"
             "• ชั้นสื่อสารเชื่อมต่อข้อมูล\n• ชั้นสื่อสารเพื่อนำส่งข้อมูล\n"
             "• ชั้นสื่อสารควบคุมเครือข่าย [1]")
    text, changed = book.in_book_order(draft, [LAYERS])
    assert changed
    assert text.split("\n")[1:] == [
        "1. ชั้นสื่อสารทางกายภาพ", "2. ชั้นสื่อสารเชื่อมต่อข้อมูล",
        "3. ชั้นสื่อสารควบคุมเครือข่าย", "4. ชั้นสื่อสารเพื่อนำส่งข้อมูล [1]"]


def test_a_list_already_in_the_books_order_is_left_as_written():
    draft = ("1. ชั้นสื่อสารทางกายภาพ\n2. ชั้นสื่อสารเชื่อมต่อข้อมูล\n"
             "3. ชั้นสื่อสารควบคุมเครือข่าย [1]")
    assert book.in_book_order(draft, [LAYERS]) == (draft, False)


def test_a_list_the_book_does_not_number_is_left_alone():
    draft = "• เป็นสายสัญญาณที่มีราคาถูก\n• ง่ายต่อการนำไปใช้งาน\n• มีอุปกรณ์สนับสนุนมากมาย [1]"
    assert book.in_book_order(draft, [CABLE]) == (draft, False)


def test_an_item_the_book_numbers_two_ways_is_not_reordered():
    twice = hit("1. ชั้นสื่อสารควบคุมเครือข่าย\n3. ชั้นสื่อสารควบคุมเครือข่าย\n"
                "2. ชั้นสื่อสารเชื่อมต่อข้อมูล\n4. ชั้นสื่อสารเพื่อนำส่งข้อมูล")
    draft = ("• ชั้นสื่อสารเพื่อนำส่งข้อมูล\n• ชั้นสื่อสารควบคุมเครือข่าย\n"
             "• ชั้นสื่อสารเชื่อมต่อข้อมูล [1]")
    assert book.in_book_order(draft, [twice]) == (draft, False)


# --------------------------------------------------------------- figures

def test_the_figure_shown_is_the_one_the_question_is_about():
    shown = book.pick_figures("สายคู่บิดเกลียวคืออะไร", [CABLE], FIGURES)
    assert [f["number"] for f in shown] == ["2.3"]
    assert shown[0]["url"] == "/static/figures/fig-2-3.jpg"
    assert shown[0]["page"] == 42


def test_a_word_every_caption_shares_does_not_bring_the_wrong_figure():
    shown = book.pick_figures("สายโคแอกเชียลมีข้อดีอะไร", [CABLE], FIGURES)
    assert [f["number"] for f in shown] == ["2.5"]


def test_a_question_about_none_of_the_figures_gets_none():
    assert book.pick_figures("บลูทูธส่งสัญญาณได้ไกลกี่เมตร", [CABLE], FIGURES) == []
    assert book.pick_figures("สายคู่บิดเกลียวคืออะไร", [], FIGURES) == []


def test_a_figure_with_no_file_is_left_out():
    assert book.pick_figures("สายคู่บิดเกลียวคืออะไร", [CABLE], {}) == []


def test_a_figure_goes_to_line_as_an_image_with_a_full_address(monkeypatch):
    from app.answer import Answer
    monkeypatch.setattr(settings, "public_base_url", "https://bot.example/")
    shown = book.pick_figures("สายคู่บิดเกลียวคืออะไร", [CABLE], FIGURES)
    messages = Answer(text="คำตอบ", citations=[CABLE.citation], source="book",
                      figures=shown).for_line_messages()
    assert [m["type"] for m in messages] == ["text", "flex", "image"]
    assert messages[2]["originalContentUrl"] == "https://bot.example/static/figures/fig-2-3.jpg"
    assert "คู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น" in messages[0]["text"]


# ------------------------------------------------------------ appearance

def test_the_card_is_blue_and_splits_a_book_reference_in_two():
    bubble = answer_bubble("คำตอบ", [CABLE.citation], source="book")
    assert bubble["header"]["backgroundColor"] == BLUE
    row = bubble["body"]["contents"][3]["contents"][0]["contents"][1]["contents"]
    assert row[0]["text"] == "บทที่ 2 ช่องทางการสื่อสารและส่วนประกอบของเครือข่าย"
    assert row[1]["text"] == "หัวข้อ ชนิดของสื่อกลางส่งข้อมูล (หน้า 42-44)"
    assert "กฎหมาย" not in bubble["footer"]["contents"][0]["text"]


@pytest.mark.parametrize("message,expected", [
    ("สวัสดีครับ", NETWORK_GREETING),
    ("ทำอะไรได้บ้าง", NETWORK_CAPABILITIES),
    # exactly what the rich menu cells send on a tap
    ("ถามเรื่องเครือข่าย", NETWORK_CAPABILITIES),
    ("ตัวอย่างคำถาม", NETWORK_EXAMPLES),
])
def test_smalltalk_speaks_for_the_networking_bot(message, expected):
    assert route(message) == expected
    assert "จรรยาบรรณ" not in expected and "กฎหมาย" not in expected


def test_a_real_question_is_not_swallowed_by_smalltalk():
    assert route("เครือข่ายแลนคืออะไร") is None
    assert route("ถามเรื่องเครือข่ายไร้สายหน่อย") is None


def test_a_group_message_opening_with_the_subject_is_not_taken_as_a_call():
    from app.line_bot import GROUP_TRIGGER
    assert GROUP_TRIGGER.match("เครือข่าย สายคู่บิดเกลียวคืออะไร")
    assert not GROUP_TRIGGER.match("เครือข่ายแลนคืออะไร")


# ------------------------------------------------------------ end to end

@pytest.fixture
def model(monkeypatch):
    """Replace the model call; the reply is set per test."""
    state = {"reply": "", "calls": []}

    async def fake_complete(system, user):
        state["calls"].append({"system": system, "user": user})
        return state["reply"]

    monkeypatch.setattr(book, "complete", fake_complete)
    return state


@needs_index
def test_a_question_from_the_book_is_answered_with_its_page_and_picture(model):
    model["reply"] = "สายคู่บิดเกลียวเป็นสายสัญญาณที่มีราคาถูก [1]"
    a = run(answer_question("สายคู่บิดเกลียวคืออะไร มีข้อดีข้อเสียอย่างไร"))
    assert a.in_scope and a.source == "book"
    assert "(บทที่ 2 หน้า" in a.text
    assert a.citations and a.citations[0].startswith("บทที่ 2 ")
    assert "สายคู่บิดเกลียว" in model["calls"][0]["user"]
    assert "2.3" in [f["number"] for f in a.figures]
    for figure in a.figures:
        path = os.path.join("web", "figures", os.path.basename(figure["url"]))
        assert os.path.exists(path), f"{path} is named but not on disk"


@needs_index
def test_a_question_about_something_else_never_reaches_the_model(model):
    a = run(answer_question("สูตรทำต้มยำกุ้งใส่อะไรบ้าง"))
    assert not a.in_scope and a.source == "book"
    assert model["calls"] == []
    assert "กฎหมาย" not in a.text and "จรรยาบรรณ" not in a.text


@needs_index
def test_a_made_up_figure_turns_the_answer_into_a_refusal(model):
    model["reply"] = "สายคู่บิดเกลียวเชื่อมโยงได้ไกลสุด 18500 เมตร [1]"
    a = run(answer_question("สายคู่บิดเกลียวเชื่อมได้ไกลกี่เมตร"))
    assert not a.in_scope
    assert "18500" not in a.text
    assert "หัวข้อที่ใกล้เคียงที่สุดในหนังสือ" in a.text
    assert a.figures == []


@needs_index
def test_an_answer_with_no_pointers_is_asked_for_once_more(model, monkeypatch):
    replies = ["สายคู่บิดเกลียวเป็นสายสัญญาณที่มีราคาถูก",
               "สายคู่บิดเกลียวเป็นสายสัญญาณที่มีราคาถูก [1]"]

    async def twice(system, user):
        model["calls"].append(user)
        return replies[len(model["calls"]) - 1]

    monkeypatch.setattr(book, "complete", twice)
    a = run(answer_question("สายคู่บิดเกลียวคืออะไร มีข้อดีข้อเสียอย่างไร"))
    assert a.in_scope and len(model["calls"]) == 2
    assert "หมายเลขชิ้น" in model["calls"][1][-200:]


@needs_index
def test_a_made_up_figure_is_not_given_a_second_try(model):
    model["reply"] = "สายคู่บิดเกลียวเชื่อมโยงได้ไกลสุด 18500 เมตร [1]"
    run(answer_question("สายคู่บิดเกลียวเชื่อมได้ไกลกี่เมตร"))
    assert len(model["calls"]) == 1


def test_a_pile_of_references_is_cut_to_two():
    other = hit("x", chapter=1, pages=(21, 21))
    third = hit("y", chapter=3, pages=(90, 90))
    text, cited = book.resolve("มี 7 ชั้น [1] [2] [3]", [CABLE, other, third])
    assert text == "มี 7 ชั้น (บทที่ 2 หน้า 42-44) (บทที่ 1 หน้า 21)"
    assert len(cited) == 3


@needs_index
def test_the_old_datasets_are_not_opened_to_answer_from_the_book(model, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the Teachers Council index was opened")
    monkeypatch.setattr("app.answer.get_retriever", boom)
    monkeypatch.setattr("app.articles.get_index", boom)
    model["reply"] = "แบบจำลอง OSI ประกอบไปด้วยชั้นสื่อสาร 7 ชั้นด้วยกัน [1]"
    assert run(answer_question("แบบจำลอง OSI มีกี่ชั้น")).in_scope


@needs_index
def test_every_figure_a_passage_names_has_a_caption_on_record():
    index = book.get_index()
    named = {n for rec in index.corpus for n in rec.get("figures", [])}
    assert named, "no passage names a figure"
    unknown = {n for n in index.figures if n not in named}
    assert not unknown, f"figures cut from the PDF that no passage captions: {unknown}"
