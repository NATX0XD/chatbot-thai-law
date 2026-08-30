# -*- coding: utf-8 -*-
"""Measure retrieval against the WangchanX question set, which carries gold sections.

ingest/tune_fusion.py chooses the fusion weights on 12 hand-written probes. That
is enough to pick between settings and far too small to state an accuracy with.
data/processed/qa_pairs.jsonl holds 11,953 expert-checked questions, each labelled
with the act and section that answers it, and 2,875 of them name a section this
corpus actually contains -- the rest point at acts outside it, mostly the codes.
Those 2,875 are a real evaluation set, and this script is what reads it.

    python -m ingest.eval_retrieval                 # 400 questions from the test split
    python -m ingest.eval_retrieval --n 0           # all of them
    python -m ingest.eval_retrieval --split train

What is measured, per question:

  hit@k   the gold section appears in the top k results
  MRR     1 / rank of the first gold section, 0 if it is absent
  refused the cosine gate would reject the question -- a false refusal here,
          since the corpus demonstrably contains the answer

Dense-only and BM25-only are scored from the same retrieval calls, so the cost of
the comparison is one embedding request per question rather than three.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import PROCESSED_DIR, settings  # noqa: E402
from app.coverage import find_gap  # noqa: E402
from app.query_expand import expand  # noqa: E402
from app.retriever import SECTION_Q_RE, THAI_DIGITS, Retriever  # noqa: E402

QA_PATH = os.path.join(PROCESSED_DIR, "qa_pairs.jsonl")
SEC_RE = re.compile(r"^(.*?)\s*มาตรา\s*(\S+)$")
TOP_K = 6


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load_gold(corpus_keys: set, split: str) -> list[tuple[str, set]]:
    """Questions whose labelled section is present in this corpus."""
    out = []
    with open(QA_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if split != "all" and d.get("split") != split:
                continue
            gold = set()
            for g in d.get("sections") or []:
                m = SEC_RE.match(norm(g))
                if not m:
                    continue
                pair = (norm(m.group(1)), m.group(2))
                if pair in corpus_keys:
                    gold.add(pair)
            if gold and d.get("question"):
                out.append((d["question"], gold))
    return out


def rank_of_gold(order: list[int], corpus, gold: set) -> int | None:
    """1-based position of the first result that is a labelled section."""
    for i, idx in enumerate(order, start=1):
        rec = corpus[idx]
        if (norm(rec["act"]), rec["section"]) in gold:
            return i
    return None


class Metric:
    def __init__(self, name: str):
        self.name = name
        self.n = 0
        self.hits = {1: 0, 3: 0, 6: 0}
        self.mrr = 0.0

    def add(self, rank: int | None) -> None:
        self.n += 1
        if rank is None:
            return
        self.mrr += 1.0 / rank
        for k in self.hits:
            if rank <= k:
                self.hits[k] += 1

    def row(self) -> str:
        p = lambda x: f"{100 * x / self.n:5.1f}%" if self.n else "    -"
        return (f"{self.name:<22} {p(self.hits[1])} {p(self.hits[3])} "
                f"{p(self.hits[6])} {self.mrr / self.n if self.n else 0:8.3f}")


def fuse(dense, sparse, w_dense, w_bm25, guarantee, corpus, top_k=TOP_K):
    """The production fusion, lifted out of Retriever.search so the baselines can
    reuse the same two rankings instead of paying for retrieval three times."""
    fused: dict[int, float] = {}
    for ranking, weight in ((dense, w_dense), (sparse, w_bm25)):
        for rank, idx in enumerate(ranking):
            idx = int(idx)
            fused[idx] = fused.get(idx, 0.0) + weight / (settings.rrf_k + rank + 1)
    selected: list[int] = []
    for idx in [int(i) for i in dense[:guarantee]]:
        if idx not in selected:
            selected.append(idx)
    for idx in sorted(fused, key=lambda i: -fused[i]):
        if len(selected) >= top_k:
            break
        if idx not in selected:
            selected.append(idx)
    return sorted(selected[:top_k], key=lambda i: -fused[i])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400, help="0 = every eligible question")
    ap.add_argument("--split", default="test", choices=["test", "train", "all"])
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    r = Retriever()
    if r.vectors is None:
        sys.exit("dense index missing -- run: python -m ingest.build_index --dense")

    keys = {(norm(rec["act"]), rec["section"]) for rec in r.corpus}
    items = load_gold(keys, args.split)
    print(f"eligible questions in {args.split}: {len(items):,}")
    if args.n and args.n < len(items):
        random.Random(args.seed).shuffle(items)
        items = items[:args.n]
    print(f"evaluating: {len(items):,}\n")

    hybrid = Metric("hybrid (production)")
    dense_only = Metric("dense only")
    bm25_only = Metric("BM25 only")
    refused_gate = refused_rule = 0

    t0 = time.time()
    for i, (question, gold) in enumerate(items, start=1):
        asked = question.translate(THAI_DIGITS)
        if find_gap(asked):
            # the coverage rule fires before retrieval, so a question it catches is
            # never answered -- and this set proves the corpus does hold the answer
            refused_rule += 1
        query, _ = expand(asked)
        dense, dense_scores = r._dense(query, settings.top_k_dense)
        sparse, _ = r._sparse(query, settings.top_k_bm25)

        if max(dense_scores.values(), default=0.0) < settings.min_dense_sim \
                and not SECTION_Q_RE.search(query):
            refused_gate += 1

        order = fuse(dense, sparse, settings.weight_dense, settings.weight_bm25,
                     settings.guarantee_top, r.corpus)
        hybrid.add(rank_of_gold(order, r.corpus, gold))
        dense_only.add(rank_of_gold([int(x) for x in dense[:TOP_K]], r.corpus, gold))
        bm25_only.add(rank_of_gold([int(x) for x in sparse[:TOP_K]], r.corpus, gold))

        if i % 25 == 0:
            print(f"  {i}/{len(items)}  {time.time() - t0:.0f}s", flush=True)

    n = len(items)
    print(f"\n{'':<22} {'hit@1':>6} {'hit@3':>6} {'hit@6':>6} {'MRR@6':>8}")
    print("-" * 54)
    for m in (hybrid, dense_only, bm25_only):
        print(m.row())

    print(f"\nfalse refusals on questions the corpus can answer ({n} asked)")
    print(f"  cosine gate < {settings.min_dense_sim}      {refused_gate:>5}"
          f"  {100 * refused_gate / n:5.1f}%")
    print(f"  coverage rule fired         {refused_rule:>5}"
          f"  {100 * refused_rule / n:5.1f}%")
    print(f"\n{time.time() - t0:.0f}s total, {(time.time() - t0) / n:.2f}s per question")


if __name__ == "__main__":
    main()
