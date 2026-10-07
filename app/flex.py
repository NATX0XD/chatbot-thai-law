# -*- coding: utf-8 -*-
"""Render an answer as a LINE Flex Message.

A plain bubble makes the answer, the statute it rests on, and the disclaimer look
like one undifferentiated wall of Thai text. The whole promise of this bot is that
a reader can check the citation, so the citation needs to be visually separable
from the prose -- and the disclaimer needs to be visible without competing with
the answer.

Layout, top to bottom:
  header   the topic, colour-coded by outcome (answered / refused)
  body     the answer text, then the sections it used as tappable-looking chips
  footer   the disclaimer in small grey type

Flex has hard limits: 10 bubbles per carousel, 50 KB per message, and no rich
text inside a text block. Everything here stays well inside those.
"""
from __future__ import annotations

import re

from app.config import settings

INK = "#1B2430"
MUTED = "#8A93A0"
LINE_GREY = "#E7EAEE"
NAVY = "#223C69"
GOLD = "#B8860B"
AMBER = "#B26B00"
# The networking bot: the blue of a patch cable and the cyan of a link light,
# in place of the navy and gold of a law book.
BLUE = "#0B4F8A"
CYAN = "#12B5CB"

# What changes with the dataset an answer was written from: the header colour,
# the rule beside each reference, and the two fixed lines of text.
THEMES = {
    "book": {"accent": BLUE, "mark": CYAN, "references": "อ้างอิงจากหนังสือ",
             "footer": "สรุปจากหนังสือคู่มือเรียนเครือข่ายคอมพิวเตอร์เบื้องต้น "
                       "ใช้ทบทวนบทเรียน ควรอ่านเนื้อหาเต็มตามหน้าที่อ้าง",
             "alt": "คำตอบจากผู้ช่วยวิชาเครือข่ายคอมพิวเตอร์"},
}
LAW_THEME = {"accent": NAVY, "mark": GOLD, "references": "อ้างอิงจากตัวบท",
             "footer": None, "alt": "คำตอบจากผู้ช่วยกฎหมายไทย"}
BOOK_CITATION = re.compile(r"^(.*?)\s+—\s+(.*)$")


def _text(text: str, **kw) -> dict:
    node = {"type": "text", "text": text or " ", "wrap": True}
    node.update(kw)
    return node


CITATION_SPLIT = re.compile(r"\s+(ข้อ|มาตรา)\s+(?=[\d๐-๙])")


def _split_citation(citation: str) -> tuple[str, str]:
    """Separate the instrument's name from the rule number it points at.

    Split on whichever unit word the citation uses. Regulations of the Teachers
    Council number their rules as ข้อ and only the Act uses มาตรา, so hard-coding
    one of them left the other's number glued to the title and printed nothing in
    the reference line.
    """
    parts = CITATION_SPLIT.split(citation)
    if len(parts) == 3:
        act, unit, number = parts
        return act, f"{unit} {number}"
    return citation, ""


def _citation_row(citation: str, mark: str = GOLD) -> dict:
    """One reference, marked with a coloured rule so it reads as evidence."""
    act, section = _split_citation(citation)
    if not section:
        # a textbook reference: "บทที่ 2 ชื่อบท — หัวข้อ ... (หน้า 42)"
        chapter = BOOK_CITATION.match(citation)
        if chapter:
            act, section = chapter.group(1), chapter.group(2)
    return {
        "type": "box", "layout": "horizontal", "spacing": "sm",
        "paddingAll": "8px", "backgroundColor": "#F7F8FA", "cornerRadius": "6px",
        "contents": [
            {"type": "box", "layout": "vertical", "width": "3px",
             "backgroundColor": mark, "cornerRadius": "2px", "contents": []},
            {"type": "box", "layout": "vertical", "flex": 1, "contents": [
                _text(act or citation, size="xs", color=INK, weight="bold"),
                _text(section or " ", size="xxs", color=MUTED),
            ]},
        ],
    }


