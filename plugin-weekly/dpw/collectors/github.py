# -*- coding: utf-8 -*-
"""GitHub 采集：搜 DSH / DeepSeek 插件仓库，按时间窗过滤。

限速说明（重要）：
  匿名调用 搜索 API 是 10 次/分钟、核心 API 60 次/小时；
  填了 token 后搜索 30 次/分钟、核心 5000 次/小时。
  所以这里默认只跑「合并后的少量查询」，且 README 抓取也做了额度保护；
  一旦探测到额度耗尽，立刻停止后续请求，把这个来源标记成「限速未采集」，
  不会静默假装没有新内容。
"""
from __future__ import annotations

import time
import urllib.parse
from datetime import timedelta
from typing import Any, Dict, List

from ..models import Item
from ..util import HttpClient, log, now, iso_date, strip_tags

API = "https://api.github.com"

# 一次运行最多消耗多少次「核心 API」（README 抓取）调用
CORE_CALL_BUDGET = 40


def _headers(token: str) -> Dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = "Bearer " + token
    return h


def _quota(client: HttpClient, headers: Dict[str, str]) -> Dict[str, int]:
    """查当前额度（这一步本身不计费）。"""
    try:
        data = client.get_json(f"{API}/rate_limit", headers=headers)
        return (data or {}).get("resources") or {}
    except Exception:
        return {}


def _remaining(resources: Dict[str, Any], name: str) -> int:
    return int(((resources.get(name) or {}).get("remaining")) or 0)


_RAW_CANDIDATES = ["README.md", "readme.md", "README.MD", "Readme.md",
                   "README.rst", "README", "README.txt"]


def _readme_via_raw(client: HttpClient, full_name: str, branch: str) -> str:
    """不占 API 额度：直接走 raw.githubusercontent.com 猜常见 README 文件名。"""
    for fname in _RAW_CANDIDATES:
        url = f"https://raw.githubusercontent.com/{full_name}/{branch}/{fname}"
        status, body = client.request(url)
        if status == 200 and body and "# " in body + " ":
            return body
    return ""


