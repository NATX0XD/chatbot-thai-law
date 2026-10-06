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


def test_one_line_with_a_made_up_number_does_not_cost_the_whole_answer():
    draft = "สายคู่บิดเกลียวมีราคาถูก [1]\nรองรับความเร็ว 1000 เมกะบิต [1]\nเชื่อมได้ไกล 100 เมตร [1]"
    kept, removed = book.drop_unsupported_numbers(draft, [CABLE])
    assert kept == "สายคู่บิดเกลียวมีราคาถูก [1]\nเชื่อมได้ไกล 100 เมตร [1]"
    assert removed == ["1000"]


def test_a_number_from_the_answer_already_given_may_be_repeated():
    draft = "ตามที่บอกไปว่ายาวได้ 185 เมตร [1]"
    assert book.drop_unsupported_numbers(draft, [CABLE], "คำตอบก่อนหน้า ยาวได้ 185 เมตร")[1] == []
    assert book.drop_unsupported_numbers(draft, [CABLE])[1] == ["185"]


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
    shown = book.pick_figures("สายคู่บิดเกลียวคืออะไร", [CABLE], [CABLE], FIGURES)
    assert [f["number"] for f in shown] == ["2.3"]
    assert shown[0]["url"] == "/static/figures/fig-2-3.jpg"
    assert shown[0]["page"] == 42


def test_a_word_every_caption_shares_does_not_bring_the_wrong_figure():
    shown = book.pick_figures("สายโคแอกเชียลมีข้อดีอะไร", [CABLE], [CABLE], FIGURES)
    assert [f["number"] for f in shown] == ["2.5"]


def test_a_question_about_none_of_the_figures_gets_none():
    assert book.pick_figures("บลูทูธส่งสัญญาณได้ไกลกี่เมตร", [CABLE], [CABLE], FIGURES) == []
    assert book.pick_figures("สายคู่บิดเกลียวคืออะไร", [], [], FIGURES) == []


def test_a_figure_with_no_file_is_left_out():
    assert book.pick_figures("สายคู่บิดเกลียวคืออะไร", [CABLE], [CABLE], {}) == []


def test_a_figure_from_another_chapter_is_not_shown():
    # "การเข้าหัว lan" cited chapter 4 and was shown รูปที่ 3.25, a coaxial
    # cable, because a chapter 3 passage was among those retrieved
    crimp = hit("ขั้นตอนที่ 3 นำมาจัดเรียงสี", chapter=4, pages=(126, 129),
                heading="ขั้นตอนการสร้างสายแลนชนิด RJ-45")
    coax = hit("รูปที่ 3.25 สายโคแอกเชียล", chapter=3, pages=(99, 99), figures=("3.25",))
    figures = {"3.25": {"file": "fig-3-25.jpg", "page": 99, "width": 800, "height": 300,
                        "caption": "สายโคแอกเชียล RG-58 A/U ที่เข้าหัวปลั๊กแบบ BNC"}}
    assert book.pick_figures("การเข้าหัว lan", [crimp], [crimp, coax], figures) == []
    assert book.pick_figures("การเข้าหัว lan", [coax], [crimp, coax], figures) != []


def photo(page, order, caption):
    return {"key": f"p{page}-{order}", "file": f"photo-{page}-{order}.jpg", "page": page,
            "caption": caption, "kind": "photo", "width": 500, "height": 400}


def test_step_photographs_come_with_the_pages_the_answer_cites():
    crimp = hit("ขั้นตอนที่ 3 นำมาจัดเรียงสี", chapter=4, pages=(126, 127))
    photos = {125: [photo(125, 1, "ขั้นตอนที่ 1 ปอกเปลือก")],
              126: [photo(126, 1, "ขั้นตอนที่ 2 แยกสาย"),
                    photo(126, 2, "ขั้นตอนที่ 3 นำมาจัดเรียงสี ดังนี้ (มาตรฐาน T568B)")],
              127: [photo(127, 1, "ขั้นตอนที่ 4 นำคีมย้ำหัว RJ-45 มา")]}
    shown = book.pick_figures("การเข้าหัว lan", [crimp], [crimp], {}, photos=photos)
    assert [f["number"] for f in shown] == ["p126-1", "p126-2", "p127-1"]
    assert shown[1]["kind"] == "photo" and shown[1]["page"] == 126
    assert shown[1]["url"] == "/static/figures/photo-126-2.jpg"
    assert book.pick_figures("การเข้าหัว lan", [], [crimp], {}, photos=photos) == []


