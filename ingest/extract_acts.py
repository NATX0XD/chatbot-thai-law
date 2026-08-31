# -*- coding: utf-8 -*-
"""Extract every section of every Act (พระราชบัญญัติ / พระราชกำหนด) into a JSONL corpus.

The source corpus keeps one row per *revision* of an act, so the same act appears
many times. Serving an old revision would give the user a rule that no longer
applies, so we keep exactly one revision per act -- see pick_current_revision.

    python -m ingest.extract_acts
"""
import json
import os
import re
import sys

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import PROCESSED_DIR, RAW_DIR  # noqa: E402
from app.thai_law import chapters, sections  # noqa: E402

OUT = os.path.join(PROCESSED_DIR, "corpus.jsonl")

ACT_PREFIXES = ("พระราชบัญญัติ", "พระราชกำหนด", "ประมวล")
UPDATE_RE = re.compile(r"\s*\((ฉบับ\s*)?Update.*?\)\s*$")
LATEST_RE = re.compile(r"Update\s*ล่าสุด")
# an amending act only lists the edits; the consolidated act already contains them
AMENDMENT_RE = re.compile(r"^พระราชบัญญัติแก้ไขเพิ่มเติม")
# "พระราชบัญญัติคุ้มครองแรงงาน (ฉบับที่ 7) พ.ศ. 2562" is the same thing under a
# different naming convention: its sections read "ให้ยกเลิกความในมาตรา ... และให้ใช้
# ความต่อไปนี้แทน". Keeping them puts near-duplicate text in the index that competes
# with the consolidated section and cites a section number that means something else.
REVISION_RE = re.compile(r"\(ฉบับที่\s*[๐-๙0-9]+\)")
YEAR_RE = re.compile(r"(พ\.ศ\.|พุทธศักราช)\s*[๐-๙0-9]{4}")
# annual budget acts are tables of allocations, not rules -- they answer no question
# a citizen would ask, and their sections run to 40k characters of digits
NOISE_RE = re.compile(r"งบประมาณรายจ่าย|โอนงบประมาณ|โอนเงินงบประมาณ")

MAX_CHUNK = 1800   # characters; keeps a chunk inside the embedder's useful window
OVERLAP = 200


def chunk(text: str):
    """Yield the section as-is, or as overlapping pieces when it is too long."""
    if len(text) <= MAX_CHUNK:
        yield text, 0
        return
    start, part = 0, 0
    while start < len(text):
        end = start + MAX_CHUNK
        piece = text[start:end]
        if end < len(text):
            cut = piece.rfind(" ")
            if cut > MAX_CHUNK * 0.6:
                piece, end = piece[:cut], start + cut
        yield piece.strip(), part
        part += 1
        start = max(end - OVERLAP, end)


def base_title(title: str) -> str:
    """Strip the revision marker and normalise whitespace.

    Source titles are inconsistent about spacing -- "ขายตรงและตลาดแบบตรง  พ.ศ. 2545"
    and "ขายตรงและตลาดแบบตรง พ.ศ. 2545" are the same act -- so without this the
    grouping keeps both and the index carries the act twice.
    """
    return re.sub(r"\s+", " ", UPDATE_RE.sub("", title)).strip()


def pick_current_revision(group: pd.DataFrame) -> pd.Series:
    """Prefer the revision the source itself marks as latest, else the longest text.

    The longest text is a good proxy because each amendment adds sections and
    footnotes; it is never shorter than the revision it replaces.
    """
    latest = group[group.title.str.contains(LATEST_RE, na=False)]
    pool = latest if len(latest) else group
    return pool.loc[pool.n.idxmax()]


def load_corpus() -> pd.DataFrame:
    frames = [pq.read_table(os.path.join(RAW_DIR, f)).to_pandas()
              for f in ("iapp_0.parquet", "iapp_1.parquet")]
    df = pd.concat(frames, ignore_index=True)
    df["title"] = df["title"].fillna("").str.strip()
    df["txt"] = df["txt"].fillna("")
    df["n"] = df["txt"].str.len()
    return df


def main():
    df = load_corpus()
    acts = df[df.title.str.startswith(ACT_PREFIXES)
              & ~df.title.str.match(AMENDMENT_RE)
              & ~df.title.str.contains(NOISE_RE, na=False)]
    print(f"acts (all revisions): {len(acts):,}")

    acts = acts.assign(base=acts.title.map(base_title))
    current = pd.DataFrame([pick_current_revision(g) for _, g in acts.groupby("base")])
    print(f"acts (current revision only): {len(current):,}")

    # drop "(ฉบับที่ N)" acts whose consolidated parent is present -- but keep the
    # orphans, where no consolidated text exists and the amendment is all we have.
    # Matching is on the act name with both the revision marker and the year removed,
    # because an amendment carries its own year: "พระราชบัญญัติยา (ฉบับที่ 3)
    # พ.ศ. 2522" amends "พระราชบัญญัติยา พ.ศ. 2510".
    def act_name(title: str) -> str:
        name = REVISION_RE.sub("", title)
        name = YEAR_RE.sub("", name)
        return re.sub(r"\s+", " ", name).strip()

    consolidated = {act_name(t) for t in current.base if not REVISION_RE.search(t)}

    def superseded(title: str) -> bool:
        return bool(REVISION_RE.search(title)) and act_name(title) in consolidated

    before = len(current)
    current = current[~current.base.map(superseded)]
    print(f"acts after dropping superseded amendments: {len(current):,} "
          f"(-{before - len(current):,})")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n_sections, n_skipped, n_acts = 0, 0, 0
    with open(OUT, "w", encoding="utf-8") as f:
        for _, row in current.iterrows():
            heads = {}
            for kind, num, head in chapters(row.txt):
                heads.setdefault(f"{kind} {num}", head)
            chapter_list = [f"{k} {v}" for k, v in heads.items()]
            act_sections = list(sections(row.txt))
            if not act_sections:
                n_skipped += 1
                continue
            n_acts += 1
            for no, body in act_sections:
                if len(body) < 20:  # stubs like "(ยกเลิก)" carry no answer
                    continue
                for piece, part in chunk(body):
                    f.write(json.dumps({
                        "id": f"{row.sysid}-{no}" + (f"-{part}" if part else ""),
                        "act": row.base,
                        "act_full": row.title,
                        "sysid": str(row.sysid),
                        "section": no,
                        "part": part,
                        "text": piece,
                        "chapters": chapter_list[:40],
                        "n_chars": len(piece),
                    }, ensure_ascii=False) + "\n")
                    n_sections += 1

    print(f"acts written : {n_acts:,}")
    print(f"acts skipped : {n_skipped:,} (no parsable มาตรา -- usually a schedule or a repeal)")
    print(f"sections     : {n_sections:,}")

    # the codes come from a different source and are appended to the same file:
    # one corpus means one index, and the retriever cannot tell them apart.
    # Chained rather than left as a separate command, because a corpus rebuilt
    # without them would quietly go back to refusing every question about
    # tenancy, inheritance or theft.
    from ingest.extract_codes import write_codes
    from ingest.extract_computer_act import write_computer_act
    with open(OUT, "a", encoding="utf-8") as f:
        n_codes, n_code_sections = write_codes(f)
        # appended last, and it must stay last: the dense index can be extended
        # instead of rebuilt only while the earlier records keep their positions
        n_cca = write_computer_act(f)
    print(f"codes        : {n_codes} ฉบับ, {n_code_sections:,} ชิ้น")
    print(f"รวม          : {n_sections + n_code_sections + n_cca:,} ชิ้น")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
