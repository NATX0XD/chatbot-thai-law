# -*- coding: utf-8 -*-
"""End-to-end behaviour of answer_question, with the LLM stubbed out.

The point of these tests is the refusal path: nothing here should ever reach the
model unless the corpus really does hold the answer.
"""
import asyncio
import os

import pytest

from app import answer as answer_mod
from app.answer import answer_question
from app.config import settings

pytestmark = pytest.mark.skipif(
    not os.path.exists(settings.bm25_path),
    reason="index not built -- run ingest.extract_acts then ingest.build_index",
)


@pytest.fixture
def spy_llm(monkeypatch):
    """Replace the Typhoon call and record whether it was reached."""
    calls = []

    async def fake_complete(system, user):
        calls.append({"system": system, "user": user})
        return "คำตอบจำลอง (พระราชบัญญัติคุ้มครองแรงงาน พ.ศ. 2541 มาตรา 118)"

    monkeypatch.setattr(answer_mod, "complete", fake_complete)
    return calls


def run(coro):
    return asyncio.run(coro)


def test_answers_a_covered_question(spy_llm):
    a = run(answer_question("ถูกเลิกจ้างกะทันหัน ได้ค่าชดเชยเท่าไหร่"))
    assert a.in_scope
    assert len(spy_llm) == 1, "the model should have been called"
    assert a.citations, "an answered question must carry citations"
    assert "มาตรา" in spy_llm[0]["user"], "sections must be passed as context"


def test_missing_code_never_reaches_the_model(spy_llm):
    a = run(answer_question("พ่อเสียชีวิตไม่ได้ทำพินัยกรรม มรดกแบ่งยังไง"))
    assert not a.in_scope
    assert spy_llm == [], "a known gap must be refused before spending an LLM call"
    assert "ประมวลกฎหมายแพ่งและพาณิชย์" in a.text, "the refusal should name the code"


def test_off_topic_never_reaches_the_model(spy_llm):
    a = run(answer_question("สูตรทำต้มยำกุ้งใส่อะไรบ้าง"))
    assert not a.in_scope
    assert spy_llm == []


def test_empty_question_is_handled(spy_llm):
    a = run(answer_question("   "))
    assert not a.in_scope
    assert spy_llm == []


def test_line_output_carries_the_disclaimer(spy_llm):
    a = run(answer_question("ถูกเลิกจ้างกะทันหัน ได้ค่าชดเชยเท่าไหร่"))
    body = a.for_line()
    assert "ไม่ใช่คำปรึกษาทางกฎหมาย" in body
    assert settings.corpus_as_of in body


def test_line_output_is_truncated(monkeypatch, spy_llm):
    async def long_answer(system, user):
        return "ก" * (settings.max_answer_chars + 500)

    monkeypatch.setattr(answer_mod, "complete", long_answer)
    a = run(answer_question("ถูกเลิกจ้างกะทันหัน ได้ค่าชดเชยเท่าไหร่"))
    body = a.for_line()
    assert "…" in body
    assert len(body) < settings.max_answer_chars + len(answer_mod.DISCLAIMER) + 20


def test_llm_failure_still_returns_the_sections(monkeypatch):
    async def boom(system, user):
        raise answer_mod.LLMUnavailable("no api key")

    monkeypatch.setattr(answer_mod, "complete", boom)
    a = run(answer_question("ถูกเลิกจ้างกะทันหัน ได้ค่าชดเชยเท่าไหร่"))
    assert a.error, "the failure should be reported"
    assert a.citations, "retrieval succeeded, so sections must still come back"
    assert "มาตรา" in a.text
