# -*- coding: utf-8 -*-
"""Draw the diagrams for บทที่ 2 and save them as PNG.

Rendered through headless Chrome rather than a plotting library, because these
are labelled boxes and arrows rather than charts, and because the report is
written in Thai: Chrome already has the fonts and the text shaping that
matplotlib would have to be taught.

    .venv/bin/python -m report.make_figures

Each figure states a fact about this system that is checked elsewhere -- the
counts come from data/processed/corpus_ksp.jsonl, the thresholds from
app/config.py. If one of those changes, change it here too.
"""
from __future__ import annotations

import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&family=JetBrains+Mono&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'IBM Plex Sans Thai', sans-serif;
  background: #fff; color: #1b1416;
  padding: 34px 38px; width: 1180px;
}
.row { display: flex; align-items: stretch; gap: 14px; }
.col { display: flex; flex-direction: column; gap: 14px; }
.box {
  border: 1.5px solid #d9d0d1; border-radius: 12px; background: #fff;
  padding: 14px 16px; line-height: 1.5;
}
.box b { display: block; font-weight: 600; font-size: 17px; margin-bottom: 3px; }
.box span { font-size: 15px; color: #6d6265; }
.accent { border-color: #8d2230; background: #fdf6f6; }
.accent b { color: #8d2230; }
.soft { background: #f7f4f4; }
.ok { border-color: #2f7d4f; background: #f4faf6; }
.ok b { color: #2f7d4f; }
.warn { border-color: #b4801f; background: #fdf9f0; }
.warn b { color: #8a5f12; }
.arrow { text-align: center; color: #b3a8aa; font-size: 21px; line-height: 1; padding: 3px 0; }
.arrow.h { display: flex; align-items: center; padding: 0 2px; }
.lbl { font-size: 14px; color: #857a7c; text-align: center; margin-top: -6px; }
.mono { font-family: 'JetBrains Mono', monospace; font-size: 14.5px; }
h4 { font-size: 15px; color: #857a7c; font-weight: 500; margin-bottom: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 15.5px; }
th, td { border: 1px solid #e2dada; padding: 9px 12px; text-align: left; vertical-align: top; }
th { background: #f7f4f4; font-weight: 600; }
td.k { color: #8d2230; white-space: nowrap; font-weight: 500; }
.grow { flex: 1; }
.center { text-align: center; }
/* code and terminal listings: the report shows real files and real output,
   so they are rendered as themselves rather than retyped into a box */
.code {
  font-family: 'JetBrains Mono', monospace; font-size: 13.5px; line-height: 1.65;
  white-space: pre-wrap; background: #fbf9f9; border: 1.5px solid #e2dada;
  border-radius: 10px; padding: 16px 18px;
}
.code .c { color: #8d7f81; }          /* comment */
.code .k { color: #8d2230; }          /* keyword */
.code .s { color: #2f7d4f; }          /* string */
.term {
  font-family: 'JetBrains Mono', monospace; font-size: 13.5px; line-height: 1.7;
  white-space: pre-wrap; background: #1b1416; color: #efe9ea;
  border-radius: 10px; padding: 16px 18px;
}
.term .p { color: #7fb98f; }          /* prompt */
.term .ok { color: #7fb98f; }
.term .d { color: #9b8f91; }
.file { font-family: 'JetBrains Mono', monospace; font-size: 13px;
        color: #857a7c; margin-bottom: 6px; }
"""


FIGURES: dict[str, str] = {}
# Chrome screenshots the window, not the page, so each figure carries the window
# height it needs. Re-check the PNG after editing a figure -- too small crops the
# bottom, too large leaves white space the report has to crop.
HEIGHTS = {
    "fig-2-1-pdf-ladder": 520,
    "fig-2-2-record": 500,
    "fig-2-3-rag": 630,
    "fig-2-4-flow": 1080,
    "fig-2-5-hybrid": 790,
    "fig-2-6-expand": 510,
    "fig-2-7-stack": 640,
    "fig-3-1-framework": 400,
    "fig-3-2-pipeline": 700,
    "fig-3-3-fetch-code": 500,
    "fig-3-4-fetch-run": 420,
    "fig-3-5-ladder-code": 470,
    "fig-3-6-audit-run": 320,
    "fig-3-7-expand-code": 400,
    "fig-3-8-prompt-code": 380,
    "fig-3-9-inspect-code": 790,
    "fig-3-10-api-json": 470,
    "fig-3-11-pytest": 320,
    "fig-3-12-testcase": 470,
    "fig-3-13-guards": 640,
    "fig-3-14-evalloop": 620,
    "fig-4-1-trajectory": 500,
}

# ---------------------------------------------------------------- 2-1 ladder
FIGURES["fig-2-1-pdf-ladder"] = """
<div class="col" style="width:1100px">
  <div class="row">
    <div class="box soft" style="width:250px">
      <b>เอกสาร PDF ต้นฉบับ</b>
      <span>10 ฉบับ จาก ksp.or.th/laws</span>
    </div>
    <div class="arrow h">&#10142;</div>
    <div class="col grow">
      <div class="box"><b>ระดับ 1 &nbsp;direct</b>
        <span>อ่านชั้นข้อความของ PDF ตรง ๆ &mdash; ใช้ได้กับเอกสารที่ฝังฟอนต์มาตรฐาน</span></div>
      <div class="box"><b>ระดับ 2 &nbsp;pua</b>
        <span>ฟอนต์ AngsanaUPC เก็บสระและวรรณยุกต์ไว้ใน Private Use Area (U+F700&ndash;U+F71A) ต้องแมปกลับเป็นยูนิโคดมาตรฐาน</span></div>
      <div class="box"><b>ระดับ 3 &nbsp;legacy</b>
        <span>ข้อความเข้ารหัส TIS-620 ผสมช่วงอักขระเฉพาะของระบบเดิม ถอดด้วย cp874 แล้วแมปช่วง 0x83&ndash;0x97 เพิ่มเอง</span></div>
      <div class="box"><b>ระดับ 4 &nbsp;ocr</b>
        <span>ไม่มีชั้นข้อความที่ใช้ได้ ต้องรู้จำอักขระด้วย Vision Framework ของ macOS (th-TH)</span></div>
    </div>
    <div class="arrow h">&#10142;</div>
    <div class="col" style="width:240px">
      <div class="box accent grow center" style="display:flex;flex-direction:column;justify-content:center">
        <b>ด่านตรวจคุณภาพ 7 ด่าน</b>
        <span>สระอำถูกแยก &middot; วรรณยุกต์หาย &middot; อักขระแปลกปลอม &middot; สัดส่วนอักษรไทย &middot; ความยาวที่ได้</span>
      </div>
    </div>
  </div>
  <div class="lbl">ระบบไล่จากระดับ 1 ลงไป และเลือกผลของ<b>ระดับแรกที่ผ่านด่านตรวจครบทุกด่าน</b> ผลของระดับ 4 ถูกบันทึกไว้ใน data/ocr/ เพื่อให้ประมวลผลซ้ำได้ผลเดิม</div>
</div>
"""

# ---------------------------------------------------------------- 2-2 record
FIGURES["fig-2-2-record"] = """
<div class="col" style="width:1080px">
  <div class="row">
    <div class="box mono soft grow" style="white-space:pre-wrap;font-size:14px;line-height:1.75">{
  "sysid":   "ksp-2556",
  "act":     "ข้อบังคับคุรุสภา ว่าด้วยจรรยาบรรณของวิชาชีพ พ.ศ. 2556",
  "short":   "ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556",
  "unit":    "ข้อ",
  "section": "12",
  "chapter": "หมวด 3 จรรยาบรรณต่อผู้รับบริการ",
  "ethics_category": "ต่อผู้รับบริการ",
  "superseded_by":   null,
  "text":    "ผู้ประกอบวิชาชีพทางการศึกษา ต้องไม่กระทำตนเป็นปฏิปักษ์
              ต่อความเจริญทางกาย สติปัญญา จิตใจ อารมณ์ และสังคม
              ของศิษย์ และผู้รับบริการ",
  "source_url": "https://www.ksp.or.th/laws/...",
  "published":  "2556-10-04"
}</div>
    <div class="col" style="width:400px">
      <table>
        <tr><th colspan="2">หน้าที่ของแต่ละฟิลด์ต่อระบบ</th></tr>
        <tr><td class="k">unit</td><td>กันไม่ให้คำตอบเขียนว่า &ldquo;ข้อบังคับ&hellip;<b>มาตรา</b> 50&rdquo; ทั้งที่ข้อบังคับไม่มีมาตรา</td></tr>
        <tr><td class="k">section</td><td>ตัวชี้ที่ชั้นตรวจสอบใช้เทียบว่าเลขที่คำตอบอ้างมีจริงหรือไม่</td></tr>
        <tr><td class="k">chapter</td><td>ใช้ดึงข้ออื่นในหมวดเดียวกันมาด้วย เมื่อคำถามเป็นการนับหรือแจกแจง</td></tr>
        <tr><td class="k">ethics_<br>category</td><td>ป้ายจรรยาบรรณ 5 ด้าน ติดแล้ว 30 ข้อ</td></tr>
        <tr><td class="k">superseded_by</td><td>ฉบับที่มายกเลิกข้อนี้ ใช้หักคะแนนไม่ให้หยิบฉบับเก่ามาตอบ</td></tr>
      </table>
    </div>
  </div>
  <div class="lbl">ตัวอย่างระเบียนจริงจาก data/processed/corpus_ksp.jsonl &mdash; ชุดข้อมูลมี 334 ระเบียน จาก 324 ข้อ/มาตรา</div>
</div>
"""

# ---------------------------------------------------------------- 2-3 RAG
FIGURES["fig-2-3-rag"] = """
<div class="col" style="width:1090px">
  <div class="row">
    <div class="col" style="width:315px">
      <h4>ก. ขั้นเตรียมข้อมูล (ทำครั้งเดียว)</h4>
      <div class="box"><b>ตัวบท 334 ระเบียน</b><span>corpus_ksp.jsonl</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>BGE-M3</b><span>แปลงข้อความเป็นเวกเตอร์ 1,024 มิติ</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box soft"><b>ดัชนี 2 ชุด</b>
        <span>vectors.npy (334&times;1,024) &middot; bm25_compact.npz</span></div>
    </div>
    <div class="arrow h">&#10142;</div>
    <div class="col grow">
      <h4>ข. ขั้นให้บริการ (ทุกคำถาม)</h4>
      <div class="box accent"><b>คำถามของผู้ใช้</b><span>&ldquo;ครูด่านักเรียนหน้าชั้น ผิดจรรยาบรรณข้อไหน&rdquo;</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>ค้นคืนตัวบทที่เกี่ยวข้อง (Retrieval)</b>
        <span>เทียบคำถามกับดัชนีทั้งสองชุด แล้วส่งตัวบท 8 ข้อที่ได้คะแนนสูงสุดต่อไป</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>เรียบเรียงคำตอบ (Generation)</b>
        <span>แบบจำลองภาษาเขียนคำตอบ<b style="display:inline;font-weight:600">จากตัวบทที่ได้รับเท่านั้น</b> ห้ามตอบจากความรู้ของตนเอง</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box ok"><b>คำตอบพร้อมเลขข้อและชื่อเอกสารที่อ้างอิง</b>
        <span>ผู้ใช้ตรวจสอบย้อนกลับไปยังตัวบทจริงได้</span></div>
    </div>
  </div>
  <div class="lbl">แนวทาง Retrieval-Augmented Generation &mdash; ปรับปรุงฐานความรู้ได้ทันทีเมื่อกฎหมายแก้ไข โดยไม่ต้องฝึกแบบจำลองใหม่</div>
</div>
"""

# ---------------------------------------------------------------- 2-4 flow
FIGURES["fig-2-4-flow"] = """
<div class="col" style="width:1070px">
  <div class="row">
    <div class="col grow">
      <div class="box accent center"><b>คำถามของผู้ใช้</b><span>ผ่านหน้าเว็บ หรือผ่าน LINE</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>1. ตรวจขอบเขตก่อนค้น &nbsp;<span class="mono">app/coverage.py</span></b>
        <span>คำถามเกี่ยวกับครูแต่อยู่นอกชุดข้อมูล เช่น วินัยข้าราชการครู หรือการขอใบอนุญาต</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>2. ขยายคำถาม &nbsp;<span class="mono">app/query_expand.py</span></b>
        <span>เติมคำศัพท์ทางกฎหมายที่ตรงกับตัวบท โดยไม่ลบคำเดิมของผู้ใช้</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>3. ค้นคืนแบบผสม &nbsp;<span class="mono">app/retriever.py</span></b>
        <span>BM25 + Dense แล้วรวมอันดับด้วย RRF (ดูภาพที่ 2-5)</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>4. ตรวจค่าความคล้าย</b>
        <span>ค่าสูงสุดต้องไม่ต่ำกว่า 0.46 มิฉะนั้นถือว่าไม่มีข้อใดใกล้เคียงคำถามเลย</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>5. เรียบเรียงคำตอบ &nbsp;<span class="mono">app/answer.py</span></b>
        <span>ส่งตัวบท 8 ข้อให้แบบจำลองภาษาพร้อมพรอมต์ 18 ข้อ &middot; temperature = 0</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>6. ตรวจคำตอบ 3 ชั้น</b>
        <span>เนื้อหาออกนอกคลัง &middot; ชื่อกฎหมายที่ไม่มีในคลัง &middot; เลขข้อ หน่วยนับ และอนุข้อที่ไม่มีจริง</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box ok center"><b>คำตอบพร้อมการอ้างอิง</b></div>
    </div>
    <div style="width:330px;display:flex;flex-direction:column;justify-content:space-around;padding-left:16px">
      <div class="box warn"><b>&#10142; ปฏิเสธ พร้อมบอกทางไปต่อ</b>
        <span>ระบุว่าคำตอบอยู่ในกฎหมายฉบับใด และควรไปสอบถามหน่วยงานใด</span></div>
      <div class="box warn"><b>&#10142; ปฏิเสธ ไม่เรียกแบบจำลอง</b>
        <span>ไม่เดาคำตอบเมื่อคลังไม่มีข้อที่เกี่ยวข้อง</span></div>
      <div class="box warn"><b>&#10142; ระงับคำตอบ</b>
        <span>ชั้นตรวจเลขข้อเทียบกับชุดข้อมูลโดยตรง จึงไม่มีการตีความความหมายเข้ามาเกี่ยวข้อง</span></div>
    </div>
  </div>
</div>
"""

# ---------------------------------------------------------------- 2-5 hybrid
FIGURES["fig-2-5-hybrid"] = """
<div class="col" style="width:1080px">
  <div class="box accent center" style="width:430px;margin:0 auto">
    <b>คำถามที่ขยายแล้ว</b><span>&ldquo;ครูด่านักเรียน&rdquo; + ดูหมิ่น เหยียดหยาม ปฏิปักษ์ต่อความเจริญทางจิตใจ</span></div>
  <div class="arrow">&#8595;</div>
  <div class="row">
    <div class="col grow">
      <div class="box"><b>BM25 &mdash; ค้นด้วยคำตรงตัว</b>
        <span>ให้คะแนนจากความถี่ของคำค้นในข้อนั้น และความหายากของคำในคลังทั้งหมด ตัดคำไทยด้วย newmm</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box soft"><b>อันดับจาก BM25</b>
        <span>แม่นเมื่อผู้ใช้พิมพ์คำที่ตรงตัวบท &middot; หาไม่เจอเลยเมื่อใช้คนละคำ</span></div>
    </div>
    <div style="width:26px"></div>
    <div class="col grow">
      <div class="box"><b>Dense &mdash; ค้นด้วยความหมาย</b>
        <span>แปลงคำถามเป็นเวกเตอร์ด้วย BGE-M3 แล้วเทียบ Cosine Similarity กับตัวบททั้ง 334 ระเบียน</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box soft"><b>อันดับจาก Dense</b>
        <span>จับความหมายได้แม้ใช้คนละคำ &middot; อาจให้ข้อที่ใกล้เคียงแต่ไม่ใช่ข้อที่ถาม</span></div>
    </div>
  </div>
  <div class="arrow">&#8595;</div>
  <div class="box accent center" style="width:660px;margin:0 auto">
    <b>รวมอันดับด้วย Reciprocal Rank Fusion</b>
    <span class="mono" style="font-size:17px;color:#8d2230;display:block;margin:7px 0 4px">RRF(d) = &Sigma;<sub>r</sub> 1 / (k + r(d))&nbsp;&nbsp;&nbsp;k = 60</span>
    <span>รวมอันดับจากทั้งสองระบบได้โดยไม่ต้องปรับสเกลคะแนนให้เท่ากันก่อน</span></div>
  <div class="arrow">&#8595;</div>
  <div class="box ok center" style="width:430px;margin:0 auto">
    <b>ตัวบท 8 ข้อที่ส่งให้แบบจำลองภาษา</b>
    <span>พร้อมข้ออื่นในหมวดเดียวกัน เมื่อคำถามเป็นการนับหรือแจกแจง</span></div>
</div>
"""

# ---------------------------------------------------------------- 2-6 expand
FIGURES["fig-2-6-expand"] = """
<div class="col" style="width:1080px">
  <table>
    <tr>
      <th style="width:27%">คำที่ผู้ใช้พิมพ์</th>
      <th style="width:6%" class="center"></th>
      <th>คำศัพท์ทางกฎหมายที่ระบบเติมให้ &mdash; ถ้อยคำที่ปรากฏจริงในตัวบท</th>
    </tr>
    <tr><td class="k">ด่า &middot; ดุ &middot; ตะคอก</td><td class="center">&#10142;</td>
        <td>ดูหมิ่น &middot; เหยียดหยาม &middot; ปฏิปักษ์ต่อความเจริญทางจิตใจ อารมณ์ และสังคมของศิษย์</td></tr>
    <tr><td class="k">เรียกเงิน &middot; รับสินบน</td><td class="center">&#10142;</td>
        <td>แสวงหาประโยชน์อันเป็นอามิสสินจ้างจากผู้รับบริการ</td></tr>
    <tr><td class="k">มาตรฐานวิชาชีพ &middot; กี่ด้าน</td><td class="center">&#10142;</td>
        <td>มาตรฐานความรู้และประสบการณ์วิชาชีพ &middot; มาตรฐานการปฏิบัติงาน &middot; มาตรฐานการปฏิบัติตน</td></tr>
    <tr><td class="k">ร้องเรียน &middot; แจ้งความผิด</td><td class="center">&#10142;</td>
        <td>กล่าวหา &middot; กล่าวโทษ &middot; คณะอนุกรรมการสอบสวน</td></tr>
    <tr><td class="k">โดนพักใบประกอบวิชาชีพ</td><td class="center">&#10142;</td>
        <td>พักใช้ใบอนุญาต &middot; เพิกถอนใบอนุญาต</td></tr>
    <tr><td class="k">พ.ร.บ.ครู &middot; พ.ร.บ.สภาครูฯ</td><td class="center">&#10142;</td>
        <td>พระราชบัญญัติสภาครูและบุคลากรทางการศึกษา พ.ศ. 2546 <i>(คำเรียกแทน)</i></td></tr>
  </table>
  <div class="row" style="margin-top:6px">
    <div class="box ok grow"><b>เติมคำ ไม่ใช่แทนที่คำ</b>
      <span>คำเดิมของผู้ใช้ยังอยู่ในคำค้นเสมอ คำถามที่ใช้ศัพท์กฎหมายถูกอยู่แล้วจึงไม่ได้รับผลกระทบ</span></div>
    <div class="box ok grow"><b>รายการที่ยังไม่มีในตาราง</b>
      <span>ทำให้คุณภาพลดลงเท่านั้น ไม่ทำให้คำถามที่เคยตอบได้เสียหาย</span></div>
    <div class="box ok grow"><b>ใช้ตารางกฎ ไม่ใช้แบบจำลองเขียนคำถามใหม่</b>
      <span>ไม่มีค่าใช้จ่ายเพิ่ม ไม่เพิ่มเวลาตอบสนอง ให้ผลเหมือนเดิมทุกครั้ง และทดสอบอัตโนมัติได้</span></div>
  </div>
</div>
"""

# ---------------------------------------------------------------- 2-7 stack
FIGURES["fig-2-7-stack"] = """
<div class="col" style="width:1080px">
  <div class="row">
    <div class="box accent center" style="width:210px"><b>ผู้ใช้</b><span>นักศึกษาคณะครุศาสตร์อุตสาหกรรม</span></div>
    <div class="arrow h">&#10142;</div>
    <div class="col grow">
      <div class="row">
        <div class="box grow"><b>LINE Messaging API</b>
          <span>บัญชีทางการ รับเหตุการณ์ผ่าน Webhook ตอบกลับเป็น Flex Message &middot; <span class="mono">app/line_bot.py</span>, <span class="mono">app/flex.py</span></span></div>
        <div class="box grow"><b>หน้าเว็บ</b>
          <span>HTML/CSS/JavaScript ให้บริการโดยเซิร์ฟเวอร์เดียวกัน &middot; <span class="mono">web/index.html</span></span></div>
      </div>
    </div>
  </div>
  <div class="arrow">&#8595;</div>
  <div class="box accent"><b>FastAPI + Uvicorn &nbsp;<span class="mono" style="font-weight:400">app/main.py</span></b>
    <span>เส้นทางให้บริการ &nbsp;<span class="mono">/chat</span> &nbsp;<span class="mono">/search</span> &nbsp;<span class="mono">/webhook</span> &nbsp;<span class="mono">/health</span> &nbsp;<span class="mono">/stats</span> &mdash; ทำงานแบบอะซิงโครนัส เพราะงานหลักคือการรอผลจากบริการภายนอก</span></div>
  <div class="arrow">&#8595;</div>
  <div class="row">
    <div class="box grow"><b>PyThaiNLP (newmm)</b>
      <span>ตัดคำไทยให้ BM25 &middot; นำเฉพาะอัลกอริทึมมาไว้ที่ <span class="mono">app/thai_tokenize/</span> เพราะการ import ทั้งไลบรารีใช้หน่วยความจำ 266 MB</span></div>
    <div class="box grow"><b>NumPy</b>
      <span>เก็บและคำนวณเวกเตอร์ทั้งหมด &middot; ดัชนี BM25 ในรูปอาเรย์ใช้ 8 MB แทน 202 MB</span></div>
    <div class="box grow"><b>บริการภายนอก</b>
      <span>Typhoon (แบบจำลองภาษาไทย) &rarr; Gemini เป็นลำดับสำรอง &middot; บริการแปลงข้อความเป็นเวกเตอร์ BGE-M3</span></div>
  </div>
  <div class="arrow">&#8595;</div>
  <div class="box soft"><b>Docker บนแพลตฟอร์ม Render &mdash; หน่วยความจำ 512 MB</b>
    <span>ดัชนีถูกสร้างไว้ล่วงหน้าแล้วคัดลอกเข้าอิมเมจ ไม่สร้างตอนติดตั้ง เพราะต้องใช้แบบจำลอง 2.2 GB และเวลาราว 18 นาที &middot; วัดการใช้หน่วยความจำสูงสุดจริงได้ 269 MB</span></div>
</div>
"""


def render(name: str, body: str) -> None:
    html = ("<!doctype html><html lang='th'><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")
    page = os.path.join(OUT, f"_{name}.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(html)
    subprocess.run(
        # old headless captures the full page height; the new one crops to the
        # window, and these diagrams are taller than any window worth setting
        [CHROME, "--headless=old", "--disable-gpu", "--hide-scrollbars",
         f"--window-size=1180,{HEIGHTS.get(name, 900)}",
         "--virtual-time-budget=6000",
         "--default-background-color=FFFFFFFF",
         f"--screenshot={os.path.join(OUT, name + '.png')}",
         f"file://{page}"],
        capture_output=True, check=True)
    os.remove(page)
    print("wrote", name + ".png")


# ------------------------------------------------------ บทที่ 3, the method
#
# Several of these show real files and real terminal output. They are captured
# from the repository as it stands, not retyped, so a reader can run the same
# command and compare.

FIGURES["fig-3-1-framework"] = """
<div class="col" style="width:1080px">
  <div class="row">
    <div class="box accent grow center" style="padding:18px"><b>3.1 &nbsp;Collection Data</b>
      <span>รวบรวมและตรึงรุ่นเอกสาร 10 ฉบับ &middot; ถอดข้อความ &middot; แยกเป็นรายข้อ &middot; ติดป้ายจรรยาบรรณ 5 ด้าน &middot; ตรวจความสมบูรณ์ &middot; สร้างดัชนี</span></div>
    <div class="arrow h">&#10142;</div>
    <div class="box accent grow center" style="padding:18px"><b>3.2 &nbsp;Development</b>
      <span>ค้นคืนแบบผสม &middot; ขยายคำถาม &middot; ออกแบบพรอมต์ &middot; ชั้นตรวจสอบคำตอบ &middot; ส่วนติดต่อผู้ใช้ &middot; นำขึ้นให้บริการ</span></div>
    <div class="arrow h">&#10142;</div>
    <div class="box accent grow center" style="padding:18px"><b>3.3 &nbsp;Evaluation</b>
      <span>ประเมินชุดข้อมูล &middot; ประเมินการค้นคืน &middot; ประเมินคุณภาพคำตอบโดยผู้ประเมินอิสระ</span></div>
  </div>
  <div class="row">
    <div class="box soft grow center"><span>ผลที่ได้คือแฟ้มคลังข้อมูลและดัชนีที่ตรวจสอบย้อนกลับได้</span></div>
    <div style="width:30px"></div>
    <div class="box soft grow center"><span>ผลที่ได้คือระบบที่ตอบพร้อมการอ้างอิง</span></div>
    <div style="width:30px"></div>
    <div class="box soft grow center"><span>ผลที่ได้คือตัวเลขความถูกต้องและรายการข้อบกพร่อง</span></div>
  </div>
  <div class="arrow">&#8593;&nbsp;&nbsp;ไม่ผ่านเกณฑ์ &rarr; กลับไปแก้ที่ 3.1 หรือ 3.2 แล้ววนประเมินใหม่&nbsp;&nbsp;&#8593;</div>
  <div class="lbl">เกณฑ์เป็นตัวตั้ง ไม่ใช่ตัวตาม &mdash; เมื่อไม่ผ่านให้แก้ระบบ ไม่ใช่ลดเกณฑ์</div>
</div>
"""

FIGURES["fig-3-2-pipeline"] = """
<div class="col" style="width:1080px">
  <div class="box accent"><b>1. ดาวน์โหลดและตรึงรุ่น &nbsp;<span class="mono" style="font-weight:400">scripts/fetch_ksp.sh</span></b>
    <span>เทียบ sha256 ของทุกไฟล์กับค่าที่บันทึกไว้ ถ้าไม่ตรงแปลว่าผู้เผยแพร่เปลี่ยนเอกสาร ต้องตรวจก่อนอัปเดตค่า เพราะเลขข้ออาจเลื่อนตามไปด้วย</span></div>
  <div class="arrow">&#8595;</div>
  <div class="box"><b>2. ถอดข้อความ &nbsp;<span class="mono" style="font-weight:400">ingest/thai_pdf_text.py</span></b>
    <span>ลำดับขั้น 4 ระดับ ผ่านด่านตรวจคุณภาพ 7 ด่าน (ดูภาพที่ 2-1) ผลของระดับ OCR บันทึกไว้ใน data/ocr/ เพื่อให้ประมวลผลซ้ำได้ผลเดิม</span></div>
  <div class="arrow">&#8595;</div>
  <div class="box"><b>3. แยกเป็นรายข้อและติดป้าย &nbsp;<span class="mono" style="font-weight:400">ingest/extract_ksp.py</span></b>
    <span>ตัดตามหัว "ข้อ"/"มาตรา" เก็บหมวดและส่วนที่สังกัด ติดป้ายจรรยาบรรณ 5 ด้าน และบันทึกว่าฉบับใดถูกยกเลิกโดยฉบับใด &rarr; corpus_ksp.jsonl</span></div>
  <div class="arrow">&#8595;</div>
  <div class="box warn"><b>4. ตรวจความสมบูรณ์ &nbsp;<span class="mono" style="font-weight:400">ingest/audit_ksp.py</span></b>
    <span>6 ด้าน ไม่ผ่านด้านใดให้กลับไปแก้ขั้นที่ 2 หรือ 3 &mdash; แยกจากการทดสอบโปรแกรมตามปกติ เพราะถามคนละคำถาม</span></div>
  <div class="arrow">&#8595;</div>
  <div class="box ok"><b>5. สร้างดัชนี &nbsp;<span class="mono" style="font-weight:400">ingest/build_index.py</span></b>
    <span>BGE-M3 &rarr; vectors.npy (334&times;1,024) &middot; ตัดคำ newmm &rarr; bm25_compact.npz &middot; ใช้เวลาราว 18 นาที ทำบนเครื่องพัฒนา ไม่ทำบนเครื่องแม่ข่าย</span></div>
</div>
"""

FIGURES["fig-3-13-guards"] = """
<div class="col" style="width:1080px">
  <div class="box accent center"><b>ร่างคำตอบจากแบบจำลองภาษา</b></div>
  <div class="arrow">&#8595;</div>
  <div class="row">
    <div class="box grow"><b>ตรวจเนื้อหานอกคลัง</b><span class="mono">app/coverage.py</span>
      <span>คำตอบพูดถึงกฎหมายที่ระบบไม่มี</span></div>
    <div class="box grow"><b>ตรวจชื่อกฎที่อ้าง</b><span class="mono">app/verify.py</span>
      <span>ชื่อเอกสารมีอยู่ในคลังหรือไม่</span></div>
    <div class="box grow"><b>ตรวจเลขข้อที่อ้าง</b><span class="mono">app/support.py</span>
      <span>เลขข้อ หน่วยนับ และอนุข้อมีจริงหรือไม่</span></div>
  </div>
  <div class="arrow">&#8595;</div>
  <div class="box warn center"><b>พบข้อผิดพลาด &rarr; ส่งกลับให้เขียนใหม่หนึ่งรอบ พร้อมระบุว่าผิดตรงไหน</b>
    <span>รับคำตอบใหม่ต่อเมื่อข้อผิดพลาดลดลง <b style="display:inline;font-weight:600">และ</b> ไม่ได้ลบข้อที่เคยอ้างถูกทิ้ง</span></div>
  <div class="arrow">&#8595;</div>
  <div class="row">
    <div class="box ok grow center"><b>แก้ได้ &rarr; ส่งคำตอบใหม่</b></div>
    <div class="box warn grow center"><b>แก้ไม่ได้ &rarr; ไม่ส่งคำตอบ บอกเหตุผล</b></div>
  </div>
  <div class="lbl">ชั้นที่ตัดสินใจได้มีเฉพาะชั้นที่เทียบกับตัวบทโดยตรง ส่วนชั้นที่ต้องตีความความหมายบันทึกไว้เฉย ๆ</div>
</div>
"""

FIGURES["fig-3-14-evalloop"] = """
<div class="col" style="width:1080px">
  <div class="row">
    <div class="col grow">
      <div class="box accent"><b>ก. เขียนเกณฑ์ก่อนแก้ระบบ</b>
        <span>61 เคสเขียนจากไฟล์ PDF ต้นฉบับ <b style="display:inline;font-weight:600">ก่อน</b> แตะโค้ดของแอป เพื่อให้เกณฑ์มาจากสิ่งที่กฎหมายเขียนไว้ ไม่ใช่จากสิ่งที่ระบบทำได้</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>ข. ผู้ประเมินอิสระยิงคำถามและตัดสิน</b>
        <span>ได้รับเอกสารเกณฑ์ ไฟล์ PDF และวิธียิง API เท่านั้น &mdash; ไม่ได้รับซอร์สโค้ด และไม่มีสิทธิ์แก้ไฟล์ใด ๆ ตัดสินทีละเคสเป็น PASS / PARTIAL / FAIL พร้อมยกข้อความจากคำตอบจริง</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box"><b>ค. แยกสาเหตุของทุกเคสที่ไม่ผ่าน</b>
        <span>(ก) ระบบ &middot; (ข) ตัวเขียนคำตอบ &middot; (ค) เคสทดสอบเขียนผิด &mdash; เพื่อให้รู้ว่าต้องแก้ที่ใด</span></div>
      <div class="arrow">&#8595;</div>
      <div class="box warn"><b>ง. แก้ระบบแล้ววนใหม่</b>
        <span>ไม่ลดเกณฑ์ และรายงานผลตามจริงแม้ยังไม่ผ่าน</span></div>
    </div>
    <div style="width:320px;padding-left:18px;display:flex;flex-direction:column;justify-content:center">
      <div class="box soft"><b>เกณฑ์ผ่านทั้งสามข้อ</b>
        <span>ในโดเมน PASS &ge; 45 จาก 50 &middot; นอกโดเมนปฏิเสธถูกทั้ง 10 &middot; ไม่มีเคสใดอ้างเลขข้อที่ไม่มีอยู่จริงแม้เคสเดียว</span></div>
      <div class="box ok" style="margin-top:14px"><b>เหตุที่ผู้ประเมินเป็นคนละตัวกับผู้พัฒนา</b>
        <span>ผู้พัฒนารู้ว่าระบบตอบอะไรได้ จึงมีแนวโน้มเขียนคำถามที่ระบบตอบได้ การแยกบทบาทตัดอคตินี้ออก</span></div>
    </div>
  </div>
</div>
"""




FIGURES["fig-3-3-fetch-code"] = """
<div class="col" style="width:1080px">
  <div class="file">scripts/fetch_ksp.sh</div>
  <div class="code"><span class="c"># The checksums pin the exact file each URL served on that date. A mismatch
# means the publisher replaced the document -- look at what changed before
# updating the hash, because the section numbering may have moved with it.</span>
<span class="k">set</span> -uo pipefail

<span class="c"># key|sha256|url|label</span>
DOCS=(
<span class="s">"ksp-2556|2c3fa473a259ddbd925d9697b7fa114190773447d31ee7e504ce9b570e776f7e|https://ratchakitcha.soc.go.th/documents/1986083.pdf|ข้อบังคับคุรุสภา ว่าด้วยจรรยาบรรณของวิชาชีพ พ.ศ. 2556"</span>
<span class="s">"ksp-2550|407f62549262423ab09301a329e5dba194099428b155fb8656058ac06a18057c|https://ratchakitcha.soc.go.th/documents/214339.pdf|ข้อบังคับคุรุสภา ว่าด้วยแบบแผนพฤติกรรม..."</span>
<span class="s">"act-2546|f07488b7f91ee88278c6f35cfac5fca6ca6be069ef3385626fb11cec960af533|https://www.ksp.or.th/wp-content/uploads/...|พระราชบัญญัติสภาครูและบุคลากรทางการศึกษา พ.ศ. 2546"</span>
  <span class="c">... รวม 10 ฉบับ ...</span>
)

<span class="k">check</span>() {
  <span class="k">local</span> want=$1 path=$2
  [ <span class="s">"$(shasum -a 256 &lt;"$path" | cut -d' ' -f1)"</span> = <span class="s">"$want"</span> ]
}</div>
</div>
"""

FIGURES["fig-3-4-fetch-run"] = """
<div class="col" style="width:1080px">
  <div class="file">$ bash scripts/fetch_ksp.sh</div>
  <div class="term">มีอยู่แล้ว: data/raw/ksp/ksp-2556.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-2550.pdf
มีอยู่แล้ว: data/raw/ksp/act-2546.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-2553.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-2559.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-2563.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-2568.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-2549.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-2569.pdf
มีอยู่แล้ว: data/raw/ksp/ksp-ann-appeal.pdf

<span class="ok">ครบทั้ง 10 ฉบับใน data/raw/ksp/</span>
<span class="d">ต่อไป: python -m ingest.extract_ksp</span></div>
</div>
"""

FIGURES["fig-3-5-ladder-code"] = """
<div class="col" style="width:1080px">
  <div class="file">ingest/thai_pdf_text.py</div>
  <div class="code"><span class="c"># AngsanaUPC keeps the tone marks in the Private Use Area. Without this map the
# whole document comes out with every vowel and tone mark missing.</span>
PUA_MAP = {0xF700: <span class="s">"ั"</span>, 0xF701: <span class="s">"ิ"</span>, 0xF70A: <span class="s">"่"</span>, 0xF70B: <span class="s">"้"</span>,
           0xF70E: <span class="s">"์"</span>, 0xF710: <span class="s">"ั"</span>, 0xF712: <span class="s">"็"</span>, 0xF8FF: <span class="s">"๐"</span>}

<span class="c"># SARA AM stored as two characters. 648 of them, and newmm splits every word
# that contains one.</span>
SPLIT_SARA = re.compile(<span class="s">r"[ก-ฮ]\s+[าำ]"</span>)

<span class="k">def</span> extract(path: str) -&gt; str:
    <span class="s">&quot;&quot;&quot;Four rungs, cheapest first. The first that passes every gate wins.&quot;&quot;&quot;</span>
    <span class="k">for</span> rung <span class="k">in</span> (from_text, from_pua, from_legacy, from_ocr):
        text = rung(path)
        <span class="k">if</span> passes_every_gate(text):
            <span class="k">return</span> text
    <span class="k">raise</span> BadExtraction(path)</div>
</div>
"""

FIGURES["fig-3-6-audit-run"] = """
<div class="col" style="width:1080px">
  <div class="file">$ python -m ingest.audit_ksp</div>
  <div class="term"><span class="ok">[ok]</span> เลขข้อเรียงครบ ไม่ข้าม ไม่ซ้ำ: ผ่าน
<span class="ok">[ok]</span> จำนวนข้อตรงกับที่นับจาก PDF: ผ่าน
<span class="ok">[ok]</span> ครบห้าด้าน และ 2556 ติดป้ายถูกหมวด: ผ่าน
<span class="ok">[ok]</span> ไม่มีข้อความหาย: ผ่าน
<span class="ok">[ok]</span> ไม่มีหัวกระดาษราชกิจจาฯ ปน: ผ่าน
<span class="ok">[ok]</span> ตัวบทห้าด้านพูดถึงด้านนั้นจริง: ผ่าน

<span class="d">รายงาน: data/processed/corpus_ksp_audit.md</span>
<span class="ok">ผ่านครบทุกด่าน</span> <span class="d">— ต่อไป: python -m ingest.build_index</span></div>
</div>
"""

FIGURES["fig-3-7-expand-code"] = """
<div class="col" style="width:1080px">
  <div class="file">app/query_expand.py</div>
  <div class="code"><span class="c"># colloquial trigger -&gt; legal vocabulary to append. Terms are *appended*, never
# substituted: the user's own words still drive BM25, and a question that
# already uses legal vocabulary is unaffected.</span>
GLOSSARY: tuple[tuple[str, ...], ...] = (
    (<span class="s">r"ด่า|ดุ|ตะคอก|ด่าทอ"</span>,
     <span class="s">"ดูหมิ่น เหยียดหยาม ปฏิปักษ์ต่อความเจริญทางจิตใจ อารมณ์ และสังคมของศิษย์"</span>),
    (<span class="s">r"เรียกเงิน|รับสินบน|เรียกรับ"</span>,
     <span class="s">"แสวงหาประโยชน์อันเป็นอามิสสินจ้างจากผู้รับบริการ"</span>),
    (<span class="s">r"มาตรฐานวิชาชีพ|กี่ด้าน"</span>,
     <span class="s">"มาตรฐานความรู้และประสบการณ์วิชาชีพ มาตรฐานการปฏิบัติงาน มาตรฐานการปฏิบัติตน"</span>),
    (<span class="s">r"ร้องเรียน|แจ้งความผิด|ฟ้อง"</span>,
     <span class="s">"กล่าวหา กล่าวโทษ คณะอนุกรรมการสอบสวน"</span>),
    <span class="c">... รวมกว่า 60 รายการ ...</span>
)</div>
</div>
"""

FIGURES["fig-3-8-prompt-code"] = """
<div class="col" style="width:1080px">
  <div class="file">app/answer.py &mdash; SYSTEM_PROMPT (ตัดมาบางส่วนจาก 18 ข้อ)</div>
  <div class="code">1. ตอบจากตัวบทที่ให้มาเท่านั้น ห้ามใช้ความรู้อื่น
2. ทุกข้อความที่เป็นสาระ ต้องอ้างที่มาในวงเล็บ โดยคัดลอกชื่อที่กำกับหน้าตัวบทมาทั้งบรรทัด
   ห้ามย่อชื่อเอง ห้ามสลับชื่อข้ามฉบับ และห้ามเปลี่ยนคำว่า <span class="s">"ข้อ"</span> เป็น <span class="s">"มาตรา"</span> หรือกลับกัน
   ข้อบังคับคุรุสภาใช้คำว่า <span class="s">"ข้อ"</span> พระราชบัญญัติใช้คำว่า <span class="s">"มาตรา"</span> ข้อบังคับไม่มีมาตรา
3. ห้ามแต่งเลขข้อหรือเลขมาตรา ถ้าไม่แน่ใจเลขข้อ ให้อธิบายโดยไม่ใส่เลข
4. ถ้าตัวบทไหนมีคำว่า (ยกเลิกแล้ว) กำกับอยู่ ห้ามอ้างเป็นกฎที่ใช้อยู่
5. ถ้าตัวบทไม่พอจะตอบ บอกตรง ๆ ว่าตัวบทไม่ได้เขียนเรื่องนี้ไว้ ห้ามเดา
6. ถ้าคำถามถามถึงครู ห้ามตอบด้วยข้อของผู้บริหารหรือศึกษานิเทศก์
12. คำว่า <span class="s">"ต้อง"</span> กับ <span class="s">"พึง"</span> ในตัวบทมีน้ำหนักต่างกัน ต้องคัดลอกมาให้ตรงตามที่ตัวบทใช้
13. ถ้าจะอ้างอนุข้อหรือวรรค เช่น (ก) (ข) (๑) ต้องแน่ใจว่าข้อความนั้นอยู่ในอนุข้อนั้นจริง</div>
</div>
"""

FIGURES["fig-3-9-inspect-code"] = """
<div class="col" style="width:1080px">
  <div class="file">app/answer.py &mdash; inspect()</div>
  <div class="code"><span class="k">def</span> inspect(text: str, hits: list[Hit]) -&gt; list[Fault]:
    <span class="s">&quot;&quot;&quot;Everything wrong with a draft, in one pass, so the repair turn sees it all.

    Reporting one fault at a time made the writer fix that one and break
    another, which is most of what the regression column of the runs was.
    &quot;&quot;&quot;</span>
    faults: list[Fault] = []

    <span class="c"># the answer drifted into law the corpus does not hold</span>
    <span class="k">if</span> (strayed := find_gap_in_answer(text, evidence)):
        faults.append(Fault(..., blocks=<span class="k">True</span>))

    <span class="c"># the answer names an instrument that does not exist in the corpus</span>
    <span class="k">for</span> law <span class="k">in</span> unsupported_laws(text, index.all_citations, evidence):
        faults.append(Fault(..., blocks=<span class="k">True</span>))

    <span class="c"># the rule number, the unit word, or the sub-item does not exist</span>
    <span class="k">for</span> problem <span class="k">in</span> impossible_citations(text, index):
        faults.append(Fault(problem, blocks=<span class="k">True</span>))

    <span class="c"># พึง reported as ต้อง, or the reverse -- two words against the text</span>
    <span class="k">for</span> problem <span class="k">in</span> modal_mismatches(text, index):
        faults.append(Fault(problem, blocks=<span class="k">False</span>))

    <span class="c"># measured at 39% of answers with 68% of those wrong: recorded, not acted on</span>
    <span class="k">for</span> problem <span class="k">in</span> unsupported_claims(text, index):
        faults.append(Fault(problem, blocks=<span class="k">False</span>, acts=<span class="k">False</span>))

    <span class="k">return</span> faults</div>
</div>
"""

FIGURES["fig-3-10-api-json"] = """
<div class="col" style="width:1080px">
  <div class="file">$ curl -s -X POST localhost:8077/chat -d '{"question":"ครูนินทาเพื่อนครูผิดข้อไหน"}'</div>
  <div class="code">{
  <span class="k">"answer"</span>: <span class="s">"ครูนินทาเพื่อนครูถือว่าผิดจรรยาบรรณต่อผู้ร่วมประกอบวิชาชีพ ... ข้อบังคับคุรุสภา
             จรรยาบรรณของวิชาชีพ 2556 ข้อ 14 ระบุว่า ผู้ประกอบวิชาชีพทางการศึกษา พึงช่วย …"</span>,
  <span class="k">"in_scope"</span>: <span class="k">true</span>,
  <span class="k">"error"</span>: <span class="k">null</span>,
  <span class="k">"faults"</span>: [<span class="s">"ข้อ 14 ไม่มีข้อความรองรับประโยคที่อ้างถึง (ข้อ 14)"</span>],
  <span class="k">"repair"</span>: <span class="s">"not attempted"</span>,
  <span class="k">"sources"</span>: [
    { <span class="k">"citation"</span>: <span class="s">"ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 14"</span>,
      <span class="k">"score"</span>: 0.0318, <span class="k">"dense"</span>: 0.7059, <span class="k">"bm25"</span>: 32.517 },
    { <span class="k">"citation"</span>: <span class="s">"ข้อบังคับคุรุสภา จรรยาบรรณของวิชาชีพ 2556 ข้อ 9"</span>,
      <span class="k">"score"</span>: 0.0280, <span class="k">"dense"</span>: 0.6114, <span class="k">"bm25"</span>: 14.828 }
  ]
}</div>
  <div class="lbl">ฟิลด์ faults และ repair เพิ่มขึ้นเพื่อให้ผู้ประเมินตรวจกลไกได้โดยตรง แทนการอนุมานจากการเทียบผลกับรอบก่อน</div>
</div>
"""

FIGURES["fig-3-11-pytest"] = """
<div class="col" style="width:1080px">
  <div class="file">$ python -m pytest tests/ -q</div>
  <div class="term">...................................................................... [ 18%]
...................................................................... [ 36%]
...................................................................... [ 55%]
...................................................................... [ 73%]
...................................................................... [ 91%]
................................                                       [100%]

<span class="ok">383 passed</span>, 7 warnings in 48.91s</div>
  <div class="lbl">ชุดทดสอบครอบคลุมการถอดข้อความ การแยกรายข้อ การตัดคำ การค้นคืน ชั้นตรวจสอบคำตอบ และส่วนติดต่อผู้ใช้ ทุกการทดสอบต้องผ่านก่อนนำระบบเข้าสู่การประเมิน</div>
</div>
"""

FIGURES["fig-3-12-testcase"] = """
<div class="col" style="width:1080px">
  <div class="file">docs/ksp-acceptance-tests.md &mdash; ตัวอย่างเคสทดสอบ 2 เคส</div>
  <div class="code"><span class="k">### KSP-021</span>
<span class="k">คำถาม</span> ครูเรียกเงินจากผู้ปกครองเพื่อแลกกับคะแนน ผิดข้อไหน
<span class="k">ต้องอ้าง</span> ข้อ 13 ข้อบังคับฯ 2556 และ/หรือ ข้อ 7 (ข) ข้อบังคับฯ 2550
<span class="k">ต้องมี</span> ถ้อยคำ <span class="s">"แสวงหาประโยชน์อันเป็นอามิสสินจ้าง"</span> หรือ <span class="s">"เรียกร้องผลตอบแทน"</span>
<span class="k">ต้องไม่มี</span> อ้างเป็นความผิดทางวินัยข้าราชการ

<span class="k">### KSP-040</span>
<span class="k">คำถาม</span> ครูไปหาเสียงช่วยผู้สมัคร ส.ส. ผิดจรรยาบรรณไหม
<span class="k">ต้องอ้าง</span> ข้อ 15 ข้อบังคับฯ 2556 และ/หรือ ข้อ 9 ข้อบังคับฯ 2550
<span class="k">ต้องมี</span> ยกหลักการยึดมั่นในระบอบประชาธิปไตยและการเป็นแบบอย่างที่ดี
       <span class="k">บอกว่าข้อบังคับจรรยาบรรณไม่ได้ห้ามเรื่องนี้ไว้โดยตรง</span>
       และข้อห้ามทางการเมืองของข้าราชการครูอยู่ในกฎหมายอื่นที่ระบบนี้ไม่มี
<span class="k">ต้องไม่มี</span> ฟันธงว่าผิดโดยอ้างข้อที่ไม่มีข้อความรองรับ</div>
  <div class="lbl">ทุกเคสระบุสามอย่าง คือคำถาม ข้อที่ต้องอ้าง และสิ่งที่คำตอบต้องมีหรือต้องไม่มี &mdash; เขียนจากไฟล์ PDF ต้นฉบับก่อนแก้โค้ดของระบบ</div>
</div>
"""

# ------------------------------------------------------ บทที่ 4, the results

FIGURES["fig-4-1-trajectory"] = """
<div class="col" style="width:1080px">
  <div class="row" style="align-items:flex-end;height:330px;gap:26px;padding-left:56px">
    ROWS
  </div>
  <div class="row" style="padding-left:56px;gap:26px">LABELS</div>
  <div class="row" style="justify-content:center;gap:28px;margin-top:10px;font-size:15px">
    <span><span style="display:inline-block;width:13px;height:13px;background:#8d2230;border-radius:3px"></span> PASS</span>
    <span><span style="display:inline-block;width:13px;height:13px;background:#d9c7ac;border-radius:3px"></span> PARTIAL</span>
    <span><span style="display:inline-block;width:13px;height:13px;background:#d9d0d1;border-radius:3px"></span> FAIL</span>
    <span style="color:#2f7d4f">&mdash;&mdash; เกณฑ์ผ่าน 45 เคส</span>
  </div>
  <div class="lbl">แต่ละรอบประเมินครบ 61 เคสโดยผู้ประเมินที่ไม่ใช่ผู้พัฒนา &mdash; เส้นเกณฑ์กำหนดไว้ก่อนการประเมินรอบแรกและไม่ถูกลดลงเมื่อไม่ผ่าน</div>
</div>
"""


def _trajectory() -> None:
    """Fill the round bars in from the measured counts.

    Written out rather than drawn with a chart library for the same reason as
    the rest of these: Chrome already has the Thai fonts, and the numbers are
    few enough to read straight off the report.
    """
    rounds = [(18, 9, 23), (19, 21, 10), (22, 19, 9), (26, 16, 8),
              (22, 18, 10), (29, 15, 6), (28, 14, 8), (29, 6, 15)]
    scale = 300 / 50          # px per case, 50 cases to the column
    bars, labels = [], []
    for i, (p, pa, f) in enumerate(rounds, 1):
        bars.append(
            f'<div class="col grow" style="gap:0;justify-content:flex-end;position:relative">'
            f'<div style="position:absolute;top:{300 - 45 * scale:.0f}px;left:-56px;right:0;'
            f'border-top:1.5px dashed #2f7d4f"></div>' if i == 1 else
            '<div class="col grow" style="gap:0;justify-content:flex-end">')
        bars.append(
            f'<div style="background:#d9d0d1;height:{f * scale:.0f}px"></div>'
            f'<div style="background:#d9c7ac;height:{pa * scale:.0f}px"></div>'
            f'<div style="background:#8d2230;height:{p * scale:.0f}px;'
            f'border-radius:5px 5px 0 0;position:relative">'
            f'<span style="position:absolute;top:-24px;left:0;right:0;text-align:center;'
            f'font-size:15px;font-weight:600;color:#8d2230">{p}</span></div></div>')
        labels.append(f'<div class="grow center" style="font-size:15px;color:#857a7c">'
                      f'รอบที่ {i}</div>')
    FIGURES["fig-4-1-trajectory"] = (FIGURES["fig-4-1-trajectory"]
                                     .replace("ROWS", "".join(bars))
                                     .replace("LABELS", "".join(labels)))


_trajectory()


def screenshot_app(question: str, port: int = 8077) -> None:
    """The one figure that is not a drawing: the running system answering.

    Driven through a throwaway copy of the page that reads the question from the
    query string and submits it, because Chrome's --screenshot cannot type. The
    copy lives under web/ so the app's own relative fetches still resolve, and is
    removed afterwards. Needs the server up: .venv/bin/uvicorn app.main:app.
    """
    import urllib.parse

    web = os.path.join(os.path.dirname(HERE), "web")
    src = open(os.path.join(web, "index.html"), encoding="utf-8").read()
    shot = os.path.join(web, "_shot.html")
    with open(shot, "w", encoding="utf-8") as fh:
        fh.write(src.replace("</body>", """
<script>
window.addEventListener('load', () => {
  const q = new URLSearchParams(location.search).get('q');
  if (!q) return;
  document.querySelector('#form input, #form textarea').value = q;
  document.getElementById('form').dispatchEvent(
      new Event('submit', {cancelable: true, bubbles: true}));
});
</script>
</body>""", 1))
    try:
        url = (f"http://localhost:{port}/static/_shot.html?q="
               + urllib.parse.quote(question))
        subprocess.run(
            [CHROME, "--headless=old", "--disable-gpu", "--hide-scrollbars",
             "--window-size=1440,1000", "--virtual-time-budget=40000",
             f"--screenshot={os.path.join(OUT, 'fig-2-1-webapp.png')}", url],
            capture_output=True, check=True)
        print("wrote fig-2-1-webapp.png")
    finally:
        os.remove(shot)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for name, body in FIGURES.items():
        render(name, body)


if __name__ == "__main__":
    main()
