# -*- coding: utf-8 -*-
"""Ask the running system all of data/eval/user_questions.jsonl and save what
it says, so that several assessors judge the same answers.

    .venv/bin/uvicorn app.main:app --port 8077 &
    .venv/bin/python -m ingest.collect_answers

Writes data/eval/user_answers.json.

Collecting once and judging many times is not a convenience. The provider does
not honour a fixed seed -- three calls at temperature 0 return two different
answers -- so if each assessor asked the questions themselves, they would each
be judging a different system, and the spread between them would measure the
provider rather than the assessors. One set of answers, three readers.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.path.join(BASE_DIR, "data", "eval", "user_questions.jsonl")
ANSWERS = os.path.join(BASE_DIR, "data", "eval", "user_answers.json")
ENDPOINT = "http://localhost:8077/chat"


def ask(question: str) -> dict:
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def main() -> None:
    with open(QUESTIONS, encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]

    collected = []
    for i, case in enumerate(cases, 1):
        started = time.monotonic()
        reply = ask(case["question"])
        collected.append({
            **case,
            "answer": reply["answer"],
            "in_scope": reply["in_scope"],
            "error": reply["error"],
            "faults": reply.get("faults", []),
            "repair": reply.get("repair"),
            "sources": [s["citation"] for s in reply["sources"][:8]],
            "seconds": round(time.monotonic() - started, 1),
        })
        print(f"[{i:2}/{len(cases)}] {collected[-1]['seconds']:5.1f}s  "
              f"{case['id']}  {case['question'][:46]}")

    with open(ANSWERS, "w", encoding="utf-8") as fh:
        json.dump(collected, fh, ensure_ascii=False, indent=1)
    total = sum(c["seconds"] for c in collected)
    print(f"\nwrote {ANSWERS}  ({len(collected)} answers, {total:.0f}s total, "
          f"median {sorted(c['seconds'] for c in collected)[len(collected) // 2]:.1f}s)")


if __name__ == "__main__":
    main()
