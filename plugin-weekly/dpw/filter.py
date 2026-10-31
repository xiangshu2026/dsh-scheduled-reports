# -*- coding: utf-8 -*-
"""相关性筛选：先本地启发式，再交模型判断“是不是有用的插件”并写功能简介。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from .config import resolve_api_key
from .models import Item
from .util import HttpClient, log

# 强相关：必须命中其一（只提「deepseek」的泛 AI 项目不算，那会把整条生态淹掉）
STRONG_HINTS = [
    "dsh", "deepseek harness", "deepseek-harness", "深度求索 harness",
    "dogebox", "dsh-plugin", "dshplugin",
]
# 弱相关（仅当同时出现插件类词时才算）
TOPIC_HINTS = ["deepseek", "harness", "深度求索", "大肥鱼", "v4.1", "v4-flash"]
# 加分项：明确是插件/技能/扩展
PLUGIN_HINTS = [
    "plugin", "插件", "extension", "skill", "技能", "扩展", "market",
    "marketplace", "工具", "addon", "hook", "mcp", "集成", "integration",
]


def _text_of(it: Item) -> str:
    parts = [it.title, it.summary_raw, it.detail, it.author]
    extra = it.extra or {}
    if extra.get("topics"):
        parts.append(" ".join(extra["topics"]))
    return " ".join(str(p) for p in parts if p).lower()


def local_filter(items: List[Item], cfg: Dict[str, Any]) -> Tuple[List[Item], List[Item]]:
    """返回 (通过, 被剔除)。剔除原因写进 extra['_drop']。"""
    f = cfg.get("filter") or {}
    block = [w.lower() for w in (f.get("blocklist") or [])]
    out: List[Item] = []
    dropped: List[Item] = []

    for it in items:
        text = _text_of(it)
        reason = ""
        if not text.strip():
            reason = "无文本"
        else:
            is_plugin = any(h in text for h in PLUGIN_HINTS)
            strong = any(h in text for h in STRONG_HINTS)
            weak = any(h in text for h in TOPIC_HINTS)
            if any(w and w in text for w in block):
                reason = "命中屏蔽词"
            elif f.get("require_topic_hit", True) and not (strong or (weak and is_plugin)):
                reason = "与 DSH 生态无关"
            elif it.source == "github" and not is_plugin:
                reason = "描述里看不出是插件/技能"
            elif any(it.title.lower().startswith(b) for b in (f.get("blacklist_repos") or [])):
                reason = "聚合清单类仓库"
        if reason:
            it.extra["_drop"] = reason
            dropped.append(it)
        else:
            # 先算一个粗分，供排序和截断
            score = 0
            score += sum(2 for h in PLUGIN_HINTS if h in text)
            score += 2 if strong else 1
            it.score = min(score, 9)
            out.append(it)
    return out, dropped


def balance_by_source(items: List[Item], per_source: int = 14) -> List[Item]:
    """每个来源各留 N 条，避免 GitHub 把名额全占了、B站抖音没机会进模型。"""
    buckets: Dict[str, List[Item]] = {}
    for it in items:
        buckets.setdefault(it.source, []).append(it)
    picked: List[Item] = []
    for src, rows in buckets.items():
        rows.sort(key=lambda x: (x.score, x.popularity), reverse=True)
        picked.extend(rows[:per_source])
    picked.sort(key=lambda x: (x.score, x.popularity), reverse=True)
    return picked


SYSTEM_PROMPT = """你是 DeepSeek Harness（DSH，深度求索官方的 AI 编程客户端）生态的插件周报编辑。
用户要从 GitHub / B站 / 抖音 里挑出「最近新出或刚有动静的、真正有用的 DSH 插件或相关工具」，只看功能简介，不需要下载安装。

判断标准：
1. 只留确实和 DeepSeek Harness（DSH）生态相关的插件、技能包、扩展、配套工具；只是普通用 DeepSeek 做的东西不算；
2. 视频类条目：只要它演示/介绍了某个具体的 DSH 插件、并且能从标题+简介看出这个插件干什么，就保留（7 分左右）；
   纯闲聊、纯实况、纯情绪、评论区实录、AI 生成的空壳仓库、引流/破解/灰色内容都算没用；
3. 同一个功能只留最有代表性的一个（优先 GitHub 仓库 > 视频）；如果视频讲的插件在 GitHub 有仓库，那条视频标 3 分；
4. 描述含糊、看不出具体功能的，标 3-4 分，不要硬编功能简介。

评分 0-10：
9-10 明确的新插件/工具，功能清楚、有实用价值
7-8  有用的插件或值得一看的工具，功能能讲清
5-6  沾边，参考价值有限
3-4  教程/讨论/信息量低
0-2  无关、广告、空壳、重复

对 score>=5 的条目，写一条功能简介：
- 中文，35 字以内，只说「它能让 DSH 干什么」，像产品说明；不要「这个视频介绍了…」「该仓库是一个…」「UP主演示了…」这类铺垫，直接写插件本身的功能；
- 不要口号、不要评价好坏、不要重复标题；
- name 给一个简短中文名（≤12 字），category 从这些里选一个：
  界面与体验 / 模型与能力 / 开发与代码 / 内容与数据 / 自动化与效率 / 音视频与媒体 / 其他

