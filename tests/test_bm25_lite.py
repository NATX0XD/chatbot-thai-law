# -*- coding: utf-8 -*-
"""The compact BM25 index must score exactly like the rank_bm25 model it replaces.

The fusion weights and the probe set in ingest/tune_fusion.py were tuned against
BM25Okapi's ranking. A scorer that merely ranks "about the same" would invalidate
that tuning without failing anything, so this asserts on the scores themselves and
on the full top-30 order, over the same queries the tuning used.

Skipped where rank_bm25 or bm25.pkl is absent -- the deployed image ships neither,
by design. Run it on the workstation after any rebuild of the index.
"""
import os
import pickle

import numpy as np
import pytest

from app.bm25_lite import BM25Lite
from app.config import settings
from app.thai_tokenize import word_tokenize

pytest.importorskip("rank_bm25", reason="build-time dependency only")
if not os.path.exists(settings.bm25_path):
    pytest.skip("bm25.pkl not present", allow_module_level=True)

QUERIES = [
    "ถูกเลิกจ้าง ได้ค่าชดเชยเท่าไหร่",
    "มาตรา 118 ว่าอย่างไร",
    "เจ้าหนี้ทวงหนี้ตี 1 ผิดไหม",
    "ลาออกต้องบอกล่วงหน้ากี่วัน",
    "ข้อมูลส่วนบุคคล ความยินยอม",
    "นายจ้างหักเงินเดือนได้ไหม",
    "หมิ่นประมาทออนไลน์",
    "สูตรทำต้มยำกุ้ง",                 # off-topic: must still agree
    "ทวงหนี้ ทวงหนี้ ทวงหนี้",          # a repeated token is scored once per
                                       # occurrence by BM25Okapi, not deduplicated
]

# float32 accumulation against rank_bm25's float64 sum; observed worst case is
# 2.6e-06, four orders of magnitude below the gap between adjacent BM25 scores
TOLERANCE = 1e-4


@pytest.fixture(scope="module")
def pair():
    with open(settings.bm25_path, "rb") as f:
        return pickle.load(f), BM25Lite()


@pytest.mark.parametrize("query", QUERIES)
def test_scores_match(pair, query):
    old, new = pair
    tokens = word_tokenize(query, keep_whitespace=False)
    a = np.asarray(old.get_scores(tokens), dtype=np.float64)
    b = np.asarray(new.get_scores(tokens), dtype=np.float64)
    assert a.shape == b.shape
    assert float(np.max(np.abs(a - b))) < TOLERANCE


@pytest.mark.parametrize("query", QUERIES)
def test_top_30_order_matches(pair, query):
    """Scores within tolerance are not enough; ties could still reorder."""
    old, new = pair
    tokens = word_tokenize(query, keep_whitespace=False)
    a = list(np.argsort(-np.asarray(old.get_scores(tokens)))[:30])
    b = list(np.argsort(-np.asarray(new.get_scores(tokens)))[:30])
    assert a == b


def test_unknown_terms_score_zero(pair):
    """A query of pure out-of-vocabulary tokens must not raise or score."""
    _, new = pair
    scores = new.get_scores(["zzzqqq", "ไม่มีคำนี้ในคลัง"])
    assert scores.shape == (new.n_docs,)
    assert not scores.any()
