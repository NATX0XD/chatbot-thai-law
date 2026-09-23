# -*- coding: utf-8 -*-
"""Get correct Thai text out of the Teachers Council PDFs.

The ten documents in data/raw/ksp/ were published over twenty years by two
different offices, and they encode Thai four different ways. Reading them all
with one call to PyMuPDF gives text that *looks* fine at a glance and is quietly
missing every tone mark, which is worse than failing outright -- "ตอง" and
"ต้อง" tokenise differently, so the retriever would silently stop matching.

So extraction is a ladder, and every rung ends at the same set of checks:

  direct   The text layer is already correct. Only ข้อบังคับฯ 2556 is.
  pua      AngsanaUPC pushes the marks that sit above tall consonants into the
           Private Use Area. Five documents do this. Fixed by PUA_MAP, which
           was read off the documents themselves -- see the table below.
  legacy   พ.ร.บ.สภาครูฯ 2546 stores TIS-620 bytes behind a Mac Roman cmap, so
           "หน้า" arrives as "Àπâ“". Fixed by re-encoding through Mac Roman and
           decoding as cp874, plus LEGACY_EXTRA for the slots cp874 has no
           character for.
  ocr      Three documents use subset fonts whose cmap is bare glyph indices,
           and the subsets have their cmap table stripped, so nothing can
           recover the characters from the text layer. They have to be rendered
           and read back.

`check` is deliberately paranoid about the fourth rung. OCR can drop a tone mark
without leaving any other trace, and the ratio gate is the only thing that
notices.

The OCR engine is the macOS Vision framework, not tesseract. That is not a
preference. Tesseract with the tha pack reads the Thai *letters* well enough but
misreads the *digits* systematically -- on ข้อบังคับฯ 2568 it turned the section
run ๑..๙ into 1 2 3 5 5 2 3 5 5 and the year ๒๕๖๘ into ๒๕๒๐๕. Every citation
this bot makes is a number, so an engine that cannot read numbers is not usable
here at any accuracy on the rest of the page. Vision reads the same pages with
the digits intact.

The cost is that OCR only runs on macOS. data/ocr/ holds the result as plain
text so that a rebuild elsewhere, or after Vision changes its output, does not
need the framework at all -- delete a file there to force it to be read again.
"""
from __future__ import annotations

import os
import re
import unicodedata

import pymupdf

# --- the PUA slots AngsanaUPC uses for marks over tall consonants -------------
#
# Every entry below was confirmed against real words in the documents rather
# than taken from a font table, because the same PUA range is used differently
# by different foundries:
#
#   F701  ปกปด -> ปกปิด          F70A  ผู้รวม -> ผู้ร่วม
#   F706  ปกปอง -> ปกป้อง        F70B  หนา -> หน้า, ขอ -> ข้อ
#   F70E  ประสงค -> ประสงค์      F710  ปญญา -> ปัญญา
#   F712  เปน -> เป็น
#
# The rest of the range follows the same shifted-glyph scheme and is filled in
# from it, so a document that uses a slot we have not seen yet still comes out
# readable instead of tripping the PUA gate for no reason.
PUA_MAP = {
    0xF700: "ั", 0xF701: "ิ", 0xF702: "ี", 0xF703: "ึ",
    0xF704: "ื", 0xF705: "่", 0xF706: "้", 0xF707: "๊",
    0xF708: "๋", 0xF709: "็", 0xF70A: "่", 0xF70B: "้",
    0xF70C: "๊", 0xF70D: "๋", 0xF70E: "์", 0xF70F: "ํ",
    0xF710: "ั", 0xF711: "ิ", 0xF712: "็", 0xF713: "ื",
    0xF714: "่", 0xF715: "้", 0xF716: "๊", 0xF717: "๋",
    0xF718: "์", 0xF719: "ํ", 0xF71A: "ุ",
    0xF8FF: "๐",  # Apple logo slot, which the 2546 Act uses for the Thai zero
}

