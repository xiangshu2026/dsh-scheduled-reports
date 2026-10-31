# -*- coding: utf-8 -*-
"""把周报渲染成 .docx（与桌面 DSH-Reports 里其他报告格式统一）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .models import Item

SOURCE_LABEL = {"github": "GitHub", "bilibili": "B站", "douyin": "抖音"}


def _add_hyperlink(paragraph, url: str, text: str, color: str = "0563C1", underline: bool = True):
    """python-docx 原生不支持超链接，这里手写一个。"""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")

    if color:
        c = OxmlElement("w:color")
        c.set(qn("w:val"), color)
        r_pr.append(c)
    if underline:
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        r_pr.append(u)

    new_run.append(r_pr)
    t = OxmlElement("w:t")
    t.text = text
    new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)
    return hyperlink


def _set_base_style(doc) -> None:
    """统一正文中文字体，避免打开后是宋体/等线混排。"""
    from docx.oxml.ns import qn
    from docx.shared import Pt

    style = doc.styles["Normal"]
    style.font.size = Pt(10.5)
    style.font.name = "微软雅黑"
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), "微软雅黑")


def render_docx(items: List[Item], ctx: Dict[str, Any], path: Path) -> Path:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    _set_base_style(doc)

    # 标题
    title = doc.add_heading(ctx.get("title_prefix", "DSH 插件周报"), level=0)
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

    # 元信息
    meta = doc.add_paragraph()
    meta_run = meta.add_run(
        f"覆盖周期 {ctx.get('period_start', '')} ~ {ctx.get('period_end', '')}"
        f"　共 {len(items)} 条　生成于 {ctx.get('generated_at', '')}")
    meta_run.font.size = Pt(9)
    meta_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_paragraph()

    groups: Dict[str, List[Item]] = {}
    for it in items:
        groups.setdefault(it.source, []).append(it)
    for k in groups:
        groups[k].sort(key=lambda x: (-x.score, -x.popularity))

    enabled = ctx.get("enabled_sources")
    order = ["github", "bilibili", "douyin"]
    if enabled:
        order = [s for s in order if s in enabled]

    for src in order:
        rows = groups.get(src) or []
        h = doc.add_heading(f"{SOURCE_LABEL.get(src, src)}（{len(rows)}）", level=1)
        for run in h.runs:
            run.font.size = Pt(14)

        if not rows:
            p = doc.add_paragraph("本周期无新增。")
            p.runs[0].italic = True
            p.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)
            continue

        for it in rows:
            p = doc.add_paragraph(style="List Bullet")
            name = it.name or it.title
            # 加粗名称 + 超链接
            bold_run = p.add_run()
            bold_run.bold = True
            _add_hyperlink(p, it.url, name)
            # 把超链接里的文字设成加粗不太方便，这里再补一个加粗标记
            p.add_run(" — ").bold = False
            feature = it.feature or (it.summary_raw or "")[:60]
            p.add_run(feature)
            if it.popularity:
                unit = "★" if it.source == "github" else "播放"
                tail = p.add_run(f"（{it.popularity} {unit}）" if it.source == "github"
                                 else f"（{it.popularity} 播放）")
                tail.font.size = Pt(9)
                tail.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    notes = ctx.get("notes") or []
    dropped = ctx.get("dropped_summary") or []
    if notes or dropped:
        doc.add_paragraph()
        h = doc.add_heading("采集说明", level=2)
        for run in h.runs:
            run.font.size = Pt(11)
        for n in notes:
            p = doc.add_paragraph(n, style="List Bullet")
            for r in p.runs:
                r.font.size = Pt(9)
        if dropped:
            p = doc.add_paragraph(f"已过滤 {len(dropped)} 条无关/重复/低质内容。")
            p.runs[0].font.size = Pt(9)
            p.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path
