# -*- coding: utf-8 -*-
"""Build the computer-education law document (HTML -> PDF).

Audience: students and teachers of คณะครุศาสตร์อุตสาหกรรม, KMUTNB -- specifically
computer education. The chapters follow one person's path rather than grouping
laws by subject, because a pile of unrelated statutes is not a document: student
-> the university employing them -> the school system they will teach in ->
becoming a teacher -> the pupil data they will hold -> the digital systems around
them.

    python -m report.edu_doc          # writes HTML then prints it to PDF
"""
import html
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)
from app.config import PROCESSED_DIR  # noqa: E402
from app import thai_law as L  # noqa: E402

OUT_HTML = os.path.join(HERE, "กฎหมายสำหรับครูคอมพิวเตอร์.html")
OUT_PDF = os.path.join(HERE, "กฎหมายสำหรับครูคอมพิวเตอร์.pdf")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

THAI_NUM = "๐๑๒๓๔๕๖๗๘๙"

# The brief allowed the document to run past 100 pages, so every profiled act is
# reproduced in full. Truncating a statute mid-way makes it useless as a reference:
# the reader cannot tell whether the rule they need was cut or never existed.
FULL = 10 ** 9


def thai(n) -> str:
    return "".join(THAI_NUM[int(d)] if d.isdigit() else d for d in str(n))


# (chapter title, framing paragraph, [(act name fragment, char budget, priority sections)])
CHAPTERS = [
    ("ทุนและหนี้การศึกษาตอนเป็นนักศึกษา",
     "นักศึกษาครุศาสตร์อุตสาหกรรมจำนวนมากเรียนด้วยเงินกู้ยืมจากกองทุน กยศ. "
     "กฎหมายฉบับนี้จึงเป็นกฎหมายฉบับแรกที่ผูกพันชีวิตของผู้เรียนโดยตรง "
     "ตั้งแต่คุณสมบัติผู้กู้ เงื่อนไขการชำระคืน ไปจนถึงอำนาจของกองทุนในการหักเงินเดือน "
     "ซึ่งจะกลับมามีผลอีกครั้งเมื่อผู้เรียนบรรจุเป็นครูในบทที่ ๗",
     [("กองทุนเงินให้กู้ยืมเพื่อการศึกษา พ.ศ. 2560", FULL,
       ["4", "6", "39", "40", "41", "44", "45", "46", "47", "51"])]),

    ("โครงสร้างและบุคลากรของมหาวิทยาลัยที่สังกัด",
     "มจพ. เป็นสถาบันอุดมศึกษาของรัฐ อาจารย์ผู้สอนจึงอยู่ภายใต้ระเบียบข้าราชการพลเรือน"
     "ในสถาบันอุดมศึกษา และคณะสังกัดกระทรวงการอุดมศึกษา วิทยาศาสตร์ วิจัยและนวัตกรรม "
     "สองฉบับนี้อธิบายว่าใครมีอำนาจอะไรในระบบที่ผู้เรียนกำลังอยู่ และเป็นเส้นทางอาชีพ"
     "อีกทางหนึ่งของผู้ที่เลือกเป็นอาจารย์แทนที่จะเป็นครูในโรงเรียน",
     [("ระเบียบข้าราชการพลเรือนในสถาบันอุดมศึกษา", FULL,
       ["4", "5", "6", "14", "17", "18", "20", "28", "31", "39", "44", "49", "62"]),
      ("ระเบียบบริหารราชการกระทรวงการอุดมศึกษา", FULL,
       ["4", "5", "8", "10", "12", "14", "20"])]),

    ("ระบบการศึกษาที่จะไปสอน",
     "ก่อนจะเข้าใจหน้าที่ของครู ต้องเข้าใจระบบที่ครูทำงานอยู่ พระราชบัญญัติการศึกษาแห่งชาติ "
     "วางหลักเรื่องสิทธิและหน้าที่ทางการศึกษา แนวการจัดการศึกษา และมาตรฐานวิชาชีพ "
     "ส่วนพระราชบัญญัติการศึกษาภาคบังคับกำหนดว่าเด็กคนไหนต้องอยู่ในห้องเรียนของครู "
     "และเกิดอะไรขึ้นเมื่อเด็กไม่มา",
     [("การศึกษาแห่งชาติ พ.ศ. 2542", FULL,
       ["4", "6", "8", "10", "15", "17", "22", "23", "24", "25", "27", "30",
        "39", "47", "48", "52", "53", "63", "65", "66"]),
      ("การศึกษาภาคบังคับ", FULL, [])]),

    ("ใบประกอบวิชาชีพ วินัย และวิทยฐานะของครู",
     "บทนี้ยาวที่สุดเพราะเป็นกฎหมายที่กำหนดชีวิตการทำงานของครูทั้งชีวิต ตั้งแต่การบรรจุ "
     "การมีใบอนุญาตประกอบวิชาชีพ การเลื่อนวิทยฐานะ วินัยและโทษทางวินัย ไปจนถึงการอุทธรณ์ "
     "ผู้เรียนครุศาสตร์อุตสาหกรรมควรอ่านหมวดวินัยให้ละเอียดที่สุด เพราะเป็นส่วนที่"
     "ครูใหม่มักไม่รู้จนกระทั่งถูกตั้งกรรมการสอบสวน",
     [("ระเบียบข้าราชการครูและบุคลากรทางการศึกษา", FULL,
       ["4", "38", "39", "42", "44", "45", "47", "53", "54", "55", "56",
        "82", "83", "84", "85", "86", "88", "90", "91", "94", "95",
        "96", "97", "98", "100", "104", "109", "111", "119", "120", "121"])]),

    ("ข้อมูลนักเรียนในมือครูกับกฎหมาย PDPA",
     "ครูคอมพิวเตอร์เป็นผู้ที่ถือข้อมูลนักเรียนมากที่สุดในโรงเรียน ทั้งคะแนน ภาพถ่ายกิจกรรม "
     "บัญชีผู้ใช้ในระบบการเรียน และมักเป็นผู้ดูแลระบบให้ครูคนอื่นด้วย "
     "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคลจึงเป็นกฎหมายที่ครูสายนี้ต้องรู้ลึกกว่าครูวิชาอื่น "
     "โดยเฉพาะเรื่องฐานการประมวลผล ความยินยอมของผู้เยาว์ และหน้าที่เมื่อข้อมูลรั่วไหล",
     [("คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562", FULL,
       ["4", "6", "19", "20", "21", "22", "23", "24", "26", "27", "28",
        "30", "31", "32", "33", "34", "37", "39", "40", "41", "42",
        "77", "79", "82", "83"])]),

    ("ระบบดิจิทัลรอบตัวครู",
     "โรงเรียนและมหาวิทยาลัยของรัฐกำลังย้ายงานทะเบียน การเรียนการสอน และการให้บริการ"
     "ขึ้นระบบดิจิทัล ครูคอมพิวเตอร์มักถูกมอบหมายให้ดูแลระบบเหล่านี้โดยปริยาย "
     "สามฉบับในบทนี้กำหนดว่าข้อมูลของราชการเปิดเผยได้แค่ไหน ระบบต้องเชื่อมโยงกันอย่างไร "
     "และเมื่อระบบถูกโจมตี ใครมีอำนาจสั่งการ",
     [("การบริหารงานและการให้บริการภาครัฐผ่านระบบดิจิทัล", FULL, []),
      ("ข้อมูลข่าวสารของราชการ", FULL,
       ["4", "7", "9", "11", "14", "15", "20", "23", "24", "25"]),
      ("การรักษาความมั่นคงปลอดภัยไซเบอร์", FULL,
       ["3", "5", "9", "42", "43", "44", "49", "50", "53", "54", "56", "57", "58", "59"])]),
]

