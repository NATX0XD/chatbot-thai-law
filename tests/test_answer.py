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


def test_a_duty_arrives_with_every_rule_that_states_it(spy_llm):
    """หมวด 3 ของข้อบังคับฯ 2556 holds five rules, and the question is how many.

    Retrieving one of the five is how "จรรยาบรรณต่อผู้รับบริการมีกี่ข้อ" came
    back as "1 ข้อ" -- an answer that is wrong, short, and confident.
    """
    run(answer_question("จรรยาบรรณต่อผู้รับบริการมีกี่ข้อ"))
    context = spy_llm[0]["user"]
    for section in ("ข้อ 9", "ข้อ 10", "ข้อ 11", "ข้อ 12", "ข้อ 13"):
        assert f"จรรยาบรรณของวิชาชีพ 2556 {section}" in context, section


def test_a_duty_named_in_the_question_is_the_duty_that_arrives(spy_llm):
    """Retrieval cannot pick between five near-identical phrasings.

    "พฤติกรรมพึงประสงค์ด้านจรรยาบรรณต่อวิชาชีพ" came back holding rules about
    ต่อตนเอง and ต่อผู้ร่วมประกอบวิชาชีพ and none about the duty it asked for.
    The name is in the question; reading it is free and exact.
    """
    run(answer_question("พฤติกรรมพึงประสงค์ด้านจรรยาบรรณต่อวิชาชีพมีอะไรบ้าง"))
    context = spy_llm[0]["user"]
    assert "จรรยาบรรณของวิชาชีพ 2556 ข้อ 8" in context
    assert "แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 6" in context


def test_the_expansion_does_not_drag_in_every_duty_at_once(spy_llm):
    """A question that names no duty gets the best-ranked one, not all five."""
    run(answer_question("ครูนินทาเพื่อนครูผิดไหม"))
    context = spy_llm[0]["user"]
    named = sum(1 for duty in ("ต่อตนเอง", "ต่อวิชาชีพ", "ต่อผู้รับบริการ",
                               "ต่อผู้ร่วมประกอบวิชาชีพ", "ต่อสังคม")
                if f"ส่วนที่ 1 จรรยาบรรณ{duty}" in context
                or f"หมวด 1 จรรยาบรรณ{duty}" in context)
    assert named <= 2, context[:400]


def test_the_regulation_that_states_the_duties_is_read_first(spy_llm):
    """2556 states each duty; 2550 illustrates it. The answer should rest on the
    first and quote the second, and the model follows whichever it reads first."""
    run(answer_question("จรรยาบรรณต่อตนเองของครูคืออะไร"))
    context = spy_llm[0]["user"]
    first = context.index("จรรยาบรรณของวิชาชีพ 2556")
    later = context.index("แบบแผนพฤติกรรมตามจรรยาบรรณ 2550")
    assert first < later


def test_a_rule_added_as_a_chapter_sibling_may_be_cited(monkeypatch):
    """The guards judge the answer against what the model was shown, not against
    the raw ranking -- otherwise the rules just added look like inventions."""
    async def fake_complete(system, user):
        return ("จรรยาบรรณต่อผู้รับบริการมี 5 ข้อ "
                "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 9) "
                "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 13)")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question("จรรยาบรรณต่อผู้รับบริการมีกี่ข้อ"))
    assert a.error is None, a.text[:200]


def test_quoting_the_corpus_about_dismissal_is_not_straying(monkeypatch):
    """ข้อ 71 ของข้อบังคับฯ 2568 lists an employer's order to dismiss as a ground
    for suspending a licence. An answer repeating that is reading the corpus."""
    async def fake_complete(system, user):
        return ("คุรุสภาพักใช้ใบอนุญาตได้เมื่อหน่วยงานต้นสังกัดมีคำสั่ง"
                "ปลดออกหรือไล่ออก "
                "(ข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ 2568 ข้อ 71)")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(
        "กรณีไหนที่คุรุสภาสั่งพักใช้ใบอนุญาตได้ทันทีโดยไม่ต้องรอผลสอบสวน"))
    assert a.error is None, a.text[:200]


def test_a_year_in_a_title_is_not_read_as_a_rule_number(monkeypatch):
    """The largest rule number in this corpus is 90; 2550 is a year."""
    async def fake_complete(system, user):
        return ("ครูต้องช่วยเหลือเกื้อกูลกัน "
                "ตามข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 8")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question("ครูนินทาเพื่อนครูผิดไหม"))
    assert a.error is None, a.text[:200]


def test_a_repealed_regulation_is_marked_in_the_context_the_model_sees(spy_llm):
    """The model cannot prefer the current text unless it can tell them apart."""
    run(answer_question("การสอบสวนการประพฤติผิดจรรยาบรรณทำอย่างไร"))
    system = spy_llm[0]["system"]
    assert "ยกเลิกแล้ว" in system, "the prompt must explain the marker"
