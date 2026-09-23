# -*- coding: utf-8 -*-
"""Pick the in-scope threshold from data instead of guessing it.

Runs the evaluation set through the retriever and reports the score
distributions for the questions the corpus should answer and the ones it must
refuse, then says where the two separate.

    python -m ingest.calibrate

The probes live in data/eval/ksp_questions.jsonl rather than in this file, so
that the same sixty questions drive the threshold here and the ranking metrics
in ingest/eval_retrieval.py, and adding a probe means editing data rather than
editing three scripts.

The refusals split into two kinds, and only one of them is a threshold's job:

  off topic       not a legal question at all. These score low and the gate
                  catches them.
  out of scope    a real legal question whose governing law is not in this
                  corpus. These score *high* -- every one of them is about a
                  teacher -- and app/coverage.py catches them instead.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import DATA_DIR, settings  # noqa: E402
from app.coverage import find_gap  # noqa: E402
from app.retriever import Retriever  # noqa: E402

EVAL_PATH = os.path.join(DATA_DIR, "eval", "ksp_questions.jsonl")

# The out-of-scope half of the evaluation set is split again here, by whether a
# coverage rule exists for it. That split is what the report is about, so it is
# computed rather than written down.


def load():
    if not os.path.exists(EVAL_PATH):
        sys.exit(f"ไม่พบชุดประเมิน {EVAL_PATH}")
    with open(EVAL_PATH, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def split(entries):
    answerable = [e["question"] for e in entries if e["expect"] == "answer"]
    refusable = [e["question"] for e in entries if e["expect"] == "refuse"]
    covered = [q for q in refusable if find_gap(q)]
    uncovered = [q for q in refusable if not find_gap(q)]
    return answerable, covered, uncovered

def report(name, questions, retriever):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}")
    print(f"{'max_dense':>10} {'max_bm25':>9}  {'top hit':<44} question")
    rows = []
    for q in questions:
        r = retriever.search(q, top_k=1)
        top = r.hits[0].citation if r.hits else "-"
        rows.append((r.max_dense, r.max_bm25))
        print(f"{r.max_dense:>10.4f} {r.max_bm25:>9.2f}  {top[:44]:<44} {q[:40]}")
    dense = sorted(x for x, _ in rows)
    bm25 = sorted(y for _, y in rows)
    print(f"\n  dense  min={dense[0]:.4f}  median={dense[len(dense)//2]:.4f}  max={dense[-1]:.4f}")
    print(f"  bm25   min={bm25[0]:.2f}  median={bm25[len(bm25)//2]:.2f}  max={bm25[-1]:.2f}")
    return rows


def main():
    r = Retriever()
    if r.vectors is None:
        sys.exit("dense index missing -- run: python -m ingest.build_index --dense")

    entries = load()
    IN_SCOPE, MISSING_LAW, OFF_TOPIC = split(entries)
    good = report("IN SCOPE (ต้องตอบได้)", IN_SCOPE, r)
    bad = report("OFF TOPIC (ไม่มีกฎดัก ต้องตกด่านคะแนน)", OFF_TOPIC, r) or [(0.0, 0.0)]
    missing = report("OUT OF SCOPE (มีกฎดัก ต้องปฏิเสธ)", MISSING_LAW, r) or [(0.0, 0.0)]

    print(f"\n{'=' * 78}\nTHRESHOLD SEPARATION\n{'=' * 78}")
    lo_good = min(d for d, _ in good)
    hi_off = max(d for d, _ in bad)
    hi_missing = max(d for d, _ in missing)
    print(f"  dense, in-scope vs off-topic : {lo_good:.4f} vs {hi_off:.4f}"
          f"  -> {'separable' if lo_good > hi_off else 'OVERLAP'}")
    if lo_good > hi_off:
        print(f"     suggested MIN_DENSE_SIM = {(lo_good + hi_off) / 2:.3f}"
              f"   (current {settings.min_dense_sim})")
    print(f"  dense, in-scope vs missing-law: {lo_good:.4f} vs {hi_missing:.4f}"
          f"  -> {'separable' if lo_good > hi_missing else 'OVERLAP -- score cannot gate these'}")
    print("     missing-law questions are handled by app/coverage.py, not by a threshold:")
    print("     they retrieve a real, on-topic act that simply does not contain the answer.")
    lo_good_b = min(b for _, b in good)
    hi_bad_b = max(b for _, b in bad + missing)
    print(f"  bm25 , in-scope vs must-refuse: {lo_good_b:.2f} vs {hi_bad_b:.2f}"
          f"  -> {'separable' if lo_good_b > hi_bad_b else 'OVERLAP -- excluded from the gate'}")

    # end-to-end behaviour of both guard layers together
    def passes(questions):
        n = 0
        for q in questions:
            if find_gap(q):          # layer 1: known missing code
                continue
            if r.search(q).in_scope:  # layer 2: cosine gate
                n += 1
        return n

    print(f"\n  both guard layers, MIN_DENSE_SIM={settings.min_dense_sim}:")
    print(f"    in-scope answered   {passes(IN_SCOPE)}/{len(IN_SCOPE)}   (want {len(IN_SCOPE)})")
    print(f"    off-topic leaked    {passes(OFF_TOPIC)}/{len(OFF_TOPIC)}   (want 0)")
    print(f"    missing-law leaked  {passes(MISSING_LAW)}/{len(MISSING_LAW)}   (want 0)")


if __name__ == "__main__":
    main()
