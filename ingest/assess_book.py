# -*- coding: utf-8 -*-
"""The networking bot's answers, read by three assessors and coded four ways.

    .venv/bin/uvicorn app.main:app --port 8077 &
    .venv/bin/python -m ingest.assess_book collect 1   # ask once, keep the answers
    .venv/bin/python -m ingest.assess_book packet 1    # what each assessor reads
    ... three assessors write data/eval/network_coding_round1_assessor{1,2,3}.json
    .venv/bin/python -m ingest.assess_book score 1     # the tables

The same design as the Teachers Council rounds in docs/assessor-rounds.md, on
data/eval/network_user_questions.jsonl: thirty topics, each asked once in the
book's words ("ตรง") and once the way a student would say it ("กำกวม").

    code 1  asked in the book's words, answered correctly
    code 0  asked in the book's words, answered incorrectly
    code 2  asked loosely, answered correctly
    code 3  asked loosely, answered incorrectly

The answers are collected ONCE per round and all three assessors read that one
set: the provider honours no seed, so three collections are three systems.

The pass mark is the thesis's own and is fixed here before anything is
measured: every assessor at 80% or above. It is not to be moved.
"""
from __future__ import annotations

import collections
import json
import os
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(BASE_DIR, "data", "eval")
QUESTIONS = os.path.join(EVAL, "network_user_questions.jsonl")
ENDPOINT = os.environ.get("CHAT_URL", "http://127.0.0.1:8077/chat")
PER_FILE = 15
PASS_MARK = 0.80
CORRECT = {1, 2}
CODE = {("ตรง", True): 1, ("ตรง", False): 0, ("กำกวม", True): 2, ("กำกวม", False): 3}
LABELS = {1: "ถามตรง ตอบตรง", 0: "ถามตรง ตอบไม่ตรง",
          2: "ถามกำกวม ตอบตรง", 3: "ถามกำกวม ตอบไม่ตรง"}

CRITERIA = """## เกณฑ์การให้รหัส

รหัส 1 ถามด้วยคำของหนังสือ และคำตอบถูกต้อง
รหัส 0 ถามด้วยคำของหนังสือ และคำตอบไม่ถูกต้อง
รหัส 2 ถามด้วยภาษาพูด (กำกวม) และคำตอบถูกต้อง
รหัส 3 ถามด้วยภาษาพูด (กำกวม) และคำตอบไม่ถูกต้อง

ลักษณะคำถาม (ตรง/กำกวม) กำหนดไว้แล้วในแต่ละข้อ ผู้ประเมินตัดสินเฉพาะว่าคำตอบถูกหรือไม่ถูก

นับว่าไม่ถูกต้องเมื่อ
- กล่าวสิ่งที่ขัดกับข้อความในหนังสือ
- สาระหลักของคำตอบอ้างบทและหน้าที่ไม่มีข้อความนั้น หรือหนังสือไม่ได้เขียนไว้เลย
- เติมตัวเลข ชื่อมาตรฐาน ชื่อเมนู ชื่อปุ่ม หรือขั้นตอนที่หนังสือไม่ได้เขียน ลงในส่วนที่อ้างหนังสือ
- แจกแจงไม่ครบเมื่อคำถามถามว่ามีอะไรบ้าง หรือขั้นตอนขาดจนทำตามไม่ได้ หรือเรียงลำดับผิด
- ตอบเรื่องอื่นที่ไม่ใช่เรื่องที่ถาม
- ปฏิเสธ หรือตอบจากความรู้ทั่วไปของ AI (ขึ้นต้นว่าหนังสือไม่ได้อธิบายไว้ หรือยืนยันกับหนังสือไม่ได้)
  ทั้งที่หนังสือมีคำตอบ

นับว่าถูกต้องเมื่อ
- สาระถูก และบทกับหน้าที่อ้างมีข้อความนั้นจริง
- สำนวนไม่สวย ข้อความถูกตัดตามความยาวที่จำกัด คำสะกดผิดที่ติดมาจากหนังสือ
  หรือมีรายละเอียดที่ถูกต้องเพิ่มมา ไม่นับเป็นข้อผิด
- ส่วนใต้ป้าย "💡 เสริมจากความรู้ทั่วไปของ AI" ไม่ต้องมีในหนังสือ นับผิดเฉพาะเมื่อเป็นข้อเท็จจริงที่ผิดชัดเจน

เกณฑ์ผ่าน: ผู้ประเมินทุกคนต้องได้ค่าความถูกต้องไม่น้อยกว่า 80%
"""


