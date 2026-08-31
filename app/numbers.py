# -*- coding: utf-8 -*-
"""Check the figures in an answer against the sections it was written from.

The dangerous failures in a legal bot are numeric. An answer can name the right
act, cite a real section, read fluently, and still say the wrong number of days
or the wrong amount of money -- and a number is exactly what the reader acts on.
Adversarial testing produced "เงินทดแทนกรณีว่างงานเดือนละ 1,000 บาท" attached to a
real section of พ.ร.บ.คุ้มครองแรงงาน; every name in that sentence was legitimate.

Checking this is possible without a model, because the answer and the statute
have to agree on a value that either appears in the source or does not. The only
obstacle is that they write it differently: the answer says "100,000 บาท" while
the statute says "หนึ่งแสนบาท", and section text uses Thai numerals throughout.
So the statute side is expanded into digits first, and then it is arithmetic.

Deliberately conservative. A figure is reported only when the source contains no
form of it at all; anything ambiguous is left alone. The point is to catch an
invented benefit, not to argue about rounding.
"""
from __future__ import annotations

import re

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

UNITS = {"ศูนย์": 0, "หนึ่ง": 1, "เอ็ด": 1, "สอง": 2, "ยี่": 2, "สาม": 3, "สี่": 4,
         "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9}
SCALES = {"สิบ": 10, "ร้อย": 100, "พัน": 1_000, "หมื่น": 10_000,
          "แสน": 100_000, "ล้าน": 1_000_000}

# a run of Thai number words, longest first so "ยี่สิบ" is not read as "ยี่"
_WORD = "|".join(sorted(list(UNITS) + list(SCALES), key=len, reverse=True))
NUMBER_WORDS = re.compile(f"(?:{_WORD})+")

# a figure worth checking: digits followed by a unit that carries legal meaning
FIGURE = re.compile(r"([\d][\d,\.]*)\s*(บาท|วัน|เดือน|ปี|ครั้ง|เท่า|คน|%|เปอร์เซ็นต์)")
PERCENT_WORD = re.compile(r"ร้อยละ\s*([\d][\d,\.]*)")


def words_to_int(text: str) -> int | None:
    """Read a run of Thai number words. Returns None if it does not parse.

    Handles the ordinary legal range: หนึ่งแสนบาท, สามสิบวัน, ยี่สิบเอ็ดปี,
    สองแสนห้าหมื่นบาท. Written iteratively rather than with a grammar because the
    forms that appear in statutes are few and the failure mode of a clever parser
    -- a confident wrong number -- is worse here than returning None.
    """
    total = 0        # everything already closed off by a large scale
    current = 0      # the group being built
    digit = None     # the unit waiting for its scale
    seen = False

    i = 0
    while i < len(text):
        for word, scale in SCALES.items():
            if text.startswith(word, i):
                if scale >= 1_000_000:
                    total = (total + current + (digit or 0)) * scale
                    current = 0
                else:
                    current += (digit if digit is not None else 1) * scale
                digit = None
                seen = True
                i += len(word)
                break
        else:
            for word, value in UNITS.items():
                if text.startswith(word, i):
                    if digit is not None:
                        current += digit
                    digit = value
                    seen = True
                    i += len(word)
                    break
            else:
                return None
    if not seen:
        return None
    return total + current + (digit or 0)


def expand(text: str) -> str:
    """Statute text with Thai numerals and Thai number words turned into digits.

    The digits are appended rather than substituted, so a section keeps both
    "สามสิบวัน" and "30" and matches an answer written either way.
    """
    text = text.translate(THAI_DIGITS)
    extra = []
    for m in NUMBER_WORDS.finditer(text):
        value = words_to_int(m.group(0))
        if value is not None:
            extra.append(str(value))
    return text + " " + " ".join(extra)


def _canonical(raw: str) -> str:
    """'100,000' and '100000.00' are the same figure."""
    value = raw.replace(",", "")
    if value.endswith(".0") or value.endswith(".00"):
        value = value.split(".")[0]
    return value


def unsupported_figures(answer: str, sections: list[str]) -> list[str]:
    """Figures stated in the answer that appear nowhere in the source sections."""
    haystack = expand(" ".join(sections))
    numbers = set(re.findall(r"\d[\d,\.]*", haystack))
    numbers = {_canonical(n) for n in numbers}

    bad = []
    for raw, unit in FIGURE.findall(answer.translate(THAI_DIGITS)):
        value = _canonical(raw)
        if value in numbers:
            continue
        # small counts are how prose is written -- "2 กรณี", "3 ปีขึ้นไป" -- and
        # flagging them would drown the real finding in noise
        if value.isdigit() and int(value) <= 3 and unit not in ("บาท", "%", "เปอร์เซ็นต์"):
            continue
        item = f"{raw} {unit}"
        if item not in bad:
            bad.append(item)
    for raw in PERCENT_WORD.findall(answer.translate(THAI_DIGITS)):
        if _canonical(raw) not in numbers:
            item = f"ร้อยละ {raw}"
            if item not in bad:
                bad.append(item)
    return bad
