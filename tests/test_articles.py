# -*- coding: utf-8 -*-
"""The journal-article corpus: how it is cut up, when it is used, what it may say."""
import asyncio

import pytest

from app import articles
from app.retriever import SearchResult
from ingest import extract_articles as ex

SOURCE = """# ชุดข้อมูล

# ส่วนที่ 1 จรรยาบรรณของวิชาชีพ

## [A01] ข้อบังคับคุรุสภา

ข้อ ๑ ข้อความของข้อบังคับซึ่งไม่ใช่บทความและต้องไม่ถูกอ่านเข้ามาในคลังบทความเด็ดขาด ไม่ว่ากรณีใด

# ส่วนที่ 2 บทความวิชาการ

## [G01] จิตวิญญาณความเป็นครู (Teacher Spirituality)

แหล่งที่มา: สมชาย ใจดี; สมหญิง รักเรียน (คณะครุศาสตร์) · วารสารทดสอบ ปีที่ 6 ฉบับที่ 2 (พ.ค.-ส.ค. 2559) หน้า 1-9 · 2016 · https://example.org/a\\_b/view/1 · ดาวน์โหลดเมื่อ 2026-10-04

บทคัดย่อ

จิตวิญญาณความเป็นครูหมายถึงการที่ครูรักและศรัทธาในวิชาชีพ เอาใจใส่ศิษย์อย่างเสมอภาค และพัฒนาตนเองอยู่เสมอ ได้ค่าเฉลี่ย 4\\.51

The purpose of this article was to present the spirituality of teachers in the present day of Thailand.

มาก

4\\.51

ผลการวิจัย

ผลการวิจัยพบว่าครูในกลุ่มตัวอย่างมีจิตวิญญาณความเป็นครูอยู่ในระดับมาก โดยด้านความรักและศรัทธาในวิชาชีพมีค่าเฉลี่ยสูงที่สุด

เอกสารอ้างอิง

สมศักดิ์ นักวิจัย. (2550). จรรยาบรรณวิชาชีพครู. กรุงเทพฯ: สำนักพิมพ์ทดสอบ รายการอ้างอิงนี้ต้องไม่อยู่ในคลัง
"""


def rows():
    return list(ex.records(SOURCE.split("\n")))


def test_only_the_articles_are_read():
    assert {r["sysid"] for r in rows()} == {"G01"}
    assert not any("ข้อบังคับซึ่งไม่ใช่บทความ" in r["text"] for r in rows())


def test_source_line_becomes_the_citation():
    r = rows()[0]
    assert r["title"] == "จิตวิญญาณความเป็นครู"
    assert r["short"] == "สมชาย ใจดี และสมหญิง รักเรียน (2559)"
    assert r["source_url"] == "https://example.org/a_b/view/1"


def test_references_english_and_table_cells_are_dropped():
    text = " ".join(r["text"] for r in rows())
    assert "รายการอ้างอิงนี้" not in text
    assert "purpose of this article" not in text
    assert "\nมาก" not in text and not any(r["text"] == "4.51" for r in rows())
    # the escape is undone, so a figure reads as the article printed it
    assert "4.51" in text and "\\" not in text


def test_a_chunk_never_crosses_a_heading():
    assert [r["heading"] for r in rows()] == ["บทคัดย่อ", "ผลการวิจัย"]


def test_an_article_without_a_source_line_stops_the_build():
    broken = SOURCE.replace("แหล่งที่มา:", "ที่มา:")
    with pytest.raises(SystemExit):
        list(ex.records(broken.split("\n")))


def test_three_authors_are_shortened():
    assert ex.short_authors("ก ข; ค ง (ม.พะเยา); จ ฉ") == "ก ข และคณะ"


# ---------------------------------------------------------------- routing

class FakeIndex:
    def __init__(self, best):
        self.best = best

    def with_abstract(self, hits):
        return hits

    class bm25:
        term_id = {"ราชภัฏ": 0, "หลักธรรม": 1, "อะไร": 2, "วินัย": 3}

    def search(self, question, vector, top_k=6):
        return [hit()], self.best


def hit(text="ผลการวิจัยพบว่าครูร้อยละ 80 มีจิตวิญญาณความเป็นครูในระดับมาก"):
    return articles.ArticleHit(rec={
        "id": "G04-3", "sysid": "G04", "title": "จิตวิญญาณความเป็นครู",
        "short": "วัลนิกา ฉลากบาง (2559)", "journal": "วารสารมหาวิทยาลัยนครพนม",
        "heading": "ผลการวิจัย", "text": text}, rrf=0.03)


