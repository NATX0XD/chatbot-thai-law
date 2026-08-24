# -*- coding: utf-8 -*-
"""Build the Thai-law dataset survey document and the chatbot-ready exports.

Reads the four downloaded HuggingFace corpora from data/raw/ and writes:
  report/รายงานชุดข้อมูลกฎหมายไทย.md   the ~100 page survey
  data/processed/sections.jsonl         every section of the 12 profiled acts
  data/processed/qa_pairs.jsonl         the WangchanX question/answer pairs, flattened
  data/processed/corpus_stats.csv       per-document statistics for the whole corpus

Run from the project root:  python -m report.build_doc
"""
import collections
import csv
import json
import os
import re
import sys

import pandas as pd
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)
sys.path.insert(0, HERE)
from app import thai_law as L  # noqa: E402
from app.config import PROCESSED_DIR, RAW_DIR  # noqa: E402

RAW = RAW_DIR
REPORT = HERE
EXPORT = PROCESSED_DIR
CHARS_PER_PAGE = 2700  # A4, Sarabun 16pt, single spacing -- the KMUTNB thesis default
THAI_NUM = "๐๑๒๓๔๕๖๗๘๙"


def thai_num(n):
    return "".join(THAI_NUM[int(d)] for d in str(n))

# ---------------------------------------------------------------- law selection

# (search key, short name, domain, char budget, priority sections rendered first)
LAWS = [
    ("คุ้มครองแรงงาน พ.ศ. 2541 (ฉบับ Update ล่าสุด)", "พ.ร.บ.คุ้มครองแรงงาน 2541", "แรงงาน", 34000,
     ["5", "9", "11/1", "17", "17/1", "20", "23", "24", "30", "32", "34", "41", "42",
      "44", "55", "56", "57", "58", "59", "61", "62", "63", "67", "70", "75", "76",
      "118", "119", "120", "121", "122", "123", "124", "125", "144"]),
    ("พระราชบัญญัติการทวงถามหนี้ พ.ศ. 2558", "พ.ร.บ.การทวงถามหนี้ 2558", "หนี้สิน", 21000, []),
    ("พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562", "พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคล 2562", "ข้อมูลส่วนบุคคล", 17000,
     ["4", "6", "19", "21", "22", "23", "24", "26", "27", "30", "31", "32", "33", "34",
      "37", "39", "40", "41", "42", "77", "79", "82", "83"]),
    ("พระราชบัญญัติคุ้มครองผู้บริโภค พ.ศ. 2522 (ฉบับ Update ล่าสุด)", "พ.ร.บ.คุ้มครองผู้บริโภค 2522", "ผู้บริโภค", 12000,
     ["3", "4", "20", "21", "22", "23", "26", "27", "29", "30", "31", "35", "35 ทวิ",
      "36", "39", "47", "48", "52", "56", "57", "59"]),
    ("พระราชบัญญัติเงินทดแทน พ.ศ. 2537 (ฉบับ Update ล่าสุด)", "พ.ร.บ.เงินทดแทน 2537", "แรงงาน", 11000,
     ["5", "13", "15", "16", "18", "20", "21", "22", "25", "26", "44", "49"]),
    ("พระราชบัญญัติความรับผิดต่อความเสียหายที่เกิดขึ้นจากสินค้าที่ไม่ปลอดภัย พ.ศ. 2551",
     "พ.ร.บ.ความรับผิดต่อสินค้าไม่ปลอดภัย 2551", "ผู้บริโภค", 7000, []),
    ("พระราชบัญญัติขายตรงและตลาดแบบตรง พ.ศ. 2545  (ฉบับ Update ล่าสุด)", "พ.ร.บ.ขายตรงและตลาดแบบตรง 2545", "ผู้บริโภค", 9000,
     ["3", "19", "20", "21", "27", "30", "31", "32", "33", "34", "35", "36", "38", "46", "47"]),
    ("พระราชบัญญัติจัดตั้งศาลแรงงานและวิธีพิจารณาคดีแรงงาน พ.ศ. 2522 (ฉบับ Update ล่าสุด)",
     "พ.ร.บ.จัดตั้งศาลแรงงานฯ 2522", "แรงงาน", 7000,
     ["8", "9", "26", "27", "31", "33", "35", "36", "39", "49", "52", "54"]),
    ("พระราชบัญญัติจัดหางานและคุ้มครองคนหางาน พ.ศ. 2528 (ฉบับ Update ล่าสุด)",
     "พ.ร.บ.จัดหางานและคุ้มครองคนหางาน 2528", "แรงงาน", 7000,
     ["4", "30", "31", "34", "36", "39", "46", "48", "63", "66", "82", "91"]),
    ("พระราชบัญญัติกองทุนเงินให้กู้ยืมเพื่อการศึกษา พ.ศ. 2560 (ฉบับ Update ล่าสุด)", "พ.ร.บ.กองทุน กยศ. 2560", "การศึกษา/หนี้", 7000,
     ["4", "39", "40", "41", "44", "45", "46", "47", "51"]),
    ("พระราชบัญญัติความเท่าเทียมระหว่างเพศ พ.ศ. 2558", "พ.ร.บ.ความเท่าเทียมระหว่างเพศ 2558", "สิทธิพลเมือง", 7000, []),
    ("พระราชบัญญัติภาษีที่ดินและสิ่งปลูกสร้าง พ.ศ. 2562", "พ.ร.บ.ภาษีที่ดินและสิ่งปลูกสร้าง 2562", "ที่ดิน/ภาษี", 7000,
     ["5", "8", "9", "37", "38", "40", "41", "43", "44", "46", "50", "51", "52", "60", "68", "94"]),
]

