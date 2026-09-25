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
        return "ครูต้องมีมาตรฐานการปฏิบัติตนตามข้อบังคับคุรุสภาว่าด้วยมาตรฐานวิชาชีพ พ.ศ. 2556"

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert not a.in_scope
    assert a.error == "unsupported citations"


def test_a_rule_number_the_model_typed_itself_never_reaches_the_reader(monkeypatch):
    """The failure a reader cannot see, and the reason numbers are no longer
    the model's to write.

    The instrument is right, the wording is plausible, and the number sends
    them to a rule about something else. Rather than refuse the answer, the
    hand-written citation is removed: what is left is true, and nothing false
    is printed. Three assessor rounds found this class of fault dominant.
    """
    async def fake_complete(system, user):
        return ("ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ "
                "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 99)")

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert "ข้อ 99" not in a.text
    assert "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์" in a.text
    assert any("ข้อ 99" in f for f in a.faults)


def test_the_unit_word_cannot_be_got_wrong_any_more(monkeypatch):
    """ข้อบังคับคุรุสภา has no มาตรา, and the model no longer chooses.

    It points at the evidence and the unit word is read off the record with
    everything else, so "ข้อบังคับฯ ... มาตรา 7" is not a mistake it is able to
    make. The guard that used to catch it -- and that refused four correct
    answers over three rounds getting there -- has nothing left to do here.
    """
    async def fake_complete(system, user):
        return "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ [1]"

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert a.in_scope and a.error is None
    assert "ข้อ" in a.text and "มาตรา" not in a.text


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


# --- citations assembled from the record, not typed by the model -------------


def _piece(section, *, sysid="ksp-2550", chapter=None, short=None, text=None):
    return answer_mod.Hit(rec={
        "id": f"{sysid}:{section}", "sysid": sysid, "unit": "ข้อ",
        "section": section, "act": "",
        # real-ish text: a pointer is checked against the record it names, so a
        # record with nothing in it reads as a pointer at the wrong rule
        "text": text or "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์หรือผู้รับบริการ "
                        "และต้องไม่จูงใจโน้มน้าวให้ปฏิบัติขัดต่อศีลธรรม",
        "short": short or "ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550",
        "chapters": [chapter] if chapter else [],
    }, rrf=0.0)


TEACHER = "หมวด 1 แบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพครู"
HEAD = "หมวด 2 แบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพผู้บริหารสถานศึกษา"


def test_a_pointer_becomes_the_citation_of_the_evidence_it_points_at():
    """Three assessor rounds measured the same fault: the sentence is right and
    the number beside it is not. The model typed 266 rule numbers across 60
    answers; now it points and the citation is read off the record."""
    hits = [_piece("7", chapter=TEACHER), _piece("12", chapter=HEAD)]
    text, typed, mispointed = answer_mod.resolve_citations(
        "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์หรือผู้รับบริการ [1](ข)(๓)", hits)
    assert "ข้อ 7(ข)(๓)" in text
    assert not typed and not mispointed


def test_the_citation_says_whose_duty_it_is():
    """ข้อบังคับฯ 2550 states the same five duties four times, once per kind of
    practitioner. Quoting one profession's rule for another was the commonest
    fault the assessors found, so the citation names the profession."""
    text, _, _ = answer_mod.resolve_citations("[1] และ [2]",
                                           [_piece("7", chapter=TEACHER),
                                            _piece("12", chapter=HEAD)])
    assert "หมวดของครู" in text
    assert "หมวดของผู้บริหารสถานศึกษา" in text


def test_a_pointer_at_evidence_that_was_never_supplied_disappears():
    text, _, _ = answer_mod.resolve_citations("ตามที่กำหนดไว้ [9]",
                                           [_piece("7", chapter=TEACHER)])
    assert "[9]" not in text and "9" not in text


def test_a_number_the_model_typed_itself_is_reported():
    """The whole point is that it stops doing this, so it has to be visible."""
    text, typed, _ = answer_mod.resolve_citations(
        "ตามข้อ 99 และ [1]", [_piece("7", chapter=TEACHER)])
    assert typed == ["ข้อ 99"]


def test_an_act_citation_carries_no_profession():
    """Only ข้อบังคับฯ 2550 repeats itself by profession."""
    text, _, _ = answer_mod.resolve_citations("[1]", [_piece(
        "54", sysid="act-2546", short="พ.ร.บ.สภาครูและบุคลากรทางการศึกษา 2546")])
    assert "หมวดของ" not in text


def test_a_number_the_evidence_does_contain_is_left_where_it_is():
    """Deleting every hand-typed number was too blunt.

    "อยู่ในข้อ 7 จรรยาบรรณต่อตนเอง" became "อยู่ใน จรรยาบรรณต่อตนเอง" on a
    question that asked which ข้อ it was, and "ข้อ 9, 10, 11, 12 และ 13" came
    out as "ได้แก่ , 10, 11, 12 และ 13" because only the first number carried
    the word ข้อ. What decides is whether the model was shown that rule, not
    who typed the number.
    """
    hits = [_piece("9", sysid="ksp-2556"), _piece("10", sysid="ksp-2556")]
    text, typed, _ = answer_mod.resolve_citations(
        "มีห้าข้อ ได้แก่ ข้อ 9, 10 และ ข้อ 99", hits)
    assert "ข้อ 9, 10" in text
    assert "ข้อ 99" not in text and typed == ["ข้อ 99"]


