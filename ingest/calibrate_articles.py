# -*- coding: utf-8 -*-
"""Print the scores that decide when a question goes to the journal articles.

Every probe is scored against both corpora: the best cosine among the rules,
the best among the articles, and the difference. app/articles.py routes on two
numbers read from this table, MIN_ARTICLE_SIM and MARGIN, and says which rows
they came from.

    python -m ingest.calibrate_articles

Probes: data/eval/ksp_questions.jsonl (the rule questions and the refusals),
data/eval/user_questions.jsonl (the acceptance set, also rule questions) and
data/eval/article_questions.jsonl (questions the articles answer).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import articles  # noqa: E402
from app.config import DATA_DIR  # noqa: E402
from app.coverage import find_gap  # noqa: E402
from app.retriever import Retriever  # noqa: E402

RULE_PROBES = os.path.join(DATA_DIR, "eval", "ksp_questions.jsonl")
ACCEPTANCE = os.path.join(DATA_DIR, "eval", "user_questions.jsonl")
DOCUMENT = os.path.join(DATA_DIR, "eval", "document_questions.jsonl")
ARTICLE_PROBES = os.path.join(DATA_DIR, "eval", "article_questions.jsonl")
GROUPS = ("ตอบได้จากตัวบท", "ถามจากบทความ", "นอกคลัง มีกฎกันไว้", "ไม่ใช่คำถามของบอท")


def load(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise SystemExit(f"ไม่พบชุดคำถาม {path}")
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    index = articles.get_index()
    if index is None:
        raise SystemExit("ยังไม่มีดัชนีบทความ รัน ingest.extract_articles "
                         "แล้ว ingest.build_article_index ก่อน")
    retriever = Retriever()
    rows = []
    for entry in load(RULE_PROBES):
        q = entry["question"]
        group = (GROUPS[0] if entry["expect"] == "answer"
                 else GROUPS[2] if find_gap(q) else GROUPS[3])
        rows.append((group, q, ""))
    # the sixty acceptance questions are rule questions too, and the ones the
    # reported results rest on -- none of them may change route
    seen = {q for _, q, _ in rows}
    rows += [(GROUPS[0], e["question"], "") for e in load(ACCEPTANCE)
             if e["question"] not in seen and not find_gap(e["question"])]
    rows += [(GROUPS[1], e["question"], e.get("article", "")) for e in load(ARTICLE_PROBES)]
    # questions written from facts in the source document, each labelled with
    # the corpus its answer lives in
    for e in load(DOCUMENT):
        if e["question"] not in seen:
            rows.append((GROUPS[0] if e["source"] == "rules" else GROUPS[1],
                         e["question"], ""))

    scored = []
    for group, q, want in rows:
        rules = retriever.search(q)
        asked = q.translate(articles.THAI_DIGITS)
        hits, best = index.search(asked, retriever._encode(asked))
        routed = articles.route(q, rules, retriever._encode,
                                retriever.vocabulary) is not None
        scored.append((group, rules.max_dense, best, routed,
                       hits[0].rec["sysid"], want, q))

    for group in GROUPS:
        part = [s for s in scored if s[0] == group]
        if not part:
            continue
        gaps = [s[2] - s[1] for s in part]
        print(f"\n{group}  n={len(part)}  ส่งไปบทความ {sum(s[3] for s in part)}")
        print(f"  ตัวบท {min(s[1] for s in part):.3f}–{max(s[1] for s in part):.3f}  "
              f"บทความ {min(s[2] for s in part):.3f}–{max(s[2] for s in part):.3f}  "
              f"ส่วนต่าง {min(gaps):+.3f}…{max(gaps):+.3f}")
        for s in sorted(part, key=lambda s: s[1] - s[2])[:6 if group == GROUPS[0] else 99]:
            hit = "" if not s[5] else (" ถูกเรื่อง" if s[5] == s[4] else f" ผิดเรื่อง(ได้ {s[4]})")
            print(f"    {'→บทความ' if s[3] else '       '} ตัวบท {s[1]:.3f} บทความ {s[2]:.3f} "
                  f"{s[2] - s[1]:+.3f}{hit}  {s[6][:56]}")
    print(f"\nเกณฑ์ที่ใช้: บทความ ≥ {articles.MIN_ARTICLE_SIM} และ (สูงกว่าตัวบท ≥ "
          f"{articles.MARGIN} หรือ ≥ {articles.NEAR_MARGIN} พร้อมคำที่ตัวบทไม่มี "
          "หรือคำถามเอ่ยถึงงานวิจัย)")


if __name__ == "__main__":
    main()
