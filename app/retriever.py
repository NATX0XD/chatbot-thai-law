# -*- coding: utf-8 -*-
"""Hybrid retrieval over the Act corpus: BM25 + dense, fused with RRF.

Why hybrid: Thai legal questions arrive in two very different shapes. Either the
user knows the vocabulary ("ค่าชดเชย มาตรา 118") -- BM25 nails those and dense
retrieval often does not, because embedding models flatten digits. Or the user
writes plain speech ("โดนไล่ออกกะทันหัน ได้เงินไหม") -- dense handles those and
BM25 returns nothing, since no section contains the word "ไล่ออก".

Reciprocal Rank Fusion is used for *ordering* because BM25 scores and cosine
similarities are not on a comparable scale and RRF needs no calibration.

RRF is useless for deciding *whether the corpus knows anything*, though: it is a
function of rank alone, so the top hit for "สูตรทำต้มยำกุ้ง" scores the same
0.0164 as the top hit for a real labour-law question. The in-scope decision
therefore reads the raw cosine and BM25 scores, which do carry magnitude.
"""
from __future__ import annotations

import os
import pickle
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.bm25_lite import BM25Lite
from app.config import settings
from app.corpus_store import open_corpus
from app.embed import get_embedder
from app.query_expand import expand
from app.thai_tokenize import word_tokenize

SECTION_Q_RE = re.compile(r"มาตรา\s*(\d+(?:/\d+)?)")
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


@dataclass
class Hit:
    rec: dict
    rrf: float
    dense_score: float = 0.0
    bm25_score: float = 0.0
    dense_rank: Optional[int] = None
    bm25_rank: Optional[int] = None

    @property
    def citation(self) -> str:
        return f"{self.rec['act']} มาตรา {self.rec['section']}"


@dataclass
class SearchResult:
    query: str                       # what was actually sent to the retrievers
    asked: str = ""                  # what the user typed
    added_terms: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    max_dense: float = 0.0
    max_bm25: float = 0.0
    exact_section: bool = False

    @property
    def in_scope(self) -> bool:
        """Does the corpus contain anything on this topic at all?

        Cosine only. BM25 is excluded on purpose -- calibration showed off-topic
        questions scoring higher on BM25 (15.1) than valid ones (12.6), because a
        long question shares common legal words with almost any section.

        Naming a section number explicitly overrides the gate: the user has told us
        which text they want, and a low cosine on "มาตรา 118 ว่าอย่างไร" says
        nothing about whether มาตรา 118 exists.
        """
        return self.exact_section or self.max_dense >= settings.min_dense_sim


