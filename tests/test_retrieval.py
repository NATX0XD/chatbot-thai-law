# -*- coding: utf-8 -*-
"""Retrieval tests. These run against the real index, so build it first:

    ./scripts/fetch_ksp.sh
    python -m ingest.extract_ksp && python -m ingest.audit_ksp
    python -m ingest.build_index

Each case pins a document and, where the answer really does live in one rule, a
number. Where several rules answer a question -- the five duties are stated once
in ข้อบังคับฯ 2556 and again, with examples, four times over in ข้อบังคับฯ 2550 --
only the document is pinned, because asserting one of them would be testing the
ranking's taste rather than whether the corpus covers the subject.
"""
import os

import pytest

from app.config import settings
from app.coverage import find_gap
from app.retriever import Retriever

pytestmark = pytest.mark.skipif(
    not os.path.exists(settings.bm25_path),
    reason="index not built -- run ingest.extract_ksp then ingest.build_index",
)

TOP_K = 8


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


def ids(res):
    return [h.rec["id"] for h in res.hits]


# (question, document key that must appear, section that must appear or None)
IN_SCOPE = [
    # --- duty to oneself ---
    ("จรรยาบรรณต่อตนเองของครูคืออะไร", "ksp-2550", "5"),
    ("ครูต้องพัฒนาตัวเองด้านไหนบ้าง", "ksp-2556", "7"),
    ("ครูเล่นการพนันผิดจรรยาบรรณไหม", "ksp-2550", "5"),
    ("ศึกษานิเทศก์ต้องมีวินัยในตนเองตามข้อไหน", "ksp-2550", "20"),

    # --- duty to the profession ---
    ("จรรยาบรรณต่อวิชาชีพเขียนว่าอย่างไร", "act-2546", "50"),
    ("ครูลอกผลงานวิชาการคนอื่นมาเป็นของตัวเอง", "ksp-2550", "6"),

    # --- duty to those served ---
    ("จรรยาบรรณต่อผู้รับบริการมีกี่ข้อ", "ksp-2550", None),
    ("ครูลงโทษนักเรียนด้วยการตีได้ไหม", "ksp-2550", "7"),
    ("ครูด่านักเรียนหน้าชั้นผิดจรรยาบรรณไหม", "ksp-2550", "7"),
    ("ครูเอาความลับของนักเรียนไปเล่าให้คนอื่นฟังได้ไหม", "ksp-2550", "7"),

    # --- duty to fellow practitioners ---
    ("จรรยาบรรณต่อผู้ร่วมประกอบวิชาชีพเขียนว่าอย่างไร", "ksp-2550", None),
    ("ครูโยนความผิดให้เพื่อนครู", "ksp-2550", "8"),
    ("ครูนินทาเพื่อนครูผิดไหม", "ksp-2550", "8"),

    # --- duty to society ---
    ("จรรยาบรรณต่อสังคมของครูคืออะไร", "ksp-2550", "9"),
    ("ครูไม่ร่วมกิจกรรมของชุมชนเลยผิดจรรยาบรรณไหม", "ksp-2550", "9"),
    ("ผู้บริหารการศึกษามีจรรยาบรรณต่อสังคมข้อไหน", "ksp-2550", "19"),

    # --- the Act behind all of it ---
    ("ใครเป็นคนกำหนดจรรยาบรรณของวิชาชีพครู", "act-2546", "50"),
    ("มาตรฐานวิชาชีพมีกี่ด้าน", "act-2546", "49"),
    ("ครูผิดจรรยาบรรณมีโทษอะไรบ้าง", "act-2546", "54"),

    # --- procedure ---
    ("ร้องเรียนครูประพฤติผิดจรรยาบรรณต้องทำยังไง", "ksp-2568", "8"),
    ("คณะอนุกรรมการสอบสวนมีกี่คน", "ksp-2568", "18"),
    ("ยื่นอุทธรณ์ได้ทางไหนบ้าง", "ksp-2549", "13"),
    ("อุทธรณ์คำวินิจฉัยได้ภายในกี่วัน", "ksp-2549", "11"),
]


