# -*- coding: utf-8 -*-
"""Bridge the gap between how people ask and how the law is written.

This is the single biggest source of retrieval failure in the system. Users type
"โดนไล่ออก ได้เงินไหม"; no section contains the word "ไล่ออก", because the statute
says "การเลิกจ้าง" and "ค่าชดเชย". Measured effect of adding the legal terms:

    โดนไล่ออก ได้เงินไหม      cosine 0.63 -> 0.77, top hit
                              พ.ร.บ.เงินเดือนข้าราชการ -> คุ้มครองแรงงาน ม.119/122/118
    เจ้าหนี้ทวงหนี้ตี 1 ผิดไหม cosine 0.64 -> 0.65, top hit
                              บริษัทมหาชน ม.162 -> ทวงถามหนี้ ม.9/11/12
    ลาพักร้อนกี่วัน            cosine 0.61 -> 0.78, top hit ม.41 -> ม.30

Terms are *appended*, never substituted: the user's own words still drive BM25,
and a question that already uses legal vocabulary is unaffected.

A rule table is used rather than an LLM rewrite because it costs nothing, adds no
latency, is deterministic, and is testable. Its limit is equally plain: it only
knows the phrases listed here. Anything outside the table falls back to the raw
question, which is the behaviour before this module existed -- so a missing entry
degrades quality, it never breaks a query that used to work.
"""
from __future__ import annotations

import re

