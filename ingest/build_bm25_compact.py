# -*- coding: utf-8 -*-
"""Convert the pickled BM25Okapi into a compact numpy inverted index.

rank_bm25 keeps one Python dict of term->count per document. At 27,203 documents
and 1.46M postings that is 202 MB of resident memory -- measured, and by itself
more than a Render free instance's entire 512 MB budget. The same postings held
as flat numpy arrays cost about 8 MB, because the cost was never the data: it was
1.46M boxed ints and 27,203 dict headers.

Scoring is unchanged. BM25Okapi.get_scores computes, for each query term q:

    idf[q] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avgdl))

The denominator's second term depends only on the document, so it is precomputed
here as `norm[d]` and the runtime is left with one multiply and one divide per
posting -- and it touches only the postings of the query's terms, instead of
walking all 27,203 documents the way get_scores does.

    python -m ingest.build_bm25_compact
"""
import json
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402

# term frequency is stored as uint8; anything above this is clipped. The corpus
# tops out at 125, so the clip never fires today -- it is a guard for re-ingests.
TF_MAX = 255


def main():
    with open(settings.bm25_path, "rb") as f:
        bm = pickle.load(f)

    terms = sorted(bm.idf)
    term_id = {t: i for i, t in enumerate(terms)}
    n_terms, n_docs = len(terms), bm.corpus_size

    # count postings per term first so the flat arrays can be filled in place
    counts = np.zeros(n_terms, dtype=np.int64)
    for freqs in bm.doc_freqs:
        for t in freqs:
            counts[term_id[t]] += 1

    ptr = np.zeros(n_terms + 1, dtype=np.int64)
    np.cumsum(counts, out=ptr[1:])
    nnz = int(ptr[-1])

    docs = np.zeros(nnz, dtype=np.int32)
    tf = np.zeros(nnz, dtype=np.uint8)
    cursor = ptr[:-1].copy()
    for d, freqs in enumerate(bm.doc_freqs):
        for t, f in freqs.items():
            i = term_id[t]
            at = cursor[i]
            docs[at] = d
            tf[at] = min(f, TF_MAX)
            cursor[i] = at + 1

    idf = np.array([bm.idf[t] for t in terms], dtype=np.float32)
    doc_len = np.asarray(bm.doc_len, dtype=np.float32)
    norm = (bm.k1 * (1 - bm.b + bm.b * doc_len / bm.avgdl)).astype(np.float32)

    out = settings.bm25_compact_path
    np.savez(out, ptr=ptr, docs=docs, tf=tf, idf=idf, norm=norm,
             k1=np.float32(bm.k1), n_docs=np.int64(n_docs))
    with open(settings.bm25_vocab_path, "w", encoding="utf-8") as f:
        json.dump(terms, f, ensure_ascii=False)

    old = os.path.getsize(settings.bm25_path) / 1e6
    new = (os.path.getsize(out) + os.path.getsize(settings.bm25_vocab_path)) / 1e6
    print(f"docs {n_docs:,}  terms {n_terms:,}  postings {nnz:,}")
    print(f"{old:.1f} MB pickle -> {new:.1f} MB compact")


if __name__ == "__main__":
    main()