# --- the slots the 2546 Act uses that cp874 cannot decode ---------------------
#
# Byte 0x88 through 0x8C hold the left-shifted marks, sixty below their TIS-620
# positions. 0x8D and 0x8E break that pattern and hold the quotation marks the
# Act uses around every defined term; both were read off the definitions in
# มาตรา 4. 0x83 is the shifted mai ek again, used only after ฝ. 0xDC is a thin
# space the typesetter left between "พ.ศ." and the year.
#
# 0x92 through 0x97 are a second block of shifted marks, and the reason they are
# listed separately is that cp874 *does* decode them -- into curly quotes and a
# bullet. So they come back looking like punctuation rather than like damage:
# "เป็น" reads as "เป“น" and "ปี" as "ป•", 170 times, while every ratio stays
# healthy. Each was read off the word it broke:
#
#   92  ป’จจุบัน -> ปัจจุบัน      95  ประจำป• -> ประจำปี
#   93  เป“นผู้ -> เป็นผู้        96  ฝ–กอบรม -> ฝึกอบรม
#   97  ฝ่าฝ—น -> ฝ่าฝืน
#
# 0x91 and 0x94 never appear in this document, so they are left out rather than
# guessed at; STRAY_MARK below is what catches them if another document uses one.
LEGACY_EXTRA = {
    0x83: "่", 0x88: "่", 0x89: "้", 0x8A: "๊", 0x8B: "๋",
    0x8C: "์", 0x8D: "“", 0x8E: "”",
    0x92: "ั", 0x93: "็", 0x95: "ี", 0x96: "ึ", 0x97: "ื",
    0xDC: " ",
}

THAI = re.compile(r"[฀-๿]")
THAI_CONSONANT = re.compile(r"[ก-ฮ]")
THAI_TONE = re.compile(r"[็-๎]")
LATIN_LETTER = re.compile(r"[A-Za-zÀ-ɏͰ-Ͽ‘-‟†-™]")
PUA = re.compile(r"[-]")
# A consonant, a space, then สระอา. Real Thai never writes that, so it is a
# reliable fingerprint of a text layer whose zero-width marks were emitted at
# the wrong x position: ข้อบังคับฯ 2563 arrives with "ท ารายงาน" for "ทำรายงาน"
# and "ค าวินิจฉัย" for "คำวินิจฉัย", 43 times, while every ratio still looks
# healthy. Those documents have to be read by OCR instead.
SPLIT_SARA = re.compile(r"[ก-ฮ]\s+[าำ]")
# Punctuation wedged between two Thai letters. A real quotation mark opens after
# a space and closes before one, so this shape only happens when a shifted mark
# came back as punctuation -- the failure the 0x92..0x97 block above caused.
STRAY_MARK = re.compile(r"[\u0e01-\u0e2e][\u2018\u2019\u201c\u201d\u2022\u2013\u2014][\u0e01-\u0e5b]")
CONTROL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# words that appear in all ten documents; their absence means the page came out
# as noise even if the character ratios happen to look plausible
MUST_CONTAIN = ("จรรยาบรรณ", "วิชาชีพ", "คุรุสภา")

# measured on ข้อบังคับฯ 2556, the one document whose text layer is already
# correct: 0.19 tone marks per consonant. The window is wide enough for the
# procedural documents, which use fewer marked words, and narrow enough that a
# document which lost its marks entirely lands far outside it.
TONE_RATIO = (0.08, 0.35)
MIN_THAI_RATIO = 0.80
OCR_DPI = 300
OCR_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ocr"
)


class ExtractionError(RuntimeError):
    """Raised when no rung of the ladder produces usable text."""


# --- normalising --------------------------------------------------------------


def normalize_pua(text: str) -> str:
    """Put PUA-encoded marks back where they belong."""
    return text.translate(PUA_MAP)


