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
    Corpus, cited_rules, impossible_citations, misattributed_citations,
    correct_modals, modal_mismatches, right_sub_item, unsupported_claims)

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


def test_the_unit_word_that_does_not_match_the_instrument_is_a_note(corpus):
    """A regulation has no มาตรา, so "ข้อบังคับฯ 2556 มาตรา 50" is wrong.

    Wrong, and not worth refusing over. It reads as a fact -- regulations have
    ข้อ, acts have มาตรา -- but it rests on having attributed the citation to
    the right instrument, and that is the unreliable half. The same shape
    appears in "...2568 ข้อ 9 และ มาตรา 51", where มาตรา 51 belongs to the act
    the sentence did not name again; blocking that refused a question the corpus
    answers in full. So it goes to the writer as a correction instead.
    """
    answer = ("จรรยาบรรณต่อผู้รับบริการมี 5 ข้อ ตามข้อบังคับคุรุสภา "
              "จรรยาบรรณของวิชาชีพ 2556 มาตรา 50")
    assert impossible_citations(answer, corpus) == []
    problems = misattributed_citations(answer, corpus)
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
    problems = modal_mismatches(must, corpus)
    assert problems and "พึง" in problems[0]
    assert modal_mismatches(must.replace("ต้องช่วยเหลือ", "พึงช่วยเหลือ"),
                            corpus) == []
    # and it is reported on its own, so it can be acted on while the overlap
    # check beside it is only logged
    assert unsupported_claims(must, corpus) == []


def test_the_modal_is_put_back_rather_than_reported(corpus):
    """The repair turn was told about this every round and shipped the wrong
    word anyway, eleven times across two rounds. Which word the rule uses is a
    fact about the corpus, so it is substituted rather than asked for."""
    must = ("ผู้ประกอบวิชาชีพทางการศึกษาต้องช่วยเหลือเกื้อกูลซึ่งกันและกัน"
            "อย่างสร้างสรรค์ ยึดมั่นในระบบคุณธรรม "
            "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)")
    fixed, notes = correct_modals(must, corpus)
    assert notes and "พึงช่วยเหลือ" in fixed
    assert modal_mismatches(fixed, corpus) == []


def test_a_negative_moves_the_modal_in_front_of_it(corpus):
    """Word for word, "ต้องไม่" becomes "พึงไม่", which is not Thai."""
    must = ("ผู้ประกอบวิชาชีพต้องไม่ละเลยการช่วยเหลือเกื้อกูลซึ่งกันและกัน"
            "อย่างสร้างสรรค์ ยึดมั่นในระบบคุณธรรม สร้างความสามัคคีในหมู่คณะ "
            "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)")
    fixed, _ = correct_modals(must, corpus)
    assert "ไม่พึงละเลย" in fixed and "พึงไม่" not in fixed


def test_a_correct_modal_is_left_alone(corpus):
    written = ("ผู้ประกอบวิชาชีพทางการศึกษาพึงช่วยเหลือเกื้อกูลซึ่งกันและกัน"
               "อย่างสร้างสรรค์ ยึดมั่นในระบบคุณธรรม "
               "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)")
    assert correct_modals(written, corpus) == (written, [])


def test_an_ambiguous_sub_item_pointer_is_not_a_wrong_one(corpus):
    """ข้อ 6 has both (ก)(๖) and (ข)(๖), on opposite sides of the same subject.

    (ก)(๖) is เลือกใช้หลักวิชาที่ถูกต้อง and (ข)(๖) is ใช้หลักวิชาการที่ไม่ถูกต้อง
    ... เกิดความเสียหาย. Reading only the first block made this checker report a
    correct prohibition as unsupported, and I passed that on as a real catch
    until the tester opened the record. A letterless pointer is ambiguous, and
    ambiguous is not wrong.
    """
    assert unsupported_claims(
        "ครูใช้หลักวิชาการที่ไม่ถูกต้องในการปฏิบัติวิชาชีพ ส่งผลให้ศิษย์เกิดความเสียหาย "
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 6 (๖))", corpus) == []


def test_an_instrument_we_failed_to_name_does_not_borrow_its_neighbours(corpus):
    """"พ.ร.บ.สภาครูฯ" matches no name and carries no year.

    The lookup fell back to the regulation named earlier in the sentence and
    reported มาตรา 52 -- which exists, and was in that case's own sources -- as
    missing, refusing an answer that had passed the round before. An instrument
    word between the name we matched and the citation means we do not know whose
    citation it is, and not knowing is not a fault in the answer.
    """
    assert impossible_citations(
        "ตามข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ 2568 ข้อ 46 "
        "และ พ.ร.บ.สภาครูฯ มาตรา 52", corpus) == []


