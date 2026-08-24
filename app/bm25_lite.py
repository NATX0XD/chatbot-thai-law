# -*- coding: utf-8 -*-
"""BM25 scoring over the compact inverted index built by ingest.build_bm25_compact.

Drop-in for the part of rank_bm25's BM25Okapi that the retriever actually uses:
`get_scores(tokens) -> np.ndarray of length n_docs`. Results are identical to the
pickle's, to float32 rounding -- ingest.build_bm25_compact copies k1, b and the
idf table straight out of the fitted model rather than refitting anything.
"""
from __future__ import annotations

import json

import numpy as np

from app.config import settings


class BM25Lite:
    def __init__(self, index_path: str | None = None, vocab_path: str | None = None):
        with open(vocab_path or settings.bm25_vocab_path, encoding="utf-8") as f:
            terms = json.load(f)
        self.term_id = {t: i for i, t in enumerate(terms)}
        z = np.load(index_path or settings.bm25_compact_path)
        # materialised on purpose: the whole index is ~8 MB, and NpzFile would
        # otherwise re-inflate a member from the zip on every attribute access
        self.ptr = z["ptr"]
        self.docs = z["docs"]
        self.tf = z["tf"]
        self.idf = z["idf"]
        self.norm = z["norm"]
        self.k1 = float(z["k1"])
        self.n_docs = int(z["n_docs"])

    def get_scores(self, tokens) -> np.ndarray:
        scores = np.zeros(self.n_docs, dtype=np.float32)
        for token in tokens:
            i = self.term_id.get(token)
            # a repeated query token is scored again, deliberately: BM25Okapi
            # iterates the token list as given, so deduplicating here would change
            # the ranking the fusion weights and the probe set were tuned against
            if i is None:
                continue
            lo, hi = self.ptr[i], self.ptr[i + 1]
            d = self.docs[lo:hi]
            f = self.tf[lo:hi].astype(np.float32)
            # np.add.at is the scatter-add form; a term's postings are unique per
            # document, so plain indexed assignment would also work, but this keeps
            # the code correct if a future ingest ever emits duplicate postings
            np.add.at(scores, d, self.idf[i] * f * (self.k1 + 1.0)
                      / (f + self.norm[d]))
        return scores