def path(kind: str, round_no: int, suffix: str = "") -> str:
    return os.path.join(EVAL, f"network_{kind}_round{round_no}{suffix}")


def questions() -> list[dict]:
    if not os.path.exists(QUESTIONS):
        raise SystemExit(f"ไม่พบ {QUESTIONS}")
    with open(QUESTIONS, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def collect(round_no: int) -> None:
    out = path("user_answers", round_no, ".json")
    if os.path.exists(out):
        raise SystemExit(f"{out} มีอยู่แล้ว -- เก็บคำตอบครั้งเดียวต่อรอบ ใช้เลขรอบใหม่")
    rows = []
    for case in questions():
        request = urllib.request.Request(
            ENDPOINT, data=json.dumps({"question": case["question"]}).encode(),
            headers={"content-type": "application/json"})
        with urllib.request.urlopen(request, timeout=300) as response:
            got = json.load(response)
        rows.append({**case, "answer": got["answer"], "in_scope": got["in_scope"],
                     "source": got["source"], "error": got["error"],
                     "figures": [f.get("caption") or f.get("key") for f in got["figures"]],
                     "passages": [{"citation": s["citation"], "text": s["text"]}
                                  for s in got["sources"]]})
        print(case["id"], got["source"], "ตอบ" if got["in_scope"] else "ปฏิเสธ")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump({"collected": time.strftime("%Y-%m-%d %H:%M"), "answers": rows},
                  handle, ensure_ascii=False, indent=1)
    print(f"{len(rows)} คำตอบ -> {out}")


def answers(round_no: int) -> list[dict]:
    source = path("user_answers", round_no, ".json")
    if not os.path.exists(source):
        raise SystemExit(f"ไม่พบ {source} -- รัน collect ก่อน")
    with open(source, encoding="utf-8") as handle:
        return json.load(handle)["answers"]


def packet(round_no: int) -> None:
    """Fifteen questions a file. A passage the search returned for several of
    them is printed once, at the end of the file, and named under each question
    by its number there: the two phrasings of a topic share most of theirs."""
    rows = answers(round_no)
    for part, start in enumerate(range(0, len(rows), PER_FILE), start=1):
        out = [f"# แฟ้มประเมินชุดเครือข่าย รอบ {round_no} ส่วนที่ {part}\n", CRITERIA]
        shelf: dict[str, int] = {}
        cites: dict[int, str] = {}
        for row in rows[start:start + PER_FILE]:
            if not row["passages"]:
                raise SystemExit(f"{row['id']} ไม่มีข้อความจากหนังสือแนบมา")
            names = []
            for passage in row["passages"]:
                number = shelf.setdefault(passage["text"], len(shelf) + 1)
                cites[number] = passage["citation"]
                names.append(f"P{number}")
            out.append(f"\n---\n\n## {row['id']} (ลักษณะคำถาม: {row['phrasing']}, "
                       f"บทที่ {row['chapter']})\n\n**คำถาม** {row['question']}\n\n"
                       f"**ที่มาของคำตอบ** {row['source']} "
                       f"({'ตอบ' if row['in_scope'] else 'ปฏิเสธ'})\n\n"
                       f"**คำตอบ**\n\n{row['answer']}\n")
            if row["figures"]:
                out.append("**รูปที่แนบ** " + " / ".join(map(str, row["figures"])) + "\n")
            out.append("**ข้อความจากหนังสือที่ระบบค้นได้ให้ข้อนี้** " + " ".join(names)
                       + " (อยู่ท้ายแฟ้ม)\n")
        out.append("\n---\n\n# ข้อความจากหนังสือ (คำต่อคำ)\n")
        for text, number in shelf.items():
            out.append(f"## P{number} — {cites[number]}\n\n{text}\n")
        target = path("review_packet", round_no, f"_{part}.md")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("\n".join(out))
        print(target, f"{len(shelf)} ชิ้น")


def coding(round_no: int, assessor: int) -> dict[str, dict]:
    source = path("coding", round_no, f"_assessor{assessor}.json")
    if not os.path.exists(source):
        raise SystemExit(f"ไม่พบ {source}")
    with open(source, encoding="utf-8") as handle:
        return {row["id"]: row for row in json.load(handle)}


def score(round_no: int) -> dict:
    rows = answers(round_no)
    phrasing = {row["id"]: row["phrasing"] for row in rows}
    summary = {"round": round_no, "questions": len(rows), "pass_mark": PASS_MARK,
               "assessors": [], "items": []}
    codes = {}
    for assessor in (1, 2, 3):
        got = coding(assessor=assessor, round_no=round_no)
        if set(got) != set(phrasing):
            raise SystemExit(f"ผู้ประเมิน {assessor}: รหัสข้อไม่ครบหรือเกิน "
                             f"{sorted(set(phrasing) ^ set(got))[:5]}")
        for item, row in got.items():
            allowed = {CODE[(phrasing[item], True)], CODE[(phrasing[item], False)]}
            if row["code"] not in allowed:
                raise SystemExit(f"ผู้ประเมิน {assessor} ข้อ {item}: รหัส {row['code']} "
                                 f"ไม่ตรงกับลักษณะคำถาม {phrasing[item]}")
        codes[assessor] = got
        spread = collections.Counter(row["code"] for row in got.values())
        right = sum(spread[c] for c in CORRECT)
        summary["assessors"].append({
            "assessor": assessor, "codes": {str(c): spread[c] for c in (1, 0, 2, 3)},
            "correct": right, "accuracy": right / len(rows),
            "passed": right / len(rows) >= PASS_MARK})
        print(f"ผู้ประเมิน {assessor}: " + "  ".join(
            f"{LABELS[c]} {spread[c]}" for c in (1, 0, 2, 3))
            + f"  -> {right}/{len(rows)} = {right / len(rows):.2%}")
    for row in rows:
        given = [codes[a][row["id"]]["code"] for a in (1, 2, 3)]
        summary["items"].append({
            "id": row["id"], "codes": given,
            "notes": [codes[a][row["id"]].get("note", "") for a in (1, 2, 3)]})
    agreed = sum(1 for item in summary["items"] if len(set(item["codes"])) == 1)
    summary["all_three_agree"] = agreed
    summary["passed"] = all(a["passed"] for a in summary["assessors"])
    total = sum(a["correct"] for a in summary["assessors"])
    summary["overall_accuracy"] = total / (3 * len(rows))
    print(f"เห็นตรงกันทั้งสามคน {agreed}/{len(rows)} ข้อ  รวม {summary['overall_accuracy']:.2%}  "
          f"{'ผ่าน' if summary['passed'] else 'ไม่ผ่าน'}เกณฑ์ทุกคน >= {PASS_MARK:.0%}")
    with open(path("assessor_summary", round_no, ".json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=1)
    return summary


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in ("collect", "packet", "score"):
        raise SystemExit("ใช้: python -m ingest.assess_book collect|packet|score <รอบ>")
    {"collect": collect, "packet": packet, "score": score}[sys.argv[1]](int(sys.argv[2]))


if __name__ == "__main__":
    main()