def answer_bubble(answer_text: str, citations: list[str], *,
                  in_scope: bool = True, heading: str = "คำตอบ",
                  source: str = "rules") -> dict:
    theme = THEMES.get(source, LAW_THEME)
    accent = theme["accent"] if in_scope else AMBER
    body: list[dict] = [_text(answer_text, size="sm", color=INK)]

    if citations:
        body += [
            {"type": "separator", "margin": "lg", "color": LINE_GREY},
            _text(theme["references"], size="xxs", color=MUTED, margin="lg"),
        ]
        # a bubble that lists ten sections is unreadable; three is enough to check
        body += [{"type": "box", "layout": "vertical", "margin": "sm", "spacing": "xs",
                  "contents": [_citation_row(c, theme["mark"]) for c in citations[:3]]}]
        if len(citations) > 3:
            body.append(_text(f"และอีก {len(citations) - 3} รายการ",
                              size="xxs", color=MUTED, margin="sm"))

    return {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "14px",
            "backgroundColor": accent,
            "contents": [_text(heading, size="sm", weight="bold", color="#FFFFFF")],
        },
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "16px",
            "spacing": "none", "contents": body,
        },
        "footer": {
            "type": "box", "layout": "vertical", "paddingAll": "12px",
            "backgroundColor": "#FAFBFC",
            "contents": [_text(
                theme["footer"] or
                "ข้อมูลเบื้องต้นจากตัวบทกฎหมาย ไม่ใช่คำปรึกษาทางกฎหมาย "
                f"คลังข้อมูลปรับปรุงถึงประมาณ {settings.corpus_as_of}",
                size="xxs", color=MUTED)],
        },
    }


def answer_message(answer_text: str, citations: list[str], *,
                   in_scope: bool = True, heading: str = "คำตอบ",
                   source: str = "rules") -> dict:
    """A Flex message; altText is what shows in the chat list and on old clients."""
    alt = (answer_text.strip().split("\n")[0][:90]
           or THEMES.get(source, LAW_THEME)["alt"])
    return {
        "type": "flex",
        "altText": alt,
        "contents": answer_bubble(answer_text, citations,
                                  in_scope=in_scope, heading=heading,
                                  source=source),
    }


THAI_LETTER = re.compile(r"[\u0E00-\u0E7F]")
ZERO_WIDTH_SPACE = "\u200b"
# One frame for every picture. A carousel is as tall as its tallest bubble:
# given each picture's own ratio, one upright photograph stretched every other
# card in the row into a column of white.
FIGURE_FRAME = "4:3"


def breakable(text: str) -> str:
    """The same text, with an invisible break allowed between Thai words.

    Thai is written without spaces, and LINE breaks a line only at one. A
    sentence that names its terms in English -- "สาย LAN คือสายเคเบิลที่ใช้..."
    -- has spaces only around those terms, so the client ended the line after
    "LAN" and left it two words long. A zero-width space between words, cut by
    newmm, lets the line run to the edge.
    """
    from pythainlp.tokenize import word_tokenize

    out = []
    for line in text.split("\n"):
        words = word_tokenize(line, engine="newmm", keep_whitespace=True)
        joined = words[:1]
        for before, after in zip(words, words[1:]):
            if THAI_LETTER.match(before[-1:]) and THAI_LETTER.match(after[:1]):
                joined.append(ZERO_WIDTH_SPACE)
            joined.append(after)
        out.append("".join(joined))
    return "\n".join(out)


def _figure_bubble(figure: dict, base_url: str) -> dict:
    url = base_url.rstrip("/") + figure["url"]
    ratio = FIGURE_FRAME
    label = (f"รูปที่ {figure['number']} {figure['caption']}"
             if figure.get("kind", "figure") == "figure" else figure["caption"])
    return {
        "type": "bubble", "size": "kilo",
        "hero": {"type": "image", "url": url, "size": "full", "aspectRatio": ratio,
                 "aspectMode": "fit", "backgroundColor": "#FFFFFF",
                 "action": {"type": "uri", "uri": url}},
        "body": {"type": "box", "layout": "vertical", "paddingAll": "12px",
                 "contents": [
                     _text(breakable(label[:160]), size="xs", color=INK),
                     _text(f"หน้า {figure['page']}", size="xxs", color=MUTED, margin="sm"),
                 ]},
    }


def figures_message(figures: list[dict], base_url: str) -> dict:
    """The answer's pictures as one swipeable row, each with what it shows.

    One message rather than one per picture: LINE takes five messages a send,
    and the eight steps of crimping a plug are eight photographs.
    """
    bubbles = [_figure_bubble(f, base_url) for f in figures[:12]]
    return {"type": "flex", "altText": f"รูปประกอบจากหนังสือ {len(bubbles)} รูป",
            "contents": bubbles[0] if len(bubbles) == 1
            else {"type": "carousel", "contents": bubbles}}
