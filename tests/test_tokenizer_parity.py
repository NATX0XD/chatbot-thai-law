# -*- coding: utf-8 -*-
"""The vendored newmm must tokenise exactly like the pythainlp it was copied from.

BM25 postings are keyed by token string. A tokeniser that splits even slightly
differently turns a matching query term into a miss, and the failure is silent --
the bot simply retrieves worse. So this compares the two implementations over
real corpus text rather than a handful of phrases.

Skipped when pythainlp is not installed: the deployed image does not ship it,
which is the entire point of the vendoring.
"""
import json
import random

import pytest

from app.config import settings
from app.thai_tokenize import word_tokenize as vendored

pythainlp = pytest.importorskip("pythainlp.tokenize",
                                reason="pythainlp is a build-time dependency only")


def upstream(text, keep_whitespace=True):
    return pythainlp.word_tokenize(text, engine="newmm",
                                   keep_whitespace=keep_whitespace)


PHRASES = [
    "ถูกเลิกจ้าง ได้ค่าชดเชยเท่าไหร่",
    "มาตรา 118 ว่าอย่างไร",
    "เจ้าหนี้ทวงหนี้ตี 1 ผิดไหม",
    "ลูกจ้างบอกเลิกสัญญาจ้าง การบอกกล่าวล่วงหน้า",
    "เงิน1,234บาท19:32น 127.0.0.1",
    "พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562",
    "  ",
    "",
]


@pytest.mark.parametrize("text", PHRASES)
@pytest.mark.parametrize("keep_ws", [True, False])
def test_phrases_match(text, keep_ws):
    assert vendored(text, keep_whitespace=keep_ws) == upstream(text, keep_ws)


def test_corpus_sample_matches():
    """200 random section bodies, the text BM25 was actually fitted on."""
    with open(settings.corpus_path, encoding="utf-8") as f:
        lines = f.readlines()
    rng = random.Random(20260824)
    for line in rng.sample(lines, 200):
        text = json.loads(line)["text"][:1500]
        assert vendored(text, keep_whitespace=False) == upstream(text, False)
