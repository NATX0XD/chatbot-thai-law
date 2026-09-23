# -*- coding: utf-8 -*-
"""End-to-end behaviour of answer_question, with the LLM stubbed out.

The point of these tests is the refusal path: nothing here should ever reach the
model unless the corpus really does hold the answer, and nothing the model writes
should reach the user unless every name and every number in it is backed by a
section that was actually retrieved.
"""
import asyncio
import os

import pytest

from app import answer as answer_mod
from app.answer import answer_question
from app.config import settings

pytestmark = pytest.mark.skipif(
    not os.path.exists(settings.bm25_path),
    reason="index not built -- run ingest.extract_ksp then ingest.build_index",
)

ANSWERABLE = "ครูด่านักเรียนหน้าชั้นผิดจรรยาบรรณไหม"


@pytest.fixture
def spy_llm(monkeypatch):
    """Replace the model call and record whether it was reached.

    The canned reply cites nothing, so the guards downstream have nothing to
    object to and the test can be about the path rather than about the content.
    """
    calls = []

    async def fake_complete(system, user):
        calls.append({"system": system, "user": user})
        return "คำตอบจำลองที่ไม่ได้อ้างตัวบทใด"

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    return calls


def run(coro):
    return asyncio.run(coro)


def test_answers_a_covered_question(spy_llm):
    a = run(answer_question(ANSWERABLE))
    assert a.in_scope
    assert len(spy_llm) == 1, "the model should have been called"
    assert a.citations, "an answered question must carry citations"
    assert "ข้อ" in spy_llm[0]["user"], "sections must be passed as context"


def test_the_prompt_tells_the_model_the_corpus_is_narrow(spy_llm):
    run(answer_question(ANSWERABLE))
    system = spy_llm[0]["system"]
    assert "จรรยาบรรณ" in system
    assert "วินัยข้าราชการ" in system, "the nearest neighbour has to be named"


def test_civil_service_discipline_never_reaches_the_model(spy_llm):
    """The closest thing to this corpus that is not in it."""
    a = run(answer_question("ข้าราชการครูทำผิดวินัยร้ายแรงมีโทษอะไรบ้าง"))
    assert not a.in_scope
    assert spy_llm == [], "a known gap must be refused before spending an LLM call"
    assert "ระเบียบข้าราชการครู" in a.text, "the refusal should name the act"


def test_licensing_never_reaches_the_model(spy_llm):
    """Also the Teachers Council, also a regulation, and still not in the corpus."""
    a = run(answer_question("ขอใบอนุญาตประกอบวิชาชีพครูต้องใช้เอกสารอะไรบ้าง"))
    assert not a.in_scope
    assert spy_llm == []


def test_off_topic_never_reaches_the_model(spy_llm):
    a = run(answer_question("สูตรทำต้มยำกุ้งใส่อะไรบ้าง"))
    assert not a.in_scope
    assert spy_llm == []


def test_empty_question_is_handled(spy_llm):
    a = run(answer_question("   "))
    assert not a.in_scope
    assert spy_llm == []


def test_line_output_carries_the_disclaimer(spy_llm):
    a = run(answer_question(ANSWERABLE))
    body = a.for_line()
    assert "ไม่ใช่คำปรึกษาทางกฎหมาย" in body
    assert settings.corpus_as_of in body


def test_line_output_is_truncated(monkeypatch, spy_llm):
    async def long_answer(system, user):
        # varied text, not one repeated character: a long run of the same thing
        # is what looks_degenerate exists to reject, and it would reject this
        return " ".join(f"ประโยคที่ {i} ว่าด้วยจรรยาบรรณของวิชาชีพทางการศึกษา"
                        for i in range(60))

    monkeypatch.setattr(answer_mod, "complete", long_answer)
    a = run(answer_question(ANSWERABLE))
    body = a.for_line()
    assert "…" in body
    assert len(body) < settings.max_answer_chars + len(answer_mod.DISCLAIMER) + 20


def test_llm_failure_still_returns_the_sections(monkeypatch):
    async def boom(system, user):
        raise answer_mod.LLMUnavailable("no api key")

    monkeypatch.setattr(answer_mod, "complete", boom)
    a = run(answer_question(ANSWERABLE))
    assert a.error, "the failure should be reported"
    assert a.citations, "retrieval succeeded, so sections must still come back"
    assert "ข้อ" in a.text


def test_an_answer_that_names_a_regulation_we_never_supplied_is_blocked(monkeypatch):
    """The easy fabrication in this domain, because the Council issues dozens.

    "ข้อบังคับคุรุสภาว่าด้วยมาตรฐานวิชาชีพ" is a real regulation and is not in
    this corpus. An answer citing it reads exactly like a correct one.
    """
    async def fake_complete(system, user):
        return ("ครูต้องมีมาตรฐานการปฏิบัติตน "
                "(ข้อบังคับคุรุสภาว่าด้วยมาตรฐานวิชาชีพ พ.ศ. 2556 ข้อ 11)")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert not a.in_scope
    assert a.error == "unsupported citations"