def rules(max_dense, exact=False):
    return SearchResult(query="q", max_dense=max_dense, exact_section=exact)


def routed(monkeypatch, article_best, rule_best, exact=False):
    monkeypatch.setattr(articles, "get_index", lambda: FakeIndex(article_best))
    return articles.route("จิตวิญญาณความเป็นครูคืออะไร", rules(rule_best, exact),
                          lambda q: [0.0])


def test_a_question_the_rules_answer_as_well_stays_with_the_rules(monkeypatch):
    # +0.063 is the closest any of the 108 rule questions came
    assert routed(monkeypatch, 0.764, 0.701) is None


def test_a_clearly_better_article_match_takes_the_question(monkeypatch):
    assert routed(monkeypatch, 0.747, 0.577)


def test_the_articles_catch_what_the_rules_refuse(monkeypatch):
    assert routed(monkeypatch, 0.60, 0.40)


def test_an_off_topic_question_reaches_neither(monkeypatch):
    # ราคาทองวันนี้: 0.391 against the articles, 0.318 against the rules
    assert routed(monkeypatch, 0.391, 0.318) is None


def test_naming_a_rule_number_keeps_the_question_on_the_rules(monkeypatch):
    assert routed(monkeypatch, 0.80, 0.50, exact=True) is None


def test_no_article_index_means_no_route(monkeypatch):
    monkeypatch.setattr(articles, "get_index", lambda: None)
    assert articles.route("จิตวิญญาณความเป็นครูคืออะไร", rules(0.3), lambda q: [0.0]) is None


# ---------------------------------------------------------------- the answer

GOOD = ("จิตวิญญาณความเป็นครูคือการรักและศรัทธาในวิชาชีพ [1]\n\n"
        "งานวิจัยนี้พบว่าครูในกลุ่มตัวอย่างร้อยละ 80 มีจิตวิญญาณความเป็นครูในระดับมาก [1]")


def written(monkeypatch, draft):
    async def fake(system, user):
        return draft
    monkeypatch.setattr(articles, "complete", fake)
    return asyncio.run(articles.write("จิตวิญญาณความเป็นครูคืออะไร", [hit()]))


def test_the_citation_is_copied_from_the_record(monkeypatch):
    answer = written(monkeypatch, GOOD)
    assert "(วัลนิกา ฉลากบาง, 2559)" in answer.text
    assert "[1]" not in answer.text
    assert answer.citations == [
        "วัลนิกา ฉลากบาง (2559) จิตวิญญาณความเป็นครู — วารสารมหาวิทยาลัยนครพนม"]


def test_the_answer_says_it_is_not_a_rule(monkeypatch):
    answer = written(monkeypatch, GOOD)
    assert answer.text.startswith(articles.NOTICE)
    assert answer.source == "articles"
    assert articles.DISCLAIMER in answer.for_line()
    assert "อ้างจากตัวบท" not in answer.for_line()


@pytest.mark.parametrize("draft", [
    "ไม่มีข้อมูลพอ",
    # nothing cited
    "จิตวิญญาณความเป็นครูคือการรักและศรัทธาในวิชาชีพ เอาใจใส่ศิษย์อย่างเสมอภาค และพัฒนาตนเองอยู่เสมอ",
    # a pointer to a passage that was never supplied
    "จิตวิญญาณความเป็นครูคือการรักและศรัทธาในวิชาชีพ เอาใจใส่ศิษย์อย่างเสมอภาค และพัฒนาตนเองอยู่เสมอ [7]",
    # an article is not a rule, and may not be cited as one
    GOOD + "\nเรื่องนี้เป็นไปตามข้อ 8 ของข้อบังคับคุรุสภา [1]",
    # a figure the passage does not contain
    GOOD.replace("ร้อยละ 80", "ร้อยละ 95"),
])
def test_a_draft_that_cannot_be_stood_behind_is_dropped(monkeypatch, draft):
    answer = written(monkeypatch, draft)
    assert not answer.in_scope and answer.source == "articles"
    assert answer.text.startswith(articles.UNANSWERED)
    # nothing the model wrote survives, only the name of the article found
    assert "ร้อยละ" not in answer.text and "ข้อ 8" not in answer.text
    assert answer.citations == [hit().citation]


