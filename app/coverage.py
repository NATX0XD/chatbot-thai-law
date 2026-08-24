# -*- coding: utf-8 -*-
"""Deterministic detection of questions this corpus cannot answer.

Similarity scores cannot catch these. "จดทะเบียนสมรสแล้วอยากหย่า" retrieves
พระราชบัญญัติจดทะเบียนครอบครัว at cosine 0.64 -- a real, on-topic act that happens
not to contain the grounds for divorce, because those live in ประมวลกฎหมายแพ่งและ
พาณิชย์ บรรพ 5, which the source corpus does not include. To the retriever this
looks exactly like a successful search.

So the gap is handled by rule rather than by score. We know precisely which codes
are absent (see บทที่ 5 of the dataset survey), so we can name them and tell the
user where to look instead, which is more useful than a generic refusal.

Patterns intentionally target *substantive* terms, not procedural ones: asking
where to register a marriage is answerable from พระราชบัญญัติจดทะเบียนครอบครัว,
asking on what grounds one may divorce is not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Gap:
    topic: str
    code: str
    pattern: re.Pattern

    def message(self) -> str:
        return (
            f"คำถามนี้อยู่ในเรื่อง{self.topic} ซึ่งกำกับโดย{self.code}\n\n"
            f"คลังข้อมูลของระบบมีเฉพาะพระราชบัญญัติและพระราชกำหนด "
            f"ยังไม่มี{self.code} ผมจึงตอบไม่ได้ และจะไม่เดาให้ครับ\n\n"
            "แนะนำให้ดูตัวบทที่ krisdika.go.th หรือปรึกษาทนายความ "
            "หรือติดต่อสภาทนายความ สายด่วน 1167 สำหรับคำปรึกษาเบื้องต้นฟรี"
        )


def _p(*words: str) -> re.Pattern:
    return re.compile("|".join(words))


GAPS: tuple[Gap, ...] = (
    Gap("เช่าทรัพย์และเงินมัดจำ", "ประมวลกฎหมายแพ่งและพาณิชย์ บรรพ 3",
        _p("มัดจำ", "เงินประกันการเช่า", "ค่าเช่าบ้าน", "ค่าเช่าห้อง", "เช่าบ้าน",
           "เช่าห้อง", "เช่าคอนโด", "เช่าที่ดิน", "สัญญาเช่า", "ผู้ให้เช่า",
           "ผู้เช่า", "ไล่ที่", "ขึ้นค่าเช่า")),
    Gap("มรดกและพินัยกรรม", "ประมวลกฎหมายแพ่งและพาณิชย์ บรรพ 6",
        _p("มรดก", "พินัยกรรม", "ทายาทโดยธรรม", "แบ่งสมบัติ", "ผู้จัดการมรดก",
           "เจ้ามรดก")),
    Gap("ครอบครัว การสมรสและการหย่า", "ประมวลกฎหมายแพ่งและพาณิชย์ บรรพ 5",
        _p("ฟ้องหย่า", "อยากหย่า", "จะหย่า", "การหย่า", "สินสมรส", "สินส่วนตัว",
           "ค่าเลี้ยงดู", "ค่าอุปการะเลี้ยงดู", "อำนาจปกครองบุตร", "หมั้น",
           "ของหมั้น", "สินสอด", "รับรองบุตร", "ฟ้องชู้")),
    Gap("การกู้ยืมเงินและหลักประกัน", "ประมวลกฎหมายแพ่งและพาณิชย์ บรรพ 3",
        _p("กู้ยืม", "ยืมเงิน", "ให้ยืมเงิน", "ค้ำประกัน", "ผู้ค้ำ", "จำนอง",
           "จำนำ", "ดอกเบี้ยเงินกู้", "สัญญาเงินกู้", "หนี้นอกระบบ")),
    # Everyday words matter more than statutory ones here. A user reporting a
    # shoplifting friend wrote "ขโมยของ", not "ลักทรัพย์" -- the rule missed it,
    # retrieval surfaced an unrelated payments act above the gate, and the model
    # invented ประมวลกฎหมายอาญา มาตรา 335 out of its own memory.
    Gap("ความผิดอาญา", "ประมวลกฎหมายอาญา",
        _p("หมิ่นประมาท", "ฉ้อโกง", "ยักยอก", "ลักทรัพย์", "ทำร้ายร่างกาย",
           "ข่มขืน", "ชิงทรัพย์", "วิ่งราว", "ปล้น", "บุกรุก", "โกงเงิน",
           "หลอกโอนเงิน", "แจ้งความ", "เจตนาฆ่า", "พรากผู้เยาว์",
           "ขโมย", "ขโมยของ", "ลักขโมย", "โจร", "ยกเค้า", "ตีชิง",
           "ทำลายทรัพย์", "เผาทรัพย์", "ปลอมแปลง", "ติดคุก", "จำคุก",
           "ต้องโทษ", "อายุความ", "ประกันตัว", "รับสารภาพ", "คดีอาญา")),
    Gap("ละเมิดและการเรียกค่าเสียหาย", "ประมวลกฎหมายแพ่งและพาณิชย์ บรรพ 2",
        _p("ละเมิด", "ค่าสินไหมทดแทน", "เรียกค่าเสียหายทางแพ่ง")),
    Gap("ประกันสังคม", "พระราชบัญญัติประกันสังคม พ.ศ. 2533",
        _p("ประกันสังคม", "ผู้ประกันตน", "มาตรา 33", "มาตรา 39", "มาตรา 40",
           "เงินชราภาพ", "เงินว่างงาน", "สปส")),
    Gap("การกระทำความผิดทางคอมพิวเตอร์", "พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์",
        _p("แฮก", "เจาะระบบ", "โพสต์ข้อมูลเท็จ", "พรบคอม", "พ\\.ร\\.บ\\.คอม")),
)


def find_gap(question: str) -> Gap | None:
    """Return the first known gap this question falls into, if any."""
    for gap in GAPS:
        if gap.pattern.search(question):
            return gap
    return None
