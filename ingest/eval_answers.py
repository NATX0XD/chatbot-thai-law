# -*- coding: utf-8 -*-
"""Check whether the answer actually says what the retrieved sections say.

ingest/eval_retrieval.py measures whether the right section was found. That is a
ceiling, not a result: the model still has to write something faithful to it, and
nothing in this project measured that until now. The gap was visible in the
documentation as "ระดับ 3 -- ยังไม่ได้วัด", and adversarial testing then produced
exactly the failure it predicted, an answer that cited พ.ร.บ.คุ้มครองแรงงาน
correctly and stated an unemployment benefit of 1,000 baht a month that appears
in no Thai law.

Three things are measured per question:

  gold       the section the dataset labels as the answer is among the ones the
             system used. This is retrieval, re-checked end to end.
  figures    every number in the answer -- days, baht, percentages -- appears in
             the sections it was written from. Deterministic, unlimited, and it
             catches the failure above exactly.
  grounded   optional, and only with --judge: a model reads the answer against
             the sections and says whether every claim follows. It catches what
             arithmetic cannot, such as an invented exception, but Gemini's free
             tier allows twenty calls a day, which is why it is not the default.

The judge is Gemini, deliberately not Typhoon. Asking the model that wrote the
answer whether the answer is sound measures its confidence, not its accuracy.

    python -m ingest.eval_answers --n 60
    python -m ingest.eval_answers --n 15 --judge
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import PROCESSED_DIR, settings  # noqa: E402
from app.numbers import unsupported_figures  # noqa: E402

QA_PATH = os.path.join(PROCESSED_DIR, "qa_pairs.jsonl")
CORPUS = os.path.join(PROCESSED_DIR, "corpus.jsonl")
SEC_RE = re.compile(r"^(.*?)\s*มาตรา\s*(\S+)$")

JUDGE_SYSTEM = """คุณคือผู้ตรวจสอบความถูกต้องของคำตอบด้านกฎหมายไทย

คุณจะได้รับ
1. คำถามของผู้ใช้
2. คำตอบที่ระบบสร้างขึ้น
3. ตัวบทกฎหมายทั้งหมดที่ระบบใช้ตอบ

หน้าที่ของคุณคือตรวจว่า ทุกข้อความที่เป็นสาระทางกฎหมายในคำตอบ มีที่มาจากตัวบทที่ให้มาหรือไม่

ถือว่า "ไม่มีที่มา" เมื่อ
- คำตอบระบุตัวเลข จำนวนเงิน จำนวนวัน หรืออัตราร้อยละ ที่ไม่ปรากฏในตัวบทที่ให้มา
- คำตอบอ้างเลขมาตราที่ไม่มีในตัวบทที่ให้มา
- คำตอบสรุปความผิดไปจากที่ตัวบทเขียนไว้
- คำตอบเพิ่มเงื่อนไขหรือข้อยกเว้นที่ตัวบทไม่ได้เขียน

ไม่ถือว่า "ไม่มีที่มา" เมื่อ
- คำตอบเรียบเรียงใหม่ด้วยภาษาที่เข้าใจง่ายกว่าตัวบท แต่ความหมายตรงกัน
- คำตอบแปลงเลขไทยเป็นเลขอารบิก หรือแปลงคำบอกจำนวนเป็นตัวเลข เช่น หนึ่งแสนบาท เป็น 100,000 บาท
- คำตอบบอกว่าข้อมูลไม่พอ หรือปฏิเสธที่จะตอบ

