# -*- coding: utf-8 -*-
"""Recall@k of the labelled KSP questions, at several values of guarantee_bm25.

    .venv/bin/python -m ingest.eval_ksp_recall

data/eval/ksp_questions.jsonl carries gold_ids of the form "ksp-2550:5". This
asks how often those rules survive into the eight chunks the answer is written
from, which is the ceiling on answer accuracy: a rule that is not retrieved
cannot be cited, and no amount of prompt work recovers it.

The sweep exists because the two retrievers disagree about this corpus. Its
regulations restate the same duty once per profession, so four chunks differ
only in the opening noun; BM25 separates them on the question's own words and
the dense encoder sees four near-identical vectors and ranks none of them.
guarantee_bm25 is how many of BM25's best keep a seat regardless of the fused
score, and the right value is an empirical question, not a taste.
"""
from __future__ import annotations

import json
import os

from app.config import settings
from app.retriever import get_retriever

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.path.join(BASE_DIR, "data", "eval", "ksp_questions.jsonl")


def main() -> None:
    with open(QUESTIONS, encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]
    cases = [c for c in cases if c.get("gold_ids")]
    retriever = get_retriever()

    baseline = settings.guarantee_bm25
    print(f"{len(cases)} labelled questions, top_k_final={settings.top_k_final}\n")
    print(f"{'guarantee_bm25':>15}{'recall':>9}{'full':>7}{'miss':>7}")
    for value in (1, 2, 3, 4):
        settings.guarantee_bm25 = value
        found = full = 0
        missed = []
        for case in cases:
            gold = {tuple(g.split(":")) for g in case["gold_ids"]}
            got = {(h.rec["sysid"], str(h.rec["section"]))
                   for h in retriever.search(case["question"]).hits}
            hit = gold & got
            found += len(hit) / len(gold)
            if hit == gold:
                full += 1
            else:
                missed.append(case["id"])
        print(f"{value:>15}{found / len(cases) * 100:>8.1f}%{full:>7}{len(missed):>7}"
              f"   {' '.join(missed[:8])}")
    settings.guarantee_bm25 = baseline


if __name__ == "__main__":
    main()