def test_a_pointer_that_lost_its_brackets_is_not_left_looking_like_a_rule():
    """"8(ข)(๓)" is a marker the substitution missed, and it reads to a teacher
    as a rule number."""
    text, _, _ = answer_mod.resolve_citations(
        "ครูต้องไม่ดูหมิ่นศิษย์ 8(ข)(๓)", [_piece("7", chapter=TEACHER)])
    assert "8(ข)(๓)" not in text
    assert "ครูต้องไม่ดูหมิ่นศิษย์" in text


def test_a_pointer_at_a_rule_that_says_nothing_of_the_kind_is_reported():
    """The fault that replaced the one taking numbers away fixed.

    The model stopped typing wrong numbers and started pointing at wrong
    records: the text of 2556 ข้อ 13 printed under a citation to 2568 ข้อ 51,
    labelled faithfully with a record that says nothing of the kind. Now that a
    citation names exactly one record, zero shared distinctive words is a wrong
    pointer rather than an attribution the checker could not resolve.
    """
    wrong = _piece("51", sysid="ksp-2568",
                   short="ข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ 2568",
                   text="เมื่อการสอบสวนแล้วเสร็จ ให้คณะอนุกรรมการสอบสวนทำรายงาน"
                        "การสอบสวนเสนอต่อคณะกรรมการมาตรฐานวิชาชีพ")
    _, _, problems = answer_mod.resolve_citations(
        "ผู้ประกอบวิชาชีพต้องให้บริการด้วยความจริงใจและเสมอภาค "
        "โดยไม่เรียกรับผลประโยชน์จากการใช้ตำแหน่งหน้าที่โดยมิชอบ [1]", [wrong])
    assert problems and "ข้อ 51" in problems[0]


def test_a_refusal_names_the_law_and_does_not_recite_the_note(monkeypatch):
    """The note is written for the model; the refusal is written for a teacher.

    Dropping one into the other produced "ระบบร่างคำตอบโดยอ้างถึง คำตอบอ้าง
    ข้อบังคับคุรุสภา 2556 ไม่ได้ระบุพฤติกรรม ... ซึ่งไม่มีอยู่ในคลังข้อมูล
    ซึ่งไม่มีอยู่ในคลังข้อมูล", which is what a user actually received.
    """
    async def fake_complete(system, user):
        return "ครูต้องมีวินัยในตนเองตามข้อบังคับคุรุสภาว่าด้วยมาตรฐานวิชาชีพ พ.ศ. 2548"

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert a.error == "unsupported citations"
    assert a.text.count("ซึ่งไม่มีอยู่ในคลังข้อมูล") == 1
    assert "คำตอบอ้าง" not in a.text


def test_a_repaired_answer_goes_through_the_same_substitution(monkeypatch):
    """The rewrite was shipped raw.

    Pointers in the first draft became citations; pointers in the second did
    not, so an accepted repair could reach a reader as "…ต่อจิตใจและอารมณ์
    2(ข)(๓)" -- a rule number the system had never checked, in an answer it had
    recorded as repaired.
    """
    drafts = iter([
        # naming a regulation the corpus does not hold is a blocking fault, so
        # a rewrite is asked for
        "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ ตามข้อบังคับคุรุสภาว่าด้วย"
        "มาตรฐานวิชาชีพ พ.ศ. 2548",
        "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์หรือผู้รับบริการ [1]",
    ])

    async def fake_complete(system, user):
        return next(drafts)

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    a = run(answer_question(ANSWERABLE))
    assert a.repair == "accepted"
    assert "[1]" not in a.text


def test_a_prose_number_is_checked_against_what_that_rule_says():
    """The leak the citation check cannot see by construction.

    "การเกี่ยวข้องกับอบายมุข ... อยู่ในข้อ 9" with a correct citation in
    brackets beside it: the bracket was checked, the sentence was not, and ข้อ 9
    is จรรยาบรรณต่อสังคม. Keeping every number the evidence happened to contain
    let this through, and both assessors named it.
    """
    society = _piece("9", text="ผู้ประกอบวิชาชีพทางการศึกษา พึงประพฤติปฏิบัติตน"
                               "เป็นผู้นำในการอนุรักษ์และพัฒนาเศรษฐกิจ สังคม "
                               "ศาสนา ศิลปวัฒนธรรม และสิ่งแวดล้อม")
    vices = _piece("5", text="ครูต้องไม่เกี่ยวข้องกับอบายมุขหรือเสพสิ่งเสพติด"
                             "จนขาดสติหรือแสดงกิริยาไม่สุภาพ")
    text, stray, _ = answer_mod.resolve_citations(
        "การเกี่ยวข้องกับอบายมุขหรือเสพสิ่งเสพติดจนขาดสติอยู่ในข้อ 9",
        [society, vices])
    assert "ข้อ 9" not in text
    assert stray == ["ข้อ 9"]

    # and the number that does carry the sentence stays
    kept, _, _ = answer_mod.resolve_citations(
        "การเกี่ยวข้องกับอบายมุขหรือเสพสิ่งเสพติดจนขาดสติอยู่ในข้อ 5",
        [society, vices])
    assert "ข้อ 5" in kept
