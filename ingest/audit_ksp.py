# -*- coding: utf-8 -*-
"""Check that corpus_ksp.jsonl is complete and faithful to the PDFs.

  python -m ingest.audit_ksp

The unit tests check that the parser behaves; this checks that the data came
out whole. They fail in different ways. A parser can be correct on every case
anyone thought to write down and still drop the last eight sections of a
document because the page footer changed halfway through, and no test would
notice, because no test knows how many sections the document has.

So this reads the corpus back, reads the PDFs again, and compares. Six checks:

  1  section numbers run 1..N with nothing missing and nothing repeated
  2  each document has the number of sections it was counted as having
  3  all five duties are present, and 2556 assigns each of its rules the right one
  4  no text was lost: the corpus holds at least 85% of the Thai between ข้อ ๑
     and the signature block
  5  no gazette masthead survived into a section body
  6  the rules that state the five duties say what those duties are

Check 6 is the one that catches a parse which succeeded and still put the rules
under the wrong headings -- everything else would pass in that case.
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import PROCESSED_DIR  # noqa: E402
from app.thai_law import to_arabic  # noqa: E402
from ingest.extract_ksp import CATEGORIES, DOCS, KSP_DIR, OUT_PATH, TAIL  # noqa: E402
from ingest.thai_pdf_text import extract  # noqa: E402

REPORT_PATH = os.path.join(PROCESSED_DIR, "corpus_ksp_audit.md")

# Counted off the PDFs by hand, once, when the corpus was first built. These are
# not copied from the parser's own output -- that would make the check circular.
# A change here has to be justified by the document actually changing.
EXPECTED_SECTIONS = {
    "ksp-2556": 15,
    "ksp-2550": 24,
    "act-2546": 90,
    "ksp-2568": 73,
    "ksp-2553": 61,
    "ksp-2559": 11,
    "ksp-2563": 8,
    "ksp-2549": 28,
    "ksp-2569": 8,
    "ksp-ann-appeal": 6,
}

# ข้อบังคับฯ 2556 states the five duties in หมวด ๑ to หมวด ๕. หมวด ๓ holds five
# rules, the rest one each, which is why this is spelled out rather than derived.
DUTY_BY_SECTION = {
    "7": "ต่อตนเอง",
    "8": "ต่อวิชาชีพ",
    "9": "ต่อผู้รับบริการ",
    "10": "ต่อผู้รับบริการ",
    "11": "ต่อผู้รับบริการ",
    "12": "ต่อผู้รับบริการ",
    "13": "ต่อผู้รับบริการ",
    "14": "ต่อผู้ร่วมประกอบวิชาชีพ",
    "15": "ต่อสังคม",
}

# a word that the rule stating each duty has to contain. If the parse filed a
# rule under the wrong heading, these stop matching even though every count and
# every ratio still looks right.
DUTY_ANCHOR = {
    "ต่อตนเอง": ("7", "วินัยในตนเอง"),
    "ต่อวิชาชีพ": ("8", "ศรัทธา"),
    "ต่อผู้รับบริการ": ("9", "ผู้รับบริการ"),
    "ต่อผู้ร่วมประกอบวิชาชีพ": ("14", "ช่วยเหลือเกื้อกูล"),
    "ต่อสังคม": ("15", "ส่วนรวม"),
}

# The word ราชกิจจานุเบกษา on its own is not evidence of anything: ข้อ 2 of every
# one of these regulations says it comes into force "ตั้งแต่วันประกาศใน
# ราชกิจจานุเบกษา". What does not belong is the masthead's shape -- a volume and
# an issue number, which no rule ever states.
MASTHEAD = re.compile(r"เล่ม\s*[๐-๙0-9]+\s*ตอน|[๐-๙0-9]+\s+ตอน(?:พิเศษ|ที่)\s+[๐-๙0-9]+")
MIN_KEPT = 0.85
THAI = re.compile(r"[ก-๛]")
# a section heading that survived past the cut means the cut ate part of the rules
ORPHAN_SECTION = {
    unit: re.compile(r"(?m)^\s*" + unit + r"\s+([๐-๙0-9]+(?:/[๐-๙0-9]+)?)")
    for unit in ("ข้อ", "มาตรา")
}
SECTION_KEY = re.compile(r"^(\d+)(?:/(\d+))?$")


def sort_key(section: str) -> tuple[int, int]:
    match = SECTION_KEY.match(section)
    return (int(match.group(1)), int(match.group(2) or 0)) if match else (0, 0)


def load() -> dict[str, list[dict]]:
    if not os.path.exists(OUT_PATH):
        sys.exit(f"ไม่พบ {OUT_PATH} — รัน python -m ingest.extract_ksp ก่อน")
    by_doc: dict[str, list[dict]] = collections.defaultdict(list)
    with open(OUT_PATH, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            by_doc[row["sysid"]].append(row)
    return by_doc


# --- the six checks -----------------------------------------------------------


def check_numbering(by_doc) -> list[str]:
    problems = []
    for doc in DOCS:
        rows = by_doc.get(doc.key, [])
        sections = sorted({r["section"] for r in rows}, key=sort_key)
        plain = [sort_key(s)[0] for s in sections if sort_key(s)[1] == 0]
        if not plain:
            problems.append(f"{doc.key}: ไม่มี{doc.unit}สักข้อ")
            continue
        missing = [n for n in range(1, max(plain) + 1) if n not in plain]
        if missing:
            problems.append(f"{doc.key}: ขาด{doc.unit} {missing}")
        seen = collections.Counter(
            (r["section"], r["part"]) for r in rows
        )
        duplicated = [key for key, count in seen.items() if count > 1]
        if duplicated:
            problems.append(f"{doc.key}: ซ้ำ {duplicated}")
    return problems


def check_counts(by_doc) -> list[str]:
    problems = []
    for doc in DOCS:
        want = EXPECTED_SECTIONS[doc.key]
        got = len({r["section"] for r in by_doc.get(doc.key, [])})
        if got != want:
            problems.append(f"{doc.key}: ได้ {got} {doc.unit} แต่นับจาก PDF ไว้ {want}")
    return problems


def check_duties(by_doc) -> list[str]:
    problems = []
    rows = [row for rows in by_doc.values() for row in rows]

    found = {row["ethics_category"] for row in rows if row["ethics_category"]}
    for duty in CATEGORIES:
        if duty not in found:
            problems.append(f"ไม่มีชิ้นไหนติดป้ายด้าน {duty} เลย")
    for stray in found - set(CATEGORIES):
        problems.append(f"มีป้ายด้านที่ไม่รู้จัก: {stray}")

    by_section = {r["section"]: r for r in by_doc.get("ksp-2556", []) if r["part"] == 0}
    for section, duty in DUTY_BY_SECTION.items():
        row = by_section.get(section)
        if row is None:
            problems.append(f"ksp-2556: ไม่มีข้อ {section}")
        elif row["ethics_category"] != duty:
            problems.append(
                f"ksp-2556 ข้อ {section}: ติดป้าย {row['ethics_category']} "
                f"แต่อยู่ในหมวด {duty}"
            )
    return problems


def operative(source: str, unit: str) -> tuple[str, str]:
    """Split a document into the part that states rules and the part that does not.

    The operative part runs from ข้อ ๑ to the signature block. What comes before
    is the preamble -- which minister approved it, at which meeting, repealing
    what -- and what comes after is the signature, the explanatory note and the
    appended forms; ข้อบังคับฯ 2553 carries eleven pages of those.
    """
    first = ORPHAN_SECTION[unit].search(source)
    opening = first.start() if first else 0
    cut = TAIL.search(source, opening)
    body = source[opening: cut.start()] if cut else source[opening:]
    dropped = source[:opening] + (source[cut.start():] if cut else "")
    return body, dropped


def measure(doc, rows) -> tuple[float, str]:
    """Share of the operative part's Thai that reached the corpus, and how it was read."""
    source, how = extract(os.path.join(KSP_DIR, f"{doc.key}.pdf"))
    body, _dropped = operative(source, doc.unit)
    in_body = len(THAI.findall(body))
    in_corpus = sum(len(THAI.findall(row["text"])) for row in rows)
    return (in_corpus / in_body if in_body else 0.0), how