@pytest.mark.parametrize("question,doc,section", IN_SCOPE)
def test_finds_the_rule_that_answers_it(retriever, question, doc, section):
    hits = retriever.search(question, top_k=TOP_K).hits
    found = [(h.rec["sysid"], h.rec["section"]) for h in hits]
    assert any(sysid == doc for sysid, _ in found), f"{doc} not in {found[:5]}"
    if section:
        assert (doc, section) in found, \
            f"{doc} {section} missing; got {found[:TOP_K]}"


@pytest.mark.parametrize("question,_doc,_sec", IN_SCOPE)
def test_answers_what_the_corpus_does_cover(retriever, question, _doc, _sec):
    res = retriever.search(question)
    assert res.in_scope, \
        f"{question!r} was refused (dense={res.max_dense:.4f} bm25={res.max_bm25:.2f})"


@pytest.mark.parametrize("question,_doc,_sec", IN_SCOPE)
def test_coverage_rules_do_not_block_answerable_questions(question, _doc, _sec):
    """The keyword rules are blunt; this guards against them over-reaching."""
    gap = find_gap(question)
    assert gap is None, f"{question!r} wrongly blocked as {gap.topic}"


# --- the five duties, each reachable by its own name ------------------------

DUTIES = ["ต่อตนเอง", "ต่อวิชาชีพ", "ต่อผู้รับบริการ",
          "ต่อผู้ร่วมประกอบวิชาชีพ", "ต่อสังคม"]


@pytest.mark.parametrize("duty", DUTIES)
def test_each_duty_retrieves_a_rule_filed_under_it(retriever, duty):
    """The label is only worth carrying if asking by name reaches it."""
    hits = retriever.search(f"จรรยาบรรณ{duty}ของครู", top_k=TOP_K).hits
    labels = [h.rec.get("ethics_category") for h in hits]
    assert duty in labels, f"ไม่มีชิ้นที่ติดป้าย {duty}; ได้ {labels}"


def test_plain_speech_and_statute_wording_reach_the_same_rule(retriever):
    """The expansion table exists for this; without it the two diverge."""
    spoken = set(ids(retriever.search("ครูนินทาเพื่อนครูผิดไหม", top_k=TOP_K)))
    written = set(ids(retriever.search(
        "วิพากษ์วิจารณ์ผู้ร่วมประกอบวิชาชีพจนแตกความสามัคคี", top_k=TOP_K)))
    assert spoken & written, f"ไม่ทับกันเลย: {spoken} vs {written}"


# --- citing a rule by number ------------------------------------------------


def test_an_explicit_ข้อ_is_honoured(retriever):
    """Council regulations number their rules as ข้อ, and people type that."""
    hits = retriever.search("ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ ข้อ 7", top_k=5).hits
    assert hits[0].rec["sysid"] == "ksp-2556"
    assert hits[0].rec["section"] == "7"


def test_an_explicit_มาตรา_is_honoured(retriever):
    hits = retriever.search("พระราชบัญญัติสภาครูฯ มาตรา 54 ว่าอย่างไร", top_k=5).hits
    top = hits[0]
    assert top.rec["sysid"] == "act-2546"
    assert top.rec["section"] == "54"


def test_thai_digits_are_normalised(retriever):
    arabic = retriever.search("จรรยาบรรณของวิชาชีพ ข้อ 7", top_k=3).hits
    thai = retriever.search("จรรยาบรรณของวิชาชีพ ข้อ ๗", top_k=3).hits
    assert arabic[0].rec["id"] == thai[0].rec["id"]


# --- citations name the right kind of instrument ----------------------------


def test_a_regulation_is_cited_as_ข้อ_and_the_act_as_มาตรา(retriever):
    """Writing "ข้อบังคับคุรุสภา มาตรา 7" would send a reader to nothing."""
    by_doc = {rec["sysid"]: rec for rec in retriever.corpus}
    assert by_doc["ksp-2556"]["unit"] == "ข้อ"
    assert by_doc["act-2546"]["unit"] == "มาตรา"

    hits = retriever.search("จรรยาบรรณต่อตนเอง", top_k=TOP_K).hits
    for hit in hits:
        expected = hit.rec["unit"]
        wrong = "มาตรา" if expected == "ข้อ" else "ข้อ"
        assert f" {expected} {hit.rec['section']}" in hit.citation
        assert f" {wrong} {hit.rec['section']}" not in hit.citation