# everyday-law coverage probes: (label, needle, regex?)
COVERAGE_PROBES = [
    ("ประมวลกฎหมายแพ่งและพาณิชย์ (เช่า/ยืม/ค้ำประกัน/ครอบครัว/มรดก)", "ประมวลกฎหมายแพ่งและพาณิชย์"),
    ("ประมวลกฎหมายอาญา", "ประมวลกฎหมายอาญา"),
    ("ประมวลกฎหมายวิธีพิจารณาความแพ่ง", "ประมวลกฎหมายวิธีพิจารณาความแพ่ง"),
    ("ประมวลกฎหมายวิธีพิจารณาความอาญา", "ประมวลกฎหมายวิธีพิจารณาความอาญา"),
    ("ประมวลกฎหมายที่ดิน", "ประมวลกฎหมายที่ดิน"),
    ("ประมวลรัษฎากร", "ประมวลรัษฎากร"),
    ("พ.ร.บ.ประกันสังคม", "พระราชบัญญัติประกันสังคม"),
    ("พ.ร.บ.ว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์", "การกระทำความผิดเกี่ยวกับคอมพิวเตอร์"),
    ("พ.ร.บ.ว่าด้วยข้อสัญญาที่ไม่เป็นธรรม", "ข้อสัญญาที่ไม่เป็นธรรม"),
    ("พ.ร.บ.วิธีพิจารณาคดีผู้บริโภค", "วิธีพิจารณาคดีผู้บริโภค"),
    ("พ.ร.บ.แรงงานสัมพันธ์", "แรงงานสัมพันธ์"),
    ("พ.ร.บ.ห้ามเรียกดอกเบี้ยเกินอัตรา", "ห้ามเรียกดอกเบี้ย"),
    ("พ.ร.บ.อาคารชุด", "พระราชบัญญัติอาคารชุด"),
    ("พ.ร.บ.การเช่าอสังหาริมทรัพย์เพื่อพาณิชยกรรมและอุตสาหกรรม", "การเช่าอสังหาริมทรัพย์"),
    ("พ.ร.บ.หลักประกันสุขภาพแห่งชาติ", "พระราชบัญญัติหลักประกันสุขภาพ"),
    ("พ.ร.บ.คุ้มครองแรงงาน", "พระราชบัญญัติคุ้มครองแรงงาน"),
    ("พ.ร.บ.การทวงถามหนี้", "พระราชบัญญัติการทวงถามหนี้"),
    ("พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคล", "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล"),
    ("พ.ร.บ.คุ้มครองผู้บริโภค", "พระราชบัญญัติคุ้มครองผู้บริโภค"),
    ("พ.ร.บ.จราจรทางบก", "พระราชบัญญัติจราจรทางบก"),
    ("พ.ร.บ.เงินทดแทน", "พระราชบัญญัติเงินทดแทน"),
    ("พ.ร.บ.การทะเบียนราษฎร", "พระราชบัญญัติการทะเบียนราษฎร"),
    ("พ.ร.บ.ภาษีที่ดินและสิ่งปลูกสร้าง", "พระราชบัญญัติภาษีที่ดินและสิ่งปลูกสร้าง"),
    ("พ.ร.บ.กองทุนเงินให้กู้ยืมเพื่อการศึกษา", "พระราชบัญญัติกองทุนเงินให้กู้ยืมเพื่อการศึกษา"),
]