def compose_sara_am(text: str) -> str:
    """Join NIKHAHIT + SARA AA back into the single character SARA AM.

    Thai typesetters write ำ as two glyphs so the circle can be positioned over
    the consonant, and every one of these PDFs does it -- 648 times across the
    ten. Unicode NFC does not compose the pair, so it survives into the index
    and splits words in half: pythainlp reads "ดําเนิน" as ดํา + เนิน and
    "สม่ําเสมอ" as สม่ํา + เสมอ, which means BM25 never matches the query a
    person actually types.
    """
    return text.replace("ํา", "ำ")


def settle(text: str) -> str:
    """The normalising every rung ends with, whatever produced the text."""
    return compose_sara_am(unicodedata.normalize("NFC", text))


def from_legacy(text: str) -> str:
    """Recover TIS-620 text that was stored behind a Mac Roman cmap.

    Round-trips one character at a time on purpose. Doing it on the whole string
    would abort at the first byte cp874 has no mapping for, and those bytes are
    exactly the tone marks -- the part worth recovering.
    """
    # Not NFKC. Mac Roman puts ช ส ต ษ ผ ป ๙ behind ™ NBSP µ … º ª ˘, and NFKC
    # rewrites every one of them -- ™ becomes the two letters "TM", NBSP becomes
    # a plain space -- which destroys the byte this function needs to read. The
    # single fold worth doing is the ohm sign, which PyMuPDF reports for the
    # slot Mac Roman calls omega, and that slot holds ฝ.
    text = text.replace("\u2126", "\u03a9")  # OHM SIGN -> GREEK CAPITAL OMEGA
    out = []
    for ch in text:
        try:
            byte = ch.encode("mac_roman")
        except UnicodeEncodeError:
            out.append(ch)
            continue
        if byte[0] in LEGACY_EXTRA:
            out.append(LEGACY_EXTRA[byte[0]])
            continue
        try:
            out.append(byte.decode("cp874"))
        except UnicodeDecodeError:
            out.append(ch)
    return "".join(out)


def looks_legacy(text: str) -> bool:
    """True when the text layer is Thai wearing a Latin costume."""
    thai = len(THAI.findall(text))
    latin = len(LATIN_LETTER.findall(text))
    return latin > 200 and thai < latin


# --- checking -----------------------------------------------------------------


def thai_ratio(text: str) -> float:
    """Share of the letters that are Thai. Digits and punctuation do not count."""
    thai = len(THAI.findall(text))
    other = len(LATIN_LETTER.findall(text)) + len(PUA.findall(text))
    total = thai + other
    return thai / total if total else 0.0


def tone_ratio(text: str) -> float:
    """Tone marks and their neighbours per consonant."""
    consonants = len(THAI_CONSONANT.findall(text))
    return len(THAI_TONE.findall(text)) / consonants if consonants else 0.0


def check(text: str) -> list[str]:
    """Return the reasons this text is not usable. Empty list means it is."""
    problems = []

    ratio = thai_ratio(text)
    if ratio < MIN_THAI_RATIO:
        problems.append(f"สัดส่วนอักษรไทย {ratio:.2f} ต่ำกว่า {MIN_THAI_RATIO}")

    leftover = set(PUA.findall(text))
    if leftover:
        shown = " ".join(f"U+{ord(c):04X}" for c in sorted(leftover)[:6])
        problems.append(f"เหลืออักขระ PUA {len(leftover)} ชนิด: {shown}")

    if CONTROL.search(text):
        problems.append("เหลืออักขระควบคุม")

    if "ํา" in text:
        problems.append("เหลือ ํ+า ที่ยังไม่รวมเป็น ำ")

    stray = STRAY_MARK.findall(text)
    if stray:
        problems.append(
            f"มีเครื่องหมายวรรคตอนคั่นกลางคำไทย {len(stray)} จุด เช่น {stray[0]!r} "
            "— น่าจะเป็นวรรณยุกต์ที่ถอดไม่ออก"
        )

    split = SPLIT_SARA.findall(text)
    if split:
        problems.append(
            f"มีสระลอยห่างจากพยัญชนะ {len(split)} จุด เช่น {split[0]!r} "
            "— ตัวบทวางวรรณยุกต์ผิดตำแหน่ง"
        )

    tones = tone_ratio(text)
    low, high = TONE_RATIO
    if not low <= tones <= high:
        problems.append(f"สัดส่วนวรรณยุกต์ต่อพยัญชนะ {tones:.3f} นอกช่วง {low}-{high}")

    if not any(word in text for word in MUST_CONTAIN):
        problems.append(f"ไม่พบคำหลักสักคำจาก {', '.join(MUST_CONTAIN)}")

    return problems


