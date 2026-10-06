# -*- coding: utf-8 -*-
"""Write one assessment round of the networking bot into the Google Sheet.

    .venv/bin/python -m ingest.assess_book score 1
    GOOGLE_SERVICE_ACCOUNT=/path/to/key.json \\
        .venv/bin/python -m ingest.push_book_assessment <spreadsheet id> 1

Adds (or replaces) the tab "ผลประเมินรอบ N": the confusion matrix of each of
the three assessors, then every question with its answer, the three codes and
what each assessor wrote. Every number is read from the assessors' coding
files through ingest.assess_book; nothing is typed in here.
"""
from __future__ import annotations

import os
import sys

from ingest.assess_book import LABELS, PASS_MARK, PER_FILE, answers, score
from ingest.plain_notes import packet_passages, plain
from ingest.push_book_test import GREEN, PINK, TEAL, Sheet, fill, token


def grid(round_no: int) -> tuple[list[list], int]:
    summary = score(round_no)
    rows = {row["id"]: row for row in answers(round_no)}
    out = [[f"ผลประเมินแชทบอทเครือข่าย รอบ {round_no} — คำถาม {summary['questions']} ข้อ "
            "ผู้ประเมินสามคนอ่านคำตอบชุดเดียวกัน (ผู้ประเมินเป็น AI agent)"],
           [],
           ["ผู้ประเมิน", "ถามตรง ตอบตรง (1)", "ถามตรง ตอบไม่ตรง (0)",
            "ถามกำกวม ตอบตรง (2)", "ถามกำกวม ตอบไม่ตรง (3)", "ตอบถูก (1+2)",
            "ค่าความถูกต้อง", f"ผ่านเกณฑ์ {PASS_MARK:.0%}"]]
    for one in summary["assessors"]:
        codes = one["codes"]
        out.append([f"คนที่ {one['assessor']}", codes["1"], codes["0"], codes["2"], codes["3"],
                    one["correct"], f"{one['accuracy']:.2%}",
                    "ผ่าน" if one["passed"] else "ไม่ผ่าน"])
    out.append(["รวมสามคน", "", "", "", "", sum(a["correct"] for a in summary["assessors"]),
                f"{summary['overall_accuracy']:.2%}",
                "ผ่านทุกคน" if summary["passed"] else "ไม่ผ่าน"])
    out.append([f"เห็นตรงกันทั้งสามคน {summary['all_three_agree']} จาก "
                f"{summary['questions']} ข้อ"])
    out.append([])
    head = len(out)
    out.append(["รหัสคำถาม", "บทที่", "ลักษณะคำถาม", "คำถาม", "คำตอบที่ได้",
                "คนที่ 1", "คนที่ 2", "คนที่ 3", "หมายเหตุคนที่ 1", "หมายเหตุคนที่ 2",
                "หมายเหตุคนที่ 3"])
    for at, item in enumerate(summary["items"]):
        row = rows[item["id"]]
        # a note names passages by their number in the packet the question was in
        passages = packet_passages(round_no, at // PER_FILE + 1)
        out.append([item["id"], row["chapter"], row["phrasing"], row["question"],
                    row["answer"], *item["codes"],
                    *(plain(note, passages) for note in item["notes"])])
    out += [[], ["ความหมายของรหัส"]] + [[code, LABELS[code]] for code in (1, 0, 2, 3)]
    return out, head


def main() -> None:
    key_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if len(sys.argv) != 3 or not key_path or not os.path.exists(key_path):
        raise SystemExit("ใช้: GOOGLE_SERVICE_ACCOUNT=<key.json> "
                         "python -m ingest.push_book_assessment <spreadsheet id> <รอบ>")
    round_no = int(sys.argv[2])
    name = f"ผลประเมินรอบ {round_no}"
    values, head = grid(round_no)
    sheet = Sheet(sys.argv[1], token(key_path))
    meta = sheet.call("?fields=sheets.properties(sheetId,title)")
    have = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    setup = [{"deleteSheet": {"sheetId": have[name]}}] if name in have else []
    setup.append({"addSheet": {"properties": {"title": name, "index": 0}}})
    made = sheet.call(":batchUpdate", {"requests": setup})["replies"]
    tab = next(r["addSheet"]["properties"]["sheetId"] for r in made if "addSheet" in r)
    sheet.call("/values:batchUpdate", {
        "valueInputOption": "RAW",
        "data": [{"range": f"'{name}'!A1", "values": values}]})
    last = head + 1 + len(answers(round_no))
    look = [fill(tab, 2, 3, 0, 8, TEAL, bold=True), fill(tab, 3, 7, 1, 2, GREEN),
            fill(tab, 3, 7, 3, 4, GREEN), fill(tab, 3, 7, 2, 3, PINK),
            fill(tab, 3, 7, 4, 5, PINK), fill(tab, head, head + 1, 0, 11, TEAL, bold=True),
            {"repeatCell": {
                "range": {"sheetId": tab, "startRowIndex": head, "endRowIndex": last,
                          "startColumnIndex": 0, "endColumnIndex": 11},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                               "verticalAlignment": "TOP"}},
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}}]
    for column, width in {0: 110, 1: 150, 2: 160, 3: 320, 4: 560, 5: 150, 6: 110, 7: 110,
                          8: 300, 9: 300, 10: 300}.items():
        look.append({"updateDimensionProperties": {
            "range": {"sheetId": tab, "dimension": "COLUMNS",
                      "startIndex": column, "endIndex": column + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})
    sheet.call(":batchUpdate", {"requests": look})
    print(f"-> แท็บ {name!r}")


if __name__ == "__main__":
    main()