def load():
    thai = pd.concat(
        [pq.read_table(os.path.join(RAW, f)).to_pandas() for f in ("thailaw_0.parquet", "thailaw_1.parquet")],
        ignore_index=True,
    )
    iapp = pd.concat(
        [pq.read_table(os.path.join(RAW, f)).to_pandas() for f in ("iapp_0.parquet", "iapp_1.parquet")],
        ignore_index=True,
    )
    wc_tr = pq.read_table(os.path.join(RAW, "wangchan_train.parquet")).to_pandas()
    wc_te = pq.read_table(os.path.join(RAW, "wangchan_test.parquet")).to_pandas()
    for df in (thai, iapp):
        df["title"] = df["title"].fillna("").str.strip()
        df["txt"] = df["txt"].fillna("")
        df["n"] = df["txt"].str.len()
    return thai, iapp, wc_tr, wc_te


def doc_type(title):
    for p in ["รัฐธรรมนูญ", "พระราชบัญญัติประกอบรัฐธรรมนูญ", "พระราชบัญญัติ", "พระราชกำหนด",
              "พระราชกฤษฎีกา", "กฎกระทรวง", "ประกาศ", "ระเบียบ", "ข้อบังคับ", "คำสั่ง",
              "เทศบัญญัติ", "ข้อบัญญัติ", "กฎบัตร", "กฎ"]:
        if title.startswith(p):
            return p
    return "อื่น ๆ"


def md_table(headers, rows, align=None):
    align = align or ["-"] * len(headers)
    sep = {"-": ":---", "r": "---:", "c": ":---:"}
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(sep[a] for a in align) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def pick_sections(raw, budget, priority):
    """Full section bodies: priority list first, then document order, until budget runs out."""
    ordered = list(L.sections(raw))
    by_no = dict(ordered)
    chosen, used, spent = [], set(), 0
    for no in priority:
        body = by_no.get(no)
        if body and no not in used:
            chosen.append((no, body))
            used.add(no)
            spent += len(body)
    rest = []
    for no, body in ordered:
        if no in used:
            continue
        if spent + len(body) > budget:
            rest.append(no)
            continue
        chosen.append((no, body))
        used.add(no)
        spent += len(body)
    chosen.sort(key=lambda kv: [int(x) for x in re.findall(r"\d+", kv[0])] or [0])
    return chosen, rest, spent, len(ordered)


# ---------------------------------------------------------------- statistics

