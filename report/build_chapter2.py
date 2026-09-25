# -*- coding: utf-8 -*-
"""Write บทที่ 2 and บทที่ 3 into the thesis document, and dump both as Markdown.

    .venv/bin/python -m report.build_chapter2

Reads  ~/Downloads/Chatbot เล่ม.docx
Writes ~/Downloads/Chatbot เล่ม (บทที่ 2-3).docx   <- a copy, never the original
       report/บทที่2-ทฤษฎีที่เกี่ยวข้อง.md
       report/บทที่3-ขั้นตอนและวิธีการดำเนินการวิจัย.md

The original is left alone on purpose: this replaces a whole chapter, and an
overwrite of the only copy is not something to find out about afterwards. Open
the new file, check it, then rename it over the old one yourself.

What it does to the copy:
  1. finds the Heading 1 that reads ทฤษฎีที่เกี่ยวข้อง
  2. deletes everything between it and the next Heading 1 (the old 2.1--2.4)
  3. writes the new chapter in its place, keeping the document's own styles
  4. appends the new bibliography entries after the last one in เอกสารอ้างอิง

Headings use the document's Heading 2 style so the table of contents still
picks them up; body text copies the formatting of an existing body paragraph,
which is how the Thai font and size come out right without naming a font here.
"""
from __future__ import annotations

import copy
import os
import shutil

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from report.chapter2_content import CHAPTER, REFERENCES
from report.chapter3_content import CHAPTER as CHAPTER3

HERE = os.path.dirname(os.path.abspath(__file__))
FIGURES = os.path.join(HERE, "figures")
SOURCE = os.path.expanduser("~/Downloads/Chatbot เล่ม.docx")
TARGET = os.path.expanduser("~/Downloads/Chatbot เล่ม (บทที่ 2-3).docx")
MARKDOWN = os.path.join(HERE, "บทที่2-ทฤษฎีที่เกี่ยวข้อง.md")
MARKDOWN3 = os.path.join(HERE, "บทที่3-ขั้นตอนและวิธีการดำเนินการวิจัย.md")

FIGURE_WIDTH = Inches(6.0)     # fits the KMUTNB margins with room to spare
INDENT = Inches(0.5)           # the thesis indents the first line of a paragraph


# ------------------------------------------------------------------- helpers

def body_style(doc):
    """The document's own body paragraph, used as the template for new ones."""
    for para in doc.paragraphs:
        if para.style.name == "Normal" and len(para.text) > 120:
            return para
    return None


def clone_format(new, template) -> None:
    """Copy paragraph and run formatting from an existing paragraph."""
    if template is None:
        return
    new.paragraph_format.line_spacing = template.paragraph_format.line_spacing
    new.paragraph_format.space_after = template.paragraph_format.space_after
    new.paragraph_format.space_before = template.paragraph_format.space_before
    if template.runs and new.runs:
        src, dst = template.runs[0], new.runs[0]
        dst.font.size = src.font.size
        dst.font.name = src.font.name
        # Word keeps the font for complex scripts in a separate attribute, and
        # Thai is a complex script: without this the text renders in the theme
        # font instead of the one the rest of the thesis uses.
        if src.font.name:
            for tag in ("w:eastAsia", "w:cs"):
                dst._element.rPr.rFonts.set(qn(tag), src.font.name)
        if src._element.rPr is not None and src._element.rPr.find(qn("w:szCs")) is not None:
            size = src._element.rPr.find(qn("w:szCs")).get(qn("w:val"))
            dst._element.get_or_add_rPr().append(
                docx.oxml.parse_xml(
                    f'<w:szCs xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:val="{size}"/>'))


class Cursor:
    """Inserts elements one after another at a fixed point in the document."""

    def __init__(self, doc, after):
        self.doc = doc
        self.at = after

    def place(self, element):
        self.at.addnext(element)
        self.at = element
        return element

    def paragraph(self, text: str, template=None, *, indent=None,
                  style=None, align=None, bold=False, colour=None, size=None):
        para = self.doc.add_paragraph(text, style=style)
        run = para.runs[0] if para.runs else para.add_run("")
        run.bold = bold
        if colour is not None:
            run.font.color.rgb = colour
        clone_format(para, template)
        if size is not None:
            run.font.size = size
        if indent is not None:
            para.paragraph_format.first_line_indent = indent
        if align is not None:
            para.alignment = align
        self.place(para._element)
        return para

    def picture(self, path: str, width):
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.add_run().add_picture(path, width=width)
        self.place(para._element)
        return para

    def table(self, header, rows, template=None):
        table = self.doc.add_table(rows=1, cols=len(header))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for cell, text in zip(table.rows[0].cells, header):
            cell.text = ""
            run = cell.paragraphs[0].add_run(text)
            run.bold = True
            clone_format(cell.paragraphs[0], template)
        for row in rows:
            cells = table.add_row().cells
            for cell, text in zip(cells, row):
                cell.text = ""
                cell.paragraphs[0].add_run(text)
                clone_format(cell.paragraphs[0], template)
        self.place(table._element)
        return table


def chapter_span(doc, title: str):
    """(heading, the elements after it that belong to that chapter).

    Chapter 3 ends at the template's own leftover headings rather than at a
    Heading 1, so the search stops at anything that is not body text.
    """
    paragraphs = doc.paragraphs
    start = next(i for i, p in enumerate(paragraphs)
                 if p.style.name == "Heading 1" and title in p.text)
    end = next((i for i in range(start + 1, len(paragraphs))
                if paragraphs[i].style.name.startswith("Heading")
                and paragraphs[i].style.name != "Heading 2"), len(paragraphs))
    return paragraphs[start], paragraphs[start + 1:end]