class Retriever:
    """Loads the corpus and both indexes once, then answers queries in-process."""

    # rows of the vector matrix converted to float32 at a time. The stored index
    # is float16 and numpy has no BLAS path for float16 matmul, but converting the
    # whole matrix up front costs 111 MB resident. A 4096-row window costs 16 MB
    # and, being cache-sized, runs no slower than the one-shot conversion.
    DENSE_CHUNK = 4096

    def __init__(self, load_dense: bool = True):
        self.corpus = open_corpus(settings.corpus_path)

        # the compact index is the serving form and the pickle is the build
        # artefact it is derived from; prefer it when present, since loading the
        # pickle instead costs 202 MB against a 512 MB budget
        if os.path.exists(settings.bm25_compact_path):
            self.bm25 = BM25Lite()
            # the compact index is derived from bm25.pkl by a separate step, so a
            # rebuild that skipped it would leave a file that still loads cleanly
            # and scores the previous corpus. Nothing downstream would notice:
            # BM25 contributes ranking, not the in-scope gate, so the damage shows
            # up only as quietly worse answers.
            if self.bm25.n_docs != len(self.corpus):
                raise RuntimeError(
                    f"bm25/corpus mismatch: {self.bm25.n_docs} documents vs "
                    f"{len(self.corpus)} chunks. Re-run ingest.build_bm25_compact.")
        else:
            with open(settings.bm25_path, "rb") as f:
                self.bm25 = pickle.load(f)

        self.vectors = None
        self.embedder = None
        if load_dense and os.path.exists(settings.vectors_path):
            # memory-mapped: the OS pages rows in as the matmul walks them and can
            # evict them again under pressure, which a heap array cannot be
            self.vectors = np.load(settings.vectors_path, mmap_mode="r")
            if len(self.vectors) != len(self.corpus):
                raise RuntimeError(
                    f"index/corpus mismatch: {len(self.vectors)} vectors vs "
                    f"{len(self.corpus)} chunks. Re-run ingest.build_index.")

    # -- lazy so that BM25-only callers (and tests) never pay the model load --
    def _encode(self, query: str) -> np.ndarray:
        if self.embedder is None:
            self.embedder = get_embedder()
        return self.embedder.encode(query)

    def _dense(self, query: str, k: int):
        if self.vectors is None:
            return [], {}
        q = np.asarray(self._encode(query), dtype=np.float32)
        sims = np.empty(len(self.vectors), dtype=np.float32)
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            # Accelerate's BLAS raises spurious FP warnings for this matmul on
            # Apple Silicon; the result matches a float64 reference to 1e-7.
            for i in range(0, len(self.vectors), self.DENSE_CHUNK):
                block = np.asarray(self.vectors[i:i + self.DENSE_CHUNK],
                                   dtype=np.float32)
                sims[i:i + len(block)] = block @ q
        k = min(k, len(sims))
        top = np.argpartition(-sims, k - 1)[:k]
        order = top[np.argsort(-sims[top])]
        return list(order), {int(i): float(sims[i]) for i in order}

    def _sparse(self, query: str, k: int):
        tokens = word_tokenize(query, keep_whitespace=False)
        scores = self.bm25.get_scores(tokens)
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        order = [int(i) for i in top[np.argsort(-scores[top])] if scores[i] > 0]
        return order, {i: float(scores[i]) for i in order}

    def search(self, query: str, top_k: Optional[int] = None) -> SearchResult:
        top_k = top_k or settings.top_k_final
        # Normalise digits once, for every path. Doing it only before tokenising
        # made "มาตรา ๑๑๘" and "มาตรา 118" retrieve different sections, because the
        # embedder saw Thai numerals while the index prefix carries Arabic ones.
        asked = query.translate(THAI_DIGITS)
        # Append the statutory vocabulary for whatever colloquial phrasing was used;
        # without this, plain-speech questions retrieve the wrong act entirely.
        query, added_terms = expand(asked)
        dense, dense_scores = self._dense(query, settings.top_k_dense)
        sparse, bm25_scores = self._sparse(query, settings.top_k_bm25)

        fused: dict[int, float] = {}
        for ranking, weight in ((dense, settings.weight_dense),
                                (sparse, settings.weight_bm25)):
            for rank, idx in enumerate(ranking):
                idx = int(idx)
                fused[idx] = fused.get(idx, 0.0) + weight / (settings.rrf_k + rank + 1)

        # an explicit "มาตรา N" in the question is a hard constraint, not a hint
        wanted = set(SECTION_Q_RE.findall(query))
        exact = False
        if wanted:
            for idx in list(fused):
                if self.corpus[idx]["section"] in wanted:
                    # a long section is split across parts; part 0 opens the rule
                    # and is what someone asking for the section wants to read
                    fused[idx] += 0.5 if self.corpus[idx].get("part", 0) == 0 else 0.4
                    exact = True

        d_rank = {int(idx): r for r, idx in enumerate(dense)}
        b_rank = {int(idx): r for r, idx in enumerate(sparse)}
        # RRF's known failure: a chunk ranked #1 by one retriever but outside the
        # other's list scores 1/61, while a chunk sitting mid-table in both scores
        # ~1/31 + 1/31 and outranks it. For "ถูกเลิกจ้าง ได้ค่าชดเชยเท่าไหร่" that
        # buried มาตรา 118 -- the section stating the severance rates, and the top
        # dense hit at 0.667 -- below its own neighbours 119 to 122. So each
        # retriever's best few results keep a seat regardless of the fused score.
        selected: list[int] = []
        for idx in [int(i) for i in dense[:settings.guarantee_top]]:
            if idx not in selected:
                selected.append(idx)
        for idx in sorted(fused, key=lambda i: -fused[i]):
            if len(selected) >= top_k:
                break
            if idx not in selected:
                selected.append(idx)
        order = sorted(selected[:top_k], key=lambda i: -fused[i])

        return SearchResult(
            query=query,
            asked=asked,
            added_terms=added_terms,
            hits=[Hit(rec=self.corpus[i], rrf=fused[i],
                      dense_score=dense_scores.get(i, 0.0),
                      bm25_score=bm25_scores.get(i, 0.0),
                      dense_rank=d_rank.get(i), bm25_rank=b_rank.get(i))
                  for i in order],
            max_dense=max(dense_scores.values(), default=0.0),
            max_bm25=max(bm25_scores.values(), default=0.0),
            exact_section=exact,
        )


_retriever: Optional[Retriever] = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
