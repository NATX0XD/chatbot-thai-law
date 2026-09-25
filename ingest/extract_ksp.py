# -*- coding: utf-8 -*-
"""Turn the Teachers Council PDFs into the corpus the retriever reads.

  data/raw/ksp/*.pdf  ->  data/processed/corpus_ksp.jsonl

The output uses the same schema as the general-law corpus, so retriever.py,
corpus_store.py and build_index.py need no change at all. Four fields are added
because this material has structure the Act corpus did not:

  unit             "ข้อ" or "มาตรา". Council regulations number their rules as
                   ข้อ; only the 2546 Act uses มาตรา. Citing "มาตรา 7 ของ
                   ข้อบังคับ" would be wrong, so the writer needs to know which.
  ethics_category  Which of the five duties a rule belongs to, taken from the
                   heading above it rather than guessed from the wording.
  source_url       The PDF it came from.
  published        Gazette date, so the answer can prefer the newer of two
                   regulations that both still sit in the index.

The five duties come out of two documents. ข้อบังคับฯ 2556 states them as
หมวด ๑ to หมวด ๕, one rule each. ข้อบังคับฯ 2550 then repeats all five as
ส่วนที่ ๑ to ส่วนที่ ๕ inside each of four chapters -- one chapter per kind of
practitioner -- and fills them with worked examples of what to do and what to
avoid. So the category is read from whichever heading, หมวด or ส่วนที่, is
titled "จรรยาบรรณต่อ...", and the rest of the corpus carries no category at all.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import PROCESSED_DIR, RAW_DIR  # noqa: E402
from app.thai_law import clean, to_arabic  # noqa: E402
from ingest.thai_pdf_text import extract  # noqa: E402

KSP_DIR = os.path.join(RAW_DIR, "ksp")
OUT_PATH = os.path.join(PROCESSED_DIR, "corpus_ksp.jsonl")

MAX_CHUNK = 1800
GAZETTE = "https://ratchakitcha.soc.go.th/documents"
KSP_UPLOAD = "https://www.ksp.or.th/wp-content/uploads"


@dataclass(frozen=True)
class Doc:
    key: str
    act: str
    unit: str          # "ข้อ" or "มาตรา"
    published: str     # gazette date, Buddhist era, YYYY-MM-DD
    url: str
    # The name an answer should use. Full titles run to eighty characters and the
    # model shortens them on its own if not given one -- it called ข้อบังคับฯ
    # แบบแผนพฤติกรรม 2550 "ข้อบังคับฯ จรรยาบรรณ 2550", which is the title of a
    # different regulation, and the citation guard rejected the whole answer.
    short: str = ""
    # Which document repealed this one, if any. ข้อ 3 ของข้อบังคับฯ 2568 repeals
    # the 2553 regulation and both of its amendments outright. All three stay in
    # the corpus -- the 2568 text refers to proceedings begun under them, and a
    # reader comparing the two needs to see both -- but an answer that cites a
    # repealed rule as current law is wrong, so the record has to say so.
    superseded_by: str | None = None


DOCS = (
    Doc("ksp-2556", "ข้อบังคับคุรุสภา ว่าด้วยจรรยาบรรณของวิชาชีพ พ.ศ. 2556",
        "ข้อ", "2556-10-04", f"{GAZETTE}/1986083.pdf",
        short="ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556"),
    Doc("ksp-2550", "ข้อบังคับคุรุสภา ว่าด้วยแบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพ พ.ศ. 2550",
        "ข้อ", "2550-04-27", f"{GAZETTE}/214339.pdf",
        short="ข้อบังคับคุรุสภา แบบแผนพฤติกรรมตามจรรยาบรรณ 2550"),
    Doc("act-2546", "พระราชบัญญัติสภาครูและบุคลากรทางการศึกษา พ.ศ. 2546",
        "มาตรา", "2546-06-11",
        f"{KSP_UPLOAD}/2023/05/1-พระราชบัญญัติสภาครูและบุคลากรทางการศึกษา-พ.ศ.-2546.pdf",
        short="พ.ร.บ.สภาครูและบุคลากรทางการศึกษา 2546"),
    Doc("ksp-2568", "ข้อบังคับคุรุสภา ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณของวิชาชีพ พ.ศ. 2568",
        "ข้อ", "2568-07-30",
        f"{KSP_UPLOAD}/2025/07/ข้อบังคับ​คุรุสภา​ฯการพิจารณา​การประพฤต.pdf",
        short="ข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ 2568"),
    Doc("ksp-2553", "ข้อบังคับคุรุสภา ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณของวิชาชีพ พ.ศ. 2553",
        "ข้อ", "2553-12-30", f"{GAZETTE}/1863175.pdf", superseded_by="ksp-2568",
        short="ข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ 2553"),
    Doc("ksp-2559", "ข้อบังคับคุรุสภา ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณของวิชาชีพ "
        "(ฉบับที่ 2) พ.ศ. 2559", "ข้อ", "2559-08-25", f"{GAZETTE}/2080413.pdf",
        superseded_by="ksp-2568",
        short="ข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ ฉบับที่ 2 พ.ศ. 2559"),
    Doc("ksp-2563", "ข้อบังคับคุรุสภา ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณของวิชาชีพ "
        "(ฉบับที่ 3) พ.ศ. 2563", "ข้อ", "2563-09-22", f"{GAZETTE}/17142857.pdf",
        superseded_by="ksp-2568",
        short="ข้อบังคับคุรุสภา การพิจารณาการประพฤติผิดจรรยาบรรณ ฉบับที่ 3 พ.ศ. 2563"),
    Doc("ksp-2549", "ข้อบังคับคุรุสภา ว่าด้วยการอุทธรณ์คำวินิจฉัยการประพฤติผิดจรรยาบรรณ"
        "ของวิชาชีพ พ.ศ. 2549", "ข้อ", "2549-12-15", f"{GAZETTE}/204062.pdf",
        short="ข้อบังคับคุรุสภา การอุทธรณ์คำวินิจฉัย 2549"),
    Doc("ksp-2569", "ข้อบังคับคุรุสภา ว่าด้วยการอุทธรณ์คำวินิจฉัยการประพฤติผิดจรรยาบรรณ"
        "ของวิชาชีพ (ฉบับที่ 2) พ.ศ. 2569", "ข้อ", "2569-04-08",
        f"{KSP_UPLOAD}/2026/04/ข้อบังคับ-อุทธรณ์จรรยบรรณฯ-ฉ.2-พ.ศ.2569-8เม.ย.69.pdf",
        short="ข้อบังคับคุรุสภา การอุทธรณ์คำวินิจฉัย ฉบับที่ 2 พ.ศ. 2569"),
    Doc("ksp-ann-appeal", "ประกาศคณะกรรมการคุรุสภา เรื่อง หลักเกณฑ์และวิธีการได้มาซึ่ง"
        "คณะอนุกรรมการอุทธรณ์คำวินิจฉัยการประพฤติผิดจรรยาบรรณของวิชาชีพ",
        "ข้อ", "2553-03-26", f"{GAZETTE}/1826563.pdf",
        short="ประกาศคณะกรรมการคุรุสภา คณะอนุกรรมการอุทธรณ์"),
)

CATEGORIES = (
    "ต่อตนเอง", "ต่อวิชาชีพ", "ต่อผู้รับบริการ",
    "ต่อผู้ร่วมประกอบวิชาชีพ", "ต่อสังคม",
)

MONTHS = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
          "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")

# Every page of every document repeats the gazette masthead. It lands in the
# middle of whatever section spans the page break, so it has to go before the
# text is reflowed, not after.
FURNITURE = re.compile(
    r"^\s*(?:"
    r"ราชกิจจานุเบกษา.*"
    r"|หน้า\s*[๐-๙0-9]+\s*"
    r"|เล่ม(?:\s+[๐-๙0-9].*)?"
    # Vision reads the masthead as four separate lines, so the volume and the
    # issue arrive without the word เล่ม in front of them
    r"|[๐-๙0-9]+\s+ตอน(?:พิเศษ|ที่)\s+[๐-๙0-9]+\s*[ก-ฮ]?\s*(?:ราชกิจจานุเบกษา.*)?"
    r"|[๐-๙0-9]{1,2}\s*(?:" + "|".join(MONTHS) + r")\s*[๐-๙0-9]{4}\s*"
    r")$"
)

# what follows is the signature block and the explanatory note, neither of which
# is a rule anyone can be judged against
TAIL = re.compile(r"(?m)^\s*(?:ประกาศ\s*ณ\s*วันที่|ผู้รับสนองพระบรมราชโองการ|หมายเหตุ\s*:-)")

# "หมวดที่ ๔" appears once, in ข้อบังคับฯ 2550, where the other three chapters
# are written "หมวด ๑". Missing it filed ศึกษานิเทศก์'s five rules under the
# chapter for ผู้บริหารการศึกษา.
HEADING = re.compile(r"^\s*(หมวด|ส่วนที่)(?:ที่)?\s+([๐-๙0-9]+)\s*$")
# the space after the number is optional: the 2546 Act's typesetter ran eight of
# them together, "มาตรา ๑๐คุรุสภาอาจมีรายได้", one for every multiple of ten
UNIT = re.compile(r"^\s*(ข้อ|มาตรา)\s+([๐-๙0-9]+(?:/[๐-๙0-9]+)?)\s*(\D.*)$")
SUBITEM = re.compile(r"^\s*\([ก-ฮ๐-๙0-9]+\)")
STRUCTURE = re.compile(r"^\s*(?:ข้อ|มาตรา|หมวด|ส่วนที่|ภาค|ลักษณะ)\s")
DUTY = re.compile(r"^จรรยาบรรณ(ต่อ.+?)\s*$")
THAI_CONSONANT = re.compile(r"[ก-ฮ]")


def is_noise(line: str) -> bool:
    """True for the stray marks OCR leaves between blocks.

    Vision reports things like "๑๓ ๐ ข เ- 1 ข ๓๑๓" for the decorative rule above
    a heading. They are short, mostly not letters, and would otherwise be glued
    onto the start of the next section's text.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 40:
        return False
    # a bare marker or a heading can be this short and still carry meaning
    if SUBITEM.match(stripped) or STRUCTURE.match(stripped):
        return False
    return len(THAI_CONSONANT.findall(stripped)) <= 2


