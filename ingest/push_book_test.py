# -*- coding: utf-8 -*-
"""Write the chatbot test sheet into a Google Sheet.

    GOOGLE_SERVICE_ACCOUNT=/path/to/key.json \\
        .venv/bin/python -m ingest.push_book_test <spreadsheet id>

The same table ingest.export_book_test writes to a workbook, put straight into
the owner's sheet. The sheet has to be shared with the service account's e-mail
as an editor; the key file stays outside this repository, which is public.

Tabs already in the sheet are left alone. The two tabs written here are
replaced whole on every run, score columns included: a score typed into the
sheet by hand is lost, so scores belong in data/eval/network_test_scores.json,
from where they are copied in. Without that file the columns are left empty.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from ingest.export_book_test import NOTE_HEAD, RUBRIC, chapter_of, load, scored, scores

API = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPE = "https://www.googleapis.com/auth/spreadsheets"
TITLE = "แบบทดสอบแชทบอทเครือข่ายคอมพิวเตอร์เบื้องต้น"
INSIDE, OUTSIDE = "คำถามจากหนังสือ", "คำถามนอกหนังสือ"
HEADS = ["บทที่", "คำถามที่ใช้", "คำตอบที่ได้", "ประเมินความถูกต้อง", "ประเมิน RAG"]
PINK = {"red": 0.957, "green": 0.780, "blue": 0.765}
GREEN = {"red": 0.851, "green": 0.918, "blue": 0.827}
TEAL = {"red": 0.788, "green": 0.867, "blue": 0.878}
WIDTHS = {0: 60, 1: 330, 2: 640, 3: 150, 4: 110, 5: 320, 6: 170, 7: 130, 8: 150, 10: 160,
          11: 60, 12: 380, 13: 70}


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def token(key_path: str) -> str:
    """An access token for the service account, signed with openssl so that no
    package has to be installed for one request."""
    with open(key_path, encoding="utf-8") as handle:
        key = json.load(handle)
    now = int(time.time())
    claim = {"iss": key["client_email"], "scope": SCOPE, "aud": key["token_uri"],
             "iat": now, "exp": now + 900}
    unsigned = (b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + "."
                + b64(json.dumps(claim).encode()))
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as body:
        body.write(unsigned)
        body.flush()
        signed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", "/dev/stdin", body.name],
            input=key["private_key"].encode(), capture_output=True)
    if signed.returncode:
        raise SystemExit("เซ็น token ไม่ได้: " + signed.stderr.decode()[:200])
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": unsigned + "." + b64(signed.stdout)}).encode()
    with urllib.request.urlopen(urllib.request.Request(key["token_uri"], data=data),
                                timeout=30) as response:
        return json.load(response)["access_token"]


class Sheet:
    def __init__(self, sheet_id: str, access: str):
        self.url, self.access = f"{API}/{sheet_id}", access

    def call(self, path: str, body: dict | None = None, method: str | None = None):
        request = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.access}",
                     "Content-Type": "application/json"},
            method=method or ("POST" if body is not None else "GET"))
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"Google ตอบ {exc.code} ที่ {path[:60]}: "
                             f"{exc.read().decode()[:300]}")


def values(rows: list[dict]) -> list[list]:
    last = len(rows) + 1
    given = scores()
    grid = [HEADS + [NOTE_HEAD if given else "", "", "คำถามตรง ตอบตรง",
                     "คำถามตรง ตอบไม่ตรง", "", "", "ระดับ", "เกณฑ์", "คะแนน"]]
    for row in rows:
        match, rag, note = scored(row, given)
        grid.append([chapter_of(row), row["question"], row["answer"], match, rag, note])
    side = [["", "ประเมินค่าความถูกต้อง", f"=COUNTIF(D2:D{last},1)",
             f"=COUNTIF(D2:D{last},0)", "", "ประเมิน RAG and LLM"]]
    side += [[""] * 6 for _ in RUBRIC[1:]]
    for at, (level, wording) in enumerate(RUBRIC):
        while len(grid) <= at + 1:
            grid.append([""] * 6)
        grid[at + 1] = (grid[at + 1] + [""] * 6)[:6] + side[at][1:] + [level, wording, level]
    return grid


def fill(tab: int, r0: int, r1: int, c0: int, c1: int, colour: dict, bold=False) -> dict:
    cell = {"backgroundColor": colour, "textFormat": {"bold": bold}}
    return {"repeatCell": {
        "range": {"sheetId": tab, "startRowIndex": r0, "endRowIndex": r1,
                  "startColumnIndex": c0, "endColumnIndex": c1},
        "cell": {"userEnteredFormat": cell},
        "fields": "userEnteredFormat(backgroundColor,textFormat.bold)"}}


def choice(tab: int, last: int, column: int, allowed: list[str]) -> dict:
    return {"setDataValidation": {
        "range": {"sheetId": tab, "startRowIndex": 1, "endRowIndex": last,
                  "startColumnIndex": column, "endColumnIndex": column + 1},
        "rule": {"condition": {"type": "ONE_OF_LIST",
                               "values": [{"userEnteredValue": v} for v in allowed]},
                 "strict": True, "showCustomUi": True}}}


def layout(tab: int, last: int) -> list[dict]:
    out = [fill(tab, 0, 1, 0, 3, {"red": 1, "green": 1, "blue": 1}, bold=True),
           fill(tab, 0, last, 3, 4, PINK), fill(tab, 0, last, 4, 5, GREEN),
           fill(tab, 0, 2, 7, 9, PINK), fill(tab, 1, 2, 6, 7, PINK),
           fill(tab, 1, 2, 10, 11, TEAL), fill(tab, 0, 1 + len(RUBRIC), 11, 14, TEAL),
           choice(tab, last, 3, ["0", "1"]), choice(tab, last, 4, ["0", "1", "2"]),
           {"repeatCell": {
               "range": {"sheetId": tab, "startRowIndex": 0, "endRowIndex": last,
                         "startColumnIndex": 0, "endColumnIndex": 6},
               "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                              "verticalAlignment": "TOP"}},
               "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
           {"updateSheetProperties": {
               "properties": {"sheetId": tab, "gridProperties": {"frozenRowCount": 1}},
               "fields": "gridProperties.frozenRowCount"}}]
    for column, width in WIDTHS.items():
        out.append({"updateDimensionProperties": {
            "range": {"sheetId": tab, "dimension": "COLUMNS",
                      "startIndex": column, "endIndex": column + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})
    return out


def main() -> None:
    key_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if len(sys.argv) != 2 or not key_path or not os.path.exists(key_path):
        raise SystemExit("ใช้: GOOGLE_SERVICE_ACCOUNT=<key.json> "
                         "python -m ingest.push_book_test <spreadsheet id>")
    rows = load()
    inside = sorted((r for r in rows if r["group"] == "book"),
                    key=lambda r: chapter_of(r) or 99)
    outside = [r for r in rows if r["group"] != "book"]

    sheet = Sheet(sys.argv[1], token(key_path))
    meta = sheet.call("?fields=properties.title,sheets.properties(sheetId,title)")
    have = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    setup = [{"updateSpreadsheetProperties": {"properties": {"title": TITLE},
                                              "fields": "title"}}]
    setup += [{"deleteSheet": {"sheetId": have[name]}}
              for name in (INSIDE, OUTSIDE) if name in have]
    setup += [{"addSheet": {"properties": {"title": name, "index": at}}}
              for at, name in enumerate((INSIDE, OUTSIDE))]
    made = sheet.call(":batchUpdate", {"requests": setup})["replies"]
    tabs = [r["addSheet"]["properties"]["sheetId"] for r in made if "addSheet" in r]

    sheet.call("/values:batchUpdate", {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": f"'{name}'!A1", "values": values(part)}
                 for name, part in ((INSIDE, inside), (OUTSIDE, outside))]})
    sheet.call(":batchUpdate", {"requests": layout(tabs[0], len(inside) + 1)
                                + layout(tabs[1], len(outside) + 1)})
    print(f"{meta['properties']['title']!r} -> {TITLE!r}")
    print(f"{INSIDE}: {len(inside)} ข้อ, {OUTSIDE}: {len(outside)} ข้อ; "
          f"แท็บเดิมที่ไม่ได้แตะ: {[n for n in have if n not in (INSIDE, OUTSIDE)]}")


if __name__ == "__main__":
    main()
