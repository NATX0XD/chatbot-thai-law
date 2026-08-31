# -*- coding: utf-8 -*-
"""Add the codes (ประมวลกฎหมาย) that the Act corpus does not contain.

The source behind data/raw/iapp_*.parquet holds 42,755 documents and not one of
them is a code: no ประมวลกฎหมายอาญา, no ประมวลกฎหมายแพ่งและพาณิชย์. That absence
is what forced app/coverage.py to exist -- a rule that refuses every question
about tenancy, loans, guarantees, family, inheritance, defamation, fraud and
theft, because the governing text was simply not there to retrieve.

The PyThaiNLP thai-law project publishes both codes separately, hand-checked and
split one row per section, under the same public-domain terms as the Act corpus
(Copyright Act B.E. 2537 s.7 excludes government legal texts from copyright).
This module reads those CSVs and writes records in the corpus schema, so the two
sources land in one index and the retriever needs no change at all.

Two rows are dropped on purpose:

  intro-*        the enacting Act, not the code -- "พระราชบัญญัตินี้เรียกว่า ..."
                 answers no question a citizen would ask
  is-cancelled   sections repealed by later amendments. Serving a repealed rule
                 is worse than serving nothing, and the flag is the source's own.

The `notes` column is dropped too. It carries editorial annotation -- which Act
amended the section and when -- rather than the rule itself, matching how
ingest/extract_acts.py drops the footnote block from the Act text.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import RAW_DIR  # noqa: E402
from app.thai_law import clean, to_arabic  # noqa: E402
from ingest.extract_acts import chunk  # noqa: E402

# (csv file, act name as it will be cited, id prefix)
CODES = (
    ("criminal-datasets.csv", "ประมวลกฎหมายอาญา", "code-criminal"),
    ("civil-and-commercial-datasets.csv", "ประมวลกฎหมายแพ่งและพาณิชย์", "code-civil"),
)

# section numbers look like "335" or "193/27"; anything else is front matter
SECTION_RE = re.compile(r"^\d+(?:/\d+)?$")
# the row text repeats its own section heading, which the Act path also strips
HEAD_RE = re.compile(r"^\s*มาตรา\s+[๐-๙0-9]+(?:/[๐-๙0-9]+)?\s*")


def _cancelled(value) -> bool:
    """The flag arrives as 'true', ' true' or NaN depending on the row."""
    return str(value).strip().lower() == "true"


def code_records(path: str, act: str, prefix: str):
    """Yield corpus records for one code CSV."""
    df = pd.read_csv(path)
    has_flag = "is-cancelled" in df.columns
    for _, row in df.iterrows():
        no = to_arabic(str(row["article"]).strip())
        if not SECTION_RE.match(no):
            continue
        if has_flag and _cancelled(row.get("is-cancelled")):
            continue
        body = clean(HEAD_RE.sub("", str(row["text"] or "")))
        if len(body) < 20:
            continue
        for piece, part in chunk(body):
            yield {
                "id": f"{prefix}-{no}" + (f"-{part}" if part else ""),
                "act": act,
                "act_full": act,
                "sysid": prefix,
                "section": no,
                "part": part,
                "text": piece,
                # the CSVs carry no บรรพ/ลักษณะ structure, and inventing one from
                # section ranges would put a guess in a field the Act path fills
                # from the source text
                "chapters": [],
                "n_chars": len(piece),
            }


def write_codes(handle) -> tuple[int, int]:
    """Append every code to an open corpus file. Returns (codes, sections)."""
    n_codes = n_sections = 0
    for filename, act, prefix in CODES:
        path = os.path.join(RAW_DIR, filename)
        if not os.path.exists(path):
            print(f"ข้าม {act}: ไม่พบ {path}")
            continue
        written = 0
        for rec in code_records(path, act, prefix):
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
        n_codes += 1
        n_sections += written
        print(f"{act}: {written:,} ชิ้น")
    return n_codes, n_sections


def main() -> None:
    """Standalone run, for checking the parse without rebuilding the corpus."""
    for filename, act, prefix in CODES:
        path = os.path.join(RAW_DIR, filename)
        recs = list(code_records(path, act, prefix))
        sections = {r["section"] for r in recs}
        print(f"{act}: {len(sections):,} มาตรา -> {len(recs):,} ชิ้น")
        print(f"   ตัวอย่าง ม.{recs[0]['section']}: {recs[0]['text'][:80]}")


if __name__ == "__main__":
    main()