def test_when_there_are_too_many_step_photographs_the_asked_about_ones_stay():
    long = hit("ขั้นตอน", chapter=5, pages=(180, 180))
    photos = {180: [photo(180, i, f"{i}. คลิกปุ่ม Next") for i in range(1, 12)]
              + [photo(180, 12, "12. เลือกสิทธิ์ Read")]}
    shown = book.pick_figures("สิทธิ์ Read ตั้งตรงไหน", [long], [long], {}, photos=photos)
    assert len(shown) == book.MAX_PHOTOS
    assert shown[-1]["number"] == "p180-12", "the step asked about is kept"
    assert [f["number"] for f in shown[:2]] == ["p180-1", "p180-2"], "in the book's order"


def test_figures_go_to_line_as_one_carousel_with_full_addresses(monkeypatch):
    from app.answer import Answer
    monkeypatch.setattr(settings, "public_base_url", "https://bot.example/")
    crimp = hit("ขั้นตอนที่ 3", chapter=2, pages=(42, 42))
    photos = {42: [photo(42, 1, "ขั้นตอนที่ 3 นำมาจัดเรียงสี")]}
    shown = book.pick_figures("สายคู่บิดเกลียวคืออะไร", [CABLE, crimp], [CABLE], FIGURES,
                              photos=photos)
    messages = Answer(text="คำตอบ", citations=[CABLE.citation], source="book",
                      figures=shown).for_line_messages()
    assert [m["type"] for m in messages] == ["text", "flex", "flex"]
    bubbles = messages[2]["contents"]["contents"]
    assert [b["hero"]["url"] for b in bubbles] == [
        "https://bot.example/static/figures/fig-2-3.jpg",
        "https://bot.example/static/figures/photo-42-1.jpg"]
    assert bubbles[0]["body"]["contents"][0]["text"] == "รูปที่ 2.3 สายคู่บิดเกลียว"
    assert bubbles[1]["body"]["contents"][0]["text"] == "ขั้นตอนที่ 3 นำมาจัดเรียงสี"
    assert "คู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น" in messages[0]["text"]


def test_one_figure_is_a_single_card_not_a_carousel():
    from app.flex import figures_message
    shown = book.pick_figures("สายคู่บิดเกลียวคืออะไร", [CABLE], [CABLE], FIGURES)
    assert figures_message(shown, "https://bot.example")["contents"]["type"] == "bubble"


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
def test_a_question_about_something_else_is_never_given_the_passages(model):
    # The gate decides it is not a question for the book. The model is then
    # asked only to word the reply to this one message; it sees no passage and
    # the answer stays a refusal whatever it writes.
    model["reply"] = "เรื่องอาหารผมช่วยไม่ได้ครับ ลองถามเรื่องเครือข่ายคอมพิวเตอร์ได้เลยครับ"
    a = run(answer_question("สูตรทำต้มยำกุ้งใส่อะไรบ้าง"))
    assert not a.in_scope and a.source == "book"
    assert [c["system"] for c in model["calls"]] == [book.CHAT_PROMPT]
    assert "ข้อความจากหนังสือ" not in model["calls"][0]["user"]
    assert a.text == model["reply"] and a.citations == [] and a.figures == []


@needs_index
def test_a_runaway_or_empty_chat_reply_falls_back_to_the_fixed_text(model):
    model["reply"] = "ต้มยำกุ้งใส่ " * 80
    assert run(answer_question("สูตรทำต้มยำกุ้งใส่อะไรบ้าง")).text == book.OUT_OF_SCOPE
    model["reply"] = ""
    assert run(answer_question("สูตรทำต้มยำกุ้งใส่อะไรบ้าง")).text == book.OUT_OF_SCOPE


@needs_index
@pytest.mark.parametrize("question", [
    "จากหนังสือมีทั้งหมดกี่บทครับ", "จากหนังสือมีทั้งหมด กี่บทครับ",
    "หนังสือเล่มนี้มีเนื้อหาเรื่องอะไรบ้าง", "ขอสารบัญหน่อย"])