# colloquial trigger -> legal vocabulary to append
GLOSSARY: tuple[tuple[str, ...], ...] = (
    # --- the five duties, by name and by paraphrase ---
    (r"กี่ด้าน|มีอะไรบ้าง|องค์ประกอบ|ครบทุกด้าน",
     "จรรยาบรรณต่อตนเอง จรรยาบรรณต่อวิชาชีพ จรรยาบรรณต่อผู้รับบริการ "
     "จรรยาบรรณต่อผู้ร่วมประกอบวิชาชีพ จรรยาบรรณต่อสังคม", r"จรรยาบรรณ|วิชาชีพ"),
    (r"พัฒนาตัวเอง|พัฒนาตนเอง|อบรม|เรียนต่อ|ทันสมัย|วิสัยทัศน์|บุคลิกภาพ",
     "วินัยในตนเอง พัฒนาตนเองด้านวิชาชีพ บุคลิกภาพ วิสัยทัศน์"),
    (r"รักวิชาชีพ|ศรัทธา|ชื่อเสียงวิชาชีพ|ศักดิ์ศรี|องค์กรวิชาชีพ",
     "รัก ศรัทธา ซื่อสัตย์สุจริต รับผิดชอบต่อวิชาชีพ สมาชิกที่ดีขององค์กรวิชาชีพ"),
    (r"ชุมชน|สังคม|สิ่งแวดล้อม|วัฒนธรรม|ภูมิปัญญา|ประชาธิปไตย|เศรษฐกิจพอเพียง",
     "จรรยาบรรณต่อสังคม อนุรักษ์ ผลประโยชน์ของส่วนรวม"),

    # --- ศิษย์ and ผู้รับบริการ are the words the text uses; nobody types them ---
    (r"นักเรียน|นักศึกษา|เด็ก|ลูกศิษย์|ผู้เรียน|ลูกค้า",
     "ศิษย์ ผู้รับบริการ"),
    (r"ด่า|ดูถูก|ประจาน|ตะคอก|ว่ากล่าวรุนแรง|เหยียด",
     "ดูหมิ่นเหยียดหยามศิษย์ พฤติกรรมที่ไม่พึงประสงค์"),
    (r"ตีเด็ก|ตีนักเรียน|ทำโทษ|ลงโทษนักเรียน|ลงโทษเด็ก|กักบริเวณ",
     "ลงโทษศิษย์อย่างไม่เหมาะสม"),
    (r"ความลับ|เปิดเผยข้อมูล|ไปเล่าให้|เอาไปบอก|ปากโป้ง|ปล่อยข่าว|แฉ",
     "เปิดเผยความลับของศิษย์ เสื่อมเสียชื่อเสียง"),
    (r"เท่ากัน|เสมอภาค|ลำเอียง|เลือกที่รัก|ไม่เป็นธรรมกับเด็ก",
     "โดยเสมอหน้า ให้บริการด้วยความจริงใจและเสมอภาค"),
    (r"รับเงิน|เรียกเงิน|สินบน|แป๊ะเจี๊ยะ|ของขวัญ|ผลประโยชน์",
     "เรียกรับหรือยอมรับผลประโยชน์จากการใช้ตำแหน่งหน้าที่โดยมิชอบ"),
    (r"สอนพิเศษ|ติวเตอร์|กวดวิชา|เก็บเงินเพิ่ม",
     "ให้บริการด้วยความจริงใจและเสมอภาค ผลประโยชน์ ตำแหน่งหน้าที่"),

    # --- conduct towards colleagues ---
    (r"นินทา|ซุบซิบ|ว่าร้าย|ใส่ร้าย|พูดลับหลัง",
     "วิพากษ์วิจารณ์ผู้ร่วมประกอบวิชาชีพ แตกความสามัคคี"),
    (r"กลั่นแกล้ง|บูลลี่|กดดันเพื่อนร่วมงาน|ตั้งแก๊ง|เล่นพรรคเล่นพวก",
     "กลั่นแกล้งผู้ร่วมประกอบวิชาชีพ กลุ่มอิทธิพลภายในองค์การ"),
    (r"โยนความผิด|โทษคนอื่น|ไม่รับผิดชอบ",
     "ปฏิเสธความรับผิดชอบ ตำหนิให้ร้ายผู้อื่น"),
    (r"ปิดบัง|ไม่บอก|ไม่แชร์ข้อมูล|หมกเม็ด",
     "ปิดบังข้อมูลข่าวสารในการปฏิบัติงาน"),
    (r"เพื่อนครู|เพื่อนร่วมงาน|ครูด้วยกัน|หมู่คณะ",
     "ผู้ร่วมประกอบวิชาชีพ ช่วยเหลือเกื้อกูล ความสามัคคี"),

    # --- conduct towards the profession ---
    (r"ลอกผลงาน|ลอกงาน|คัดลอก|ขโมยผลงาน|ก็อป",
     "คัดลอกหรือนำผลงานของผู้อื่นมาเป็นของตน"),
    (r"มีชู้|ชู้สาว|คุกคามทางเพศ|ล่วงละเมิดทางเพศ|ลวนลาม|จีบนักเรียน",
     "ประพฤติผิดทางชู้สาว ล่วงละเมิดทางเพศ พฤติกรรมที่ไม่พึงประสงค์"),
    (r"พนัน|บ่อน|หวย|เหล้า|สุรา|เมา|ยาเสพติด|เสพยา|บุหรี่ไฟฟ้า",
     "อบายมุข สิ่งเสพติด พฤติกรรมที่ไม่พึงประสงค์"),
    (r"ทำงานนอก|อาชีพเสริม|รับจ้างทำ|ขายของออนไลน์",
     "ประกอบการงานอื่นที่ไม่เหมาะสมกับการเป็นผู้ประกอบวิชาชีพทางการศึกษา"),

    # --- penalties: nobody types the five outcomes, everybody types "โทษ" ---
    # not a bare "โทษ": "ลงโทษนักเรียน" contains it, and the penalties the
    # Council can impose are not what that question is about
    # "โทษ...มีกี่สถาน" matched none of these triggers, so มาตรา 54 -- the one
    # section that lists the penalties -- was never retrieved, and five rounds
    # of assessors marked the answer wrong for the same reason each time.
    (r"มีโทษ|บทลงโทษ|โทษอะไร|โทษของ|กี่สถาน|สถานใด|โดนอะไร|ผลที่ตามมา"
     r"|ซีเรียสแค่ไหน|ลงโทษครู",
     "ยกข้อกล่าวหา ตักเตือน ภาคทัณฑ์ พักใช้ใบอนุญาต เพิกถอนใบอนุญาต "
     "คณะกรรมการมาตรฐานวิชาชีพมีอำนาจวินิจฉัยชี้ขาด"),
    (r"ยึดใบอนุญาต|โดนพักใบ|ถูกถอนใบ|เสียใบอนุญาต|หมดสิทธิ์สอน",
     "พักใช้ใบอนุญาต เพิกถอนใบอนุญาต"),
    # "ระยะเวลาสูงสุดของการพักใช้ใบอนุญาต" is the one labelled question retrieval
    # has never answered: the cap lives in มาตรา 54 (๔), whose words are these.
    (r"สูงสุด|นานสุด|ไม่เกินกี่|กี่ปี|นานเท่าไหร่|นานแค่ไหน",
     "มีกำหนดเวลาตามที่เห็นสมควร ไม่เกินห้าปี", r"พักใช้|ใบอนุญาต|เพิกถอน"),

    # --- procedure ---
    (r"ร้องเรียน|แจ้งเรื่อง|เอาผิดครู|ฟ้องครู|แจ้งคุรุสภา|ร้องทุกข์",
     "การกล่าวหา การกล่าวโทษ ยื่นเรื่องต่อคุรุสภา หนังสือกล่าวหา"),
    # What a complaint must contain is ข้อ 8; ข้อ 37, about what the sub-committee
    # weighs afterwards, outranked it and the answer was written half out of the
    # wrong rule. These are ข้อ 8's own words.
    (r"รายการใด|ต้องมีอะไร|ต้องใส่อะไร|ต้องระบุ|เขียนอย่างไร|เขียนยังไง",
     "ทำเป็นหนังสือ ใช้ถ้อยคำสุภาพ สาระสำคัญ ชื่อและที่อยู่ของผู้กล่าวหา "
     "ลายมือชื่อผู้กล่าวหา", r"กล่าวหา|กล่าวโทษ|ร้องเรียน|คำร้อง"),
    # Not a glossary entry for "ฉบับใดที่ใช้อยู่ในปัจจุบัน": tried, and appending
    # the title and commencement clauses put ข้อ 1 and ข้อ 2 of every regulation
    # in the corpus at the top and pushed the repeal clause -- the rule that
    # actually answers it -- out. Labelled recall fell 98% to 94%. Retrieval
    # already returns ข้อ 3 first; the failure on that question is on the answer
    # side, not here.
    (r"สอบสวน|สืบสวน|ตั้งกรรมการ|ตั้งคณะกรรมการ",
     "คณะอนุกรรมการสืบสวน คณะอนุกรรมการสอบสวน"),
    (r"ไม่ร้ายแรง|เล็กน้อย|ไม่หนัก",
     "ประพฤติผิดจรรยาบรรณของวิชาชีพไม่ร้ายแรง ตักเตือน ภาคทัณฑ์ "
     "โดยไม่ต้องแต่งตั้งคณะอนุกรรมการสอบสวน"),
    (r"อุทธรณ์|ขอทบทวน|ไม่ยอมรับคำวินิจฉัย|สู้ต่อ",
     "อุทธรณ์คำวินิจฉัย คณะอนุกรรมการอุทธรณ์ คณะกรรมการคุรุสภา"),
    (r"กี่วัน|ภายในกี่|ระยะเวลา|เลยกำหนด",
     "นับแต่วันที่ได้รับแจ้ง ภายในกำหนด", r"อุทธรณ์|กล่าวหา|สอบสวน|ชี้แจง"),

    # --- who the rules apply to ---
    (r"ผอ|ผู้อำนวยการ|ครูใหญ่|หัวหน้าสถานศึกษา", "ผู้บริหารสถานศึกษา"),
    (r"ศึกษานิเทศก์|ศน\.", "ศึกษานิเทศก์"),
    (r"ผู้บริหารเขต|ผอ\.เขต|เขตพื้นที่", "ผู้บริหารการศึกษา"),
    # มาตรฐานวิชาชีพ (three standards, มาตรา 49) and จรรยาบรรณ (five duties,
    # มาตรา 50) are adjacent sections about different things, and the bot
    # answered "มาตรฐานวิชาชีพมี 5 ด้าน" from the wrong one in five successive
    # acceptance runs. The three names are what tell the two apart.
    (r"มาตรฐานวิชาชีพ|มาตรฐานการปฏิบัติ",
     "มาตรฐานความรู้และประสบการณ์วิชาชีพ มาตรฐานการปฏิบัติงาน มาตรฐานการปฏิบัติตน"),
    (r"ใครบังคับใช้|ใครกำหนด|ใครดูแล",
     "คุรุสภา คณะกรรมการคุรุสภา คณะกรรมการมาตรฐานวิชาชีพ"),
)

# (trigger, terms to append, optional pattern the question must also contain)
COMPILED = tuple((re.compile(entry[0]), entry[1],
                  re.compile(entry[2]) if len(entry) > 2 else None)
                 for entry in GLOSSARY)


def expand(question: str) -> tuple[str, list[str]]:
    """Return (query for retrieval, legal terms that were added)."""
    added: list[str] = []
    for pattern, terms, context in COMPILED:
        if not pattern.search(question):
            continue
        # a word can belong to two areas of law at once; the context pattern is
        # how an entry says "only when the question is about that area"
        if context is not None and not context.search(question):
            continue
        for term in terms.split():
            if term not in added and term not in question:
                added.append(term)
    if not added:
        return question, []
    return f"{question} {' '.join(added)}", added