# --- reading ------------------------------------------------------------------


def text_layer(path: str) -> str:
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _vision_page(png: bytes) -> str:
    """Read one rendered page with the macOS Vision framework."""
    try:
        import Vision
        from Foundation import NSData
    except ImportError as exc:  # pragma: no cover - platform dependent
        raise ExtractionError(
            "ต้อง OCR แต่เรียก Vision ของ macOS ไม่ได้\n"
            "    ติดตั้งด้วย: pip install pyobjc-framework-Vision\n"
            "    หรือรันบนเครื่อง macOS แล้ว commit ผลใน data/ocr/ มาด้วย"
        ) from exc

    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(
        NSData.dataWithBytes_length_(png, len(png)), None
    )
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["th-TH"])
    # language correction rewrites words towards a dictionary, which on legal
    # Thai turns rare but correct terms into common wrong ones
    request.setUsesLanguageCorrection_(False)
    handler.performRequests_error_([request], None)

    lines = []
    for observation in request.results() or []:
        best = observation.topCandidates_(1)
        if best:
            lines.append(best[0].string())
    return "\n".join(lines)


def ocr(path: str, cache_dir: str | None = None) -> str:
    """Render every page and read it back. Cached as plain text under data/ocr/."""
    cache_dir = cache_dir or OCR_CACHE_DIR
    cached = os.path.join(cache_dir, os.path.splitext(os.path.basename(path))[0] + ".txt")
    if os.path.exists(cached):
        with open(cached, encoding="utf-8") as handle:
            return handle.read()

    pages = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pages.append(_vision_page(page.get_pixmap(dpi=OCR_DPI).tobytes("png")))
    text = "\n".join(pages)

    os.makedirs(cache_dir, exist_ok=True)
    with open(cached, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


def extract(path: str, allow_ocr: bool = True) -> tuple[str, str]:
    """Read one PDF. Returns (text, which rung of the ladder produced it).

    Raises ExtractionError with every rung's complaint when none of them works,
    rather than returning the least-bad attempt. A document that silently loses
    its tone marks would poison the index in a way no later step can detect.
    """
    raw = text_layer(path)
    attempts: list[tuple[str, str]] = []

    if looks_legacy(raw):
        attempts.append(("legacy", normalize_pua(from_legacy(raw))))
    else:
        attempts.append(("direct", raw))
        if PUA.search(raw):
            attempts.append(("pua", normalize_pua(raw)))
    attempts = [(name, settle(text)) for name, text in attempts]

    failures = []
    for name, text in attempts:
        problems = check(text)
        if not problems:
            return text, name
        failures.append(f"  {name}: {'; '.join(problems)}")

    if not allow_ocr:
        raise ExtractionError(f"{path} อ่านไม่ได้\n" + "\n".join(failures))

    text = settle(ocr(path))
    problems = check(text)
    if problems:
        failures.append(f"  ocr: {'; '.join(problems)}")
        raise ExtractionError(f"{path} อ่านไม่ได้แม้ผ่าน OCR\n" + "\n".join(failures))
    return text, "ocr"
