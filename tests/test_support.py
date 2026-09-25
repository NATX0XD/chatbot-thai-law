# -*- coding: utf-8 -*-
"""Checking a citation against the rule it points at.

The wrong pairings here are quoted from six rounds of acceptance testing, and the
right ones are answers the same tester passed. Both halves matter: a check that
fires on correct answers is worse than no check, because what it costs is the
answer. The structural checks block; the ones that judge meaning feed the repair
turn instead, which is what makes a false positive survivable.
"""
import os

import pytest

from app.config import settings
from app.corpus_store import open_corpus
from app.support import (
    Corpus, conviction_on_thin_evidence, impossible_citations,
    unsupported_claims)

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
    assert impossible_citations(answer, corpus) == []


def test_a_sub_item_written_as_a_rule_number_is_a_pointer(corpus):
    """"มาตรา 9 ข้อ ๑" is one citation and a pointer into it."""
    assert impossible_citations(
        "คุรุสภามีอำนาจกำหนดจรรยาบรรณของวิชาชีพ "
        "(พ.ร.บ.สภาครูและบุคลากรทางการศึกษา 2546 มาตรา 9 ข้อ ๑)", corpus) == []


def test_a_rule_number_the_instrument_does_not_have(corpus):
    """ข้อบังคับฯ 2556 ends at ข้อ 15."""
    problems = impossible_citations(
        "ตามข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 99 ที่กำหนดไว้", corpus)
    assert problems and "99" in problems[0]


def test_the_unit_word_has_to_match_the_instrument(corpus):
    """A regulation has no มาตรา, so this pair cannot exist.

    The tester caught this one twice over: an answer that counted the five
    duties correctly and then attributed them to "ข้อบังคับฯ 2556 มาตรา 50".
    """
    problems = impossible_citations(
        "จรรยาบรรณต่อผู้รับบริการมี 5 ข้อ ตามข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ "
        "2556 มาตรา 50", corpus)
    assert problems and "50" in problems[0]


def test_a_sub_item_pointer_has_to_land_inside_the_block_it_names(corpus):
    """ข้อ 8 lists two items under (ก) and five under (ข).

    Looking for "(๕)" anywhere in the rule finds it, which is why this check
    reads the lettered block rather than the whole text.
    """
    problems = impossible_citations(
        "ครูปิดบังข้อมูลจนงานเสียหาย "
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 8 (ก)(๕))", corpus)
    assert problems and "(ก)(๕)" in problems[0]


def test_a_shortened_instrument_name_does_not_hand_the_citation_to_its_neighbour(
        corpus):
    """The false positive round six caught, the first hour this check was on.

    The writer names instruments its own way. "แบบแผนพฤติกรรม 2550" matches no
    name in the corpus, so the search walked back past it to ข้อบังคับฯ 2556 --
    named earlier in the same sentence -- and read ข้อ 8 (ข)(๑) against ข้อ 8 of
    the wrong regulation, which has no lettered blocks at all. It then refused a
    correct answer on the ground that the sub-item did not exist. It does: ข้อ 8
    (ข)(๑) ของข้อบังคับฯ 2550 is "ปิดบังข้อมูลข่าวสารในการปฏิบัติงาน จนทำให้เกิด
    ความเสียหาย" -- which was the answer to the question.
    """
    assert impossible_citations(
        "ครูปิดบังข้อมูลจนงานเสียหาย ผิดจรรยาบรรณต่อผู้ร่วมประกอบวิชาชีพ "
        "ตามข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14 "
        "และแบบแผนพฤติกรรม 2550 ข้อ 8 (ข)(๑)", corpus) == []


def test_a_sub_item_no_instrument_has_is_still_impossible(corpus):
    """Attribution got a second reader, not an exemption.

    Widening to the whole corpus is what makes the message true: the sub-item is
    reported missing only when no rule of that number anywhere has it.
    """
    assert impossible_citations(
        "ครูปิดบังข้อมูล (ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 "
        "ข้อ 8 (ก)(๙))", corpus)


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


def test_the_structural_checks_are_the_ones_that_block(corpus):
    """They read the corpus and make no judgement about meaning, so they cannot
    produce a false positive the way the lexical check can."""
    wrong_pairing = WRONG_PAIRINGS[0][0]
    assert impossible_citations(wrong_pairing, corpus) == []
    assert unsupported_claims(wrong_pairing, corpus)


# --- what the sixth acceptance round asked for -------------------------------


def test_the_sentence_after_a_citation_counts_as_its_claim(corpus):
    """The forward window, and the reason this check stayed off for two rounds.

    "(ข้อ 7) ครูต้องไม่ดูหมิ่นศิษย์" is as common a shape as the reverse, and
    reading only backwards left nothing in front to compare -- or worse, left
    the previous citation's sentence there.
    """
    assert unsupported_claims(
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 7) "
        "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์หรือผู้รับบริการ", corpus) == []