def test_a_question_about_the_book_itself_is_answered_by_counting(model, question):
    a = run(answer_question(question))
    assert a.in_scope and model["calls"] == []
    assert "มีทั้งหมด 7 บท" in a.text
    assert "บทที่ 1 เครือข่ายการสื่อสาร (หน้า 12-30)" in a.text
    assert "บทที่ 7 " in a.text


@pytest.mark.parametrize("question", ["คุณเป็นใคร", "คุณรู้เรื่องอะไรบ้าง", "ถามอะไรได้บ้าง",
                                      "ไม่รู้จะถามอะไร"])
def test_asking_the_bot_about_itself_gets_the_introduction(question):
    assert route(question) == NETWORK_CAPABILITIES


@pytest.mark.parametrize("question", ["เซิร์ฟเวอร์เป็นอะไรกับเครื่องลูกข่าย",
                                      "ฮับคืออะไร", "โปรโตคอลคืออะไรบ้าง"])
def test_a_networking_question_is_not_taken_for_one_about_the_bot(question):
    assert route(question) is None
    assert not book.ABOUT_BOOK.search(question)


@pytest.mark.parametrize("message", ["อยากรู้เพิ่มเติมอีก", "แล้วข้อเสียล่ะ", "ยกตัวอย่างหน่อย",
                                     "ไม่เข้าใจ", "ทำไมล่ะ", "ขอรูปหน่อย"])
def test_a_follow_up_is_read_with_the_question_before_it(message):
    assert book.with_context(message, "สาย Lan คืออะไร") == f"{message} — สาย Lan คืออะไร"
    assert book.with_context(message, None) == message


@pytest.mark.parametrize("message", ["แบบจำลอง OSI มีกี่ชั้น", "โทโปโลยีแบบดาวคืออะไร",
                                     "ฮับกับสวิตช์ต่างกันอย่างไร"])
def test_a_new_question_is_not_tied_to_the_one_before(message):
    assert book.with_context(message, "สาย Lan คืออะไร") == message


@needs_index
def test_a_follow_up_goes_on_instead_of_being_refused(model):
    model["reply"] = "สายแลนเป็นสายคู่บิดเกลียวที่ใช้เชื่อมต่อเครือข่าย [1]"
    a = run(answer_question("อยากรู้เพิ่มเติมอีก", "สาย Lan คืออะไร",
                            "สาย LAN คือสายคู่บิดเกลียว (บทที่ 4 หน้า 124-125)"))
    assert a.in_scope and a.citations
    sent = model["calls"][0]["user"]
    assert sent.startswith("คำถามก่อนหน้าของนักเรียน\nสาย Lan คืออะไร\n\n"
                           "คำถามตอนนี้ ซึ่งถามต่อจากคำถามก่อนหน้า\nอยากรู้เพิ่มเติมอีก")
    assert "คำตอบที่ให้ไปแล้ว\nสาย LAN คือสายคู่บิดเกลียว" in sent


def test_line_keeps_the_last_question_of_a_chat_for_a_while(monkeypatch):
    from app import line_bot
    monkeypatch.setattr(line_bot, "_last_question", {})
    assert line_bot.previous_question("U1") == (None, None)
    line_bot.remember_question("U1", "สาย Lan คืออะไร", "คำตอบ")
    assert line_bot.previous_question("U1") == ("สาย Lan คืออะไร", "คำตอบ")
    assert line_bot.previous_question("U2") == (None, None)
    monkeypatch.setattr(line_bot.time, "time", lambda: 10 ** 12)
    assert line_bot.previous_question("U1") == (None, None)


