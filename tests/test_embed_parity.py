# -*- coding: utf-8 -*-
"""The hosted embedder must return the same vectors the index was built with.

This is the one claim the whole serving change rests on: `vectors.npy` was
produced by sentence-transformers running BAAI/bge-m3 locally, and it is reused
untouched. If the provider serves a different checkpoint, a different pooling, or
a truncated dense head, every cosine shifts and `min_dense_sim = 0.54` stops
meaning what ingest/calibrate.py measured -- silently, as worse retrieval rather
than an error.

Needs both backends, so it is skipped unless EMBED_API_KEY is set and torch is
installed. Run it on a workstation before deploying, not in CI:

    EMBED_API_KEY=... .venv/bin/python -m pytest tests/test_embed_parity.py -q -s
"""
import numpy as np
import pytest

from app.config import settings

pytest.importorskip("sentence_transformers",
                    reason="local reference model not installed")
if not settings.embed_api_key:
    pytest.skip("EMBED_API_KEY not set", allow_module_level=True)

from app.embed import ApiEmbedder, LocalEmbedder  # noqa: E402

QUERIES = [
    "ถูกเลิกจ้าง ได้ค่าชดเชยเท่าไหร่",
    "มาตรา 118 ว่าอย่างไร",
    "เจ้าหนี้ทวงหนี้ตี 1 ผิดไหม",
    "ลูกจ้างบอกเลิกสัญญาจ้าง การบอกกล่าวล่วงหน้า สัญญาจ้างสิ้นสุด",
    "ข้อมูลส่วนบุคคล ความยินยอม",
    "สวัสดีครับ",
    "สูตรทำต้มยำกุ้ง",
]

# 0.99 is not a soft target. Two runs of the same checkpoint differ only by
# float rounding and land above 0.999; anything meaningfully below that means a
# different model, and the stored index would no longer be comparable.
MIN_COSINE = 0.99


@pytest.fixture(scope="module")
def pair():
    return LocalEmbedder(), ApiEmbedder()


@pytest.mark.parametrize("query", QUERIES)
def test_hosted_matches_local(pair, query):
    local, api = pair
    a, b = local.encode(query), api.encode(query)
    assert a.shape == b.shape, f"dimension differs: {a.shape} vs {b.shape}"
    cos = float(np.dot(a, b))
    print(f"  cos={cos:.6f}  {query}")
    assert cos >= MIN_COSINE, f"cosine {cos:.4f} for {query!r}"


def test_hosted_vectors_land_in_the_index_the_same_way(pair):
    """Cosine parity is necessary but the retrieved ranking is what matters."""
    from app.retriever import Retriever

    r = Retriever()
    local, api = pair
    for query in QUERIES[:4]:
        r.embedder = local
        want = [h.citation for h in r.search(query).hits]
        r.embedder = api
        got = [h.citation for h in r.search(query).hits]
        assert got == want, f"{query!r}\n  local {want}\n  api   {got}"
