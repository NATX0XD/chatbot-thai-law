# -*- coding: utf-8 -*-
"""Put each answer beside the verbatim text of every rule it cites.

    .venv/bin/python -m ingest.review_packet 7

Writes data/eval/review_packet_round<N>_1..4.md, fifteen questions per file.

An assessor who has to go looking for the text will read some of it and skim the
rest. Worse, the first version of this script matched citations with a regex
that could not span the nested brackets of a sub-item pointer -- "(ข้อบังคับ
คุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550 ข้อ 5(ข)(๑) หมวดของครู)" -- so most
items arrived with no rule text attached at all, and the assessor reading them
marked twenty answers wrong for citing rules it could not see. That measured the
packet, not the system. The check at the end of this script exists for that.

Citations are found by their unit word and number, and the instrument is read
from the text in front of them, which is how app/support.py resolves them too.
"""
from __future__ import annotations

import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(BASE_DIR, "data", "eval")
CORPUS = os.path.join(BASE_DIR, "data", "processed", "corpus_ksp.jsonl")
PER_FILE = 15

UNIT_NUMBER = re.compile(r"(ข้อ|มาตรา)\s*([๐-๙0-9]{1,3}(?:/[๐-๙0-9]{1,3})?)")
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
# how far back to look for the instrument name the citation belongs to
NAME_WINDOW = 120


def load_corpus() -> list[dict]:
    with open(CORPUS, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def cited_records(answer: str, recs: list[dict]) -> list[dict]:
    """Every record the answer cites, in the order it cites them."""
    by_short = {}
    by_number = {}
    for r in recs:
        by_short.setdefault((r["short"], r["unit"], str(r["section"])), r)
        by_number.setdefault((r["unit"], str(r["section"])), []).append(r)
    shorts = sorted({r["short"] for r in recs}, key=len, reverse=True)

    found: list[dict] = []
    seen: set[str] = set()
    plain = answer.translate(THAI_DIGITS)
    for m in UNIT_NUMBER.finditer(plain):
        unit, number = m.group(1), m.group(2)
        before = plain[max(0, m.start() - NAME_WINDOW):m.start()]
        named = next((s for s in shorts if s in before), None)
        hits = ([by_short[(named, unit, number)]]
                if named and (named, unit, number) in by_short
                else by_number.get((unit, number), []))
        for rec in hits[:4]:
            if rec["id"] not in seen:
                seen.add(rec["id"])
                found.append(rec)
    return found


def main() -> None:
    round_no = sys.argv[1] if len(sys.argv) > 1 else "7"
    recs = load_corpus()
    with open(os.path.join(EVAL, f"user_answers_round{round_no}.json"),
              encoding="utf-8") as fh:
        answers = json.load(fh)

    items, missing = [], []
    for a in answers:
        block = [f"### {a['id']}  [{a['phrasing']}]",
                 f"คำถาม: {a['question']}", "", "คำตอบ:", a["answer"], ""]
        cited = cited_records(a["answer"], recs)
        for rec in cited:
            block.append(f"  [ตัวบท {rec['short']} {rec['unit']} {rec['section']}]"
                         f"  ({' > '.join(rec.get('chapters') or [])})")
            block.append(f"  {rec['text']}")
            block.append("")
        if not cited:
            block.append("  (คำตอบนี้ไม่ได้อ้างข้อหรือมาตราใด)")
            block.append("")
            if UNIT_NUMBER.search(a["answer"]):
                missing.append(a["id"])
        block.append("-" * 70)
        items.append("\n".join(block))

    for start in range(0, len(items), PER_FILE):
        path = os.path.join(EVAL, f"review_packet_round{round_no}_"
                                  f"{start // PER_FILE + 1}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(items[start:start + PER_FILE]))
        print(f"wrote {path}")

    quoted = sum(1 for i in items if "[ตัวบท" in i)
    print(f"\n{quoted}/{len(items)} items carry the text of the rules they cite")
    if missing:
        raise SystemExit(f"these cite a rule but got no text: {', '.join(missing)}")


if __name__ == "__main__":
    main()