def body_lines(text: str):
    """Drop the masthead, the signature block and the OCR noise."""
    cut = TAIL.search(text)
    if cut:
        text = text[: cut.start()]
    for line in text.split("\n"):
        if FURNITURE.match(line) or is_noise(line):
            continue
        yield line


def paragraphs(lines: list[str]) -> str:
    """Reflow one section, keeping its lettered and numbered items apart.

    app.thai_law.clean treats a blank line as a paragraph break and every other
    newline as a wrap artifact, which is exactly right for the running text. The
    one thing it cannot know is that "(ก)" and "(๑)" start a new item, so those
    get a blank line in front of them first.
    """
    out = []
    for line in lines:
        if SUBITEM.match(line) and out:
            out.append("")
        out.append(line)
    return clean("\n".join(out))


def chunk(text: str):
    """Yield the section whole, or in pieces when it is too long.

    Cuts on a paragraph edge when there is one, because in ข้อบังคับฯ 2550 that
    edge is the boundary between two listed behaviours -- splitting mid-item
    would file half a behaviour under a section number that no longer explains
    it.
    """
    if len(text) <= MAX_CHUNK:
        yield text, 0
        return
    start = part = 0
    while start < len(text):
        end = start + MAX_CHUNK
        piece = text[start:end]
        if end < len(text):
            for stop in ("\n\n", " "):
                cut = piece.rfind(stop)
                if cut > MAX_CHUNK * 0.5:
                    piece, end = piece[:cut], start + cut
                    break
        yield piece.strip(), part
        part += 1
        start = end


