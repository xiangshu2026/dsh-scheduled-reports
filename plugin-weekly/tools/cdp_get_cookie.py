# -*- coding: utf-8 -*-
"""通过 Edge/Chrome 的 CDP 远程调试端口读取 Cookie。

为什么需要这个：
  · Edge 127+ 启用 App-Bound 加密（v20），Cookie 库里的 encrypted_value
    用离线 DPAPI 解不开；
  · Edge 136+ 又对「默认 profile」禁用了 --remote-debugging-port。
  · 唯一可行的办法：把关键 profile 文件复制到临时目录（绕开默认 profile 限制），
    用 CDP 启动浏览器让它自己解密，再通过 Storage.getCookies 拿明文。

用法：
    python tools/cdp_get_cookie.py            # 读抖音 Cookie 并写入 config.json
    python tools/cdp_get_cookie.py bilibili   # 读 B站 Cookie
    python tools/cdp_get_cookie.py douyin --browser chrome

前提：目标浏览器必须完全退出（否则复制不到最新的 Cookie 库）。
脚本会自动启动一个（移到屏幕外的）浏览器实例，读完自动关闭。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dpw.util import log

BROWSERS = {
    "edge": {
        "exe": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "user_data": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data",
        "proc": "msedge.exe",
    },
    "chrome": {
        "exe": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "user_data": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
        "proc": "chrome.exe",
    },
}

# 每个来源需要哪些 cookie 域名
DOMAINS = {
    "douyin": [".douyin.com", "douyin.com", ".iesdouyin.com"],
    "bilibili": [".bilibili.com", "bilibili.com"],
}


def _is_running(proc_name: str) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {proc_name}"],
                             capture_output=True, text=True, timeout=10)
        return proc_name.lower() in (out.stdout or "").lower()
    except Exception:
        return False


def _http_json(url: str, timeout: float = 3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


class CDP:
    def __init__(self, ws_url: str):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=20,
                                              suppress_origin=True)
        self.seq = 0

    def call(self, method: str, params: dict | None = None, timeout: float = 15):
        self.seq += 1
        msg = {"id": self.seq, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv()
            if not raw:
                continue
            data = json.loads(raw)
            if data.get("id") == self.seq:
                if "error" in data:
                    raise RuntimeError(f"{method} 失败: {data['error']}")
                return data.get("result")
        raise TimeoutError(f"{method} 超时")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


# 各站点用来"激活" cookie 上下文的页面
ACTIVATE_URL = {
    "douyin": "https://www.douyin.com/",
    "bilibili": "https://www.bilibili.com/",
}

# 复制到临时 profile 的关键文件（整个 User Data 有 2.5GB，只拿这几个就够）
PROFILE_FILES = [
    ("Local State", "Local State"),
    ("Default/Network/Cookies", "Default/Network/Cookies"),
    ("Default/Preferences", "Default/Preferences"),
]


def extract_cookies(browser: str, site: str, domains: list[str],
                    port: int = 9699) -> dict[str, str]:
    """复制关键 profile 文件到临时目录，用 CDP 让浏览器自己解密 Cookie。

    为什么这么绕：
      · Edge 136+ 对「默认 profile」禁用 --remote-debugging-port（防 cookie 窃取）
      · Edge 127+ 用 App-Bound 加密（v20），离线 DPAPI 解不开
      · 所以只能：复制关键文件 → 用非默认路径启动（绕开调试限制）→
        让浏览器自己解密 → 通过 CDP 的 Storage.getCookies 拿明文
      · 必须非 headless，且先导航到目标站，否则 cookie 上下文不会初始化
    """
    import shutil

    cfg = BROWSERS[browser]
    user_data = cfg["user_data"]
    if not user_data.exists():
        raise RuntimeError(f"{browser} 没有用户数据目录：{user_data}")

    exe = next((p for p in cfg["exe"] if os.path.exists(p)), None)
    if not exe:
        raise RuntimeError(f"找不到 {browser} 的可执行文件")

    tmp = Path(tempfile.gettempdir()) / f"_dsh_cookie_{browser}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "Default" / "Network").mkdir(parents=True, exist_ok=True)

    copied = 0
    for rel_src, rel_dst in PROFILE_FILES:
        s = user_data / rel_src
        d = tmp / rel_dst
        if s.exists():
            shutil.copy2(s, d)
            copied += 1
    # WAL / journal 也带上，避免最近写入的 cookie 丢失
    for extra in ("Cookies-wal", "Cookies-journal"):
        s = user_data / "Default" / "Network" / extra
        if s.exists():
            shutil.copy2(s, tmp / "Default" / "Network" / extra)
    if copied < 2:
        raise RuntimeError("关键 profile 文件没复制成功")
    log(f"  已复制 profile 关键文件 {copied} 个到临时目录")

    proc = subprocess.Popen([
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={tmp}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-position=-2400,-2400",   # 挪到屏幕外，少打扰
        "--window-size=800,600",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        ver = None
        for _ in range(60):
            time.sleep(0.5)
            try:
                ver = _http_json(f"http://127.0.0.1:{port}/json/version")
                break
            except Exception:
                continue
        if not ver:
            raise RuntimeError("CDP 调试端口没起来")
        log(f"  CDP 已连接：{ver.get('Browser')}")

        ws_url = ver.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError("CDP 没返回 webSocketDebuggerUrl")

        cdp = CDP(ws_url)
        try:
            # 关键：先建一个页面导航到目标站，触发 cookie 上下文初始化
            target_url = ACTIVATE_URL.get(site, "about:blank")
            cdp.call("Target.createTarget", {"url": target_url})
            log(f"  已打开 {target_url} 激活 cookie 上下文 …")
            time.sleep(8)

            result = cdp.call("Storage.getCookies", {}, timeout=25)
        finally:
            cdp.close()

        cookies = (result or {}).get("cookies") or []
        log(f"  浏览器里共 {len(cookies)} 条 Cookie")

        picked: dict[str, str] = {}
        for c in cookies:
            domain = (c.get("domain") or "").lower()
            if any(domain == d or domain.endswith(d.lstrip(".")) or domain.endswith(d)
                   for d in domains):
                name = c.get("name")
                value = c.get("value")
                if name and value is not None:
                    picked[name] = value
        return picked
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    site = argv[0] if argv else "douyin"
    browser = "edge"
    if "--browser" in argv:
        browser = argv[argv.index("--browser") + 1]

    if site not in DOMAINS:
        log(f"不认识的站点：{site}（可选：{', '.join(DOMAINS)}）")
        return 1

    cfg = BROWSERS[browser]
    if _is_running(cfg["proc"]):
        log(f"{browser} 还在运行，请先完全退出（任务管理器结束 {cfg['proc']}）")
        return 1

    log(f"从 {browser} 读取 {site} 的 Cookie …")
    try:
        picked = extract_cookies(browser, site, DOMAINS[site])
    except Exception as e:
        log(f"失败：{e}")
        return 1

    if not picked:
        log(f"没找到 {site} 的 Cookie —— 请先在 {browser} 里登录 {site} 再试")
        return 1

    # 关键 cookie 检查
    keys = set(picked)
    important = {
        "douyin": ["sessionid", "sessionid_ss", "sid_guard", "uid_tt", "ttwid"],
        "bilibili": ["SESSDATA", "bili_jct", "DedeUserID", "buvid3"],
    }[site]
    hit = [k for k in important if k in keys]
    log(f"  取到 {len(picked)} 条，关键项命中 {len(hit)}/{len(important)}：{', '.join(hit) or '无'}")
    if site == "douyin" and "sessionid" not in keys and "sessionid_ss" not in keys:
        log("  警告：没有 sessionid，可能没登录成功，抖音搜索仍会要求登录")

    cookie_str = "; ".join(f"{k}={v}" for k, v in picked.items())
    cfg_path = ROOT / "config.json"
    data = {}
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    data.setdefault(site, {})["cookie"] = cookie_str
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  已写入 config.json 的 {site}.cookie（{len(cookie_str)} 字符）")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
