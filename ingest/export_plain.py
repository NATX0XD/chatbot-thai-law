# -*- coding: utf-8 -*-
"""The same test run, written so someone who has not read the thesis can follow it.

    .venv/bin/python -m ingest.export_plain 8

ingest/export_results.py writes the version the thesis cites: outcome codes
0/1/2/3, the phrasings named "ตรง" and "คลุมเครือ", "ค่าความถูกต้อง". That
wording is the advisor's and has to stay. It also means a reader who opens the
file cold cannot tell what code 3 is, or that a code is a phrasing and an outcome
at once.

This writes a second workbook saying the same things in ordinary Thai. Both come
from the same coding files, so the totals agree; only the words differ.

The one-line reason a question failed is in PLAIN_FAULT below. Each line is a
summary of what the assessors actually wrote, and their words are kept verbatim
in the next column of the sheet so the summary can be checked against them.
Nothing here is written from the corpus or guessed.
"""
from __future__ import annotations

import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from ingest.export_results import (CORRECT, EVAL, RIGHT_FILL, SPLIT_FILL,
                                   WRONG_FILL, cited, coding, load,
                                   rounds_available, widths)

BIG = Font(bold=True, size=13)
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="4F6228")
WRAP = Alignment(vertical="top", wrap_text=True)

PHRASING = {
    "ตรง": "ถามแบบทางการ ใช้ศัพท์กฎหมาย",
    "คลุมเครือ": "ถามแบบคนทั่วไปพูด",
}

# what went wrong, summarised from the assessors' notes for round 8. The kind is
# a grouping of those summaries, not a label the assessors used.
PLAIN_FAULT: dict[str, tuple[str, str]] = {
    "U-02b": ("ตอบกว้างกว่าที่กฎเขียน",
              "ตอบว่าครูวิจารณ์องค์กรวิชาชีพผิดจรรยาบรรณทุกกรณี "
              "แต่ข้อของครูไม่ได้ห้ามไว้กว้างขนาดนั้น"),
    "U-08a": ("หยิบกฎของวิชาชีพผิดประเภท",
              "คำถามถามเรื่องครูดูหมิ่นศิษย์ แต่ยกข้อ 16 ซึ่งเป็นของ"
              "ผู้บริหารการศึกษา และเป็นเรื่องรักศรัทธาวิชาชีพ ไม่ใช่เรื่องศิษย์"),
    "U-12b": ("ยกกฎที่พูดเรื่องอื่นมาตอบ",
              "ยกข้อ 65 มาอ้างว่าเป็นขั้นตอนสอบสวน แต่ข้อ 65 เป็นเรื่อง"
              "พักใช้ใบอนุญาตได้โดยไม่ต้องรอผลสอบสวน"),
    "U-15b": ("อ้างเลขข้อผิด",
              "ตอบว่าข้อความ ประพฤติตนเหมาะสมกับสถานภาพ อยู่ในข้อ 6 "
              "แต่ข้อความนี้อยู่ในข้อ 5(ก)(๑)"),
    "U-16b": ("เติมผลที่กฎไม่ได้เขียน",
              "ตอบว่าเพิกถอนใบอนุญาตได้ทันที แต่ข้อ 66 ให้อำนาจแค่"
              "พักใช้ใบอนุญาตไว้ก่อนระหว่างสอบสวน"),
    "U-18a": ("นับเวลาจากวันผิด",
              "ตอบว่านับห้าปีจากวันถูกเพิกถอน แต่ข้อ 28 นับจาก"
              "วันที่รับทราบคำสั่ง"),
    "U-19b": ("เติมผลที่กฎไม่ได้เขียน",
              "ตอบว่าถ้าไม่แก้ไขคำร้อง คุรุสภาจะไม่รับเรื่อง แต่ข้อ 8 เขียนแค่ว่า"
              "ให้ส่งเลขาธิการเสนอกรรมการพิจารณา"),
    "U-22b": ("บอกตัวบุคคลและกำหนดเวลาผิด",
              "ตอบว่าประธานอนุกรรมการสอบสวนเป็นผู้แจ้งและต้องแจ้งภายใน 15 วัน "
              "แต่ข้อ 34 ระบุประธานกรรมการ และข้อ 20 เขียนว่าแจ้งโดยไม่ชักช้า "
              "ไม่ได้กำหนด 15 วัน"),
    "U-23b": ("บอกจังหวะเวลาผิด",
              "ตอบว่ายื่นคำชี้แจงเพิ่มได้ตอนสอบสวนยังไม่เสร็จ แต่ข้อ 39 "
              "ให้ยื่นเมื่อสอบสวนเสร็จแล้ว"),
    "U-24a": ("เติมผลที่กฎไม่ได้เขียน",
              "เติมท้ายคำตอบว่าถ้าไม่ยื่นถือว่าไม่ประสงค์จะชี้แจง "
              "ซึ่งมาตรา 53 และข้อ 34 ไม่ได้เขียนผลอย่างนี้ไว้"),
    "U-24b": ("เติมผลที่กฎไม่ได้เขียน",
              "เติมท้ายคำตอบว่าไม่ยื่นภายใน 15 วันถือว่าไม่ประสงค์จะชี้แจง "
              "ซึ่งข้อ 34 ไม่ได้เขียนผลอย่างนี้ไว้"),
    "U-27b": ("ยกกฎที่พูดเรื่องอื่นมาตอบ",
              "อ้างข้อ 3 ของฉบับ 2556 ว่าเป็นกรอบกำหนดพฤติกรรมผิดจรรยาบรรณ "
              "แต่ข้อ 3 เป็นเรื่องยกเลิกฉบับเก่า"),
    "U-29b": ("ตอบกลับความหมายของกฎ",
              "ตัวบทห้ามการไม่แสวงหาความรู้ แต่ตอบกลับด้านเป็น "
              "ต้องไม่แสวงหาความรู้ ซึ่งหมายความตรงข้ามกัน"),
}