def test_one_citations_sentence_is_not_read_as_anothers(corpus):
    """Both windows stop at the nearest other citation."""
    assert unsupported_claims(
        "ครูต้องไม่ดูหมิ่นเหยียดหยามศิษย์ "
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 7) "
        "และพึงช่วยเหลือเกื้อกูลซึ่งกันและกันอย่างสร้างสรรค์ ยึดมั่นในระบบคุณธรรม "
        "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)", corpus) == []


def test_a_claim_is_compared_against_the_sub_item_it_cites(corpus):
    """ข้อ 8 (ข) has five items; citing (ข)(๑) for what (ข)(๓) says is wrong.

    Compared against the whole rule this passes -- the words are all in ข้อ 8.
    Narrowing to the block the pointer names is what makes it visible.
    """
    assert unsupported_claims(
        "ครูสร้างกลุ่มอิทธิพลภายในองค์การหรือกลั่นแกล้งผู้ร่วมประกอบวิชาชีพ "
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 8 (ข)(๑))", corpus)
    assert unsupported_claims(
        "ครูสร้างกลุ่มอิทธิพลภายในองค์การหรือกลั่นแกล้งผู้ร่วมประกอบวิชาชีพ "
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 8 (ข)(๓))",
        corpus) == []


def test_reporting_a_should_as_a_must_is_caught(corpus):
    """ข้อ 14 says พึง. An answer that says ต้อง tells a teacher they can be
    disciplined for something the regulation does not say that about."""
    must = ("ผู้ประกอบวิชาชีพทางการศึกษาต้องช่วยเหลือเกื้อกูลซึ่งกันและกัน"
            "อย่างสร้างสรรค์ ยึดมั่นในระบบคุณธรรม "
            "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)")
    problems = unsupported_claims(must, corpus)
    assert problems and "พึง" in problems[0]
    assert unsupported_claims(must.replace("ต้องช่วยเหลือ", "พึงช่วยเหลือ"),
                              corpus) == []


VERDICT = "ครูไปหาเสียงช่วยผู้สมัคร ส.ส. ผิดจรรยาบรรณไหม"


def test_a_verdict_with_no_rule_about_the_conduct_is_reported():
    """KSP-040, wrong in the same way for six rounds.

    The regulations say nothing about canvassing; the political restrictions on
    civil servants are in an act this corpus does not hold. BM25 is the signal
    -- 8.5 here against 24 to 45 for conduct the rules do describe -- because
    word overlap with the question is exactly what query expansion exists to
    make unnecessary.
    """
    assert conviction_on_thin_evidence(
        VERDICT, "การหาเสียงช่วยผู้สมัคร ส.ส. ถือว่าผิดจรรยาบรรณต่อสังคม", 8.5)


def test_an_answer_that_says_the_code_is_silent_is_not_a_conviction():
    assert not conviction_on_thin_evidence(
        VERDICT, "ข้อบังคับจรรยาบรรณไม่ได้เขียนเรื่องการหาเสียงไว้โดยตรง", 8.5)


def test_conduct_the_rules_do_describe_is_left_alone():
    """The lowest in-domain verdict question measured scores 11.9."""
    assert not conviction_on_thin_evidence(
        "ครูด่านักเรียนหน้าชั้นเรียน ผิดจรรยาบรรณไหม",
        "ถือว่าผิดจรรยาบรรณต่อผู้รับบริการ", 35.9)
    assert not conviction_on_thin_evidence(
        "ครูใช้หลักวิชาผิดจนศิษย์เสียหาย เข้าข่ายพฤติกรรมใด",
        "ถือว่าผิดจรรยาบรรณต่อผู้รับบริการ", 11.9)


def test_a_hedge_followed_by_a_verdict_is_still_a_verdict():
    """The commoner shape, and the one that slipped through first.

    "ตัวบทไม่ได้ระบุชัดเจนว่าห้าม ... แต่ ... ถือว่าผิดจรรยาบรรณ" reads to a
    teacher as a conviction. Only a disclaimer with the last word counts.
    """
    assert conviction_on_thin_evidence(
        VERDICT,
        "ตัวบทไม่ได้ระบุชัดเจนว่าห้ามเข้าร่วมกิจกรรมทางการเมืองทุกกรณี "
        "แต่การกระทำที่ขัดกับการเป็นแบบอย่างที่ดี ถือว่าผิดจรรยาบรรณ", 8.5)
    assert not conviction_on_thin_evidence(
        VERDICT,
        "บางคนมองว่าถือว่าผิดจรรยาบรรณ แต่ข้อบังคับไม่ได้เขียนเรื่องนี้ไว้", 8.5)