# --------------------------------------------------------------------- build

def write_docx() -> None:
    shutil.copy(SOURCE, TARGET)
    doc = docx.Document(TARGET)
    template = body_style(doc)

    # chapter 3 first: replacing chapter 2 shifts every paragraph index after it
    write_chapter(doc, template, "ดําเนินการวิจัย", CHAPTER3)
    write_chapter(doc, template, "ทฤษฎีที่เกี่ยวข้อง", CHAPTER)

    append_references(doc)
    doc.save(TARGET)
    print("wrote", TARGET)


def write_chapter(doc, template, title: str, blocks: list[tuple]) -> None:
    heading, old = chapter_span(doc, title)
    for para in old:
        para._element.getparent().remove(para._element)

    cur = Cursor(doc, heading._element)
    grey = RGBColor(0x88, 0x88, 0x88)

    for kind, payload in blocks:
        if kind == "intro":
            cur.paragraph(payload, template, indent=INDENT)
        elif kind == "toc":
            for line in payload:
                cur.paragraph(line, template, indent=INDENT)
        elif kind == "h2":
            cur.paragraph(payload, style="Heading 2")
        elif kind == "h3":
            para = cur.paragraph(payload, template, indent=INDENT)
            para.runs[0].bold = True
        elif kind == "p":
            cur.paragraph(payload, template, indent=INDENT)
        elif kind == "bullet":
            para = cur.paragraph(payload, template)
            para.paragraph_format.left_indent = INDENT
            para.paragraph_format.first_line_indent = Inches(-0.25)
            para.runs[0].text = "•  " + para.runs[0].text
        elif kind == "figure":
            stem, caption = payload
            path = os.path.join(FIGURES, stem + ".png")
            if not os.path.exists(path):
                raise FileNotFoundError(f"{path} -- run report.make_figures first")
            cur.picture(path, FIGURE_WIDTH)
            cur.paragraph(caption, template, align=WD_ALIGN_PARAGRAPH.CENTER)
        elif kind == "table":
            caption, header, rows = payload
            cur.paragraph(caption, template, align=WD_ALIGN_PARAGRAPH.CENTER)
            cur.table(header, rows, template)
            cur.paragraph("", template)
        elif kind == "note":
            cur.paragraph(payload, template, indent=INDENT,
                          colour=grey, size=Pt(12))
        else:
            raise ValueError(f"unknown block: {kind}")
    print(f"  {title}: {len(blocks)} blocks")


def append_references(doc) -> None:
    """Put the new entries after the last one under เอกสารอ้างอิง."""
    paragraphs = doc.paragraphs
    start = next((i for i, p in enumerate(paragraphs)
                  if "เอกสารอ้างอิง" in p.text and len(p.text) < 40), None)
    if start is None:
        print("  (no bibliography found -- new references not appended)")
        return
    last = paragraphs[-1]
    for i in range(len(paragraphs) - 1, start, -1):
        if paragraphs[i].text.strip():
            last = paragraphs[i]
            break

    template = None
    for para in paragraphs[start + 1:]:
        if para.text.strip().startswith("["):
            template = para
            break

    cur = Cursor(doc, last._element)
    for number, text in REFERENCES:
        para = cur.paragraph(f"[{number}]  {text}",
                             template, style=template.style if template else None)
        para.paragraph_format.left_indent = Inches(0.4)
        para.paragraph_format.first_line_indent = Inches(-0.4)
    print(f"  appended references [{REFERENCES[0][0]}]–[{REFERENCES[-1][0]}]")


# ------------------------------------------------------------------ markdown

def write_markdown(blocks: list[tuple], title: str, path: str,
                   references=None) -> None:
    out = [f"# {title}", ""]
    for kind, payload in blocks:
        if kind == "intro":
            out += [payload, ""]
        elif kind == "toc":
            out += payload + [""]
        elif kind == "h2":
            out += ["", "## " + payload, ""]
        elif kind == "h3":
            out += ["### " + payload, ""]
        elif kind == "p":
            out += [payload, ""]
        elif kind == "bullet":
            out += ["- " + payload]
        elif kind == "note":
            out += ["> " + payload, ""]
        elif kind == "figure":
            stem, caption = payload
            out += [f"![{caption}](figures/{stem}.png)", "", f"**{caption}**", ""]
        elif kind == "table":
            caption, header, rows = payload
            out += [f"**{caption}**", ""]
            out += ["| " + " | ".join(header) + " |"]
            out += ["|" + "|".join([":--"] * len(header)) + "|"]
            out += ["| " + " | ".join(r) + " |" for r in rows]
            out += [""]
    if references:
        out += ["", "## เอกสารอ้างอิงที่เพิ่ม", ""]
        out += [f"[{n}]  {t}\n" for n, t in references]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("wrote", path)


if __name__ == "__main__":
    write_docx()
    write_markdown(CHAPTER, "บทที่ 2 ทฤษฎีที่เกี่ยวข้อง", MARKDOWN, REFERENCES)
    write_markdown(CHAPTER3, "บทที่ 3 ขั้นตอนและวิธีการดำเนินการวิจัย", MARKDOWN3)
