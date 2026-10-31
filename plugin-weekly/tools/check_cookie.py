# -*- coding: utf-8 -*-
"""校验 config.json 里配置的 Cookie 是否真的能用。

用法：
    python tools/check_cookie.py            # 检查所有已配置的
    python tools/check_cookie.py douyin     # 只查抖音
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dpw.util import HttpClient, log


def check_douyin(cookie: str, client: HttpClient) -> bool:
    q = urllib.parse.quote("deepseek 插件")
    url = ("https://www.douyin.com/aweme/v1/web/general/search/single/"
           f"?keyword={q}&offset=0&count=5&aid=6383&device_platform=webapp"
           "&channel=channel_pc_web&search_channel=aweme_general"
           "&search_source=normal_search&query_correct_type=1&is_filter_search=0")
    try:
        data = client.get_json(url, headers={
            "Referer": "https://www.douyin.com/", "Cookie": cookie})
    except Exception as e:
        log(f"  请求失败：{e}")
        return False
    code = (data or {}).get("status_code")
    msg = (data or {}).get("status_msg", "")
    if code == 0:
        n = len((data or {}).get("data") or [])
        log(f"  抖音 Cookie 可用：搜到 {n} 条结果")
        return True
    log(f"  抖音 Cookie 不可用：status_code={code} {msg}")
    if code == 2483:
        log("  → 说明 Cookie 里没有有效的登录态（sessionid），请重新复制完整 Cookie")
    return False


def check_bilibili(cookie: str, client: HttpClient) -> bool:
    url = ("https://api.bilibili.com/x/web-interface/search/type"
           "?search_type=video&keyword=deepseek&page=1")
    try:
        data = client.get_json(url, headers={
            "Referer": "https://www.bilibili.com/", "Cookie": cookie})
    except Exception as e:
        log(f"  请求失败：{e}")
        return False
    if (data or {}).get("code") == 0:
        log(f"  B站 Cookie 可用：搜到 {len((data.get('data') or {}).get('result') or [])} 条")
        return True
    log(f"  B站 Cookie 异常：code={(data or {}).get('code')} {(data or {}).get('message')}")
    return False


CHECKS = {"douyin": check_douyin, "bilibili": check_bilibili}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cfg_path = ROOT / "config.json"
    if not cfg_path.exists():
        log("找不到 config.json")
        return 1
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    client = HttpClient(proxy=cfg.get("proxy"))

    targets = argv or [k for k in CHECKS if (cfg.get(k) or {}).get("cookie")]
    if not targets:
        log("config.json 里没有任何已配置的 Cookie")
        return 1

    ok_all = True
    for site in targets:
        cookie = ((cfg.get(site) or {}).get("cookie") or "").strip()
        log(f"[{site}]")
        if not cookie:
            log("  未配置 Cookie")
            ok_all = False
            continue
        log(f"  Cookie 长度 {len(cookie)} 字符")
        if not CHECKS[site](cookie, client):
            ok_all = False
    return 0 if ok_all else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