def test_the_rules_an_answer_cites_are_counted(corpus):
    """What stops a repair from passing by deleting the flagged citation."""
    answer = ("ครูต้องไม่ดูหมิ่นศิษย์ (ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตาม"
              "จรรยาบรรณ 2550 ข้อ 7) และพึงช่วยเหลือเกื้อกูลกัน "
              "(ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14)")
    assert cited_rules(answer, corpus) == {"7", "14"}
    # correcting the unit word is a repair, not the loss of a citation
    assert cited_rules(answer.replace("ข้อ 7", "มาตรา 7"), corpus) == {"7", "14"}
    hedged = "ครูควรประพฤติตนให้เหมาะสมตามจรรยาบรรณของวิชาชีพ"
    assert not cited_rules(hedged, corpus) >= cited_rules(answer, corpus)


def test_a_rule_split_across_records_is_read_as_one(corpus):
    """ข้อ 7 ของข้อบังคับฯ 2550 is stored in two pieces.

    (ข)(๗) เรียกร้องผลตอบแทนจากศิษย์ sits alone in the second one, so reading
    only the first reported the rule as having no (๗) and refused an answer that
    had quoted it word for word. Ten of the corpus's 334 records are
    continuations like this.
    """
    assert impossible_citations(
        "ครูเรียกร้องผลตอบแทนจากศิษย์หรือผู้รับบริการในงานตามหน้าที่ "
        "(ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 7 (ข)(๗))",
        corpus) == []


RULE_7 = "ksp-2550", "ข้อ", "7"
RULE_8 = "ksp-2550", "ข้อ", "8"


def _text(corpus, key):
    return corpus.by_rule[key]["text"]


def test_a_pointer_at_the_wrong_sub_item_is_moved_to_the_right_one(corpus):
    """All three assessors named this as the largest remaining fault class: the
    rule is right and the pointer inside it is not. ข้อ 8(ข)(๑) is the rule
    against withholding information; (ข)(๓) is the one against forming
    factions."""
    sentence = ("ครูไม่พึงปิดบังข้อมูลข่าวสารในการปฏิบัติงานจนทำให้เกิด"
                "ความเสียหายต่องาน")
    assert right_sub_item(sentence, _text(corpus, RULE_8),
                          ["ข", "๓"], corpus) == ["ข", "๑"]


def test_a_pointer_the_rule_cannot_support_is_dropped(corpus):
    """"เลือกปฏิบัติ" was cited to ข้อ 7(ข)(๑) of ข้อบังคับฯ 2550, which reads
    "ลงโทษศิษย์อย่างไม่เหมาะสม". No block of ข้อ 7 carries it -- it is in the
    chapters for the other three professions -- so the citation keeps the rule
    and loses the pointer rather than sending a reader to the wrong text."""
    sentence = ("การปฏิบัติงานโดยมุ่งประโยชน์ส่วนตนและการเลือกปฏิบัติต่อศิษย์"
                "อย่างไม่เป็นธรรม")
    assert right_sub_item(sentence, _text(corpus, RULE_7),
                          ["ข", "๑"], corpus) is None


def test_a_correct_pointer_is_left_where_it_is(corpus):
    sentence = "ครูไม่พึงลงโทษศิษย์อย่างไม่เหมาะสมจนเกิดความเสียหายแก่ร่างกายและจิตใจ"
    assert right_sub_item(sentence, _text(corpus, RULE_7),
                          ["ข", "๑"], corpus) == ["ข", "๑"]


def test_the_duty_and_its_opposite_are_told_apart_by_weight(corpus):
    """ข้อ 8 states the duty under (ก) and forbids its opposite under (ข), so
    ความสามัคคี alone matches both halves. (ข)(๕) matches all three distinctive
    words; a plain filter called that a tie and gave up."""
    sentence = ("ครูไม่พึงวิพากษ์วิจารณ์ผู้ร่วมประกอบวิชาชีพในเรื่องที่"
                "ก่อให้เกิดความเสียหายหรือแตกความสามัคคี")
    assert right_sub_item(sentence, _text(corpus, RULE_8),
                          ["ข", "๑"], corpus) == ["ข", "๕"]