严格只输出 JSON，形如：
{"results":[{"id":0,"score":8,"keep":true,"name":"启动动画","category":"界面与体验","feature":"给 DSH 加启动动画画面"}]}
不要输出 JSON 以外的任何字符。"""


def _build_prompt(batch: List[Item]) -> str:
    lines = ["以下是待评估条目（每条含来源、标题、热度、原文摘要），请逐条评估：", ""]
    for i, it in enumerate(batch):
        src = {"github": "GitHub 仓库", "bilibili": "B站视频", "douyin": "抖音视频"}.get(it.source, it.source)
        lines.append(f"[{i}] 来源：{src}")
        lines.append(f"    标题：{it.title}")
        if it.author:
            lines.append(f"    作者：{it.author}")
        meta = []
        if it.published_at:
            meta.append(f"发布 {it.published_at}")
        if it.popularity:
            unit = "star" if it.source == "github" else "播放"
            meta.append(f"{it.popularity} {unit}")
        if meta:
            lines.append("    " + " / ".join(meta))
        body = (it.detail or it.summary_raw or "")[:900].replace("\n", " ")
        if body:
            lines.append(f"    内容：{body}")
        lines.append("")
    return "\n".join(lines)


def _parse_json_block(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^[\s]*\\u0060{3}(?:json)?", "", text)
    text = re.sub(r"\\u0060{3}[\s]*$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def llm_review(items: List[Item], cfg: Dict[str, Any], client: HttpClient) -> Tuple[List[Item], str]:
    """交给模型复核并生成简介。返回 (保留条目, 说明信息)。"""
    llm = cfg.get("llm") or {}
    if not llm.get("enabled", True):
        return _fallback_features(items), "模型复核已关闭（config.llm.enabled=false）"

    key = resolve_api_key(cfg)
    if not key:
        return _fallback_features(items), "没找到 DeepSeek API Key，已退化为关键词摘要"

    batch_size = max(1, int(llm.get("batch_size", 8)))
    max_cand = int(llm.get("max_candidates", 32))
    items = items[:max_cand]
    keep: List[Item] = []
    errors: List[str] = []

    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        payload = {
            "model": llm.get("model", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(batch)},
            ],
            "temperature": float(llm.get("temperature", 0.2)),
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = client.post_json(
                llm.get("base_url", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
                payload,
                headers={"Authorization": "Bearer " + key},
                timeout=int(llm.get("timeout", 120)),
            )
            if not isinstance(resp, dict) or not resp.get("choices"):
                detail = ""
                if isinstance(resp, dict):
                    detail = str((resp.get("error") or {}).get("message") or resp)[:120]
                raise RuntimeError(f"模型接口返回异常：{detail or resp!r}"[:160])
            content = resp["choices"][0]["message"]["content"]
        except Exception as e:
            errors.append(f"批次 {start // batch_size + 1}: {e}")
            keep.extend(_fallback_features(batch))
            continue

        data = _parse_json_block(content)
        results = (data or {}).get("results") or []
        if not results:
            errors.append(f"批次 {start // batch_size + 1}: 模型没返回可解析 JSON")
            keep.extend(_fallback_features(batch))
            continue

        by_id = {int(r.get("id", -1)): r for r in results if isinstance(r, dict)}
        for i, it in enumerate(batch):
            r = by_id.get(i)
            if not r:
                continue
            it.score = int(r.get("score") or 0)
            it.name = (r.get("name") or "").strip()[:16]
            it.category = (r.get("category") or "").strip()[:16]
            it.feature = (r.get("feature") or "").strip()
            if r.get("keep", True) and it.score >= int(llm.get("min_score", 5)):
                keep.append(it)

    note = "模型复核完成"
    if errors:
        note += "（部分批次失败：" + "; ".join(errors[:2]) + "）"
    if not keep and not errors:
        note = "模型认为本周期没有值得写进周报的新插件"
    return keep, note


_CN_STOP = re.compile(r"^(这个|一个|本|该|关于|介绍|分享|推荐)")


def _fallback_features(items: List[Item]) -> List[Item]:
    """没有模型时用原文摘要拼一句像样的简介，保证程序能独立跑通。"""
    out = []
    for it in items:
        text = (it.summary_raw or it.detail or "").strip()
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"^[#\-\*\s]+", "", text)
        # 去掉英文长串与链接，保留可读的中文说明
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\b[A-Za-z0-9_\-]{18,}\b", "", text)
        text = text.strip(" -—·|")
        feature = text[:60] if text else "（原文无描述）"
        it.feature = feature
        it.name = it.name or (it.title[:14] if it.source != "github"
                              else it.title.split("/")[-1][:14])
        it.category = it.category or _guess_category(it)
        it.score = it.score or 5
        out.append(it)
    return out


def _guess_category(it: Item) -> str:
    t = (it.title + " " + it.summary_raw).lower()
    table = [
        ("界面与体验", ["ui", "界面", "主题", "动画", "侧边栏", "外观", "字体"]),
        ("模型与能力", ["model", "模型", "推理", "路由", "context", "prompt"]),
        ("开发与代码", ["code", "代码", "dev", "ide", "git", "编译", "调试"]),
        ("内容与数据", ["数据", "爬", "采集", "搜索", "文档", "notion", "知识库"]),
        ("音视频与媒体", ["视频", "音频", "image", "图片", "语音", "tts", "字幕"]),
        ("自动化与效率", ["自动", "auto", "定时", "批处理", "workflow", "效率"]),
    ]
    for name, words in table:
        if any(w in t for w in words):
            return name
    return "其他"