def header(sheet, names: list[str]) -> None:
    sheet.append(names)
    for cell in sheet[1]:
        cell.font, cell.fill, cell.alignment = HEAD, HEAD_FILL, WRAP
    sheet.freeze_panes = "A2"


def verdict_of(marks: list[int]) -> str:
    right = sum(1 for m in marks if m in CORRECT)
    if not marks:
        return "ยังไม่ได้ตรวจ"
    if right == len(marks):
        return "ตอบถูก"
    if right == 0:
        return "ตอบผิด"
    return f"ผู้ตรวจเห็นไม่ตรงกัน ({right} ใน {len(marks)} คนว่าถูก)"


def notes_for(row_id: str, codes: dict[int, dict]) -> str:
    out = []
    for n in sorted(codes):
        entry = codes[n].get(row_id)
        if entry and entry["code"] not in CORRECT and entry.get("note"):
            out.append(f"ผู้ตรวจคนที่ {n}: {entry['note']}")
    return "\n".join(out)


def sheet_readme(book, round_no: int) -> None:
    codes = coding(round_no)
    ids = sorted(next(iter(codes.values())))
    per = {n: sum(1 for i in ids if codes[n][i]["code"] in CORRECT)
           for n in sorted(codes)}
    total = sum(per.values())
    tests = len(ids) * len(per)
    unanimous_wrong = [i for i in ids
                       if all(codes[n][i]["code"] not in CORRECT for n in codes)]

    sheet = book.create_sheet("อ่านก่อน")
    lines = [
        ("ผลการทดสอบแชทบอทตอบคำถามจรรยาบรรณวิชาชีพครู "
         f"รอบที่ {round_no}", True),
        ("", False),
        ("ทดสอบอะไร", True),
        (f"ตั้งคำถามกับแชทบอท {len(ids)} คำถาม เก็บคำตอบไว้ "
         "แล้วให้คนอ่าน 3 คนตรวจทีละคำตอบว่าตรงกับตัวบทกฎหมายจริงหรือไม่ "
         "ทั้งสามคนอ่านคำตอบชุดเดียวกัน จึงเทียบกันได้", False),
        ("", False),
        ("ผลออกมาอย่างไร", True),
    ]
    for n, right in per.items():
        pct = right / len(ids) * 100
        lines.append((f"ผู้ตรวจคนที่ {n} เห็นว่าตอบถูก {right} จาก {len(ids)} "
                      f"คำถาม คิดเป็น {pct:.2f}% "
                      f"({'ถึงเกณฑ์' if pct >= 80 else 'ยังไม่ถึงเกณฑ์'})", False))
    lines += [
        (f"รวมทั้งสามคน ตอบถูก {total} จาก {tests} ครั้งที่ตรวจ "
         f"คิดเป็น {total / tests * 100:.2f}%", False),
        ("", False),
        ("เกณฑ์ที่ตั้งไว้", True),
        ("ผู้ตรวจ ทุกคน ต้องเห็นว่าตอบถูกไม่น้อยกว่า 80% "
         "ไม่ใช่ดูค่าเฉลี่ยของสามคนรวมกัน", False),
        ("", False),
        ("ยังเหลืออะไร", True),
        (f"มี {len(unanimous_wrong)} คำถามที่ผู้ตรวจทั้งสามคนเห็นตรงกันว่า"
         f"ตอบผิด คือ {', '.join(unanimous_wrong)} "
         "ดูรายละเอียดที่แผ่น ข้อที่ยังตอบผิด", False),
        ("", False),
        ("ในไฟล์นี้มีอะไร", True),
        ("แผ่น ผลรวม — ตัวเลขสรุปทั้งหมด", False),
        (f"แผ่น รายคำถาม — ทั้ง {len(ids)} คำถาม คำตอบเต็ม และผลตรวจ", False),
        ("แผ่น ข้อที่ยังตอบผิด — เฉพาะข้อที่มีคนเห็นว่าผิด พร้อมเหตุผล", False),
        ("แผ่น กฎหมายที่ใช้ตอบ — แชทบอทอ่านกฎหมายฉบับไหนมาตอบ", False),
        ("", False),
        ("หมายเหตุ", True),
        ("ไฟล์นี้เป็นฉบับอ่านง่าย ตัวเลขทุกตัวมาจากไฟล์ผลตรวจชุดเดียวกับ"
         "ฉบับที่ใช้อ้างในเล่ม ต่างกันแค่คำที่ใช้เรียก", False),
    ]
    for text, bold in lines:
        sheet.append([text])
        if bold:
            sheet.cell(sheet.max_row, 1).font = BIG
        sheet.cell(sheet.max_row, 1).alignment = Alignment(wrap_text=True,
                                                           vertical="top")
    widths(sheet, {"A": 105})