def stats_chapter(thai, iapp, wc_tr, wc_te):
    out = ["## บทที่ ๔ สถิติเชิงลึกของคลังข้อมูล\n"]
    out.append("### ๔.๑ ขนาดโดยรวม\n")
    total = int(iapp.n.sum())
    out.append(md_table(
        ["รายการ", "ค่าที่วัดได้"],
        [["จำนวนเอกสารทั้งหมด", f"{len(iapp):,} ฉบับ"],
         ["ความยาวรวม", f"{total:,} ตัวอักษร"],
         ["เทียบเป็นหน้า A4", f"ประมาณ {total // CHARS_PER_PAGE:,} หน้า"],
         ["เทียบเป็นหนังสือ ๓๐๐ หน้า", f"ประมาณ {total // (CHARS_PER_PAGE * 300):,} เล่ม"],
         ["ความยาวเฉลี่ยต่อฉบับ", f"{int(iapp.n.mean()):,} ตัวอักษร"],
         ["ความยาวมัธยฐาน", f"{int(iapp.n.median()):,} ตัวอักษร"],
         ["ฉบับที่สั้นที่สุด", f"{int(iapp.n.min()):,} ตัวอักษร"],
         ["ฉบับที่ยาวที่สุด", f"{int(iapp.n.max()):,} ตัวอักษร"]],
        ["-", "r"]))
    out.append("""
ตัวเลขความยาวมัธยฐานที่ต่ำกว่าค่าเฉลี่ยมากบอกว่าการกระจายตัวเบ้ขวาอย่างรุนแรง คือมีเอกสารสั้นจำนวนมหาศาลและเอกสารยาวมากจำนวนน้อย เอกสารสั้นเหล่านั้นส่วนใหญ่คือประกาศของหน่วยงานที่มีเนื้อหาไม่กี่บรรทัด ซึ่งมีผลต่อการออกแบบดัชนีค้นคืนโดยตรง เพราะการตัดชิ้นส่วนด้วยขนาดคงที่จะทำให้เอกสารสั้นเหล่านี้กลายเป็นชิ้นส่วนที่ไร้บริบท
""")

    out.append("\n### ๔.๒ การกระจายตัวของความยาว\n")
    bins = [(0, 500), (500, 1000), (1000, 2000), (2000, 5000), (5000, 10000),
            (10000, 30000), (30000, 100000), (100000, 10**9)]
    rows = []
    for lo, hi in bins:
        c = int(((iapp.n >= lo) & (iapp.n < hi)).sum())
        label = f"{lo:,}–{hi:,}" if hi < 10**9 else f"มากกว่า {lo:,}"
        bar = "█" * max(1, round(60 * c / len(iapp))) if c else ""
        rows.append([label, f"{c:,}", f"{100 * c / len(iapp):.1f}%", bar])
    out.append(md_table(["ช่วงความยาว (ตัวอักษร)", "จำนวนฉบับ", "สัดส่วน", "แผนภูมิ"], rows, ["-", "r", "r", "-"]))
    out.append("""
กว่าครึ่งของคลังเป็นเอกสารที่สั้นกว่าสามพันตัวอักษร ในทางปฏิบัติหมายความว่าเอกสารเหล่านี้ควรถูกทำดัชนีทั้งฉบับเป็นชิ้นส่วนเดียว ไม่ต้องตัดย่อย ส่วนเอกสารกลุ่มที่ยาวเกินหนึ่งหมื่นตัวอักษรซึ่งมีอยู่ราวหนึ่งในหก คือกลุ่มที่ต้องตัดตามมาตราตามวิธีในบทที่ ๖
""")

    out.append("\n### ๔.๓ ประเภทเอกสาร\n")
    dt = iapp.title.map(doc_type).value_counts()
    rows = [[k, f"{v:,}", f"{100 * v / len(iapp):.1f}%",
             "█" * max(1, round(60 * v / len(iapp)))] for k, v in dt.items()]
    out.append(md_table(["ประเภท", "จำนวน", "สัดส่วน", "แผนภูมิ"], rows, ["-", "r", "r", "-"]))
    out.append("""
ข้อสังเกตที่สำคัญที่สุดจากตารางนี้คือ พระราชบัญญัติซึ่งเป็นสิ่งที่คนทั่วไปเรียกว่า "กฎหมาย" มีสัดส่วนไม่ถึงร้อยละห้าของคลัง ส่วนที่เหลืออีกกว่าร้อยละเก้าสิบเป็นกฎหมายลำดับรอง คือประกาศ กฎกระทรวง ระเบียบ และข้อบัญญัติท้องถิ่น

สัดส่วนนี้เป็นทั้งโอกาสและกับดัก โอกาสคือกฎหมายลำดับรองมักมีรายละเอียดที่ตอบคำถามเชิงปฏิบัติได้ตรงกว่าตัวพระราชบัญญัติ เช่น อัตราค่าธรรมเนียม แบบฟอร์ม และเงื่อนไขเฉพาะ ส่วนกับดักคือถ้าไม่จัดลำดับความสำคัญ ระบบค้นคืนจะดึงประกาศท้องถิ่นที่ไม่เกี่ยวข้องขึ้นมาก่อนตัวบทหลัก เพราะประกาศเหล่านั้นมีจำนวนมากกว่าหลายสิบเท่าและมักใช้ถ้อยคำซ้ำกัน

ข้อเสนอคือใส่น้ำหนักตามลำดับศักดิ์ของกฎหมายในขั้นจัดอันดับ ให้พระราชบัญญัติและพระราชกำหนดมาก่อนกฎกระทรวง และให้ข้อบัญญัติท้องถิ่นมาท้ายสุด เว้นแต่ผู้ใช้ระบุพื้นที่มาชัดเจน
""")

    out.append("\n### ๔.๔ ความทันสมัยของข้อมูล\n")
    yr = iapp.title.str.extract(r"พ\.ศ\.\s*(2[45]\d\d)")[0].dropna().astype(int)
    yr = yr[(yr >= 2500) & (yr <= 2570)]
    vc = yr.value_counts().sort_index()
    peak = int(vc.max())
    rows = []
    for y, c in vc.items():
        if y >= 2535:
            rows.append([y, f"{c:,}", "█" * max(1, round(48 * c / peak))])
    out.append(md_table(["พ.ศ. ที่ปรากฏในชื่อเอกสาร", "จำนวนฉบับ", "แผนภูมิ"], rows, ["r", "r", "-"]))
    out.append(f"""
เอกสารที่ระบุปีในชื่อมี {len(yr):,} ฉบับ คิดเป็นร้อยละ {100 * len(yr) / len(iapp):.0f} ของคลัง ที่เหลือเป็นประกาศที่ไม่ระบุปีในชื่อ

รูปทรงของแผนภูมิคือหลักฐานสำคัญที่สุดข้อหนึ่งของรายงานนี้ จำนวนเอกสารเพิ่มขึ้นต่อเนื่องจนถึงจุดสูงสุดช่วง ๒๕๕๙ ถึง ๒๕๖๑ แล้วร่วงลงอย่างฉับพลัน ปี ๒๕๖๒ เหลือ {int(vc.get(2562, 0)):,} ฉบับ ปี ๒๕๖๓ เหลือ {int(vc.get(2563, 0)):,} ฉบับ และปี ๒๕๖๔ เหลือ {int(vc.get(2564, 0)):,} ฉบับ

การลดลงแบบนี้ไม่ใช่รูปแบบของการออกกฎหมายจริง เพราะรัฐไทยไม่ได้หยุดออกกฎหมายในปี ๒๕๖๓ แต่เป็นรูปแบบของการเก็บข้อมูลที่หยุดลง ข้อสรุปคือคลังนี้สะท้อนกฎหมายไทย ณ ราวปี ๒๕๖๓ ระบบที่สร้างจากคลังนี้จึงต้องแจ้งข้อจำกัดนี้ต่อผู้ใช้อย่างชัดเจน และต้องมีแผนเก็บข้อมูลเพิ่มเอง
""")

    out.append("\n### ๔.๕ การซ้ำซ้อนของเอกสารฉบับปรับปรุง\n")
    base = iapp.title.str.replace(r"\s*\((ฉบับ )?Update.*?\)\s*$", "", regex=True).str.strip()
    dup = base.value_counts()
    multi = int((dup > 1).sum())
    out.append(md_table(
        ["รายการ", "ค่าที่วัดได้"],
        [["ชื่อเอกสารฐานที่ไม่ซ้ำกัน", f"{base.nunique():,}"],
         ["ชื่อฐานที่มีมากกว่าหนึ่งฉบับ", f"{multi:,}"],
         ["เอกสารส่วนเกินจากการเก็บทุกรุ่น", f"{len(iapp) - base.nunique():,}"],
         ["สัดส่วนส่วนเกิน", f"{100 * (len(iapp) - base.nunique()) / len(iapp):.1f}%"]],
        ["-", "r"]))
    top = [[t[:70], c] for t, c in dup.head(10).items()]
    out.append("\nชื่อฐานที่มีจำนวนฉบับมากที่สุดสิบอันดับแรก\n")
    out.append(md_table(["ชื่อเอกสารฐาน", "จำนวนฉบับ"], top, ["-", "r"]))
    out.append("""
ความซ้ำซ้อนนี้มีสองสาเหตุที่ต้องแยกจากกัน สาเหตุแรกคือกฎหมายฉบับเดียวถูกเก็บไว้หลายรุ่นตามการแก้ไข สังเกตได้จากวงเล็บที่ระบุว่าเป็นฉบับปรับปรุง ณ วันที่ใด กรณีนี้ต้องกรองให้เหลือเฉพาะรุ่นล่าสุด มิฉะนั้นระบบอาจตอบด้วยตัวบทที่ถูกแก้ไปแล้ว

สาเหตุที่สองคือประกาศที่ใช้ชื่อเรื่องเดียวกันซ้ำ ๆ แต่มีเนื้อหาต่างกันจริง เช่น ประกาศเรื่องพื้นที่ปรากฏเหตุการณ์อันกระทบต่อความมั่นคง ซึ่งออกใหม่ทุกช่วงเวลาและระบุพื้นที่ต่างกัน กรณีนี้ห้ามกรองทิ้ง เพราะแต่ละฉบับคือข้อมูลคนละชุด

การแยกสองกรณีนี้ทำได้ด้วยการดูวงเล็บระบุรุ่นในชื่อ ถ้ามีคำว่า Update ให้เก็บฉบับที่ยาวที่สุดหรือรหัสเอกสารสูงสุด ถ้าไม่มีให้เก็บทุกฉบับ
""")

    out.append("\n### ๔.๖ สถิติของชุดคำถาม-คำตอบ\n")
    wc = pd.concat([wc_tr.assign(split="train"), wc_te.assign(split="test")], ignore_index=True)
    qlen = wc.question.str.len()
    alen = wc.positive_answer.fillna("").str.len()
    npos = wc.positive_contexts.map(len)
    nneg = wc.hard_negative_contexts.map(len)
    out.append(md_table(
        ["รายการ", "ชุดฝึก", "ชุดทดสอบ", "รวม"],
        [["จำนวนคู่ถาม-ตอบ", f"{len(wc_tr):,}", f"{len(wc_te):,}", f"{len(wc):,}"],
         ["ความยาวคำถามเฉลี่ย", f"{int(wc_tr.question.str.len().mean())}",
          f"{int(wc_te.question.str.len().mean())}", f"{int(qlen.mean())}"],
         ["ความยาวคำตอบเฉลี่ย", f"{int(wc_tr.positive_answer.fillna('').str.len().mean()):,}",
          f"{int(wc_te.positive_answer.fillna('').str.len().mean()):,}", f"{int(alen.mean()):,}"],
         ["บริบทเชิงบวกเฉลี่ยต่อข้อ", f"{wc_tr.positive_contexts.map(len).mean():.2f}",
          f"{wc_te.positive_contexts.map(len).mean():.2f}", f"{npos.mean():.2f}"],
         ["บริบทเชิงลบเฉลี่ยต่อข้อ", f"{wc_tr.hard_negative_contexts.map(len).mean():.2f}",
          f"{wc_te.hard_negative_contexts.map(len).mean():.2f}", f"{nneg.mean():.2f}"]],
        ["-", "r", "r", "r"]))

    cnt = collections.Counter()
    secs = collections.Counter()
    for ctxs in wc.positive_contexts:
        for c in ctxs:
            cnt[c["metadata"]["law_title"]] += 1
            secs[(c["metadata"]["law_title"], c["metadata"]["section"])] += 1
    out.append(f"\nชุดข้อมูลอ้างอิงกฎหมาย {len(cnt)} ฉบับ และอ้างถึงมาตราที่ไม่ซ้ำกัน {len(secs):,} มาตรา การกระจายตัวตามกฎหมายเป็นดังนี้\n")
    tot = sum(cnt.values())
    rows = [[t[:64], f"{v:,}", f"{100 * v / tot:.1f}%"] for t, v in cnt.most_common()]
    out.append(md_table(["กฎหมายที่อ้างอิง", "จำนวนครั้ง", "สัดส่วน"], rows, ["-", "r", "r"]))
    out.append("""
ตารางนี้คือหลักฐานของข้อค้นพบที่ ๖ ในบทสรุป กฎหมายห้าอันดับแรกล้วนเป็นกฎหมายธุรกิจและตลาดทุน ไม่มีพระราชบัญญัติคุ้มครองแรงงาน ไม่มีกฎหมายเช่าทรัพย์ ไม่มีกฎหมายครอบครัวและมรดก

แม้ประมวลกฎหมายแพ่งและพาณิชย์จะขึ้นเป็นอันดับหนึ่ง แต่เมื่อตรวจดูมาตราที่อ้างจริงจะพบว่ากระจุกอยู่ที่หมวดหุ้นส่วนบริษัทและนิติกรรมสัญญาเชิงธุรกิจ ไม่ใช่บรรพครอบครัวหรือบรรพมรดก

ข้อสรุปเชิงปฏิบัติคือ ชุดนี้ใช้ฝึกและประเมิน "ความสามารถในการค้นมาตราให้ตรง" ได้ดีเยี่ยม แต่ใช้ประเมิน "ความสามารถในการตอบคำถามชาวบ้าน" ไม่ได้ ต้องสร้างชุดประเมินของตนเองเพิ่ม ตามข้อเสนอในบทที่ ๙
""")
    return "\n".join(out) + "\n\n---\n\n"


