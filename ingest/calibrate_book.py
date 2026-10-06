# -*- coding: utf-8 -*-
"""Print the best cosine of each probe question against the textbook.

  python -m ingest.calibrate_book

`book_min_sim` in app/config.py is read from this output. The probes are in
data/eval/network_questions.jsonl, one per line, each with a `group`:

  book      answerable from the book
  beyond    about networking, but nothing the book covers
  offtopic  not about networking at all
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import book  # noqa: E402
from app.config import DATA_DIR, settings  # noqa: E402

PROBES = os.path.join(DATA_DIR, "eval", "network_questions.jsonl")


def main() -> None:
    if not os.path.exists(PROBES):
        raise SystemExit(f"ไม่พบ {PROBES}")
    with open(PROBES, encoding="utf-8") as handle:
        probes = [json.loads(line) for line in handle if line.strip()]
    index = book.get_index()
    groups: dict[str, list[tuple[float, str, str]]] = {}
    for probe in probes:
        hits, best = index.find(probe["question"])
        groups.setdefault(probe["group"], []).append(
            (best, hits[0].rec["id"], probe["question"]))
    for group, rows in groups.items():
        rows.sort()
        passed = sum(score >= settings.book_min_sim for score, _, _ in rows)
        print(f"\n{group}  n={len(rows)}  {rows[0][0]:.3f} – {rows[-1][0]:.3f}  "
              f"ผ่านด่าน {settings.book_min_sim}: {passed}")
        for score, top, question in rows:
            print(f"  {score:.3f}  {top:10s} {question[:70]}")


if __name__ == "__main__":
    main()