def sheet_totals(book, round_no: int) -> None:
    answers = {r["id"]: r for r in
               load(os.path.join(EVAL, f"user_answers_round{round_no}.json"))}
    codes = coding(round_no)
    ids = sorted(next(iter(codes.values())))
    sheet = book.create_sheet("ผลรวม")

    header(sheet, ["ผู้ตรวจ", "จำนวนคำถาม", "เห็นว่าตอบถูก", "เห็นว่าตอบผิด",
                   "ตอบถูกกี่เปอร์เซ็นต์", "ถึงเกณฑ์ 80% หรือยัง"])
    total = 0
    for n in sorted(codes):
        right = sum(1 for i in ids if codes[n][i]["code"] in CORRECT)
        total += right
        pct = right / len(ids) * 100
        sheet.append([f"คนที่ {n}", len(ids), right, len(ids) - right,
                      round(pct, 2), "ถึงแล้ว" if pct >= 80 else "ยังไม่ถึง"])
        for cell in sheet[sheet.max_row]:
            cell.fill = RIGHT_FILL if pct >= 80 else WRONG_FILL
    tests = len(ids) * len(codes)
    sheet.append(["รวมสามคน",
                  f"{len(ids)} คำถาม x {len(codes)} คน = {tests} ครั้ง",
                  total, tests - total, round(total / tests * 100, 2),
                  "ถึงแล้ว" if total / tests >= 0.8 else "ยังไม่ถึง"])
    for cell in sheet[sheet.max_row]:
        cell.font = Font(bold=True)

    sheet.append([])
    sheet.append(["แยกตามวิธีถาม"])
    sheet.cell(sheet.max_row, 1).font = BIG
    # the counts here are checks, not questions: three people read every
    # question, so thirty questions are ninety judgements. Naming both columns
    # keeps the reader from reading 82 as "82 of 30".
    sheet.append(["วิธีถาม", "จำนวนคำถาม", "จำนวนครั้งที่ตรวจ (คำถาม x 3 คน)",
                  "ตรวจแล้วว่าถูก", "ตรวจแล้วว่าผิด", "ตอบถูกกี่เปอร์เซ็นต์"])
    for cell in sheet[sheet.max_row]:
        cell.font = Font(bold=True)
        cell.alignment = WRAP
    for raw, plain in PHRASING.items():
        group = [i for i in ids if answers[i]["phrasing"] == raw]
        checks = len(group) * len(codes)
        right = sum(1 for i in group for n in codes
                    if codes[n][i]["code"] in CORRECT)
        sheet.append([plain, len(group), checks, right, checks - right,
                      round(right / checks * 100, 2)])

    sheet.append([])
    sheet.append(["ผู้ตรวจเห็นตรงกันแค่ไหน"])
    sheet.cell(sheet.max_row, 1).font = BIG
    agreed = [i for i in ids
              if len({codes[n][i]["code"] in CORRECT for n in codes}) == 1]
    sheet.append(["ตัดสินเหมือนกันทั้งสามคน", f"{len(agreed)} จาก {len(ids)} คำถาม"])
    disputed = [i for i in ids if i not in agreed]
    sheet.append(["ตัดสินไม่เหมือนกัน", ", ".join(disputed) or "ไม่มี"])
    wrong_all = [i for i in ids
                 if all(codes[n][i]["code"] not in CORRECT for n in codes)]
    sheet.append(["ทั้งสามคนว่าตอบผิด", ", ".join(wrong_all) or "ไม่มี"])
    widths(sheet, {"A": 34, "B": 14, "C": 16, "D": 16, "E": 22, "F": 22})


