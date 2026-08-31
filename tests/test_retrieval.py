# -*- coding: utf-8 -*-
"""Retrieval tests. These run against the real index, so build it first:

    python -m ingest.extract_acts && python -m ingest.build_index
"""
import os

import pytest

from app.config import settings
from app.coverage import find_gap
from app.retriever import Retriever

pytestmark = pytest.mark.skipif(
    not os.path.exists(settings.bm25_path),
    reason="index not built -- run ingest.extract_acts then ingest.build_index",
)


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


# (question, act substring that must appear, section that must appear)
IN_SCOPE = [
    ("ถูกเลิกจ้างกะทันหัน ได้ค่าชดเชยเท่าไหร่", "คุ้มครองแรงงาน", "118"),
    ("ทำงานครบหนึ่งปี ลาพักผ่อนประจำปีได้กี่วัน", "คุ้มครองแรงงาน", "30"),
    ("เจ้าหนี้โทรทวงหนี้ตอนกลางคืนได้ไหม", "ทวงถามหนี้", "9"),
    ("ลูกจ้างประสบอันตรายจากการทำงาน นายจ้างต้องจ่ายอะไรบ้าง", "เงินทดแทน", None),
    ("เก็บข้อมูลส่วนบุคคลต้องขอความยินยอมไหม", "ข้อมูลส่วนบุคคล", None),
    # the two codes, added after the Act corpus. Every one of these used to be
    # refused by a coverage rule, because the governing text was not there.
    ("เจ้าของบ้านยึดเงินมัดจำ ทำอะไรได้บ้าง", "แพ่งและพาณิชย์", None),
    # no section is pinned here: มาตรา 1599, 1603, 1620 and 1629 all answer part
    # of it, and asserting one of them would test the ranking's taste rather than
    # whether the corpus now covers inheritance at all
    ("พ่อเสียชีวิตไม่ได้ทำพินัยกรรม มรดกตกทอดแก่ใคร", "แพ่งและพาณิชย์", None),
    ("เหตุฟ้องหย่ามีอะไรบ้าง", "แพ่งและพาณิชย์", "1516"),
    ("กู้ยืมเงินเกินสองพันบาทต้องทำหลักฐานเป็นหนังสือไหม", "แพ่งและพาณิชย์", "653"),
    ("ใส่ความผู้อื่นให้เสียชื่อเสียงมีความผิดอะไร", "อาญา", "326"),
    ("ลักทรัพย์ในเวลากลางคืนมีโทษเท่าไหร่", "อาญา", "335"),
]


@pytest.mark.parametrize("question,act_part,section", IN_SCOPE)
def test_finds_the_right_act(retriever, question, act_part, section):
    hits = retriever.search(question, top_k=8).hits
    acts = [h.rec["act"] for h in hits]
    assert any(act_part in a for a in acts), f"{act_part} not in {acts[:4]}"
    if section:
        pairs = [(h.rec["act"], h.rec["section"]) for h in hits]
        assert any(act_part in a and s == section for a, s in pairs), \
            f"มาตรา {section} missing; got {pairs[:6]}"


def test_explicit_section_number_is_honoured(retriever):
    """A user who types a section number expects that exact section back."""
    hits = retriever.search("พระราชบัญญัติคุ้มครองแรงงาน มาตรา 118 ว่าอย่างไร", top_k=5).hits
    top = hits[0]
    assert top.rec["section"] == "118"
    assert "คุ้มครองแรงงาน" in top.rec["act"]


def test_thai_digits_are_normalised(retriever):
    arabic = retriever.search("คุ้มครองแรงงาน มาตรา 118", top_k=3).hits
    thai = retriever.search("คุ้มครองแรงงาน มาตรา ๑๑๘", top_k=3).hits
    assert arabic[0].rec["id"] == thai[0].rec["id"]


OFF_TOPIC = [
    "สูตรทำต้มยำกุ้งใส่อะไรบ้าง",
    "ทีมฟุตบอลไหนชนะบอลโลกปีที่แล้ว",
    "ช่วยเขียนโค้ด python อ่านไฟล์ csv ให้หน่อย",
]

# legal questions whose governing law is absent from this corpus. Answering these
# from whatever the retriever scraped up is the failure mode that hurts users most,
# so they are tested as hard as the off-topic ones.
#
# The list changed when the two substantive codes were added: tenancy, inheritance
# and defamation moved into IN_SCOPE, and what is left is procedure. The criminal
# code says what defamation is; ป.วิ.อาญา, which the corpus still lacks, says how
# to report it and how bail works.
MISSING_LAW = [
    "โดนโกงออนไลน์ ไปแจ้งความที่โรงพักไหนก็ได้ไหม",
    "ขอประกันตัวในชั้นสอบสวนต้องใช้หลักทรัพย์เท่าไหร่",
    "ศาลตัดสินแล้วลูกหนี้ไม่จ่าย จะยึดทรัพย์บังคับคดียังไง",
]


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_cosine_gate_rejects_off_topic(retriever, question):
    """Layer 2. Questions that are not about law at all score below the threshold."""
    res = retriever.search(question)
    assert not res.in_scope, \
        f"{question!r} passed the gate (dense={res.max_dense:.4f} bm25={res.max_bm25:.2f})"


@pytest.mark.parametrize("question", MISSING_LAW)
def test_coverage_rule_catches_missing_codes(retriever, question):
    """Layer 1. These score *above* the cosine gate -- they retrieve a real act that
    simply does not govern the question -- so only the coverage rule can stop them."""
    assert find_gap(question) is not None, f"{question!r} has no coverage rule"


def test_the_score_gate_alone_would_not_be_enough(retriever):
    """Documents *why* layer 1 exists.

    Some missing-code questions do fall below the cosine gate -- it depends on
    whether any act in the corpus happens to sit near the topic. The claim layer 1
    rests on is weaker but sufficient: at least one of them sails straight through,
    so the gate alone cannot be trusted with this class of question.
    """
    slipped = {q: retriever.search(q).max_dense
               for q in MISSING_LAW if retriever.search(q).in_scope}
    assert slipped, ("every missing-code probe now scores below the gate; "
                     "if this holds for a wider set, the coverage rules could be "
                     "reconsidered")


@pytest.mark.parametrize("question,_act,_sec", IN_SCOPE)
def test_coverage_rules_do_not_block_answerable_questions(question, _act, _sec):
    """The keyword rules are blunt; this guards against them over-reaching."""
    gap = find_gap(question)
    assert gap is None, f"{question!r} wrongly blocked as {gap.topic}"


@pytest.mark.parametrize("question,_act,_sec", IN_SCOPE)
def test_answers_what_the_corpus_does_cover(retriever, question, _act, _sec):
    res = retriever.search(question)
    assert res.in_scope, \
        f"{question!r} was refused (dense={res.max_dense:.4f} bm25={res.max_bm25:.2f})"