ตอบกลับเป็น JSON อย่างเดียว ไม่ต้องมีข้อความอื่น รูปแบบ
{"grounded": true หรือ false, "unsupported": ["ข้อความที่ไม่มีที่มา", ...], "note": "เหตุผลสั้นๆ หนึ่งประโยค"}"""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load_gold(split: str) -> list[tuple[str, set]]:
    keys = set()
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            keys.add((norm(rec["act"]), rec["section"]))

    out = []
    with open(QA_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if split != "all" and d.get("split") != split:
                continue
            gold = set()
            for g in d.get("sections") or []:
                m = SEC_RE.match(norm(g))
                if m and (norm(m.group(1)), m.group(2)) in keys:
                    gold.add((norm(m.group(1)), m.group(2)))
            if gold and d.get("question"):
                out.append((d["question"], gold))
    return out


def judge(client, question: str, answer: str, sections: list[str]) -> dict:
    body = ("คำถาม\n" + question + "\n\nคำตอบของระบบ\n" + answer
            + "\n\nตัวบทที่ระบบใช้\n" + "\n\n".join(sections))
    resp = client.chat.completions.create(
        model=settings.gemini_model,
        messages=[{"role": "system", "content": JUDGE_SYSTEM},
                  {"role": "user", "content": body}],
        temperature=0.0, max_tokens=800)
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    # the judge sometimes writes a sentence before or after the object; take the
    # outermost braces rather than discarding an otherwise usable verdict
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # a judge that cannot be parsed is not a verdict; counted separately
        # rather than silently scored as a pass
        return {"grounded": None, "unsupported": [], "note": raw[:160]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--split", default="test", choices=["test", "train", "all"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--url", default="https://thai-law-bot-c5zo.onrender.com")
    ap.add_argument("--judge", action="store_true",
                    help="also ask Gemini whether every claim is supported "
                         "(free tier allows only 20 calls a day)")
    args = ap.parse_args()

    client = None
    if args.judge:
        if not settings.gemini_api_key:
            sys.exit("--judge ต้องมี GEMINI_API_KEY -- ตั้งใน .env")
        from openai import OpenAI
        client = OpenAI(api_key=settings.gemini_api_key,
                        base_url=settings.gemini_base_url, timeout=90)

    items = load_gold(args.split)
    random.Random(args.seed).shuffle(items)
    items = items[:args.n]
    print(f"ตรวจ {len(items)} คำถาม ผ่าน {args.url}\n")

    grounded = ungrounded = unparsed = refused = 0
    gold_used = 0
    figure_clean = figure_bad = 0
    failures = []
    figure_failures = []
    t0 = time.time()

    with httpx.Client(timeout=180) as http:
        for i, (question, gold) in enumerate(items, start=1):
            try:
                r = http.post(f"{args.url}/chat", json={"question": question})
                d = r.json()
            except Exception as exc:
                print(f"  {i}. เรียกไม่สำเร็จ: {exc}")
                continue

            cites = [s["citation"] for s in d.get("sources", [])]
            used_gold = any((norm(c.rsplit(" มาตรา ", 1)[0]),
                             c.rsplit(" มาตรา ", 1)[-1]) in gold for c in cites)
            gold_used += used_gold

            if not d.get("in_scope"):
                refused += 1
                print(f"  {i}. ปฏิเสธ | เฉลยอยู่ในผลค้น: {used_gold} | {question[:44]}")
                continue

            sections = [f"{s['citation']}\n{s['text']}" for s in d["sources"]]

            # deterministic first: every figure in the answer must appear in the
            # sections it was written from. No model, no quota, and it catches the
            # failure that matters most in a legal answer.
            floating = unsupported_figures(d["answer"], sections)
            if floating:
                figure_bad += 1
                figure_failures.append((question, floating, cites[:2]))
            else:
                figure_clean += 1

            if client is None:
                print(f"  {i}. {'ตัวเลขลอย ' + str(floating) if floating else 'ตัวเลขตรงตัวบท'}"
                      f" | เฉลยอยู่ในผลค้น: {used_gold} | {question[:40]}")
                continue

            verdict = judge(client, question, d["answer"], sections)
            ok = verdict.get("grounded")
            if ok is None:
                unparsed += 1
            elif ok:
                grounded += 1
            else:
                ungrounded += 1
                failures.append((question, d["answer"], cites[:2], verdict))
            mark = {True: "ตรงตัวบท", False: "ไม่มีที่มา", None: "ตัดสินไม่ได้"}[ok]
            print(f"  {i}. {mark} | เฉลยอยู่ในผลค้น: {used_gold} | {question[:44]}")

    n = len(items)
    answered = grounded + ungrounded + unparsed
    print(f"\n{'=' * 74}")
    print(f"คำถามทั้งหมด            {n}")
    print(f"  ตอบ                   {answered}")
    print(f"  ปฏิเสธ                {refused}")
    print(f"เฉลยอยู่ในมาตราที่ค้นได้  {gold_used}/{n}  ({100 * gold_used / n:.1f}%)")
    checked = figure_clean + figure_bad
    if checked:
        print(f"\nตรวจตัวเลขในคำตอบ {checked} ข้อ")
        print(f"  ทุกตัวเลขมีในตัวบท     {figure_clean}  ({100 * figure_clean / checked:.1f}%)")
        print(f"  มีตัวเลขที่ไม่มีในตัวบท {figure_bad}  ({100 * figure_bad / checked:.1f}%)")
    for question, floating, cites in figure_failures:
        print(f"\n  {question[:70]}")
        print(f"    อ้าง {cites}")
        print(f"    ตัวเลขที่ไม่พบในตัวบท: {floating}")
    if answered:
        print(f"\nในคำตอบ {answered} ข้อ")
        print(f"  ทุกข้อความมีที่มาจากตัวบท  {grounded}  ({100 * grounded / answered:.1f}%)")
        print(f"  มีข้อความที่ไม่มีที่มา     {ungrounded}  ({100 * ungrounded / answered:.1f}%)")
        if unparsed:
            print(f"  ผู้ตรวจตอบไม่เป็นรูปแบบ    {unparsed}")

    for question, answer, cites, verdict in failures:
        print(f"\n{'-' * 74}\nคำถาม  {question}")
        print(f"อ้าง   {cites}")
        print(f"เหตุ   {verdict.get('note', '')}")
        for claim in verdict.get("unsupported", [])[:4]:
            print(f"  ไม่มีที่มา: {claim}")
    print(f"\n{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
