# -*- coding: utf-8 -*-
"""生成周报：Markdown 正文 + JSON 快照。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import Item

SOURCE_LABEL = {
    "github": "GitHub",
    "bilibili": "B站",
    "douyin": "抖音",
}


def group_by_source(items: List[Item]) -> Dict[str, List[Item]]:
    g: Dict[str, List[Item]] = {"github": [], "bilibili": [], "douyin": []}
    for it in items:
        g.setdefault(it.source, []).append(it)
    for k in g:
        g[k].sort(key=lambda x: (-x.score, -x.popularity))
    return g


def _one_line(it: Item) -> str:
    """一条 = 名称 + 一句功能 + 出处链接。"""
    name = it.name or it.title
    feature = it.feature or (it.summary_raw or "")[:50]
    meta = []
    if it.source == "github" and it.popularity:
        meta.append(f"★{it.popularity}")
    elif it.source != "github" and it.popularity:
        meta.append(f"{it.popularity} 播放")
    if it.author and it.source != "github":
        meta.append(f"@{it.author}")
    tail = f"（{'，'.join(meta)}）" if meta else ""
    return f"- **[{name}]({it.url})** — {feature}{tail}"


def render_markdown(items: List[Item], ctx: Dict[str, Any]) -> str:
    start, end = ctx.get("period_start", ""), ctx.get("period_end", "")
    groups = group_by_source(items)
    total = len(items)

    lines: List[str] = []
    lines.append(f"# {ctx.get('title_prefix', 'DSH 插件周报')}｜{end}")
    lines.append("")
    lines.append(f"> 覆盖周期 {start} ~ {end}　共 {total} 条　"
                 f"生成于 {ctx.get('generated_at', '')}")
    lines.append("")

    if not total:
        lines.append("本周期没有筛出值得写的新插件。")
        lines.append("")

    stats = ctx.get("source_stats") or {}
    enabled = ctx.get("enabled_sources")
    order = ["github", "bilibili", "douyin"]
    if enabled:
        order = [s for s in order if s in enabled]
    for src in order:
        rows = groups.get(src) or []
        st = stats.get(src) or {}
        lines.append(f"## {SOURCE_LABEL.get(src, src)}（{len(rows)}）")
        lines.append("")
        if not rows:
            if st.get("skipped"):
                lines.append(f"_本周期未采集：{st['skipped']}_")
            elif st.get("collected"):
                lines.append(f"_本周期采到 {st['collected']} 条，"
                             f"经筛选/去重后无新增。_")
            else:
                lines.append("_本周期无新增。_")
            lines.append("")
            continue
        for it in rows:
            lines.append(_one_line(it))
        lines.append("")

    notes = ctx.get("notes") or []
    if notes:
        lines.append("---")
        lines.append("")
        lines.append("### 采集说明")
        lines.append("")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.append("---")
    lines.append("")
    dropped = ctx.get("dropped_summary") or []
    if dropped:
        lines.append(f"_已过滤 {len(dropped)} 条无关/重复/低质内容。_")
    return "\n".join(lines).rstrip() + "\n"


def save_report(markdown: str, items: List[Item], ctx: Dict[str, Any],
                out_dir: Path, keep_latest: bool = True,
                dated: bool = False, filename: str = "weekly",
                stamp_override: str | None = None,
                fallback_to_root: bool = True) -> Dict[str, str]:
    """写报告。

    dated=True 时优先写 out_dir/<YYYY-MM-DD>/；
    如果那个日期文件夹还没建（比如当天其他报告没跑），
    且 fallback_to_root=True，就直接写 out_dir 根目录，不自己新建空文件夹。

    文件名统一带日期后缀，和桌面已有的「电脑状况报告-2026-10-19.docx」风格一致。
    """
    stamp = stamp_override or ctx.get("period_end", "report")
    target = out_dir
    if dated:
        candidate = out_dir / stamp
        if candidate.is_dir():
            target = candidate
        elif not fallback_to_root:
            target = candidate
        # fallback_to_root 且日期文件夹不存在 → target 保持 out_dir 根目录

    target.mkdir(parents=True, exist_ok=True)
    base_name = f"{filename}-{stamp}"
    md_path = target / f"{base_name}.md"
    md_path.write_text(markdown, encoding="utf-8")

    payload = {
        "generated_at": ctx.get("generated_at"),
        "period_start": ctx.get("period_start"),
        "period_end": ctx.get("period_end"),
        "count": len(items),
        "items": [it.to_dict() for it in items],
        "notes": ctx.get("notes") or [],
        "source_stats": ctx.get("source_stats") or {},
    }
    json_path = target / f"{base_name}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    paths = {"markdown": str(md_path), "json": str(json_path)}
    if keep_latest:
        latest = target / "latest.md"
        latest.write_text(markdown, encoding="utf-8")
        paths["latest"] = str(latest)
    return paths