def category_of(chapters: list[str]) -> str | None:
    """Which of the five duties these headings put the rule under."""
    for heading in chapters:
        title = heading.split(" ", 2)[-1] if " " in heading else heading
        match = DUTY.match(title)
        if match and match.group(1) in CATEGORIES:
            return match.group(1)
    return None


def units(text: str, unit_word: str):
    """Yield (number, body, chapters) for each ข้อ or มาตรา in document order."""
    lines = list(body_lines(text))
    chapters: dict[str, str] = {}
    number = None
    buffer: list[str] = []
    pending: tuple[str, str] | None = None  # a heading waiting for its title

    def flush():
        if number is not None and buffer:
            yield_value = (number, paragraphs(buffer), _snapshot(chapters))
            return yield_value
        return None

    for line in lines:
        if pending:
            title = line.strip()
            if title:
                kind, num = pending
                chapters[kind] = f"{kind} {to_arabic(num)} {title}"
                if kind == "หมวด":
                    chapters.pop("ส่วนที่", None)
                pending = None
            continue

        head = HEADING.match(line)
        if head:
            done = flush()
            if done:
                yield done
            number, buffer = None, []
            pending = (head.group(1), head.group(2))
            continue

        start = UNIT.match(line)
        if start and start.group(1) == unit_word:
            done = flush()
            if done:
                yield done
            number = to_arabic(start.group(2))
            buffer = [start.group(3)]
            continue

        if number is not None:
            buffer.append(line)

    done = flush()
    if done:
        yield done


