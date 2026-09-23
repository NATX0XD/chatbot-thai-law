# -*- coding: utf-8 -*-
"""Grid-search the fusion weights against the labelled evaluation set.

Records how settings.weight_dense / weight_bm25 / guarantee_top were chosen.
Re-run after changing the embedding model or the corpus:

    python -m ingest.tune_fusion

Probes come from data/eval/ksp_questions.jsonl -- the fifty answerable ones,
each labelled with the rules that answer it as "sysid:section". Reported:

    doc@1   the right document is the top hit
    doc@3   it appears in the top three
    rule@1  the exact rule that answers the question is the top hit
    rule@6  it appears anywhere in what the model is shown

rule@6 is the one that decides whether a correct answer is reachable at all;
the others describe how much work the model has to do to find it.

The supersession penalty is applied here exactly as app/retriever.py applies it,
because leaving it out would tune the weights against a ranking the bot does not
actually serve.
"""
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import DATA_DIR, settings  # noqa: E402
from app.query_expand import expand  # noqa: E402
from app.retriever import (  # noqa: E402
    SECTION_Q_RE, SUPERSEDED_PENALTY, THAI_DIGITS, Retriever,
)

EVAL_PATH = os.path.join(DATA_DIR, "eval", "ksp_questions.jsonl")

R = Retriever()


def probes():
    """(question, {"sysid:section", ...}) for every answerable, labelled entry."""
    if not os.path.exists(EVAL_PATH):
        sys.exit(f"ไม่พบชุดประเมิน {EVAL_PATH}")
    out = []
    with open(EVAL_PATH, encoding="utf-8") as handle:
        for line in handle:
            entry = json.loads(line)
            if entry["expect"] == "answer" and entry["gold_ids"]:
                out.append((entry["question"], set(entry["gold_ids"])))
    return out


PROBES = probes()


def key(rec) -> str:
    return f"{rec['sysid']}:{rec['section']}"


def run(w_dense, w_bm25, g_dense, g_bm25, top_k=6):
    doc1 = doc3 = rule1 = rule6 = 0
    for question, gold in PROBES:
        gold_docs = {g.split(":")[0] for g in gold}
        query, _ = expand(question.translate(THAI_DIGITS))
        dense, _dscore = R._dense(query, settings.top_k_dense)
        sparse, _bscore = R._sparse(query, settings.top_k_bm25)

        fused = {}
        for ranking, weight in ((dense, w_dense), (sparse, w_bm25)):
            for rank, idx in enumerate(ranking):
                idx = int(idx)
                fused[idx] = fused.get(idx, 0.0) + weight / (settings.rrf_k + rank + 1)

        wanted = set(SECTION_Q_RE.findall(query))
        for idx in list(fused):
            if wanted and R.corpus[idx]["section"] in wanted:
                fused[idx] += 0.5
            if R.corpus[idx].get("superseded_by"):
                fused[idx] *= SUPERSEDED_PENALTY

        selected = []
        for idx in [int(i) for i in dense[:g_dense]] + [int(i) for i in sparse[:g_bm25]]:
            if idx not in selected and not R.corpus[idx].get("superseded_by"):
                selected.append(idx)
        for idx in sorted(fused, key=lambda i: -fused[i]):
            if len(selected) >= top_k:
                break
            if idx not in selected:
                selected.append(idx)
        recs = [R.corpus[i] for i in sorted(selected[:top_k], key=lambda i: -fused[i])]

        if recs and recs[0]["sysid"] in gold_docs:
            doc1 += 1
        if any(r["sysid"] in gold_docs for r in recs[:3]):
            doc3 += 1
        if recs and key(recs[0]) in gold:
            rule1 += 1
        if any(key(r) in gold for r in recs):
            rule6 += 1
    return doc1, doc3, rule1, rule6


def pct(n):
    return f"{n:>3}/{len(PROBES):<3} {n / len(PROBES):>5.0%}"


def main():
    print(f"{len(PROBES)} labelled questions from {EVAL_PATH}\n")
    header = (f"{'w_dense':>7} {'w_bm25':>6} {'gD':>3} {'gB':>3} | "
              f"{'doc@1':>11} {'doc@3':>11} {'rule@1':>11} {'rule@6':>11}")
    print(header)

    best = None
    for wd, wb, gd, gb in itertools.product([1.0, 1.5, 2.0, 3.0],
                                            [0.0, 0.25, 0.5, 1.0],
                                            [0, 1, 2, 3], [0, 1, 2]):
        d1, d3, r1, r6 = run(wd, wb, gd, gb)
        # rule@6 decides reachability, so it is weighted above the rest
        score = 2 * r6 + r1 + d1 + d3
        if best is None or score > best[0]:
            best = (score, wd, wb, gd, gb, d1, d3, r1, r6)
        if (wd, wb) in [(3.0, 0.25), (2.0, 0.5), (3.0, 0.0)] and (gd, gb) in ((2, 0), (0, 0)):
            print(f"{wd:>7} {wb:>6} {gd:>3} {gb:>3} | "
                  f"{pct(d1)} {pct(d3)} {pct(r1)} {pct(r6)}")

    print()
    print(f"BEST: w_dense={best[1]} w_bm25={best[2]} "
          f"guarantee_dense={best[3]} guarantee_bm25={best[4]}")
    print(f"      doc@1 {pct(best[5])}  doc@3 {pct(best[6])}  "
          f"rule@1 {pct(best[7])}  rule@6 {pct(best[8])}")

    d1, d3, r1, r6 = run(settings.weight_dense, settings.weight_bm25,
                         settings.guarantee_top, settings.guarantee_bm25)
    print(f"CURRENT: w_dense={settings.weight_dense} w_bm25={settings.weight_bm25} "
          f"guarantee_top={settings.guarantee_top} "
          f"guarantee_bm25={settings.guarantee_bm25}")
    print(f"      doc@1 {pct(d1)}  doc@3 {pct(d3)}  rule@1 {pct(r1)}  rule@6 {pct(r6)}")


if __name__ == "__main__":
    main()
