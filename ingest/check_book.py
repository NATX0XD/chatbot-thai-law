# -*- coding: utf-8 -*-
"""Ask the running bot the probe questions and check each answer against the book.

    .venv/bin/uvicorn app.main:app --port 8077 &
    python -m ingest.check_book

Reads data/eval/network_questions.jsonl, writes data/eval/network_answers.json.

  book      passes when it is answered, every expected string is in the answer
            ("a|b" means either spelling), and the expected figure, if one is
            named, comes back with it
  beyond    passes when it is refused: the book does not cover it
  offtopic  passes when it is refused

That is a floor, not a verdict. A string check cannot see a correct word in a
wrong sentence, so the saved answers still have to be read.
"""
import json
import os
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.environ.get("QUESTIONS") or os.path.join(
    BASE_DIR, "data", "eval", "network_questions.jsonl")
ANSWERS = QUESTIONS.replace("_questions.jsonl", "_answers.json")
ENDPOINT = os.environ.get("CHAT_URL", "http://127.0.0.1:8077/chat")


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
        text = reply["answer"]
        shown = [f["number"] for f in reply.get("figures", [])]
        if case["group"] == "book":
            missing = [fact for fact in case["expect"]
                       if not any(option in text for option in fact.split("|"))]
            if case.get("figure") and case["figure"] not in shown:
                missing.append(f"รูปที่ {case['figure']}")
            passed = bool(reply.get("in_scope")) and not missing
        else:
            missing = []
            passed = not reply.get("in_scope")
        results.append({**case, "answer": text, "in_scope": reply.get("in_scope"),
                        "error": reply.get("error"), "figures": shown,
                        "citations": [s["citation"] for s in reply.get("sources", [])][:3],
                        "missing": missing, "passed": passed})
        print(f"{'ผ่าน' if passed else 'ตก  '} {case['id']} {case['group']:8s}"
              f" รูป {shown or '-'}"
              + (f"  ขาด {missing}" if missing else "")
              + (f"  ({reply.get('error')})" if reply.get("error") else ""), flush=True)

    with open(ANSWERS, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=1)
    for group in ("book", "beyond", "offtopic"):
        rows = [r for r in results if r["group"] == group]
        print(f"{group}: {sum(r['passed'] for r in rows)}/{len(rows)}")
    print(f"-> {ANSWERS}")


if __name__ == "__main__":
    main()
