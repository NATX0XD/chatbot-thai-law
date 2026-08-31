# -*- coding: utf-8 -*-
"""Build a consolidated พ.ร.บ.คอมพิวเตอร์ from the 2550 act and its 2560 amendment.

Why this file exists at all. Neither iapp/rag_thai_laws nor pythainlp/thailaw
contains this Act -- checked across all 42,755 documents -- and krisdika.go.th,
which publishes the consolidated "ฉบับ Update" of every Act, does not resolve from
this machine. What is reachable is Thai Wikisource, which carries both the 2550
Act and the 2560 amending Act transcribed from the Royal Gazette and marked as
proofread, under public domain terms (Copyright Act B.E. 2537 s.7).

The catch is that an amending Act is not readable law. Its sections say things
like "ให้ยกเลิกความในมาตรา ๑๔ ... และให้ใช้ความต่อไปนี้แทน". Indexing it as-is would
answer "โพสต์ข้อมูลเท็จผิดไหม" with an instruction to repeal a section. Indexing the
2550 Act as-is is worse: มาตรา ๑๔, the most-cited section of the whole Act, was
rewritten in 2560, so the bot would state a penalty that no longer applies.

So the two are merged here, and every operation is printed. Four kinds appear:

    replace section    ยกเลิกความในมาตรา N ... และให้ใช้ความต่อไปนี้แทน
    add section        เพิ่มความต่อไปนี้เป็นมาตรา N/1
    append paragraphs  เพิ่มความต่อไปนี้เป็นวรรคสองและวรรคสามของมาตรา N
    replace paragraph  ยกเลิกความในวรรคสองของมาตรา N ... และให้ใช้ความต่อไปนี้แทน

The last one is the only place a judgement is made: the base section is split on
line breaks and the numbered paragraph is swapped. It applies to exactly two
sections, 21 and 26, and both are printed in full by `main()` so the result can be
read against the Gazette rather than trusted.

    python -m ingest.extract_computer_act          # parse and print an audit
    python -m ingest.extract_computer_act --fetch  # re-download from Wikisource
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import RAW_DIR  # noqa: E402
from app.thai_law import clean, to_arabic  # noqa: E402
from ingest.extract_acts import chunk  # noqa: E402

ACT = "พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ พ.ศ. 2550"
ACT_FULL = f"{ACT} (แก้ไขเพิ่มเติมโดยฉบับที่ 2 พ.ศ. 2560)"
SYSID = "act-computer-crime"

WIKISOURCE = "https://th.wikisource.org/w/api.php"
PAGES = {
    "computer_act_2550.txt":
        "พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ พ.ศ. 2550",
    "computer_act_2560.txt":
        "พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ (ฉบับที่ 2) พ.ศ. 2560",
}

# the transcription puts the section number on its own line: "มาตรา\n๑๔\nผู้ใด..."
SECTION_RE = re.compile(r"(?m)^มาตรา\s*\n\s*([๐-๙0-9]+(?:/[๐-๙0-9]+)?)\s*\n")
# ...while quoted replacement text keeps it inline: '"มาตรา ๑๔ ผู้ใด...'
QUOTED_SECTION_RE = re.compile(r'(?m)^"?มาตรา\s+([๐-๙0-9]+(?:/[๐-๙0-9]+)?)\s+')

ORDINALS = {"หนึ่ง": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5}


# ------------------------------------------------------------------ fetching

def fetch() -> None:
    """Pull both Acts from Wikisource and store the rendered text verbatim."""
    os.makedirs(RAW_DIR, exist_ok=True)
    for filename, title in PAGES.items():
        query = urllib.parse.urlencode(
            {"action": "parse", "page": title, "prop": "text", "format": "json"})
        # Wikimedia rejects the default urllib agent with 403; their policy asks
        # for a descriptive one that identifies the tool
        request = urllib.request.Request(
            f"{WIKISOURCE}?{query}",
            headers={"User-Agent": "thai-law-bot/1.0 (KMUTNB student project; "
                                   "statute ingest; contact via GitHub NATX0XD)"})
        with urllib.request.urlopen(request, timeout=60) as resp:
            payload = json.load(resp)
        html = payload["parse"]["text"]["*"]
        html = re.sub(r"(?is)<(script|style|table)[^>]*>.*?</\1>", " ", html)
        text = re.sub(r"<[^>]+>", "\n", html)
        for entity, char in (("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"),
                             ("&gt;", ">"), ("&#160;", " "), ("&nbsp;", " ")):
            text = text.replace(entity, char)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        path = os.path.join(RAW_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"-> {path} ({len(text):,} ตัวอักษร)")


def _read(filename: str) -> str:
    path = os.path.join(RAW_DIR, filename)
    if not os.path.exists(path):
        sys.exit(f"ไม่พบ {path} -- รัน: python -m ingest.extract_computer_act --fetch")
    with open(path, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ parsing

def parse_sections(text: str, pattern: re.Pattern = SECTION_RE,
                   drop_quotes: bool = False) -> dict[str, str]:
    """Split a statute into {section number: body}, in document order.

    `drop_quotes` is for the quoted text inside an amending section, where the
    closing quote belongs to the container rather than to the section. It must
    stay off for the outer parse: the instruction body keeps its quote, and that
    is how _payload finds where the replacement text begins.
    """
    out: dict[str, str] = {}
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if drop_quotes:
            body = body.strip('"').strip()
        no = to_arabic(m.group(1))
        if body and no not in out:
            out[no] = body
    return out


def _payload(body: str) -> str:
    """The quoted text an amending section introduces, without its quotes."""
    first = body.find('"')
    if first == -1:
        return ""
    return body[first + 1:].strip().rstrip('"').strip()


def parse_amendments(text_2560: str) -> list[tuple]:
    """Turn the amending Act into a list of (kind, section, arg, text)."""
    ops: list[tuple] = []
    for _, body in parse_sections(text_2560).items():
        head = body.split("\n", 1)[0]
        payload = _payload(body)
        if not payload:
            continue

        m = re.search(r"ยกเลิกความใน(วรรค\S+)ของมาตรา\s+([๐-๙0-9/]+)", head)
        if m:
            ordinal = ORDINALS.get(m.group(1).replace("วรรค", "", 1))
            if ordinal is None:
                raise ValueError(f"ไม่รู้จักลำดับวรรค {m.group(1)!r} ของมาตรา {m.group(2)}")
            ops.append(("replace_paragraph", to_arabic(m.group(2)),
                        ordinal, payload))
            continue

        m = re.search(r"เพิ่มความต่อไปนี้เป็นวรรค.*?ของมาตรา\s+([๐-๙0-9/]+)", head)
        if m:
            ops.append(("append_paragraphs", to_arabic(m.group(1)), None, payload))
            continue

        # both "ยกเลิกความในมาตรา N ... แทน" and "เพิ่มความ ... เป็นมาตรา N" carry
        # their result as one or more full sections inside the quoted payload,
        # so the payload itself says which sections it defines
        if "มาตรา" in head:
            for no, text in parse_sections(payload, QUOTED_SECTION_RE,
                                           drop_quotes=True).items():
                ops.append(("set_section", no, None, text))
    return ops


def consolidate(verbose: bool = False) -> dict[str, str]:
    """Apply the 2560 amendment to the 2550 Act."""
    base = parse_sections(_read("computer_act_2550.txt"))
    ops = parse_amendments(_read("computer_act_2560.txt"))

    for kind, no, arg, text in ops:
        if kind == "set_section":
            action = "แทนที่" if no in base else "เพิ่มใหม่"
            base[no] = text
        elif kind == "append_paragraphs":
            action = "ต่อท้าย"
            base[no] = base.get(no, "") + "\n" + text
        elif kind == "replace_paragraph":
            action = f"แทนวรรคที่ {arg}"
            paragraphs = base.get(no, "").split("\n")
            index = arg - 1
            # the replacement repeats the section heading; drop it so the body
            # reads the same way every other paragraph does
            replacement = QUOTED_SECTION_RE.sub("", text, count=1).strip()
            if 0 <= index < len(paragraphs):
                paragraphs[index] = replacement
            else:
                paragraphs.append(replacement)
                action += " (ไม่พบวรรคเดิม จึงต่อท้าย)"
            base[no] = "\n".join(paragraphs)
        if verbose:
            print(f"  {action:<28} มาตรา {no}")

    return dict(sorted(base.items(), key=lambda kv: [
        int(p) for p in kv[0].split("/")]))


# ------------------------------------------------------------------ records

def records():
    """Corpus records, in the same schema as every other act."""
    for no, body in consolidate().items():
        text = clean(body)
        if len(text) < 20:
            continue
        for piece, part in chunk(text):
            yield {
                "id": f"{SYSID}-{no}" + (f"-{part}" if part else ""),
                "act": ACT,
                "act_full": ACT_FULL,
                "sysid": SYSID,
                "section": no,
                "part": part,
                "text": piece,
                "chapters": ["หมวด 1 ความผิดเกี่ยวกับคอมพิวเตอร์",
                             "หมวด 2 พนักงานเจ้าหน้าที่"],
                "n_chars": len(piece),
            }


def write_computer_act(handle) -> int:
    """Append the consolidated Act to an open corpus file. Returns chunk count."""
    if not os.path.exists(os.path.join(RAW_DIR, "computer_act_2550.txt")):
        print("ข้าม พ.ร.บ.คอมพิวเตอร์: ไม่พบไฟล์ต้นฉบับ "
              "(รัน python -m ingest.extract_computer_act --fetch)")
        return 0
    written = 0
    for rec in records():
        handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written += 1
    print(f"{ACT}: {written:,} ชิ้น")
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="re-download from Wikisource")
    args = ap.parse_args()
    if args.fetch:
        fetch()
        return

    print("การแก้ไขที่ใช้จากฉบับที่ 2 พ.ศ. 2560")
    merged = consolidate(verbose=True)
    print(f"\nรวม {len(merged)} มาตรา: {', '.join(list(merged)[:40])}")
    for no in ("14", "21", "26"):
        if no in merged:
            print(f"\n--- มาตรา {no} หลังรวม ---\n{clean(merged[no])[:700]}")


if __name__ == "__main__":
    main()