# ---------------------------------------------------------------- coverage probe

def coverage_table(iapp):
    rows = []
    for label, needle in COVERAGE_PROBES:
        hit = iapp[iapp.title.str.contains(needle, na=False, regex=False)]
        if len(hit) == 0:
            rows.append([label, "0", "**ไม่พบ**", "—"])
            continue
        # the document is the act itself only when its title *starts* with the needle;
        # anything else merely cites it
        own = hit[hit.title.str.startswith(needle)]
        if len(own):
            verdict, top = "พบตัวบท", own.sort_values("n", ascending=False).iloc[0]
        else:
            verdict, top = "**พบแต่ไม่ใช่ตัวบท**", hit.sort_values("n", ascending=False).iloc[0]
        rows.append([label, f"{len(hit):,}", verdict, top.title[:58]])
    return md_table(["กฎหมายที่ตรวจหา", "จำนวนที่พบ", "ผล", "เอกสารที่ยาวที่สุดที่พบ"],
                    rows, ["-", "r", "-", "-"])


# ---------------------------------------------------------------- law content

def law_chapters(iapp):
    """Render the profiled acts and collect their sections for export."""
    parts, export, summary = [], [], []
    for n, (key, short, domain, budget, priority) in enumerate(LAWS, start=1):
        hit = iapp[iapp.title.str.contains(key, na=False, regex=False)]
        if hit.empty:
            continue
        row = hit.sort_values("n", ascending=False).iloc[0]
        chosen, rest, spent, total_secs = pick_sections(row.txt, budget, priority)
        chaps = list(L.chapters(row.txt))

        for no, body in L.sections(row.txt):
            export.append({"law": short, "law_full": row.title, "domain": domain,
                           "sysid": str(row.sysid), "section": no,
                           "text": body, "n_chars": len(body)})

        parts.append(f"\n### ๗.{thai_num(n)} {short}\n")
        parts.append(md_table(
            ["รายการ", "ค่า"],
            [["ชื่อเต็มตามต้นฉบับ", row.title],
             ["รหัสเอกสารต้นทาง", row.sysid],
             ["หมวดที่จัดไว้", domain],
             ["ความยาวข้อความดิบ", f"{int(row.n):,} ตัวอักษร"],
             ["จำนวนมาตราที่สกัดได้", f"{total_secs} มาตรา"],
             ["จำนวนหมวด", f"{len(chaps)} หมวด"],
             ["มาตราที่แสดงในรายงานนี้", f"{len(chosen)} มาตรา ({spent:,} ตัวอักษร)"]],
            ["-", "-"]))

        if chaps:
            parts.append("\n**โครงสร้างหมวด**\n")
            parts.append(md_table(["ลำดับ", "หัวข้อ"],
                                  [[f"{k} {num}", head] for k, num, head in chaps], ["-", "-"]))
        if rest:
            shown = ", ".join(rest[:40]) + (" …" if len(rest) > 40 else "")
            parts.append(f"\n> มาตราที่ไม่ได้แสดงในรายงานเนื่องจากข้อจำกัดความยาว รวม {len(rest)} มาตรา "
                         f"ได้แก่มาตรา {shown} ตัวบทฉบับเต็มทุกมาตราอยู่ในไฟล์ `export/sections.jsonl`\n")

        parts.append("\n**ตัวบท**\n")
        for no, body in chosen:
            parts.append(f"\n**มาตรา {no}** {L.to_arabic(body) if False else body}\n")
        summary.append([short, domain, total_secs, f"{int(row.n):,}", len(chosen)])
    return "\n".join(parts), export, summary


