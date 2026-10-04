# -*- coding: utf-8 -*-
"""Ask the running system questions whose answers are written in the source
document, and check each answer for the facts the document states.

    .venv/bin/uvicorn app.main:app --port 8077 &
    python -m ingest.check_document

Reads data/eval/document_questions.jsonl, writes data/eval/document_answers.json.

A pass means three things: the answer came from the corpus the fact lives in
(rules or articles), it was not a refusal, and every expected string is in it.
That is a floor, not a verdict -- it cannot see a correct figure attached to the
wrong label, so the saved answers still have to be read.
"""
import json
import os
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.environ.get("QUESTIONS") or os.path.join(BASE_DIR, "data", "eval", "document_questions.jsonl")
ANSWERS = os.path.splitext(QUESTIONS)[0].replace("_questions", "_answers") + ".json"
ENDPOINT = os.environ.get("CHAT_URL", "http://127.0.0.1:8077/chat")
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def ask(question: str) -> dict:
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def main() -> None:
    if not os.path.exists(QUESTIONS):
        raise SystemExit(f"ไม่พบชุดคำถาม {QUESTIONS}")
    with open(QUESTIONS, encoding="utf-8") as handle:
        cases = [json.loads(line) for line in handle if line.strip()]

    results = []
    for case in cases:
        reply = ask(case["question"])
        text = reply["answer"].translate(THAI_DIGITS)
        missing = [fact for fact in case["expect"] if fact not in text]
        passed = (not missing and reply.get("in_scope")
                  and reply.get("source") == case["source"])
        results.append({**case, "answer": reply["answer"],
                        "got_source": reply.get("source"),
                        "in_scope": reply.get("in_scope"),
                        "faults": reply.get("faults"),
                        "missing": missing, "passed": bool(passed)})
        print(f"{'ผ่าน' if passed else 'ตก  '} {case['id']:9s} "
              f"ตอบจาก {reply.get('source')}"
              + (f"  ขาด {missing}" if missing else ""), flush=True)

    with open(ANSWERS, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=1)
    for source in ("rules", "articles"):
        group = [r for r in results if r["source"] == source]
        print(f"{source}: {sum(r['passed'] for r in group)}/{len(group)}")
    print(f"-> {ANSWERS}")


if __name__ == "__main__":
    main()