def test_a_repealed_regulation_says_so_in_its_citation(retriever):
    repealed = next(h for h in retriever.corpus if h.get("superseded_by"))
    hit = next(h for h in retriever.search("การสอบสวน", top_k=40).hits
               if h.rec["sysid"] == repealed["sysid"])
    assert "ยกเลิกแล้ว" in hit.citation


# --- the newer of two overlapping regulations wins --------------------------

# ข้อ 3 ของข้อบังคับฯ 2568 repealed the 2553 regulation and both amendments to
# it. All three are still indexed, because the 2568 text refers to proceedings
# begun under them, so ranking is the only thing keeping them out of answers.
SUPERSEDED = {"ksp-2553", "ksp-2559", "ksp-2563"}

CURRENT_PROCEDURE = [
    "ร้องเรียนครูประพฤติผิดจรรยาบรรณต้องทำยังไง",
    "คณะอนุกรรมการสอบสวนมีกี่คน",
    "กรณีไหนพักใช้ใบอนุญาตได้ทันทีโดยไม่ต้องรอผลสอบสวน",
    "ความผิดไม่ร้ายแรงต้องตั้งคณะกรรมการสอบสวนทุกครั้งไหม",
]


@pytest.mark.parametrize("question", CURRENT_PROCEDURE)
def test_the_repealed_version_does_not_lead(retriever, question):
    hits = retriever.search(question, top_k=TOP_K).hits
    assert hits[0].rec["sysid"] not in SUPERSEDED, \
        f"นำด้วยฉบับที่ถูกยกเลิก: {hits[0].rec['id']}"


def test_the_repealed_version_is_still_reachable(retriever):
    """Down-ranked, not hidden -- a proceeding begun in 2565 ran under it."""
    hits = retriever.search("ข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ 2553",
                            top_k=20).hits
    assert any(h.rec["sysid"] in SUPERSEDED for h in hits)


# --- what the corpus does not hold ------------------------------------------

OFF_TOPIC = [
    "สูตรทำต้มยำกุ้งใส่อะไรบ้าง",
    "ทีมฟุตบอลไหนชนะบอลโลกปีที่แล้ว",
    "ช่วยเขียนโค้ด python อ่านไฟล์ csv ให้หน่อย",
]

# Legal questions whose governing law is absent. Every one of these is about a
# teacher, which is what makes them dangerous: they retrieve real, on-topic
# regulations that do not govern the question.
MISSING_LAW = [
    "ข้าราชการครูทำผิดวินัยร้ายแรงมีโทษอะไรบ้าง",
    "ขอใบอนุญาตประกอบวิชาชีพครูต้องใช้เอกสารอะไรบ้าง",
    "โรงเรียนหักเงินเดือนครูอัตราจ้างได้ไหม",
    "ครูถูกเลิกจ้างได้ค่าชดเชยเท่าไหร่",
]


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_cosine_gate_rejects_off_topic(retriever, question):
    """Layer 2. Questions that are not about law at all score below the threshold."""
    res = retriever.search(question)
    assert not res.in_scope, \
        f"{question!r} passed the gate (dense={res.max_dense:.4f} bm25={res.max_bm25:.2f})"


@pytest.mark.parametrize("question", MISSING_LAW)
def test_coverage_rule_catches_law_the_corpus_lacks(retriever, question):
    """Layer 1. Only a rule that knows what is missing can stop these."""
    assert find_gap(question) is not None, f"{question!r} has no coverage rule"


def test_the_score_gate_alone_would_not_be_enough(retriever):
    """Documents *why* layer 1 exists.

    At least one missing-law probe sails straight through the cosine gate, so
    the gate alone cannot be trusted with this class of question. On the general
    -law corpus this was a weak claim; on this one it is emphatic, because every
    probe is phrased in the vocabulary of school and teaching.
    """
    slipped = {q: retriever.search(q).max_dense
               for q in MISSING_LAW if retriever.search(q).in_scope}
    assert slipped, ("every missing-law probe now scores below the gate; "
                     "if this holds for a wider set, the coverage rules could be "
                     "reconsidered")