def _snapshot(chapters: dict[str, str]) -> list[str]:
    """Headings in document order: the หมวด first, then the ส่วนที่ inside it."""
    return [chapters[kind] for kind in ("หมวด", "ส่วนที่") if kind in chapters]


def records(doc: Doc):
    """Yield corpus records for one document."""
    path = os.path.join(KSP_DIR, f"{doc.key}.pdf")
    text, _how = extract(path)
    seen = set()
    for number, body, chapters in units(text, doc.unit):
        if number in seen or len(body) < 20:
            continue
        seen.add(number)
        category = category_of(chapters)
        for piece, part in chunk(body):
            yield {
                "id": f"{doc.key}-{number}" + (f"-{part}" if part else ""),
                "act": doc.act,
                "act_full": doc.act,
                "sysid": doc.key,
                "section": number,
                "part": part,
                "text": piece,
                "chapters": chapters,
                "n_chars": len(piece),
                "unit": doc.unit,
                "ethics_category": category,
                "source_url": doc.url,
                "published": doc.published,
                "superseded_by": doc.superseded_by,
                "short": doc.short,
            }


# "ให้ยกเลิกความในข้อ ๗ แห่งข้อบังคับคุรุสภา ว่าด้วยการอุทธรณ์คำวินิจฉัย ...
#  พ.ศ. ๒๕๔๙ และให้ใช้ความต่อไปนี้แทน" -- an amending regulation says which
# rule of which year it replaces, and that is the only place the corpus records
# it. Without reading this, ข้อ 7 ของ 2549 looks current: it still says eleven
# members, and the nine-member replacement sits in a different document under a
# different number. The assessors caught the system answering from it.
AMENDS = re.compile(
    r"ให้ยกเลิกความใน(ข้อ|มาตรา)\s*([๐-๙0-9]+(?:/[๐-๙0-9]+)?)"
    r"[\s\S]{0,160}?พ\.ศ\.\s*([๐-๙0-9]{4})")


def mark_amendments(rows: list[dict]) -> int:
    """Point every amended rule at the rule that replaced it, and back again."""
    by_year = {}
    for row in rows:
        for year in re.findall(r"25[0-9]{2}", row.get("short") or ""):
            by_year.setdefault(year, row["sysid"])
    index = {(r["sysid"], r["unit"], r["section"]): r for r in rows}

    marked = 0
    for row in rows:
        for unit, number, raw_year in AMENDS.findall(row["text"]):
            number = to_arabic(number)
            target_id = by_year.get(to_arabic(raw_year))
            target = index.get((target_id, unit, number)) if target_id else None
            if target is None or target["sysid"] == row["sysid"]:
                continue
            target["amended_by"] = f"{row['short']} {row['unit']} {row['section']}"
            row["amends"] = f"{target['short']} {unit} {number}"
            marked += 1
    return marked


def main() -> None:
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    collected = [row for doc in DOCS for row in records(doc)]
    marked = mark_amendments(collected)
    by_doc: dict[str, list[dict]] = {}
    for row in collected:
        by_doc.setdefault(row["sysid"], []).append(row)

    total = 0
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        for doc in DOCS:
            rows = by_doc.get(doc.key, [])
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            numbers = {r["section"] for r in rows}
            tagged = {r["ethics_category"] for r in rows if r["ethics_category"]}
            note = f" [{len(tagged)} ด้าน]" if tagged else ""
            print(f"{doc.key:16s} {len(numbers):3d} {doc.unit} -> {len(rows):3d} ชิ้น{note}")
            total += len(rows)
    print(f"\n{total:,} ชิ้น -> {OUT_PATH}")
    print(f"ข้อที่ถูกแก้ไขโดยฉบับแก้ไขเพิ่มเติม: {marked} ข้อ")
    print("ต่อไป: python -m ingest.audit_ksp")


if __name__ == "__main__":
    main()
