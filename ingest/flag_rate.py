# -*- coding: utf-8 -*-
"""How often the claim check fires on answers a human reads as correct.

    .venv/bin/uvicorn app.main:app --port 8077 &
    .venv/bin/python -m ingest.flag_rate [n]

The number this prints is the one that decides whether the check is allowed to
drive the repair turn. It fires on a wrong citation and on a correct answer
alike; only measuring tells them apart, and the sixth acceptance round showed
what guessing costs -- a false positive on the five duties rewrote a correct
answer into one that counted three.

Answers are drawn from data/eval/ksp_questions.jsonl and printed in full next to
what fired, so the reading is done by eye. Nothing here scores itself.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

from app.config import settings
from app.corpus_store import open_corpus
from app.support import Corpus, impossible_citations, unsupported_claims

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.path.join(BASE_DIR, "data", "eval", "ksp_questions.jsonl")
ENDPOINT = "http://localhost:8077/chat"


def ask(question: str) -> dict:
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    corpus = Corpus(list(open_corpus(settings.corpus_path)))
    with open(QUESTIONS, encoding="utf-8") as fh:
        questions = [json.loads(line)["question"] for line in fh][:limit]

    flagged = blocked = refused = 0
    for i, question in enumerate(questions, 1):
        answer = ask(question)
        text = answer["answer"]
        if answer.get("error"):
            refused += 1
            print(f"\n[{i}] REFUSED {answer['error']} | {question}")
            continue
        claims = unsupported_claims(text, corpus)
        structural = impossible_citations(text, corpus)
        flagged += bool(claims)
        blocked += bool(structural)
        mark = "FLAG" if claims or structural else "    "
        print(f"\n[{i}] {mark} {question}")
        for problem in structural + claims:
            print(f"      - {problem}")
        if claims or structural:
            print("      " + text[:600].replace("\n", "\n      "))

    answered = len(questions) - refused
    print(f"\nanswered {answered}/{len(questions)}  "
          f"claim check fired on {flagged}  structural on {blocked}")


if __name__ == "__main__":
    main()