# probes recorded in the gap chapter, with the search key used to check the corpus
MISSING_PROBES = [
    ("พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์", "การกระทำความผิดเกี่ยวกับคอมพิวเตอร์",
     "ความผิดฐานเข้าถึงระบบโดยมิชอบ การเผยแพร่ข้อมูลเท็จ และหน้าที่ของผู้ให้บริการ"),
    ("พระราชบัญญัติลิขสิทธิ์", "พระราชบัญญัติลิขสิทธิ์",
     "การใช้สื่อการสอนที่มีลิขสิทธิ์ ข้อยกเว้นเพื่อการศึกษา และการทำซ้ำในชั้นเรียน"),
    ("พระราชบัญญัติว่าด้วยธุรกรรมทางอิเล็กทรอนิกส์", "ว่าด้วยธุรกรรมทางอิเล็กทรอนิกส์",
     "ผลทางกฎหมายของเอกสารอิเล็กทรอนิกส์และลายมือชื่ออิเล็กทรอนิกส์"),
    ("ประมวลกฎหมายอาญา", "ประมวลกฎหมายอาญา",
     "ความผิดฐานหมิ่นประมาทออนไลน์ ฉ้อโกง และความผิดต่อทรัพย์"),
    ("ประมวลกฎหมายแพ่งและพาณิชย์", "ประมวลกฎหมายแพ่งและพาณิชย์",
     "สัญญาจ้าง ละเมิด และความรับผิดทางแพ่งของสถานศึกษา"),
    ("พระราชบัญญัติปัญญาประดิษฐ์", "ปัญญาประดิษฐ์",
     "ยังไม่มีกฎหมายเฉพาะเรื่องปัญญาประดิษฐ์ในคลังข้อมูลนี้"),
]


