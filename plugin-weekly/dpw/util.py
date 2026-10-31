# -*- coding: utf-8 -*-
"""HTTP 与会话工具：统一 UA、超时、重试、可选代理、日志。"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    return datetime.now(TZ)


def log(msg: str) -> None:
    stamp = now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("utf-8", "replace").decode("utf-8", "replace"), flush=True)


class HttpClient:
    """带重试的简易 HTTP 客户端。proxy=None 自动探测本机 7897。"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 25, retries: int = 2):
        self.proxy = self._detect_proxy(proxy)
        self.timeout = timeout
        self.retries = retries
        handlers = []
        if self.proxy:
            handlers.append(urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}))
        else:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    @staticmethod
    def _detect_proxy(proxy: Optional[str]) -> Optional[str]:
        if proxy == "":
            return None
        if proxy:
            return proxy
        env = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
        if env:
            return env
        # 自动探测 Clash 默认端口
        import socket
        for port in (7897, 7890, 10809):
            s = socket.socket()
            s.settimeout(0.3)
            try:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return f"http://127.0.0.1:{port}"
            finally:
                s.close()
        return None

    def request(self, url: str, headers: Optional[Dict[str, str]] = None,
                data: Optional[bytes] = None, method: Optional[str] = None,
                timeout: Optional[int] = None) -> tuple[int, str]:
        h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
        if headers:
            h.update(headers)
        last_err = ""
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=h, method=method)
                with self.opener.open(req, timeout=timeout or self.timeout) as r:
                    raw = r.read()
                    return r.status, raw.decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", "ignore")
                except Exception:
                    pass
                last_err = f"HTTP {e.code}: {body[:200]}"
                if e.code in (403, 404, 401):
                    return e.code, body
                time.sleep(1.5 * (attempt + 1))
            except Exception as e:  # 网络类错误
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
        return 0, last_err

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None,
                 timeout: Optional[int] = None) -> Any:
        status, body = self.request(url, headers=headers, timeout=timeout)
        if status == 0:
            raise RuntimeError(body)
        return json.loads(body)

    def post_json(self, url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None,
                  timeout: Optional[int] = None) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        status, body = self.request(url, headers=h, data=data, method="POST", timeout=timeout)
        if status == 0:
            raise RuntimeError(body)
        return json.loads(body)


def strip_tags(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", "", text or "")
    return (text.replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")).strip()


def iso_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def days_ago(days: int) -> datetime:
    return now() - timedelta(days=days)
