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

from app.config import settings

INK = "#1B2430"
MUTED = "#8A93A0"
LINE_GREY = "#E7EAEE"
NAVY = "#223C69"
GOLD = "#B8860B"
AMBER = "#B26B00"


def _text(text: str, **kw) -> dict:
    node = {"type": "text", "text": text or " ", "wrap": True}
    node.update(kw)
    return node


def _citation_row(citation: str) -> dict:
    """One statute reference, marked with a gold rule so it reads as evidence."""
    act, _, section = citation.rpartition(" มาตรา ")
    return {
        "type": "box", "layout": "horizontal", "spacing": "sm",
        "paddingAll": "8px", "backgroundColor": "#F7F8FA", "cornerRadius": "6px",
        "contents": [
            {"type": "box", "layout": "vertical", "width": "3px",
             "backgroundColor": GOLD, "cornerRadius": "2px", "contents": []},
            {"type": "box", "layout": "vertical", "flex": 1, "contents": [
                _text(act or citation, size="xs", color=INK, weight="bold"),
                _text(f"มาตรา {section}" if section else " ", size="xxs", color=MUTED),
            ]},
        ],
    }


def answer_bubble(answer_text: str, citations: list[str], *,
                  in_scope: bool = True, heading: str = "คำตอบ") -> dict:
    accent = NAVY if in_scope else AMBER
    body: list[dict] = [_text(answer_text, size="sm", color=INK)]

    if citations:
        body += [
            {"type": "separator", "margin": "lg", "color": LINE_GREY},
            _text("อ้างอิงจากตัวบท", size="xxs", color=MUTED, margin="lg"),
        ]
        # a bubble that lists ten sections is unreadable; three is enough to check
        body += [{"type": "box", "layout": "vertical", "margin": "sm", "spacing": "xs",
                  "contents": [_citation_row(c) for c in citations[:3]]}]
        if len(citations) > 3:
            body.append(_text(f"และอีก {len(citations) - 3} มาตรา",
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
                "ข้อมูลเบื้องต้นจากตัวบทกฎหมาย ไม่ใช่คำปรึกษาทางกฎหมาย "
                f"คลังข้อมูลปรับปรุงถึงประมาณ {settings.corpus_as_of}",
                size="xxs", color=MUTED)],
        },
    }


def answer_message(answer_text: str, citations: list[str], *,
                   in_scope: bool = True, heading: str = "คำตอบ") -> dict:
    """A Flex message; altText is what shows in the chat list and on old clients."""
    alt = answer_text.strip().split("\n")[0][:90] or "คำตอบจากผู้ช่วยกฎหมายไทย"
    return {
        "type": "flex",
        "altText": alt,
        "contents": answer_bubble(answer_text, citations,
                                  in_scope=in_scope, heading=heading),
    }