def _readme_excerpt(client: HttpClient, full_name: str, headers: Dict[str, str],
                    branch: str = "HEAD", limit: int = 2500) -> str:
    """取 README 纯文本，抽成一段能读的摘录（跳过 badge / 图片 / 标题）。"""
    url = f"{API}/repos/{full_name}/readme"
    h = dict(headers)
    h["Accept"] = "application/vnd.github.raw"
    status, body = client.request(url, headers=h)
    if status != 200 or not body:
        # API 额度不足时退回 raw 域名（不计额度）
        body = _readme_via_raw(client, full_name, branch)
        if not body:
            return ""
    lines: List[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith(("[![", "![", "<img", "<p align", "<div align", "---", "===")):
            continue
        if line.startswith("#"):
            if line.count("#") == 1:
                continue
            line = line.lstrip("#").strip()
        if low.startswith(("badge", "[license", "[prs", "[issues", "[stars")):
            continue
        line = strip_tags(line)
        if not line or line.lower() in {"table of contents", "目录"}:
            continue
        lines.append(line)
        if sum(len(x) for x in lines) > limit:
            break
    return " ".join(lines)[:limit]


def collect(cfg: Dict[str, Any], client: HttpClient, seen_urls: set,
            status_out: Dict[str, Any] | None = None) -> List[Item]:
    """采集 GitHub 上的 DSH 插件仓库。

    额度策略（针对匿名 60 次/时 的现实）：
      - 只发 2-3 次搜索请求（per_page=100 一次拿满）
      - README 一律走 raw.githubusercontent.com（不占 API 额度）
      - 每次搜索之间等 6.5 秒，避免撞「每分钟 10 次」的搜索限速
    """
    g = cfg["github"]
    if not g.get("enabled", True):
        return []

    def note_status(key: str, val: Any) -> None:
        if status_out is not None:
            status_out[key] = val

    days = int(cfg.get("lookback_days", 7))
    cutoff = now() - timedelta(days=days)
    token = (g.get("token") or "").strip()
    headers = _headers(token)

    res = _quota(client, headers)
    if res:
        search_left = _remaining(res, "search")
        core_left = _remaining(res, "core")
        log(f"  [GitHub] 剩余额度：搜索 {search_left} 次 / 核心 {core_left} 次"
            f"（{'已填 token' if token else '匿名模式'}）")
        if search_left <= 0:
            msg = ("GitHub 搜索额度已用尽（匿名每小时 60 次核心 / 每分钟 10 次搜索），"
                   "本周期跳过。填 config.github.token 可提到 5000 次/时")
            log("  [GitHub] " + msg)
            note_status("skipped", msg)
            return []
    else:
        search_left, core_left = 10, 60

    out: List[Item] = []
    seen_repo: set = set()
    queries = g.get("queries", [])
    max_cand = int(g.get("max_candidates", 60))
    search_used = 0
    hit_limit = False

    for q in queries:
        if search_left - search_used <= 0:
            hit_limit = True
            break
        url = (f"{API}/search/repositories?q={urllib.parse.quote(q)}"
               f"&sort=updated&order=desc&per_page=100")
        try:
            data = client.get_json(url, headers=headers)
        except Exception as e:
            log(f"  [GitHub] 查询失败 q={q!r}: {str(e)[:120]}")
            continue
        search_used += 1
        if isinstance(data, dict) and data.get("message"):
            msg = str(data.get("message"))[:120]
            log(f"  [GitHub] API 消息: {msg}")
            hit_limit = "rate limit" in msg.lower()
            if hit_limit:
                break
            continue

        for repo in (data or {}).get("items", []):
            full = repo.get("full_name", "")
            if not full or full.lower() in seen_repo:
                continue
            pushed = (repo.get("pushed_at") or "")[:10]
            created = (repo.get("created_at") or "")[:10]
            active = pushed and pushed >= iso_date(cutoff)
            fresh = created and created >= iso_date(cutoff)
            if not (active or fresh):
                continue
            if repo.get("archived") or repo.get("fork"):
                continue
            stars = int(repo.get("stargazers_count") or 0)
            if stars < int(g.get("min_stars", 0)):
                continue
            seen_repo.add(full.lower())
            out.append(Item(
                source="github",
                kind="repo",
                title=full,
                url=repo.get("html_url", ""),
                author=(repo.get("owner") or {}).get("login", ""),
                published_at=created,
                updated_at=pushed,
                popularity=stars,
                summary_raw=(repo.get("description") or "").strip(),
                extra={
                    "topics": repo.get("topics") or [],
                    "language": repo.get("language") or "",
                    "forks": repo.get("forks_count") or 0,
                    "default_branch": repo.get("default_branch") or "HEAD",
                    "is_new": bool(fresh),
                },
            ))
        if len(out) >= max_cand:
            break
        time.sleep(6.5)   # 搜索接口 10 次/分钟，留足间隔

    if hit_limit and not out:
        msg = "GitHub 搜索额度在采集过程中耗尽，本周期数据不完整"
        log("  [GitHub] " + msg)
        note_status("skipped", msg)

    # 热度优先，取前 N 个抓 README
    out.sort(key=lambda x: (x.extra.get("is_new", False), x.popularity), reverse=True)
    out = out[:max_cand]
    want = int(g.get("fetch_readme_top", 25))
    got_readme = 0
    for it in out[:want]:
        branch = it.extra.get("default_branch") or "HEAD"
        # 先走 raw 域名（不占额度），失败才用 API
        it.detail = _readme_via_raw(client, it.title, branch)
        if not it.detail:
            it.detail = _readme_excerpt(client, it.title, headers, branch)
        if it.detail:
            got_readme += 1
        else:
            it.detail = it.summary_raw or ""
        time.sleep(0.1)
    for it in out[want:]:
        it.detail = it.summary_raw or ""
    if want:
        log(f"  [GitHub] README 抓到 {got_readme}/{min(want, len(out))} 个")

    fresh_items = [it for it in out if it.url.lower() not in seen_urls]
    for it in fresh_items:
        seen_urls.add(it.url.lower())

    if not out:
        log("  [GitHub] 0 个候选（可能额度不足或本周期确实没有新仓库）")
    else:
        log(f"  [GitHub] 命中 {len(fresh_items)} 个候选（近 {days} 天有动静）")
    return fresh_items