def test_ordinary_words_starting_with_kho_are_not_rule_numbers():
    assert articles.reject(GOOD + "\nข้อเสนอแนะ 2 ประการของบทความนี้ [1]", [hit()]) is None


def test_the_same_article_is_not_named_twice_in_a_row():
    text, cited = articles.resolve("ครูรักศิษย์ [1] [1]\nครูพัฒนาตน [1]  ", [hit()])
    assert text == "ครูรักศิษย์ (วัลนิกา ฉลากบาง, 2559)\nครูพัฒนาตน (วัลนิกา ฉลากบาง, 2559)"
    assert len(cited) == 1


def test_a_short_tail_is_not_cut_off_from_its_sentence():
    ranking = "ก" * 990 + " และ 4) ด้านความรักและศรัทธาในวิชาชีพครู ตามลำดับ"
    assert list(ex.split_long(ranking)) == [ranking]
    assert len(list(ex.split_long("ก " * 900))) == 2


def test_the_abstract_of_the_best_article_comes_along():
    index = articles.ArticleIndex.__new__(articles.ArticleIndex)
    index.corpus = [{"id": "G04-1", "sysid": "G04", "heading": "บทคัดย่อ"},
                    {"id": "G04-2", "sysid": "G04", "heading": "บทนำ"},
                    {"id": "G09-1", "sysid": "G09", "heading": "บทคัดย่อ"}]
    index.abstracts = {"G04": [0], "G09": [2]}
    found = index.with_abstract([articles.ArticleHit(rec=index.corpus[1], rrf=0.1)])
    assert [h.rec["id"] for h in found] == ["G04-2", "G04-1"]


def test_asking_what_a_study_found_goes_to_the_articles(monkeypatch):
    monkeypatch.setattr(articles, "get_index", lambda: FakeIndex(0.76))
    asked = "งานวิจัยพบว่าจรรยาบรรณวิชาชีพครูมีกี่องค์ประกอบ"
    # two hundredths above the rules: not enough on its own
    assert articles.route(asked, rules(0.74), lambda q: [0.0])
    assert articles.route("จรรยาบรรณวิชาชีพครูมีกี่องค์ประกอบ", rules(0.74),
                          lambda q: [0.0]) is None


def test_a_word_the_rules_never_use_lowers_the_bar(monkeypatch):
    monkeypatch.setattr(articles, "get_index", lambda: FakeIndex(0.70))
    rule_words = {"วินัย": 0, "จรรยาบรรณ": 1}
    go = lambda q, lead: articles.route(q, rules(0.70 - lead), lambda _: [0.0], rule_words)
    assert go("นักศึกษาครูราชภัฏปฏิบัติตนตามจรรยาบรรณระดับใด", 0.047)
    # the same lead without such a word, and such a word without the lead
    assert go("ครูต้องมีวินัยอะไรบ้าง", 0.047) is None
    assert go("นักศึกษาครูราชภัฏปฏิบัติตนตามจรรยาบรรณระดับใด", 0.004) is None


def test_an_item_of_a_questionnaire_is_not_a_rule_of_law():
    scale = GOOD + "\nแบบวัดมี 20 ข้อ โดยข้อ 1 ถึงข้อ 10 วัดการปฏิบัติหน้าที่ครู [1]"
    assert articles.reject(scale, [hit("แบบวัดมีข้อคำถาม 20 ข้อ ร้อยละ 80")]) is None


def test_a_line_from_memory_is_removed_and_a_copied_one_is_kept():
    passage = hit("หลักจริยธรรมด้านการครองคน ได้แก่ พรหมวิหาร 4 สังคหวัตถุ 4 และอคติ 4")
    draft = ("หลักด้านการครองคน ได้แก่ พรหมวิหาร 4 สังคหวัตถุ 4 และอคติ 4 [1]\n"
             "• สังคหวัตถุ 4\n"
             "• สังคหวัตถุ 4 ได้แก่ ทาน สมถะ ปัญญา และวิริยะ")
    text, dropped = articles.drop_ungrounded(draft, [passage])
    assert "สมถะ" not in text and len(dropped) == 1
    assert "• สังคหวัตถุ 4" in text and "[1]" in text


def test_an_author_email_is_not_kept():
    assert "@" not in ex.unescape("มหาวิทยาลัยราชภัฏรำไพพรรณี * อีเมล: someone77@gmail.com")
