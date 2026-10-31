# -*- coding: utf-8 -*-
"""B 站采集：走公开搜索接口，按发布时间窗过滤。"""
from __future__ import annotations

import time
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List

from ..models import Item
from ..util import HttpClient, log, now, strip_tags, TZ

SEARCH = "https://api.bilibili.com/x/web-interface/search/type"
FINGER = "https://api.bilibili.com/x/frontend/finger/spi"


def _buvid_cookie(client: HttpClient) -> str:
    """免登录也能拿到 buvid3/buvid4，带上后 412 风控概率显著下降。"""
    try:
        data = client.get_json(FINGER, headers={"Referer": "https://www.bilibili.com/"})
        d = (data or {}).get("data") or {}
        b3, b4 = d.get("b_3"), d.get("b_4")
        if b3:
            return f"buvid3={b3}" + (f"; buvid4={b4}" if b4 else "")
    except Exception as e:
        log(f"  [B站] 取 buvid 失败（不影响主流程）：{str(e)[:60]}")
    return ""


def collect(cfg: Dict[str, Any], client: HttpClient, seen_urls: set,
            status_out: Dict[str, Any] | None = None) -> List[Item]:
    b = cfg["bilibili"]
    if not b.get("enabled", True):
        return []

    days = int(cfg.get("lookback_days", 7))
    cutoff_ts = int((now().timestamp())) - days * 86400
    out: List[Item] = []
    seen_bv: set = set()
    headers = {"Referer": "https://www.bilibili.com/", "Origin": "https://www.bilibili.com"}
    cookie = (b.get("cookie") or "").strip()
    if not cookie:
        cookie = _buvid_cookie(client)
        if cookie:
            log("  [B站] 已自动获取 buvid3 匿名 Cookie")
    if cookie:
        headers["Cookie"] = cookie
    blocked = 0

    for kw in b.get("keywords", []):
        for page in range(1, int(b.get("pages_per_keyword", 1)) + 1):
            q = urllib.parse.quote(kw)
            url = f"{SEARCH}?search_type=video&keyword={q}&page={page}&order=pubdate"
            data = None
            for attempt in range(2):
                try:
                    data = client.get_json(url, headers=headers)
                    break
                except Exception as e:
                    msg = str(e)
                    if "412" in msg:
                        if attempt == 0:
                            time.sleep(6)      # 风控冷却后重试一次
                            continue
                        blocked += 1
                        log(f"  [B站] 关键词 {kw!r} 被风控(412)，跳过")
                        break
                    log(f"  [B站] 搜索失败 kw={kw!r}: {msg[:80]}")
                    break
            if data is None:
                continue
            if not isinstance(data, dict) or data.get("code") != 0:
                log(f"  [B站] 接口返回异常 kw={kw!r}: {str(data)[:120]}")
                continue
            results = ((data.get("data") or {}).get("result") or [])
            for r in results:
                bvid = r.get("bvid") or ""
                if not bvid or bvid in seen_bv:
                    continue
                pubdate = int(r.get("pubdate") or 0)
                if pubdate and pubdate < cutoff_ts:
                    continue
                play = int(r.get("play") or 0)
                if play < int(b.get("min_views", 0)):
                    continue
                seen_bv.add(bvid)
                title = strip_tags(r.get("title") or "")
                desc = strip_tags(r.get("description") or "")
                pub = datetime.fromtimestamp(pubdate, TZ).strftime("%Y-%m-%d") if pubdate else ""
                out.append(Item(
                    source="bilibili",
                    kind="video",
                    title=title,
                    url=f"https://www.bilibili.com/video/{bvid}",
                    author=r.get("author") or "",
                    published_at=pub,
                    popularity=play,
                    summary_raw=desc,
                    detail=(desc or title)[:1200],
                    extra={
                        "bvid": bvid,
                        "duration": r.get("duration") or "",
                        "danmaku": r.get("video_review") or 0,
                        "typename": r.get("typename") or "",
                    },
                ))
            time.sleep(1.5)   # 关键词间隔，避免触发风控

    out.sort(key=lambda x: (x.published_at, x.popularity), reverse=True)
    out = out[: int(b.get("max_candidates", 60))]
    out = [it for it in out if not (it.url.lower() in seen_urls)]
    for it in out:
        seen_urls.add(it.url.lower())

    if blocked:
        log(f"  [B站] 有 {blocked} 个关键词被风控(412)，可在 config.json 的 bilibili.cookie 填浏览器 Cookie 缓解")
        if status_out is not None and not out:
            status_out["skipped"] = f"全部关键词被 B站风控(412)，本周期采集不完整"
    log(f"  [B站] 命中 {len(out)} 个候选（近 {days} 天）")
    return out
