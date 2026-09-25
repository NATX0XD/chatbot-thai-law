# -*- coding: utf-8 -*-
"""Put the three assessors' outcome codes side by side.

    .venv/bin/python -m ingest.score_assessors

Reads data/eval/coding_assessor{1,2,3}.json, prints the three tables บทที่ 4
needs, and writes data/eval/assessor_summary.json for the report builder.

Also prints where the assessors disagreed. That number belongs in the thesis:
three readers who never spoke to each other and still agree is a different
claim from three readers who split, and the reader of the thesis cannot tell
which it was from an average.
"""
from __future__ import annotations

import collections
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(BASE_DIR, "data", "eval")
CORRECT = {1, 2}          # ตรง-correct and คลุมเครือ-correct
LABELS = {
    1: "ถามด้วยคำตรงตัวบท ตอบถูกต้อง",
    2: "ถามด้วยภาษาพูด ตอบถูกต้อง",
    0: "ถามด้วยคำตรงตัวบท ตอบไม่ถูกต้อง",
    3: "ถามด้วยภาษาพูด ตอบไม่ถูกต้อง",
}


def load(n: int) -> dict[str, int]:
    with open(os.path.join(EVAL, f"coding_assessor{n}.json"), encoding="utf-8") as fh:
        return {row["id"]: row["code"] for row in json.load(fh)}


def main() -> None:
    codings = {n: load(n) for n in (1, 2, 3)}
    ids = sorted(codings[1])
    total = len(ids)

    print(f"ตารางที่ 4-1  ผลรายบุคคล ({total} คำถามต่อคน)\n")
    print(f"{'ผู้ประเมิน':<12}{'ทั้งหมด':>8}{'ถูก':>7}{'ไม่ถูก':>8}{'ค่าความถูกต้อง':>16}")
    per_person = {}
    for n, coding in codings.items():
        right = sum(1 for i in ids if coding[i] in CORRECT)
        per_person[n] = right
        print(f"{'คนที่ ' + str(n):<12}{total:>8}{right:>7}{total - right:>8}"
              f"{right / total * 100:>15.2f}%")

    tests = total * len(codings)
    right = sum(per_person.values())
    print(f"\nตารางที่ 4-2  โดยรวม\n")
    print(f"  จำนวนการทดสอบทั้งหมด        {tests}")
    print(f"  คำตอบที่ถูกต้อง             {right}")
    print(f"  คำตอบที่ไม่ถูกต้อง           {tests - right}")
    print(f"  ค่าความถูกต้องโดยรวม        {right / tests * 100:.2f}%")

    print(f"\nตารางที่ 4-3  การกระจายรหัสผลลัพธ์\n")
    spread = collections.Counter(c for coding in codings.values()
                                 for c in coding.values())
    for code in (1, 2, 0, 3):
        n = spread[code]
        print(f"  {code}  {LABELS[code]:<36}{n:>5}{n / tests * 100:>9.2f}%")
    print(f"     {'รวม':<36}{tests:>5}{100.0:>9.2f}%")

    # by phrasing, which is what the code split is for
    with open(os.path.join(EVAL, "user_questions.jsonl"), encoding="utf-8") as fh:
        phrasing = {json.loads(line)["id"]: json.loads(line)["phrasing"]
                    for line in fh if line.strip()}
    print()
    for kind in ("ตรง", "คลุมเครือ"):
        subset = [i for i in ids if phrasing[i] == kind]
        hits = sum(1 for i in subset for c in codings.values() if c[i] in CORRECT)
        asked = len(subset) * len(codings)
        print(f"  คำถามแบบ{kind:<12}{hits}/{asked} = {hits / asked * 100:.2f}%")

    disputed = [i for i in ids
                if len({codings[n][i] in CORRECT for n in codings}) > 1]
    unanimous_right = [i for i in ids
                       if all(codings[n][i] in CORRECT for n in codings)]
    print(f"\n  ตัดสินตรงกันทั้งสามคน       {total - len(disputed)}/{total} "
          f"({(total - len(disputed)) / total * 100:.1f}%)")
    print(f"  เห็นตรงกันว่าถูกทั้งสามคน    {len(unanimous_right)}/{total}")
    if disputed:
        print(f"  เคสที่เห็นไม่ตรงกัน          {', '.join(disputed)}")

    summary = {
        "questions": total,
        "assessors": len(codings),
        "per_person": {str(n): {"right": r, "wrong": total - r,
                                "accuracy": round(r / total * 100, 2)}
                       for n, r in per_person.items()},
        "overall": {"tests": tests, "right": right, "wrong": tests - right,
                    "accuracy": round(right / tests * 100, 2)},
        "codes": {str(c): {"n": spread[c], "percent": round(spread[c] / tests * 100, 2)}
                  for c in (1, 2, 0, 3)},
        "agreement": {"unanimous": total - len(disputed), "disputed": disputed},
    }
    path = os.path.join(EVAL, "assessor_summary.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
