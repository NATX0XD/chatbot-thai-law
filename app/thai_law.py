"""Utilities for cleaning and slicing Thai legal text from the krisdika-derived corpora.

The source text keeps the original page layout: paragraphs are separated by a blank
line while every other newline is a wrap artifact from the scrape. Sections are split
on the raw text first -- reflowing before splitting would make in-text references such
as "ตามมาตรา ๒๓" look like section headers.
"""
import re

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# cp1252 smart-quote bytes leaked into the source HTML during the original scrape
MOJIBAKE = {
    "\x93": "“", "\x94": "”", "\x91": "‘", "\x92": "’",
    "\x96": "–", "\x97": "—", "\x85": "...",
}

FOOTNOTE_RE = re.compile(r"\[[๐-๙0-9]+\]")
SECTION_SPLIT_RE = re.compile(r"\n\s*\n(?=\s*มาตรา\s+[๐-๙0-9]+)")
SECTION_HEAD_RE = re.compile(r"^\s*มาตรา\s+([๐-๙0-9]+(?:/[๐-๙0-9]+)?)")
CHAPTER_RE = re.compile(r"(?m)^\s*(หมวด|ส่วนที่|ลักษณะ|บรรพ)\s+([๐-๙0-9]+)\s*\n\s*(.+)")
TRAILING_HEAD_RE = re.compile(r"\n\n(หมวด|ส่วนที่|ลักษณะ|บรรพ)\s+[๐-๙0-9]+\b.*$", re.S)

# everything from here on is countersignature, fee schedules, amendment notes and
# the raw footnote block -- none of it belongs in a retrievable section.
# "หมายเหตุ :-" is listed separately because some acts place the explanatory note
# before the countersignature, so anchoring only on ผู้รับสนอง left the note glued
# to the final section: 52 sections across 51 acts carried it.
TAIL_RE = re.compile(r"ผู้รับสนองพระบรมราชโองการ"
                     r"|หมายเหตุ\s*:-"
                     r"|\[[๐-๙0-9]+\]\s*\n?\s*ราชกิจจานุเบกษา")


def main_body(text: str) -> str:
    """Trim the enacting tail so section splitting does not pick up footnote echoes."""
    m = TAIL_RE.search(text)
    return text[: m.start()] if m else text


def clean(text: str, keep_footnote_marks: bool = False) -> str:
    """Fix the mojibake and reflow hard-wrapped lines back into paragraphs."""
    for bad, good in MOJIBAKE.items():
        text = text.replace(bad, good)
    text = text.replace("\xa0", " ")
    if not keep_footnote_marks:
        text = FOOTNOTE_RE.sub("", text)
    text = re.sub(r"\n[ \t]*\n[\s]*", "\x00", text)  # paragraph breaks -> sentinel
    text = text.replace("\n", " ")
    text = text.replace("\x00", "\n\n")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def to_arabic(text: str) -> str:
    return text.translate(THAI_DIGITS)


def sections(raw: str):
    """Yield (section_number, cleaned_body) for each มาตรา in document order."""
    seen = set()
    for chunk in SECTION_SPLIT_RE.split(main_body(raw)):
        m = SECTION_HEAD_RE.match(chunk)
        if not m:
            continue
        no = to_arabic(m.group(1))
        if no in seen:
            continue
        seen.add(no)
        body = clean(chunk[m.end():]).lstrip(" .:")
        # a chapter heading sits between two sections and lands at the end of the
        # preceding chunk -- it belongs to neither section's text
        body = TRAILING_HEAD_RE.sub("", body).strip()
        yield no, body


def section_map(raw: str) -> dict:
    return dict(sections(raw))


def chapters(raw: str):
    """Yield (kind, number, heading) for the หมวด / ส่วนที่ / ลักษณะ / บรรพ structure."""
    for kind, num, head in CHAPTER_RE.findall(main_body(raw)):
        head = clean(head).split("\n")[0].strip()
        if head and not head.startswith("มาตรา"):
            yield kind, to_arabic(num), head


def truncate(text: str, limit: int = 0) -> str:
    """Cut a body to roughly `limit` characters on a paragraph or word edge."""
    if not limit or len(text) <= limit:
        return text
    cut = text[:limit]
    for stop in ("\n\n", " "):
        idx = cut.rfind(stop)
        if idx > limit * 0.6:
            return cut[:idx].rstrip() + " …"
    return cut + " …"
