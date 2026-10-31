# -*- coding: utf-8 -*-
"""从本机 Edge / Chrome 提取抖音 Cookie，写进 config.json 的 douyin.cookie。

前置条件：
  1. 先用浏览器登录抖音（www.douyin.com），随便搜一次确认能搜出结果；
  2. 完全退出该浏览器（任务管理器里确认 msedge.exe / chrome.exe 都没了），
     否则 Cookie 库被独占锁住（ERROR_SHARING_VIOLATION）。
  3. python tools/get_douyin_cookie.py

读不到时会给出手动方案，不会假成功。
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dpw.util import log


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_unprotect(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise RuntimeError("CryptUnprotectData 失败")
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return out


def _master_key(user_data_dir: Path):
    ls_path = user_data_dir / "Local State"
    if not ls_path.exists():
        return None, "没有 Local State 文件"
    ls = json.loads(ls_path.read_text(encoding="utf-8"))
    os_crypt = ls.get("os_crypt") or {}
    enc = os_crypt.get("encrypted_key")
    if not enc:
        return None, "Local State 里没有 encrypted_key"
    raw = base64.b64decode(enc)
    if raw[:5] != b"DPAPI":
        return None, "encrypted_key 格式异常"
    key = _dpapi_unprotect(raw[5:])
    if os_crypt.get("app_bound_encrypted_key"):
        log("  注意：该浏览器启用了 App-Bound 加密，部分 Cookie 可能解不开")
    return key, ""


def _find_cookies_db(user_data_dir: Path):
    for prof in ("Default", "Profile 1", "Profile 2", "Profile 3"):
        p = user_data_dir / prof / "Network" / "Cookies"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def _decrypt(key: bytes, enc: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if enc[:3] == b"v10":
        return AESGCM(key).decrypt(enc[3:15], enc[15:], None)
    if enc[:3] == b"v20":
        raise RuntimeError("v20 (App-Bound) 无法离线解密")
    return enc   # 未加密


BROWSERS = [
    ("Edge", Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"),
    ("Chrome", Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"),
]


def extract(browser_name: str, user_dir: Path) -> str:
    log(f"检查 {browser_name}: {user_dir}")
    if not user_dir.exists():
        log("  未安装/无数据，跳过")
        return ""
    db = _find_cookies_db(user_dir)
    if not db:
        log("  找不到 Cookies 数据库，跳过")
        return ""
    key, err = _master_key(user_dir)
    if not key:
        log(f"  取主密钥失败：{err}")
        return ""

    tmp = Path(tempfile.gettempdir()) / f"_ck_{browser_name}.db"
    try:
        shutil.copy2(db, tmp)
    except PermissionError:
        log("  数据库被浏览器占用（请先完全退出浏览器再跑一次）")
        return ""
    except Exception as e:
        log(f"  复制失败：{e}")
        return ""

    con = sqlite3.connect(str(tmp))
    rows = con.execute(
        "select host_key, name, encrypted_value from cookies "
        "where host_key like '%douyin%'").fetchall()
    con.close()
    try:
        tmp.unlink()
    except Exception:
        pass

    log(f"  找到 {len(rows)} 条抖音相关 Cookie")
    pairs, failed = [], 0
    for host, name, enc in rows:
        try:
            value = _decrypt(key, enc)
            if value:
                pairs.append(f"{name}={value.decode('utf-8', 'ignore')}")
        except Exception:
            failed += 1
    if failed:
        log(f"  有 {failed} 条解不开（App-Bound 加密）")
    if not pairs:
        return ""
    return "; ".join(pairs)


def main() -> int:
    cfg_path = ROOT / "config.json"
    for name, path in BROWSERS:
        cookie = extract(name, path)
        if cookie:
            cfg = {}
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            cfg.setdefault("douyin", {})["cookie"] = cookie
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"✔ 已写入 config.json（douyin.cookie，{len(cookie)} 字符，来自 {name}）")
            log("  现在可以跑：python run_weekly.py")
            return 0

    log("")
    log("没能自动取到 Cookie。手动方案（30 秒）：")
    log("  1. 浏览器打开 https://www.douyin.com 并登录，随便搜一次「deepseek 插件」；")
    log("  2. 按 F12 → Application/应用 → Storage/存储 → Cookies → https://www.douyin.com；")
    log("  3. 把全部 cookie 复制成一行 name=value; name=value 的形式；")
    log("  4. 粘到 config.json 的 douyin.cookie 字段里（引号保留）；")
    log("  5. 再跑 python run_weekly.py。")
    log("")
    log("抖音搜索接口必须登录，这是平台限制，程序不会假装取到数据。")
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