# ---------------------------------------------------------------- QA samples

def qa_chapter(wc_tr, wc_te, n_samples=72, answer_limit=800):
    wc = pd.concat([wc_tr.assign(split="train"), wc_te.assign(split="test")], ignore_index=True)
    export = []
    for _, r in wc.iterrows():
        pos = list(r.positive_contexts)
        export.append({
            "split": r.split,
            "question": r.question,
            "answer": r.positive_answer,
            "wrong_answer": r.hard_negative_answer,
            "laws": sorted({c["metadata"]["law_title"] for c in pos}),
            "sections": [f'{c["metadata"]["law_title"]} มาตรา {c["metadata"]["section"]}' for c in pos],
            "n_pos": len(pos),
            "n_neg": len(r.hard_negative_contexts),
        })

    # spread the samples across the laws instead of letting ป.พ.พ. dominate
    by_law = collections.defaultdict(list)
    for idx, e in enumerate(export):
        if e["laws"] and e["answer"]:
            by_law[e["laws"][0]].append(idx)
    order, cursor = [], 0
    laws_cycle = sorted(by_law, key=lambda k: -len(by_law[k]))
    while len(order) < n_samples and any(cursor < len(by_law[k]) for k in laws_cycle):
        for k in laws_cycle:
            if cursor < len(by_law[k]) and len(order) < n_samples:
                order.append(by_law[k][cursor])
        cursor += 1

    parts = []
    for i, idx in enumerate(order, start=1):
        e = export[idx]
        cite = "; ".join(e["sections"][:3]) + (" …" if len(e["sections"]) > 3 else "")
        ans = L.truncate(re.sub(r"\s+", " ", e["answer"]).strip(), answer_limit)
        parts.append(f"\n**ตัวอย่างที่ {thai_num(i)}**\n")
        parts.append(f"**คำถาม** {e['question'].strip()}\n")
        parts.append(f"**มาตราที่อ้าง** {cite}\n")
        parts.append(f"**คำตอบของผู้เชี่ยวชาญ** {ans}\n")
    return "\n".join(parts), export