def test_an_answer_that_cites_a_rule_number_out_of_thin_air_is_blocked(monkeypatch):
    """The failure a reader cannot see.

    The instrument is right, the wording is plausible, and the number sends them
    to a rule about something else entirely.
    """
    async def fake_complete(system, user):
        return ("ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ "
                "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 99)")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert not a.in_scope
    assert a.error == "unsupported sections"
    assert "ข้อ 99" in a.text


def test_calling_a_regulations_rule_a_มาตรา_is_blocked(monkeypatch):
    """ข้อบังคับคุรุสภา has no มาตรา, so this citation points at nothing.

    It is the kind of slip that survives every other check -- the regulation is
    real, the number is real, and the two together are not.
    """
    async def fake_complete(system, user):
        return ("ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ "
                "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 มาตรา 7)")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert not a.in_scope
    assert a.error == "unsupported sections"


def test_an_answer_that_wanders_into_civil_service_discipline_is_blocked(monkeypatch):
    """The leak no earlier guard catches.

    The question is about ethics, the retrieved text is about ethics, and the
    model answers with the penalties an employer can impose -- dismissal, pay
    cuts -- which come from a different act with a different procedure. Nothing
    it cited was fabricated; the gap is in what it said.
    """
    async def fake_complete(system, user):
        return ("ครูที่ประพฤติผิดอาจถูกลงโทษทางวินัยตามระเบียบข้าราชการครู "
                "ตั้งแต่ตัดเงินเดือนจนถึงปลดออก")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert not a.in_scope
    assert a.error == "answer beyond corpus"
    assert "ระเบียบข้าราชการครู" in a.text


PROSE_ABOUT_REGULATIONS = [
    "ข้อบังคับไม่ได้ระบุว่าการเล่นการพนันทุกรูปแบบผิดจรรยาบรรณ",
    "ข้อบังคับฉบับนี้มีผลใช้บังคับตั้งแต่วันถัดจากวันประกาศในราชกิจจานุเบกษา",
    "ข้อบังคับเดิมที่เกี่ยวข้องทั้งหมดถูกยกเลิกแล้ว",
    "ตามข้อบังคับที่เกี่ยวข้อง และข้อบังคับคุรุสภาไม่ได้กำหนดไว้",
    "ข้อบังคับว่าด้วยจรรยาบรรณของวิชาชีพ แบ่งออกเป็น 5 ด้าน",
]


@pytest.mark.parametrize("sentence", PROSE_ABOUT_REGULATIONS)
def test_ordinary_prose_about_a_regulation_is_not_a_fabricated_citation(
        monkeypatch, sentence):
    """ข้อบังคับ is this corpus's everyday noun, not only the start of a title.

    Reading these as instrument names rejected twelve of fifty correct answers
    in acceptance testing, including the one asking which regulation is in force.
    """
    async def fake_complete(system, user):
        return ("ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ "
                "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 7) "
                + sentence)

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert a.error is None, a.text[:200]
    assert a.in_scope


def test_a_sub_item_pointer_is_not_read_as_a_second_citation(monkeypatch):
    """"มาตรา 9 ข้อ ๑" is one citation and a pointer into it."""
    async def fake_complete(system, user):
        return ("คุรุสภามีอำนาจกำหนดจรรยาบรรณ "
                "(พ.ร.บ.สภาครูและบุคลากรทางการศึกษา 2546 มาตรา 9 ข้อ ๑)")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question("ใครเป็นคนกำหนดจรรยาบรรณของวิชาชีพครู"))
    assert a.error is None, a.text[:200]


def test_an_answer_that_collapses_into_repetition_is_not_sent(monkeypatch):
    """Two acceptance cases came back as "ข้อ 8 ข้อ 8 ข้อ 8" for hundreds of
    characters. It cites nothing and claims nothing, so every other guard
    passes it, and the reader gets a cut-off answer with no content in it."""
    async def fake_complete(system, user):
        return "ครูพึงช่วยเหลือเกื้อกูลกัน " + "ข้อ 8 " * 200

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert a.error == "degenerate answer"
    assert a.citations, "retrieval worked, so the sections still come back"


def test_the_context_says_which_chapter_each_rule_sits_in(spy_llm):
    """ข้อบังคับฯ 2550 states the same five duties once per kind of practitioner."""
    run(answer_question("ศึกษานิเทศก์ต้องมีวินัยในตนเองตามข้อไหน"))
    context = spy_llm[0]["user"]
    assert "(อยู่ใน หมวด" in context
    assert "ส่วนที่" in context


def test_a_repealed_regulation_is_marked_in_the_context_the_model_sees(spy_llm):
    """The model cannot prefer the current text unless it can tell them apart."""
    run(answer_question("การสอบสวนการประพฤติผิดจรรยาบรรณทำอย่างไร"))
    system = spy_llm[0]["system"]
    assert "ยกเลิกแล้ว" in system, "the prompt must explain the marker"