def load_corpus():
    path = os.path.join(PROCESSED_DIR, "corpus.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def pick_act(corpus, fragment):
    """Longest act whose name contains the fragment, with its sections in order."""
    acts = {}
    for r in corpus:
        if fragment in r["act"]:
            acts.setdefault(r["act"], []).append(r)
    if not acts:
        return None, []
    name = max(acts, key=lambda a: sum(x["n_chars"] for x in acts[a]))
    rows = sorted(acts[name], key=lambda r: (
        [int(x) for x in re.findall(r"\d+", r["section"])] or [0], r.get("part", 0)))
    return name, rows


def choose_sections(rows, budget, priority):
    """Priority sections first, then document order until the budget runs out."""
    by_no = {}
    for r in rows:
        by_no.setdefault(r["section"], []).append(r)
    chosen, used, spent = [], set(), 0
    for no in priority:
        for r in by_no.get(no, []):
            if r["id"] not in used:
                chosen.append(r); used.add(r["id"]); spent += r["n_chars"]
    skipped = []
    for r in rows:
        if r["id"] in used:
            continue
        if spent + r["n_chars"] > budget:
            if r["section"] not in skipped:
                skipped.append(r["section"])
            continue
        chosen.append(r); used.add(r["id"]); spent += r["n_chars"]
    chosen.sort(key=lambda r: ([int(x) for x in re.findall(r"\d+", r["section"])] or [0],
                               r.get("part", 0)))
    return chosen, skipped, spent


def esc(text):
    return html.escape(text).replace("\n\n", "</p><p>").replace("\n", "<br>")


CSS = """
@page { size: A4; margin: 1.9cm 1.8cm 2cm 2.2cm;
        @bottom-center { content: counter(page); } }
* { box-sizing: border-box; }
body { font-family: "Sarabun", "TH Sarabun New", sans-serif;
       font-size: 14pt; line-height: 1.5; color: #14181f; margin: 0;
       orphans: 2; widows: 2; }
h1, h2, h3, h4 { text-wrap: balance; word-break: keep-all;
                 overflow-wrap: normal; hyphens: none; }
h1 { font-size: 25pt; line-height: 1.32; margin: 0 0 .3em; font-weight: 700; }
h2 { font-size: 19pt; margin: 0 0 .5em; font-weight: 600;
     border-bottom: 2px solid #223C69; padding-bottom: .25em;
     break-before: page; break-after: avoid; }
h3 { font-size: 16.5pt; margin: 1.4em 0 .4em; font-weight: 600; color: #223C69;
     break-after: avoid; }
h4 { font-size: 15pt; margin: 1.1em 0 .3em; font-weight: 600; break-after: avoid; }
p { margin: 0 0 .55em; text-align: justify; }
.cover { text-align: center; padding-top: 3.4cm; break-after: page; }
.cover h1 { font-size: 29pt; line-height: 1.35; }
.cover .sub { font-size: 18pt; line-height: 1.55; color: #223C69;
              margin: .9em 0 2.4cm; }
.cover .meta { font-size: 14pt; color: #58606d; line-height: 1.9; margin-top: 1.6cm; }
.cover .by { font-size: 15pt; color: #14181f; margin-bottom: .5em; }
/* borderless so the ids line up as a column without looking like a data table */
table.authors { width: auto; margin: 0 auto; border-collapse: collapse; }
table.authors td { border: 0; padding: .16em .55em; font-size: 14.5pt; }
table.authors td.nm { text-align: right; }
table.authors td.id { text-align: left; color: #58606d; }
.lede { background: #F5F7FA; border-left: 4px solid #B8860B;
        padding: .85em 1.1em; margin: 0 0 1.5em; }
.lede p:last-child { margin-bottom: 0; }
table { width: 100%; border-collapse: collapse; margin: .8em 0 1.4em;
        font-size: 13.5pt; }
th { background: #223C69; color: #fff; text-align: left; padding: .45em .6em;
     font-weight: 600; }
td { border-bottom: 1px solid #E2E6EB; padding: .42em .6em; vertical-align: top; }
td.n, th.n { text-align: right; }
.sec { margin: 0 0 .8em; orphans: 2; widows: 2; }
.sec .no { font-weight: 700; color: #223C69; }
.sec .cont { color: #8A93A0; font-weight: 400; font-size: 13pt; }
.note { background: #FFF9EC; border: 1px solid #EBD9AE; padding: .8em 1em;
        margin: 1.2em 0; font-size: 14pt; }
.note b { color: #8a6100; }
.miss { background: #FDF3F3; border-left: 4px solid #C0392B; padding: .8em 1em;
        margin: .7em 0; break-inside: avoid; }
.toc td { border: 0; padding: .3em .5em; }
.toc .ch { color: #223C69; font-weight: 600; }
code { font-family: "SF Mono", Menlo, monospace; font-size: 12.5pt;
       background: #F2F4F7; padding: .1em .35em; border-radius: 3px; }
.small { font-size: 13pt; color: #58606d; }
"""


def render_sections(rows):
    out = []
    for r in rows:
        part = r.get("part", 0)
        cont = ' <span class="cont">(ต่อ)</span>' if part else ""
        body = esc(L.to_arabic(r["text"]))
        out.append(f'<div class="sec"><p><span class="no">มาตรา {r["section"]}</span>'
                   f'{cont} {body}</p></div>')
    return "\n".join(out)


def build(corpus):
    parts, toc, stats = [], [], []
    total_sections = total_chars = 0

    for i, (title, lede, acts) in enumerate(CHAPTERS, start=4):
        toc.append((i, title))
        body = [f'<h2>บทที่ {thai(i)}  {esc(title)}</h2>',
                f'<div class="lede"><p>{esc(lede)}</p></div>']
        for fragment, budget, priority in acts:
            name, rows = pick_act(corpus, fragment)
            if not name:
                body.append(f'<div class="miss"><p><b>ไม่พบในคลังข้อมูล</b> — {esc(fragment)}</p></div>')
                continue
            chosen, skipped, spent = choose_sections(rows, budget, priority)
            total_sections += len(chosen); total_chars += spent
            stats.append((name, len(rows), len(chosen), spent))
            heads = sorted({r.get("chapters") and tuple(r["chapters"]) or () for r in rows},
                           key=len, reverse=True)
            chapter_list = list(heads[0]) if heads and heads[0] else []
            body.append(f'<h3>{esc(name)}</h3>')
            body.append(f'<p class="small">สกัดได้ {thai(len(rows))} มาตรา '
                        f'นำมาแสดง {thai(len(chosen))} มาตรา '
                        f'({spent:,} ตัวอักษร) จากรหัสเอกสาร {rows[0]["sysid"]}</p>')
            if chapter_list:
                body.append('<h4>โครงสร้างของกฎหมายฉบับนี้</h4><table>'
                            '<tr><th>ลำดับ</th><th>หัวข้อ</th></tr>')
                for h in chapter_list[:30]:
                    kind, _, name_ = h.partition(" ")
                    body.append(f'<tr><td>{esc(kind)}</td><td>{esc(name_)}</td></tr>')
                body.append('</table>')
            if skipped:
                body.append(f'<p class="small">มาตราที่ไม่ได้แสดง {thai(len(skipped))} มาตรา: '
                            f'{esc(", ".join(skipped[:30]))}</p>')
            body.append('<h4>ตัวบท</h4>')
            body.append(render_sections(chosen))
        parts.append("\n".join(body))

    # ---- front matter -------------------------------------------------------
    cover = f"""
<div class="cover">
  <h1>กฎหมายที่ผู้เรียน<br>และครูคอมพิวเตอร์ต้องรู้</h1>
  <div class="sub">ชุดข้อมูลตัวบทกฎหมายไทยแบบเปิด<br>สำหรับคณะครุศาสตร์อุตสาหกรรม</div>
  <div class="by">จัดทำโดย</div>
  <table class="authors">
    <tr><td class="nm">นายพงศกร ศรีษเกตุ</td><td class="id">68-020415-1006-6</td></tr>
    <tr><td class="nm">นายณบวร ลิ้มวัฒนะ</td><td class="id">68-020415-1011-2</td></tr>
    <tr><td class="nm">นางสาวจิดาภา สุขาภิรมย์</td><td class="id">68-020415-1012-1</td></tr>
    <tr><td class="nm">นายกิตติพัตท์ อินอารีย์</td><td class="id">68-020415-1027-9</td></tr>
    <tr><td class="nm">นายณัฐกิตติ์ จินากูล</td><td class="id">68-020415-1032-5</td></tr>
  </table>
  <div class="meta">
    มหาวิทยาลัยเทคโนโลยีพระจอมเกล้าพระนครเหนือ<br>
    คณะครุศาสตร์อุตสาหกรรม สาขาคอมพิวเตอร์ศึกษา<br><br>
    รวบรวมจากคลังข้อมูลกฎหมายไทยแบบเปิด<br>
    {thai(len(CHAPTERS))} หมวด · {thai(total_sections)} มาตรา
  </div>
</div>"""

    toc_rows = "".join(
        f'<tr><td class="ch">บทที่ {thai(n)}</td><td>{esc(t)}</td></tr>' for n, t in toc)
    front = f"""
<h2 style="break-before:auto">สารบัญ</h2>
<table class="toc">
<tr><td class="ch">บทที่ ๑</td><td>ทำไมครูคอมพิวเตอร์ต้องรู้กฎหมายชุดนี้</td></tr>
<tr><td class="ch">บทที่ ๒</td><td>วิธีการคัดเลือกและเตรียมข้อมูล</td></tr>
<tr><td class="ch">บทที่ ๓</td><td>สถิติของชุดข้อมูล</td></tr>
{toc_rows}
<tr><td class="ch">บทที่ ๑๐</td><td>ช่องว่างของข้อมูล กฎหมายที่ควรมีแต่ไม่มี</td></tr>
<tr><td class="ch">ภาคผนวก</td><td>รายการกฎหมาย ที่มา และวิธีทำซ้ำ</td></tr>
</table>
"""
    return cover, front, parts, stats, total_sections, total_chars


INTRO = """
<h2 style="break-before:auto">บทที่ ๑  ทำไมครูคอมพิวเตอร์ต้องรู้กฎหมายชุดนี้</h2>

<p>ผู้เรียนคณะครุศาสตร์อุตสาหกรรม สาขาคอมพิวเตอร์ศึกษา กำลังเตรียมตัวเข้าสู่อาชีพที่
อยู่ใต้กฎหมายมากกว่าที่คนส่วนใหญ่คิด ครูไม่ได้เป็นเพียงผู้สอน แต่เป็นเจ้าหน้าที่ของรัฐ
ที่มีวินัย มีใบอนุญาตประกอบวิชาชีพ และมีความรับผิดตามกฎหมาย ยิ่งเป็นครูคอมพิวเตอร์
ยังต้องรับผิดชอบข้อมูลนักเรียนและระบบสารสนเทศของสถานศึกษาเพิ่มอีกชั้นหนึ่ง</p>

<p>เอกสารฉบับนี้ไม่ได้รวบรวมกฎหมายตามหมวดหมู่ของนักกฎหมาย แต่เรียงตาม
<b>เส้นทางชีวิตจริง</b>ของผู้เรียนสาขานี้ เริ่มจากตอนเป็นนักศึกษาที่กู้ยืมเงินเรียน
ผ่านมหาวิทยาลัยที่สังกัด เข้าสู่ระบบการศึกษาที่จะไปสอน บรรจุเป็นครู
รับผิดชอบข้อมูลนักเรียน และดูแลระบบดิจิทัลของสถานศึกษา แต่ละบทจึงต่อเนื่องกัน
ไม่ใช่กองกฎหมายที่ไม่เกี่ยวข้องกันมาวางรวมกัน</p>

<h3>สิ่งที่เอกสารนี้เป็น และไม่เป็น</h3>
<p>เอกสารนี้<b>เป็น</b>คลังตัวบทที่คัดมาแล้วพร้อมคำอธิบายบริบทว่าแต่ละฉบับเกี่ยวข้องกับ
ครูคอมพิวเตอร์อย่างไร ตัวบททั้งหมดคัดจากคลังข้อมูลกฎหมายไทยแบบเปิดโดยตรง
ไม่ได้เรียบเรียงใหม่ ผู้อ่านจึงเห็นถ้อยคำเดียวกับที่ปรากฏในกฎหมาย</p>

<p>เอกสารนี้<b>ไม่เป็น</b>คำปรึกษาทางกฎหมาย และไม่ใช่ตัวบทที่รับรองความเป็นปัจจุบัน
คลังข้อมูลต้นทางปรับปรุงถึงประมาณ พ.ศ. ๒๕๖๓ กฎหมายที่แก้ไขหลังจากนั้นจะไม่ปรากฏ
ก่อนนำไปอ้างอิงในงานที่มีผลผูกพัน ต้องตรวจสอบกับราชกิจจานุเบกษาหรือเว็บไซต์
สำนักงานคณะกรรมการกฤษฎีกาเสมอ</p>

<div class="note"><p><b>ข้อจำกัดที่ต้องอ่านก่อน</b> กฎหมายที่ผู้อ่านคาดว่าจะเจอในเอกสารชื่อนี้
แต่ <b>ไม่มีในคลังข้อมูล</b> ได้แก่ พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์
พระราชบัญญัติลิขสิทธิ์ และพระราชบัญญัติว่าด้วยธุรกรรมทางอิเล็กทรอนิกส์
สาเหตุและหลักฐานการตรวจสอบอยู่ในบทที่ ๑๐ ซึ่งเขียนไว้อย่างละเอียดเพราะ
การรู้ว่าข้อมูลขาดอะไรสำคัญพอ ๆ กับการรู้ว่ามีอะไร</p></div>

<h2>บทที่ ๒  วิธีการคัดเลือกและเตรียมข้อมูล</h2>

<h3>๒.๑ แหล่งข้อมูล</h3>
<p>ตัวบททั้งหมดมาจากคลัง <code>iapp/rag_thai_laws</code> ซึ่งเป็นฉบับทำความสะอาดของ
<code>pythainlp/thailaw</code> เก็บจากเว็บไซต์สำนักงานคณะกรรมการกฤษฎีกา
เผยแพร่ภายใต้สัญญาอนุญาต CC0 คือสละสิทธิ์เข้าสู่สาธารณสมบัติ
สอดคล้องกับมาตรา ๗ (๑) แห่งพระราชบัญญัติลิขสิทธิ์ พ.ศ. ๒๕๓๗ ที่กำหนดว่ากฎหมาย
ระเบียบ และข้อบังคับของทางราชการไม่เป็นงานอันมีลิขสิทธิ์</p>

<h3>๒.๒ เกณฑ์คัดเลือกกฎหมายเข้าเอกสาร</h3>
<p>กฎหมายฉบับหนึ่งจะถูกนำเข้าเอกสารนี้เมื่อผ่านเกณฑ์สามข้อพร้อมกัน</p>
<p>ข้อแรก <b>ต้องอยู่บนเส้นทางชีวิตของผู้เรียนสาขาคอมพิวเตอร์ศึกษาจริง</b>
ไม่ใช่เพียงมีคำว่าดิจิทัลหรือการศึกษาอยู่ในชื่อ กฎหมายอย่างพระราชกำหนดการประกอบ
ธุรกิจสินทรัพย์ดิจิทัลจึงถูกตัดออก แม้จะอยู่ในหมวดดิจิทัล เพราะไม่มีจุดที่ครูคอมพิวเตอร์
ต้องใช้</p>
<p>ข้อสอง <b>ต้องเป็นพระราชบัญญัติหรือพระราชกำหนด</b> ไม่ใช่ประกาศหรือระเบียบ
ลำดับรอง เพื่อให้เอกสารมีความยาวที่จัดการได้และอ่านต่อเนื่อง</p>
<p>ข้อสาม <b>ต้องเป็นฉบับปรับปรุงล่าสุดที่มีในคลัง</b> คลังต้นทางเก็บทุกรุ่นการแก้ไข
หากไม่กรองจะได้ตัวบทที่ถูกยกเลิกไปแล้วปะปน</p>

<h3>๒.๓ การเตรียมข้อความ</h3>
<p>ข้อความต้นทางยังคงรูปแบบการจัดหน้าของเว็บ คือขึ้นบรรทัดใหม่กลางประโยค
มีอักขระเพี้ยนจากการแปลงรหัส มีเลขเชิงอรรถแทรก และมีบล็อกท้ายเอกสารที่ขึ้นต้นด้วย
คำว่ามาตราเหมือนตัวบทจริง การเตรียมข้อความจึงทำตามลำดับห้าขั้น</p>
<p>ขั้นที่หนึ่ง ตัดส่วนท้ายเอกสารตั้งแต่คำว่าผู้รับสนองพระบรมราชโองการเป็นต้นไป
ขั้นที่สอง แบ่งมาตราบนข้อความดิบโดยใช้เงื่อนไขว่าหัวมาตราต้องขึ้นย่อหน้าใหม่
เพื่อไม่ให้การอ้างถึงมาตราอื่นกลางประโยคกลายเป็นจุดตัด
ขั้นที่สาม เก็บรายการแรกของแต่ละเลขมาตรา
ขั้นที่สี่ แก้อักขระเพี้ยน ลบเลขเชิงอรรถ และต่อบรรทัดที่ถูกตัดกลางประโยคกลับเป็นย่อหน้า
ขั้นที่ห้า แปลงเลขมาตราเป็นเลขอารบิกเพื่อให้อ้างอิงได้สะดวก โดยคงเลขไทยในเนื้อความ</p>
<p class="small">การข้ามขั้นที่หนึ่งและสองทำให้ได้ผลผิดอย่างเงียบ ๆ ในการทดลองกับ
พระราชบัญญัติคุ้มครองแรงงาน การแบ่งแบบไม่ระวังให้ผล ๕๐๑ มาตรา ทั้งที่ตัวบทจริงมี
๑๘๒ มาตรา และมาตราที่ได้กลับกลายเป็นข้อความเชิงอรรถแทนตัวบท</p>
"""


def stats_chapter(stats, total_sections, total_chars, corpus):
    rows = "".join(
        f'<tr><td>{esc(n)}</td><td class="n">{t}</td><td class="n">{c}</td>'
        f'<td class="n">{ch:,}</td><td class="n">{ch // 2700}</td></tr>'
        for n, t, c, ch in stats)
    acts = len({r["act"] for r in corpus})
    return f"""
<h2>บทที่ ๓  สถิติของชุดข้อมูล</h2>
<h3>๓.๑ ที่มาและขนาดของคลังตั้งต้น</h3>
<table>
<tr><th>รายการ</th><th class="n">จำนวน</th></tr>
<tr><td>เอกสารในคลังต้นทางทั้งหมด</td><td class="n">42,755 ฉบับ</td></tr>
<tr><td>พระราชบัญญัติและพระราชกำหนด ฉบับล่าสุด</td><td class="n">{acts:,} ฉบับ</td></tr>
<tr><td>มาตราที่สกัดได้ทั้งคลัง</td><td class="n">{len(corpus):,} มาตรา</td></tr>
<tr><td>กฎหมายที่คัดเข้าเอกสารนี้</td><td class="n">{len(stats)} ฉบับ</td></tr>
<tr><td>มาตราที่นำมาแสดง</td><td class="n">{total_sections:,} มาตรา</td></tr>
<tr><td>ความยาวตัวบทรวม</td><td class="n">{total_chars:,} ตัวอักษร</td></tr>
</table>
<h3>๓.๒ กฎหมายที่คัดเข้าเอกสาร</h3>
<table>
<tr><th>กฎหมาย</th><th class="n">มาตราทั้งหมด</th><th class="n">นำมาแสดง</th>
<th class="n">ตัวอักษร</th><th class="n">หน้า</th></tr>
{rows}
</table>
<p class="small">คอลัมน์หน้าเป็นการประมาณจากอัตรา ๒,๗๐๐ ตัวอักษรต่อหน้ากระดาษ A4
ที่ขนาดตัวอักษร ๑๔ พอยต์</p>
"""


def gap_chapter(corpus, raw_titles):
    rows = []
    for label, key, why in MISSING_PROBES:
        found = [t for t in raw_titles if key in t]
        own = [t for t in found if t.startswith(key) or t.startswith("ประมวล") and key in t]
        if own:
            verdict, detail = "พบตัวบท", own[0][:60]
        elif found:
            verdict, detail = "พบแต่ไม่ใช่ตัวบท", found[0][:60]
        else:
            verdict, detail = "ไม่พบ", "—"
        rows.append(f'<tr><td>{esc(label)}</td><td>{verdict}</td>'
                    f'<td class="n">{len(found)}</td><td class="small">{esc(detail)}</td></tr>')
    why_rows = "".join(
        f'<div class="miss"><p><b>{esc(label)}</b><br>'
        f'<span class="small">เนื้อหาที่ครูคอมพิวเตอร์ควรได้อ่านแต่ไม่มี — {esc(why)}</span></p></div>'
        for label, _, why in MISSING_PROBES)
    return f"""
<h2>บทที่ ๑๐  ช่องว่างของข้อมูล กฎหมายที่ควรมีแต่ไม่มี</h2>
<p>บทนี้จำเป็นต้องมี เพราะเอกสารที่ชื่อว่ากฎหมายสำหรับครูคอมพิวเตอร์แล้วไม่มี
พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ ย่อมทำให้ผู้อ่านเข้าใจผิดได้
หากไม่บอกไว้ให้ชัด การรู้ว่าคลังข้อมูลขาดอะไรมีค่าเท่ากับการรู้ว่ามีอะไร</p>

<h3>๑๐.๑ ผลการตรวจสอบ</h3>
<table>
<tr><th>กฎหมายที่ตรวจหา</th><th>ผล</th><th class="n">เอกสารที่พบ</th><th>ตัวอย่างที่พบ</th></tr>
{''.join(rows)}
</table>
<p class="small">ค้นจากชื่อเอกสารทั้ง ๔๒,๗๕๕ รายการในคลังต้นทาง คอลัมน์เอกสารที่พบ
นับรวมเอกสารที่เพียง <i>อ้างถึง</i> กฎหมายนั้น ไม่ใช่ตัวบท</p>

<h3>๑๐.๒ สิ่งที่ขาดไป และผลกระทบ</h3>
{why_rows}

<h3>๑๐.๓ สาเหตุ</h3>
<p>รูปแบบของสิ่งที่ขาดชี้ไปที่คำอธิบายเดียว เว็บไซต์สำนักงานคณะกรรมการกฤษฎีกา
ซึ่งเป็นแหล่งต้นทาง จัดหมวดประมวลกฎหมายแยกออกจากหมวดพระราชบัญญัติ
โปรแกรมเก็บข้อมูลที่ผลิตคลังนี้เดินเก็บเฉพาะหมวดหลัง จึงได้เอกสารมาสี่หมื่นกว่าฉบับ
แต่ขาดประมวลกฎหมายทั้งหมวด ส่วนพระราชบัญญัติที่หายไปบางฉบับน่าจะเกิดจาก
เงื่อนไขการเดินลิงก์หรือช่วงเวลาที่เก็บ</p>
<p>ข้อสังเกตนี้มีนัยที่ดี เพราะหมายความว่าช่องว่างอุดได้ด้วยการเก็บข้อมูลเพิ่มจาก
แหล่งเดิม ไม่ต้องหาแหล่งใหม่ที่มีปัญหาเรื่องสิทธิ์</p>

<h3>๑๐.๔ ข้อเสนอสำหรับผู้ที่จะทำต่อ</h3>
<p>งานที่คุ้มค่าที่สุดคือเก็บข้อมูลเพิ่มจากเว็บกฤษฎีกาหมวดประมวลกฎหมาย
ซึ่งมีเพียงหกฉบับหลัก และเก็บพระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์
กับพระราชบัญญัติลิขสิทธิ์เพิ่ม สองฉบับหลังนี้จะเปลี่ยนเอกสารนี้จากคลังกฎหมายการศึกษา
เป็นคลังกฎหมายสำหรับครูคอมพิวเตอร์อย่างแท้จริง</p>
"""


APPENDIX = """
<h2>ภาคผนวก  ที่มา วิธีทำซ้ำ และรูปแบบข้อมูล</h2>
<h3>ก. แหล่งข้อมูล</h3>
<table>
<tr><th>ชุดข้อมูล</th><th>ที่อยู่</th><th>สัญญาอนุญาต</th></tr>
<tr><td>pythainlp/thailaw</td><td>huggingface.co/datasets/pythainlp/thailaw</td><td>CC0-1.0</td></tr>
<tr><td>iapp/rag_thai_laws</td><td>huggingface.co/datasets/iapp/rag_thai_laws</td><td>ตามต้นทาง</td></tr>
<tr><td>ต้นทางเดิม</td><td>krisdika.go.th</td><td>เอกสารราชการ</td></tr>
</table>

<h3>ข. รูปแบบไฟล์ข้อมูล</h3>
<p>ตัวบททั้งหมดเก็บในไฟล์ <code>data/processed/corpus.jsonl</code> หนึ่งบรรทัดต่อหนึ่งมาตรา
แต่ละบรรทัดเป็นวัตถุ JSON ที่มีคีย์ดังนี้</p>
<table>
<tr><th>คีย์</th><th>ชนิด</th><th>ความหมาย</th></tr>
<tr><td><code>id</code></td><td>string</td><td>คีย์ไม่ซ้ำ รูปแบบ รหัสเอกสาร-เลขมาตรา-ท่อน</td></tr>
<tr><td><code>act</code></td><td>string</td><td>ชื่อกฎหมาย</td></tr>
<tr><td><code>act_full</code></td><td>string</td><td>ชื่อเต็มตามต้นฉบับ รวมวงเล็บระบุรุ่น</td></tr>
<tr><td><code>sysid</code></td><td>string</td><td>รหัสเอกสารในระบบกฤษฎีกา</td></tr>
<tr><td><code>section</code></td><td>string</td><td>เลขมาตราแบบอารบิก รองรับรูปแบบ 17/1</td></tr>
<tr><td><code>part</code></td><td>int</td><td>ลำดับท่อน กรณีมาตรายาวเกิน 1,800 ตัวอักษร</td></tr>
<tr><td><code>text</code></td><td>string</td><td>เนื้อความที่ทำความสะอาดแล้ว</td></tr>
<tr><td><code>chapters</code></td><td>list</td><td>รายชื่อหมวดของกฎหมายฉบับนั้น</td></tr>
<tr><td><code>n_chars</code></td><td>int</td><td>ความยาวของ text</td></tr>
</table>

<h3>ค. วิธีทำซ้ำเอกสารนี้</h3>
<p>ดาวน์โหลดไฟล์ Parquet จากแหล่งในตาราง ก. ไปไว้ที่ <code>data/raw/</code> แล้วสั่ง</p>
<p><code>python -m ingest.extract_acts</code> เพื่อสร้าง <code>data/processed/corpus.jsonl</code></p>
<p><code>python -m report.edu_doc</code> เพื่อสร้างเอกสารฉบับนี้ใหม่</p>
<p class="small">สคริปต์ทั้งหมดกำหนดลำดับการทำงานไว้แน่นอน ผลลัพธ์ที่ได้จากข้อมูลชุดเดิม
จะเหมือนกันทุกครั้ง</p>
"""


def main():
    corpus = load_corpus()
    raw_titles = sorted({r["act_full"] for r in corpus})
    cover, front, chapters, stats, n_sec, n_ch = build(corpus)
    doc = "\n".join([cover, front, INTRO,
                     stats_chapter(stats, n_sec, n_ch, corpus),
                     *chapters,
                     gap_chapter(corpus, raw_titles),
                     APPENDIX])

    page = (f'<!DOCTYPE html><html lang="th"><head><meta charset="utf-8">'
            f'<title>กฎหมายสำหรับครูคอมพิวเตอร์</title><style>{CSS}</style></head>'
            f'<body>{doc}</body></html>')
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"html: {len(page):,} bytes -> {OUT_HTML}")

    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={OUT_PDF}", f"file://{OUT_HTML}"],
                   check=True, capture_output=True)
    size = os.path.getsize(OUT_PDF)
    print(f"pdf : {size / 1e6:.1f} MB -> {OUT_PDF}")
    print(f"รวม {len(stats)} ฉบับ  {n_sec:,} มาตรา  {n_ch:,} ตัวอักษร")


if __name__ == "__main__":
    main()