# ---------------------------------------------------------------- main

def main():
    os.makedirs(REPORT, exist_ok=True)
    os.makedirs(EXPORT, exist_ok=True)
    from report import narrative as N
    from report import narrative2 as N2

    thai, iapp, wc_tr, wc_te = load()
    print("loaded:", len(thai), len(iapp), len(wc_tr), len(wc_te))

    toc = """## สารบัญ

| บท | เรื่อง |
|:---|:---|
| ๑ | บทสรุปสำหรับผู้บริหาร |
| ๒ | วิธีการสำรวจ |
| ๓ | แคตตาล็อกชุดข้อมูล ๖ ชุด |
| ๔ | สถิติเชิงลึกของคลังข้อมูล |
| ๕ | การวิเคราะห์ช่องว่างของข้อมูล |
| ๖ | การทำความสะอาดและการตัดแบ่งข้อความ |
| ๗ | คลังตัวบทกฎหมายที่ใช้ในชีวิตประจำวัน ๑๒ ฉบับ |
| ๘ | คลังตัวอย่างคำถาม-คำตอบจากชุด WangchanX |
| ๙ | ข้อเสนอสถาปัตยกรรมและแผนดำเนินงาน |
| ภาคผนวก | รายการไฟล์ แหล่งข้อมูล และรูปแบบไฟล์ส่งออก |

**ผู้อ่านที่มีเวลาจำกัด** อ่านบทที่ ๑ และตารางในหัวข้อ ๕.๕ ก็เพียงพอต่อการตัดสินใจว่าโครงการนี้ทำได้หรือไม่ และควรเริ่มจากหมวดใด

---

"""
    doc = [N.COVER, toc, N.EXEC, N.METHOD, N2.CATALOG,
           stats_chapter(thai, iapp, wc_tr, wc_te),
           N.GAP_INTRO, "\n### ๕.๒ ผลการตรวจสอบรายฉบับ\n",
           coverage_table(iapp), N.GAP_ANALYSIS, N2.CLEANING, N.CONTENT_INTRO]

    laws_md, sections_export, summary = law_chapters(iapp)
    doc.append("\n### ๗.๐ สรุปกฎหมายที่สกัดมา\n")
    doc.append(md_table(["กฎหมาย", "หมวด", "จำนวนมาตรา", "ความยาวดิบ", "แสดงในรายงาน"],
                        summary, ["-", "-", "r", "r", "r"]))
    doc.append(laws_md)
    doc.append("\n\n---\n\n")

    qa_md, qa_export = qa_chapter(wc_tr, wc_te)
    doc.append(N.QA_INTRO)
    doc.append(qa_md)
    doc.append("\n\n---\n\n")
    doc.append(N2.ARCHITECTURE)
    doc.append(N2.APPENDIX_INTRO)

    body = "\n".join(doc)
    n_chars = len(body)
    body += (f"\n### ภาคผนวก ง ข้อมูลของรายงานฉบับนี้\n\n"
             f"ความยาวรวม {n_chars:,} ตัวอักษร คิดเป็นประมาณ {n_chars // CHARS_PER_PAGE} หน้ากระดาษ A4 "
             f"เมื่อจัดหน้าด้วยแบบอักษรขนาด ๑๖ พอยต์ ระยะบรรทัดเดี่ยว\n\n"
             f"ตัวบทกฎหมายที่สกัดและส่งออกทั้งหมด {len(sections_export):,} มาตรา "
             f"คู่ถาม-ตอบที่ส่งออก {len(qa_export):,} คู่\n")

    out_md = os.path.join(REPORT, "รายงานชุดข้อมูลกฎหมายไทย.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(body)

    with open(os.path.join(EXPORT, "sections.jsonl"), "w", encoding="utf-8") as f:
        for e in sections_export:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(os.path.join(EXPORT, "qa_pairs.jsonl"), "w", encoding="utf-8") as f:
        for e in qa_export:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    yr = iapp.title.str.extract(r"พ\.ศ\.\s*(2[45]\d\d)")[0]
    with open(os.path.join(EXPORT, "corpus_stats.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sysid", "title", "doc_type", "year", "n_chars"])
        for sysid, title, y, n in zip(iapp.sysid, iapp.title, yr, iapp.n):
            w.writerow([sysid, title, doc_type(title), "" if pd.isna(y) else y, n])

    print(f"report: {len(body):,} chars ~ {len(body)//CHARS_PER_PAGE} pages -> {out_md}")
    print(f"sections.jsonl: {len(sections_export):,} | qa_pairs.jsonl: {len(qa_export):,}")


if __name__ == "__main__":
    main()