def check_text_kept(by_doc) -> list[str]:
    """Check that the operative part reached the corpus nearly whole.

    Measured against `operative`, not the whole PDF: counting the preamble and
    the appended forms as loss would report every document as broken and so hide
    the one that is.

    Where those two edges land is then checked as well, because a cut in the
    wrong place shrinks both sides of the ratio at once and hides the loss it
    caused. Not by how far into the document they fall -- ประกาศคณะกรรมการคุรุสภา
    is six pages of rules and seven of forms, so a cut at 47% is right there and
    wrong elsewhere -- but by whether any section was left outside them.
    """
    problems = []
    for doc in DOCS:
        source, _how = extract(os.path.join(KSP_DIR, f"{doc.key}.pdf"))
        body, dropped = operative(source, doc.unit)

        have = {row["section"] for row in by_doc.get(doc.key, [])}
        orphans = sorted(
            {to_arabic(m.group(1)) for m in ORPHAN_SECTION[doc.unit].finditer(dropped)}
            - have
        )
        if orphans:
            problems.append(f"{doc.key}: ตัดทิ้ง{doc.unit}ที่ยังไม่ได้เก็บ {orphans}")
            continue

        in_body = len(THAI.findall(body))
        in_corpus = sum(len(THAI.findall(r["text"])) for r in by_doc.get(doc.key, []))
        kept = in_corpus / in_body if in_body else 0.0
        if kept < MIN_KEPT:
            problems.append(
                f"{doc.key}: เก็บอักษรไทยของตัวบทไว้ {kept:.0%} "
                f"({in_corpus:,}/{in_body:,}) ต่ำกว่า {MIN_KEPT:.0%}"
            )
    return problems


