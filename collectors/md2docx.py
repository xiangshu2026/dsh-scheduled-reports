# -*- coding: utf-8 -*-
"""
Convert the DSH daily Markdown reports into formatted Word documents.

Handles: headings (#..####), bullet/numbered lists, tables, bold,
inline code, [links](url) as real Word hyperlinks, blockquotes and
horizontal rules. CJK text gets an explicit w:eastAsia font so it
renders correctly in Word.
"""

import argparse
import os
import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

CJK_FONT = "\u5fae\u8f6f\u96c5\u9ed1"   # Microsoft YaHei  (Word falls back if the font is absent)
LATIN_FONT = "Calibri"
MONO_FONT = "Consolas"

INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def _set_fonts(run, mono=False):
    """Assign latin + East Asian font names on a run."""
    name = MONO_FONT if mono else LATIN_FONT
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), MONO_FONT if mono else CJK_FONT)


def add_hyperlink(paragraph, url, text):
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")

    rfonts = OxmlElement("w:rFonts")
    rfonts.set(qn("w:ascii"), LATIN_FONT)
    rfonts.set(qn("w:hAnsi"), LATIN_FONT)
    rfonts.set(qn("w:eastAsia"), CJK_FONT)
    rpr.append(rfonts)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rpr.append(color)

    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rpr.append(u)

    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text

    run.append(rpr)
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def add_inline(paragraph, text, base_bold=False):
    """Render inline markdown (bold / code / links) into a paragraph."""
    for piece in INLINE_RE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            run = paragraph.add_run(piece[2:-2])
            run.bold = True
            _set_fonts(run)
        elif piece.startswith("`") and piece.endswith("`") and len(piece) > 2:
            run = paragraph.add_run(piece[1:-1])
            _set_fonts(run, mono=True)
        elif piece.startswith("[") and "](" in piece and piece.endswith(")"):
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", piece)
            if m:
                add_hyperlink(paragraph, m.group(2), m.group(1))
            else:
                run = paragraph.add_run(piece)
                _set_fonts(run)
        else:
            run = paragraph.add_run(piece)
            if base_bold:
                run.bold = True
            _set_fonts(run)


def add_rule(document):
    p = document.add_paragraph()
    ppr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "BFBFBF")
    borders.append(bottom)
    ppr.append(borders)


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_separator_row(cells):
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def add_table(document, rows):
    header = rows[0]
    body = rows[1:]
    ncols = len(header)
    table = document.add_table(rows=1 + len(body), cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for j, text in enumerate(header):
        cell = table.cell(0, j)
        cell.text = ""
        add_inline(cell.paragraphs[0], text, base_bold=True)

    for i, row in enumerate(body, start=1):
        for j in range(ncols):
            text = row[j] if j < len(row) else ""
            cell = table.cell(i, j)
            cell.text = ""
            add_inline(cell.paragraphs[0], text)

    document.add_paragraph()


def configure_styles(document):
    normal = document.styles["Normal"]
    normal.font.name = LATIN_FONT
    normal.font.size = Pt(10.5)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), CJK_FONT)

    for style_name in ("Title", "Heading 1", "Heading 2", "Heading 3",
                       "Heading 4", "List Bullet", "List Bullet 2",
                       "List Number", "Quote"):
        try:
            st = document.styles[style_name]
        except KeyError:
            continue
        st.font.name = LATIN_FONT
        srpr = st.element.get_or_add_rPr()
        srf = srpr.find(qn("w:rFonts"))
        if srf is None:
            srf = OxmlElement("w:rFonts")
            srpr.append(srf)
        srf.set(qn("w:eastAsia"), CJK_FONT)


def convert(md_path, docx_path):
    with open(md_path, "r", encoding="utf-8") as fh:
        lines = fh.read().replace("\r\n", "\n").split("\n")

    document = Document()
    configure_styles(document)

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # blank
        if not stripped:
            i += 1
            continue

        # horizontal rule
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            add_rule(document)
            i += 1
            continue

        # table
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = split_row(lines[i])
                if not is_separator_row(cells):
                    rows.append(cells)
                i += 1
            if rows:
                add_table(document, rows)
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            style = {1: "Title", 2: "Heading 1", 3: "Heading 2",
                     4: "Heading 3"}.get(level, "Heading 4")
            p = document.add_paragraph(style=style)
            add_inline(p, m.group(2))
            i += 1
            continue

        # blockquote
        if stripped.startswith(">"):
            p = document.add_paragraph(style="Quote")
            add_inline(p, re.sub(r"^>\s?", "", stripped))
            i += 1
            continue

        # bullet list
        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if m:
            indent = len(m.group(1).replace("\t", "    "))
            style = "List Bullet" if indent < 2 else (
                "List Bullet 2" if indent < 4 else "List Bullet 3")
            try:
                p = document.add_paragraph(style=style)
            except KeyError:
                p = document.add_paragraph(style="List Bullet")
            add_inline(p, m.group(2))
            i += 1
            continue

        # numbered list
        m = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
        if m:
            p = document.add_paragraph(style="List Number")
            add_inline(p, m.group(2))
            i += 1
            continue

        # ordinary paragraph
        p = document.add_paragraph()
        add_inline(p, stripped)
        i += 1

    document.save(docx_path)
    return docx_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md", help="markdown file, or a directory of .md files")
    ap.add_argument("--outdir", default=None,
                    help="output directory (default: alongside the source)")
    args = ap.parse_args()

    targets = []
    if os.path.isdir(args.md):
        for name in sorted(os.listdir(args.md)):
            if name.lower().endswith(".md"):
                targets.append(os.path.join(args.md, name))
    else:
        targets.append(args.md)

    if not targets:
        print("no .md files found")
        return 1

    ok = 0
    failed = []
    for src in targets:
        outdir = args.outdir or os.path.dirname(os.path.abspath(src))
        os.makedirs(outdir, exist_ok=True)
        dst = os.path.join(outdir,
                           os.path.splitext(os.path.basename(src))[0] + ".docx")
        try:
            convert(src, dst)
            ok += 1
        except Exception as exc:                      # noqa: BLE001
            failed.append((os.path.basename(src), str(exc)))

    # stdout stays ASCII-only on purpose: the caller redirects it into a
    # UTF-8 log, and non-ASCII here would risk a codepage mismatch.
    def _a(text):
        return str(text).encode("ascii", "backslashreplace").decode("ascii")

    print("converted_ok=%d" % ok)
    print("converted_failed=%d" % len(failed))
    for name, msg in failed:
        print("FAILED %s : %s" % (_a(name), _a(msg)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
