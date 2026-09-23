# -*- coding: utf-8 -*-
"""Checking a citation against the rule it points at.

The wrong pairings here are quoted from four rounds of acceptance testing, and
the right ones are answers the same tester passed. Both halves matter: the check
this module exists to enable is only worth switching on if it stays silent on
the second half, and today it does not -- see the flag-rate test at the bottom,
which pins the reason it ships off.
"""
import os

import pytest

from app.config import settings
from app.corpus_store import open_corpus
from app.support import Corpus, unsupported_claims

pytestmark = pytest.mark.skipif(
    not os.path.exists(settings.corpus_path),
    reason="corpus not built -- run ingest.extract_ksp",
)


@pytest.fixture(scope="module")
def corpus():
    return Corpus(list(open_corpus(settings.corpus_path)))


SUPPORTED = [
    "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์หรือผู้รับบริการ "
    "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 7)",
    "พักใช้ใบอนุญาตได้ไม่เกินห้าปี "
    "(พ.ร.บ.สภาครูและบุคลากรทางการศึกษา 2546 มาตรา 54)",
    "ครูพึงช่วยเหลือเกื้อกูลซึ่งกันและกันอย่างสร้างสรรค์ ยึดมั่นในระบบคุณธรรม "
    "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)",
    "อุทธรณ์ได้ภายใน 30 วันนับแต่วันที่ได้รับแจ้งคำวินิจฉัย "
    "(ข้อบังคับคุรุสภา การอุทธรณ์คำวินิจฉัย 2549 ข้อ 11)",
    "ครูปิดบังข้อมูลข่าวสารในการปฏิบัติงานจนเกิดความเสียหาย "
    "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 8 (ข)(๑))",
]


@pytest.mark.parametrize("answer", SUPPORTED)
def test_a_citation_that_carries_its_sentence_is_left_alone(corpus, answer):
    assert unsupported_claims(answer, corpus) == []


def test_a_rule_number_the_instrument_does_not_have(corpus):
    """ข้อบังคับฯ 2556 ends at ข้อ 15."""
    problems = unsupported_claims(
        "ตามข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 99 ที่กำหนดไว้", corpus)
    assert problems and "99" in problems[0]


def test_the_unit_word_has_to_match_the_instrument(corpus):
    """A regulation has no มาตรา, so this pair cannot exist.

    The tester caught this one twice over: an answer that counted the five
    duties correctly and then attributed them to "ข้อบังคับฯ 2556 มาตรา 50".
    """
    problems = unsupported_claims(
        "จรรยาบรรณต่อผู้รับบริการมี 5 ข้อ ตามข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ "
        "2556 มาตรา 50", corpus)
    assert problems and "50" in problems[0]


def test_a_sub_item_pointer_has_to_land_inside_the_block_it_names(corpus):
    """ข้อ 8 lists two items under (ก) and five under (ข).

    Looking for "(๕)" anywhere in the rule finds it, which is why this check
    reads the lettered block rather than the whole text.
    """
    problems = unsupported_claims(
        "ครูปิดบังข้อมูลจนงานเสียหาย "
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 8 (ก)(๕))", corpus)
    assert problems and "(ก)(๕)" in problems[0]


WRONG_PAIRINGS = [
    # ข้อ 10 is about fostering learning; it contains no หลักวิชา
    ("ครูใช้หลักวิชาการที่ไม่ถูกต้องจนศิษย์เสียหาย ถือว่าผิด "
     "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 10)", "10"),
    # ข้อ 9 is about treating pupils equally, not about the environment
    ("ครูต้องเป็นผู้นำในการอนุรักษ์สิ่งแวดล้อมและภูมิปัญญาท้องถิ่น "
     "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 9)", "9"),
]


@pytest.mark.parametrize("answer,number", WRONG_PAIRINGS)
def test_a_claim_sharing_no_rare_word_with_its_rule_is_reported(
        corpus, answer, number):
    problems = unsupported_claims(answer, corpus)
    assert problems and number in problems[0], problems


def test_sharing_only_common_words_is_not_support(corpus):
    """ครู, วิชาชีพ and จรรยาบรรณ are in almost every rule.

    A check that accepts them as evidence of support never fires at all, which
    is why the comparison is on the claim's rarest words rather than any word.
    """
    vague = ("ครูผู้ประกอบวิชาชีพทางการศึกษาต้องรักษาจรรยาบรรณของวิชาชีพ "
             "โดยงดเว้นการเสพเมทแอมเฟตามีนและการพนันออนไลน์ "
             "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)")
    assert unsupported_claims(vague, corpus)


def test_a_claim_too_short_to_judge_is_left_alone(corpus):
    """The mechanism behind the flag rate that keeps this switched off.

    The claim is taken from the words before the citation, and the writer
    routinely puts the sentence after it instead -- leaving nothing in front to
    compare, or leaving the previous citation's sentence there. Five of twelve
    correct answers were flagged that way when this was measured.
    """
    assert unsupported_claims(
        "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 12) "
        "ครูต้องไม่กระทำตนเป็นปฏิปักษ์ต่อความเจริญทางกายของศิษย์", corpus) == []


def test_it_ships_switched_off(corpus):
    """Turning it on means re-measuring the flag rate on correct answers first,
    not re-deciding. See app/support.py for what has to be fixed."""
    assert settings.claim_check_blocks is False