def check_no_masthead(by_doc) -> list[str]:
    problems = []
    for doc in DOCS:
        for row in by_doc.get(doc.key, []):
            found = MASTHEAD.search(row["text"])
            if found:
                problems.append(f"{row['id']}: มี \"{found.group()}\" ปนอยู่ในเนื้อความ")
    return problems


def check_duty_wording(by_doc) -> list[str]:
    """The five rules have to say what the five duties are."""
    problems = []
    by_section = {r["section"]: r for r in by_doc.get("ksp-2556", []) if r["part"] == 0}
    for duty, (section, word) in DUTY_ANCHOR.items():
        row = by_section.get(section)
        if row is None:
            problems.append(f"ksp-2556: ไม่มีข้อ {section} ที่ต้องเป็นด้าน {duty}")
        elif word not in row["text"]:
            problems.append(
                f"ksp-2556 ข้อ {section} (ด้าน {duty}): ไม่มีคำว่า \"{word}\" "
                f"— ได้ข้อความว่า {row['text'][:60]}…"
            )
    return problems


CHECKS = (
    ("เลขข้อเรียงครบ ไม่ข้าม ไม่ซ้ำ", check_numbering),
    ("จำนวนข้อตรงกับที่นับจาก PDF", check_counts),
    ("ครบห้าด้าน และ 2556 ติดป้ายถูกหมวด", check_duties),
    ("ไม่มีข้อความหาย", check_text_kept),
    ("ไม่มีหัวกระดาษราชกิจจาฯ ปน", check_no_masthead),
    ("ตัวบทห้าด้านพูดถึงด้านนั้นจริง", check_duty_wording),
)


def main() -> None:
    by_doc = load()
    total = sum(len(rows) for rows in by_doc.values())

    lines = [
        "# ตรวจความสมบูรณ์ของ corpus_ksp.jsonl",
        "",
        f"{len(by_doc)} ฉบับ / "
        f"{sum(len({r['section'] for r in rows}) for rows in by_doc.values()):,} ข้อและมาตรา / "
        f"{total:,} ชิ้น",
        "",
        "| ฉบับ | หน่วย | ข้อ/มาตรา | ชิ้น | ติดป้ายด้าน | เก็บตัวบทไว้ | อ่านด้วย |",
        "|:---|:---|---:|---:|---:|---:|:---|",
    ]
    for doc in DOCS:
        rows = by_doc.get(doc.key, [])
        tagged = sum(1 for r in rows if r["ethics_category"])
        kept, how = measure(doc, rows)
        lines.append(
            f"| `{doc.key}` | {doc.unit} | {len({r['section'] for r in rows})} | "
            f"{len(rows)} | {tagged or '—'} | {kept:.0%} | {how} |"
        )
    lines.append("")

    failed = 0
    for name, run in CHECKS:
        problems = run(by_doc)
        mark = "ผ่าน" if not problems else f"**ไม่ผ่าน** ({len(problems)})"
        print(f"{'[ok] ' if not problems else '[!!] '}{name}: {mark}")
        lines.append(f"## {name} — {mark}")
        lines.append("")
        if problems:
            failed += 1
            for problem in problems:
                print(f"     {problem}")
                lines.append(f"- {problem}")
        else:
            lines.append("ไม่พบปัญหา")
        lines.append("")

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print(f"\nรายงาน: {REPORT_PATH}")

    if failed:
        sys.exit(f"ไม่ผ่าน {failed} จาก {len(CHECKS)} ด่าน — อย่าเพิ่งสร้างดัชนี")
    print("ผ่านครบทุกด่าน — ต่อไป: python -m ingest.build_index")


if __name__ == "__main__":
    main()
