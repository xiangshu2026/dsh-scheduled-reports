# -*- coding: utf-8 -*-
"""抖音采集。

抖音的网页搜索接口强制登录（status_code=2483「请先登录，再继续搜索吧」），
所以这里采用：config.douyin.cookie 填浏览器登录后的完整 Cookie 串。
没填 Cookie 时本来源自动跳过，并在报告里明确标注「本周期抖音未采集」，
不会静默假装成功。
"""
from __future__ import annotations

import time
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List

from ..models import Item
from ..util import HttpClient, log, now, TZ

SEARCH = "https://www.douyin.com/aweme/v1/web/general/search/single/"


def _fmt_ts(ts: Any) -> str:
    try:
        ts = int(ts)
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d")
    except Exception:
        return ""


def collect(cfg: Dict[str, Any], client: HttpClient, seen_urls: set,
            status_out: Dict[str, Any] | None = None) -> List[Item]:
    d = cfg["douyin"]
    if not d.get("enabled", True):
        return []
    cookie = (d.get("cookie") or "").strip()
    if not cookie:
        log("  [抖音] 跳过：搜索接口需登录（config.json 的 douyin.cookie 为空，"
            "运行 python tools/get_douyin_cookie.py 可自动提取）")
        return []

    days = int(cfg.get("lookback_days", 7))
    cutoff_ts = int(now().timestamp()) - days * 86400
    headers = {
        "Referer": "https://www.douyin.com/",
        "Cookie": cookie,
    }
    out: List[Item] = []
    seen_id: set = set()

    for kw in d.get("keywords", []):
        q = urllib.parse.quote(kw)
        url = (f"{SEARCH}?keyword={q}&offset=0&count={int(d.get('count_per_keyword', 10))}"
               "&aid=6383&device_platform=webapp&channel=channel_pc_web"
               "&search_channel=aweme_general&search_source=normal_search&query_correct_type=1"
               "&is_filter_search=0")
        try:
            data = client.get_json(url, headers=headers)
        except Exception as e:
            log(f"  [抖音] 搜索失败 kw={kw!r}: {e}")
            continue
        if not isinstance(data, dict) or data.get("status_code") != 0:
            msg = (data or {}).get("status_msg", "")
            log(f"  [抖音] 接口返回 status={str((data or {}).get('status_code'))} {msg[:60]}"
                "（Cookie 可能已过期，重新复制一次即可）")
            continue

        for entry in (data.get("data") or []):
            aweme = entry.get("aweme_info") or {}
            aid = aweme.get("aweme_id") or ""
            if not aid or aid in seen_id:
                continue
            created = int(aweme.get("create_time") or 0)
            if created and created < cutoff_ts:
                continue
            seen_id.add(aid)
            stats = aweme.get("statistics") or {}
            desc = (aweme.get("desc") or "").strip()
            author = ((aweme.get("author") or {}).get("nickname") or "")
            out.append(Item(
                source="douyin",
                kind="video",
                title=(desc.splitlines()[0] if desc else "（无标题）")[:80],
                url=f"https://www.douyin.com/video/{aid}",
                author=author,
                published_at=_fmt_ts(created),
                popularity=int(stats.get("digg_count") or 0),
                summary_raw=desc,
                detail=desc[:1200],
                extra={"aweme_id": aid, "comments": stats.get("comment_count") or 0},
            ))
        time.sleep(1.0)

    out.sort(key=lambda x: (x.published_at, x.popularity), reverse=True)
    out = out[: int(d.get("max_candidates", 40))]
    fresh = [it for it in out if it.url.lower() not in seen_urls]
    for it in fresh:
        seen_urls.add(it.url.lower())
    log(f"  [抖音] 命中 {len(fresh)} 个候选（近 {days} 天）")
    return fresh