def sheet_questions(book, round_no: int) -> None:
    answers = {r["id"]: r for r in
               load(os.path.join(EVAL, f"user_answers_round{round_no}.json"))}
    codes = coding(round_no)
    sheet = book.create_sheet("รายคำถาม")
    header(sheet, ["ลำดับ", "รหัส", "เรื่องที่ถาม", "วิธีถาม", "คำถาม",
                   "คำตอบของแชทบอท", "แชทบอทอ้างกฎข้อไหน", "ผลตรวจ",
                   "ผิดเรื่องอะไร", "ผู้ตรวจบันทึกไว้ว่า"])
    for order, (row_id, a) in enumerate(answers.items(), start=1):
        marks = [codes[n][row_id]["code"] for n in sorted(codes)
                 if row_id in codes[n]]
        verdict = verdict_of(marks)
        kind, why = PLAIN_FAULT.get(row_id, ("", ""))
        sheet.append([order, row_id, a["category"],
                      PHRASING.get(a["phrasing"], a["phrasing"]),
                      a["question"], a["answer"],
                      "\n".join(cited(a["answer"])), verdict,
                      f"{kind}\n{why}".strip(), notes_for(row_id, codes)])
        fill = (RIGHT_FILL if verdict == "ตอบถูก" else
                WRONG_FILL if verdict == "ตอบผิด" else
                SPLIT_FILL if marks else None)
        for cell in sheet[sheet.max_row]:
            cell.alignment = WRAP
            if fill:
                cell.fill = fill
        sheet.row_dimensions[sheet.max_row].height = 120
    widths(sheet, {"A": 8, "B": 10, "C": 24, "D": 24, "E": 40, "F": 70,
                   "G": 20, "H": 26, "I": 46, "J": 50})


def sheet_failures(book, round_no: int) -> None:
    answers = {r["id"]: r for r in
               load(os.path.join(EVAL, f"user_answers_round{round_no}.json"))}
    codes = coding(round_no)
    sheet = book.create_sheet("ข้อที่ยังตอบผิด")
    header(sheet, ["รหัส", "คำถาม", "กี่คนว่าผิด", "ผิดแบบไหน",
                   "ผิดอย่างไร", "ผู้ตรวจบันทึกไว้ว่า"])
    rows = [i for i in answers
            if any(codes[n][i]["code"] not in CORRECT
                   for n in codes if i in codes[n])]
    for row_id in sorted(rows):
        wrong = sum(1 for n in codes if codes[n][row_id]["code"] not in CORRECT)
        kind, why = PLAIN_FAULT.get(row_id, ("", ""))
        sheet.append([row_id, answers[row_id]["question"],
                      f"{wrong} จาก {len(codes)} คน", kind, why,
                      notes_for(row_id, codes)])
        for cell in sheet[sheet.max_row]:
            cell.alignment = WRAP
            cell.fill = WRONG_FILL if wrong == len(codes) else SPLIT_FILL
        sheet.row_dimensions[sheet.max_row].height = 90
    sheet.append([])
    sheet.append([f"รวม {len(rows)} คำถามที่มีผู้ตรวจอย่างน้อยหนึ่งคนเห็นว่าผิด "
                  "ช่องสีแดงคือทั้งสามคนเห็นตรงกันว่าผิด "
                  "ช่องสีเหลืองคือเห็นไม่ตรงกัน"])
    widths(sheet, {"A": 10, "B": 40, "C": 16, "D": 28, "E": 60, "F": 60})