@needs_index
def test_a_made_up_figure_never_reaches_the_reader_as_the_books(model):
    # Until 2026-10-06 this draft became a plain refusal. The owner then asked
    # for the model's own knowledge to fill in where the book cannot be used,
    # so the question is asked again without the passages -- and whatever comes
    # back is printed as the model's, never with a page of the book beside it.
    replies = ["สายคู่บิดเกลียวเชื่อมโยงได้ไกลสุด 18500 เมตร [1]",
               "โดยทั่วไปสายคู่บิดเกลียวเชื่อมได้ไกลราวหนึ่งร้อยเมตรครับ"]

    async def two(system, user):
        model["calls"].append(system)
        return replies[len(model["calls"]) - 1]

    mp = pytest.MonkeyPatch()
    mp.setattr(book, "complete", two)
    try:
        a = run(answer_question("สายคู่บิดเกลียวเชื่อมได้ไกลกี่เมตร"))
    finally:
        mp.undo()
    assert "18500" not in a.text
    assert a.source == "model" and a.citations == [] and a.figures == []
    assert a.text.startswith(book.UNVERIFIED_NOTICE)
    assert "(บทที่" not in a.text.split("หัวข้อที่ใกล้เคียงที่สุดในหนังสือ")[0]
    assert "หัวข้อที่ใกล้เคียงที่สุดในหนังสือ" in a.text
    assert model["calls"][1] == book.GENERAL_PROMPT


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
def test_a_made_up_figure_is_not_given_a_second_try_at_the_passages(model):
    model["reply"] = "สายคู่บิดเกลียวเชื่อมโยงได้ไกลสุด 18500 เมตร [1]"
    a = run(answer_question("สายคู่บิดเกลียวเชื่อมได้ไกลกี่เมตร"))
    systems = [c["system"] for c in model["calls"]]
    assert systems == [book.SYSTEM_PROMPT, book.GENERAL_PROMPT]
    assert "(บทที่" not in a.text.split("หัวข้อที่ใกล้เคียงที่สุดในหนังสือ")[0]


# ------------------------------------------- the model's own knowledge

def test_what_the_model_adds_is_split_from_what_the_book_says():
    raw = "สายมีราคาถูก [1]\nเสริม:\nสาย CAT6 รองรับความเร็วสูงกว่า"
    assert book.split_supplement(raw) == ("สายมีราคาถูก [1]",
                                          "สาย CAT6 รองรับความเร็วสูงกว่า")
    assert book.split_supplement("สายมีราคาถูก [1]") == ("สายมีราคาถูก [1]", "")


def test_a_supplement_cannot_carry_a_reference_to_the_book():
    assert book.clean_supplement("IPv6 ยาว 128 บิต [2]") == "IPv6 ยาว 128 บิต"
    assert book.clean_supplement("ไม่มีข้อมูลพอ") == ""


@needs_index
def test_an_addition_is_printed_under_the_label_and_outside_the_guards(model):
    model["reply"] = ("สายคู่บิดเกลียวเป็นสายสัญญาณที่มีราคาถูก [1]\n"
                      "เสริม:\nสาย CAT6 รองรับความเร็ว 10000 เมกะบิตต่อวินาทีในระยะสั้น")
    a = run(answer_question("สายคู่บิดเกลียวคืออะไร มีข้อดีข้อเสียอย่างไร"))
    assert a.in_scope and a.source == "book" and a.citations
    above, below = a.text.split(book.SUPPLEMENT_LABEL)
    assert "(บทที่ 2 หน้า" in above and "CAT6" not in above
    assert "CAT6" in below and "บทที่" not in below


@needs_index
def test_a_networking_question_the_book_lacks_is_answered_as_the_models_own(model):
    replies = ["ไม่มีข้อมูลพอ", "IPv6 มีความยาว 128 บิตครับ"]

    async def two(system, user):
        model["calls"].append(system)
        return replies[len(model["calls"]) - 1]

    mp = pytest.MonkeyPatch()
    mp.setattr(book, "complete", two)
    try:
        a = run(answer_question("IPv6 มีความยาวกี่บิต"))
    finally:
        mp.undo()
    assert a.source == "model" and a.in_scope
    assert a.text.startswith(book.MODEL_NOTICE) and "128" in a.text
    assert a.citations == [] and a.figures == []
    assert a.disclaimer == book.MODEL_DISCLAIMER
    assert model["calls"][1] == book.GENERAL_PROMPT


@needs_index
def test_when_the_model_knows_nothing_either_it_is_still_a_refusal(model):
    model["reply"] = "ไม่มีข้อมูลพอ"
    a = run(answer_question("IPv6 มีความยาวกี่บิต"))
    assert not a.in_scope and len(model["calls"]) == 2


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
    assert index.photos, "no step photographs were loaded"
    assert all(i["kind"] == "photo" for group in index.photos.values() for i in group)
    unknown = {n for n in index.figures if n not in named}
    assert not unknown, f"figures cut from the PDF that no passage captions: {unknown}"