def sheet_laws(book) -> None:
    import json
    from ingest.export_results import CORPUS
    with open(CORPUS, encoding="utf-8") as fh:
        recs = [json.loads(line) for line in fh if line.strip()]
    # What each instrument is for, in one phrase, matched on its title. Ordered
    # most specific first and checked in that order: "จรรยาบรรณของวิชาชีพ" is
    # inside almost every title here -- "ว่าด้วยการพิจารณาการประพฤติผิด
    # จรรยาบรรณของวิชาชีพ" contains it too -- so an unordered lookup labelled all
    # ten as the five duties. The five-duty pattern is anchored on
    # "ว่าด้วยจรรยาบรรณ", which only its own title has.
    ABOUT = (
        ("คณะอนุกรรมการอุทธรณ์", "วิธีตั้งคณะอนุกรรมการที่พิจารณาอุทธรณ์"),
        ("แบบแผนพฤติกรรม", "ขยายว่าแต่ละด้านทำอะไรได้ ทำอะไรไม่ได้ "
                           "แยกตามวิชาชีพสี่ประเภท"),
        ("การพิจารณาการประพฤติผิด",
         "ขั้นตอนเมื่อมีคนร้องเรียนว่าครูผิดจรรยาบรรณ และโทษที่ได้รับ"),
        ("การอุทธรณ์คำวินิจฉัย", "ขั้นตอนอุทธรณ์เมื่อไม่เห็นด้วยกับคำวินิจฉัย"),
        ("ว่าด้วยจรรยาบรรณ", "หลักจรรยาบรรณ 5 ด้านที่ครูต้องถือปฏิบัติ"),
        ("พระราชบัญญัติสภาครู",
         "กฎหมายแม่บท ตั้งคุรุสภา สั่งให้มีจรรยาบรรณ 5 ด้าน และกำหนดโทษ"),
    )
    sheet = book.create_sheet("กฎหมายที่ใช้ตอบ")
    header(sheet, ["ชื่อกฎหมาย", "เรื่องอะไร", "แบ่งได้กี่ข้อ",
                   "ประกาศเมื่อ", "ยังใช้อยู่ไหม", "ลิงก์ต้นฉบับ"])
    groups: dict[str, list[dict]] = {}
    for r in recs:
        groups.setdefault(r["act_full"], []).append(r)
    unnamed = []
    for name, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        about = next((v for pattern, v in ABOUT if pattern in name), "")
        if not about:
            unnamed.append(name)
        if "(ฉบับที่" in name:
            about += " (ฉบับแก้ไขเพิ่มเติม)"
        repealed = sum(1 for r in rows if r.get("superseded_by"))
        sheet.append([name, about, len(rows), rows[0].get("published", ""),
                      "ถูกยกเลิกแล้ว" if repealed == len(rows) else "ใช้อยู่",
                      rows[0].get("source_url", "")])
        for cell in sheet[sheet.max_row]:
            cell.alignment = WRAP
    if unnamed:
        # shipping a blank here reads as "this one does not matter"; a wrong
        # label is worse. Stop and add the phrase.
        raise SystemExit("no plain description for: " + ", ".join(unnamed))
    sheet.append([])
    sheet.append([f"รวม {len(groups)} ฉบับ แบ่งเป็น {len(recs)} ชิ้น "
                  "แชทบอทค้นจากชิ้นเหล่านี้แล้วยกมาตอบ "
                  "ฉบับที่ถูกยกเลิกยังเก็บไว้เพราะฉบับใหม่อ้างถึงเรื่องที่"
                  "เริ่มดำเนินการไว้ตามฉบับเดิม แต่ระบบติดป้ายกำกับไว้"])
    widths(sheet, {"A": 62, "B": 42, "C": 14, "D": 14, "E": 16, "F": 46})


def main() -> None:
    round_no = int(sys.argv[1]) if len(sys.argv) > 1 else max(rounds_available())
    book = Workbook()
    book.remove(book.active)
    sheet_readme(book, round_no)
    sheet_totals(book, round_no)
    sheet_questions(book, round_no)
    sheet_failures(book, round_no)
    sheet_laws(book)
    path = os.path.join(EVAL, f"ผลการทดสอบแชทบอท รอบ {round_no} "
                              f"(ฉบับอ่านง่าย).xlsx")
    book.save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
