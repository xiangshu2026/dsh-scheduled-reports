# -*- coding: utf-8 -*-
"""配置加载：优先 config.json，缺省用内置默认值。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: Dict[str, Any] = {
    "lookback_days": 7,
    "timezone": "+08:00",

    # 代理：null=自动探测 127.0.0.1:7897；""=强制直连；"http://ip:port"=显式
    "proxy": None,

    "github": {
        "enabled": True,
        "token": "",
        "min_stars": 0,
        "max_candidates": 60,
        "fetch_readme_top": 25,
        "queries": [
            "topic:dsh-plugin",
            "topic:deepseek-plugin",
            "dsh-plugin in:name",
            "\"deepseek harness\" plugin in:name,description",
            "deepseek plugin in:name,description,readme",
        ],
    },

    "bilibili": {
        "enabled": True,
        "keywords": [
            "deepseek 插件",
            "dsh 插件",
            "deepseek harness 插件",
            "dsh-plugin",
            "deepseek harness",
        ],
        "pages_per_keyword": 1,
        "min_views": 100,
        "max_candidates": 60,
    },

    "douyin": {
        "enabled": True,
        # 抖音搜索接口必须登录：在浏览器登录抖音后复制完整 Cookie 串填这里。
        # 留空则本来源自动跳过（会在报告里注明）。
        "cookie": "",
        "keywords": ["deepseek 插件", "dsh 插件", "deepseek harness"],
        "count_per_keyword": 10,
        "max_candidates": 40,
    },

    # 本地启发式 + 模型复核
    "filter": {
        "require_topic_hit": True,
        "per_source_quota": 14,
        "blocklist": [
            "破解", "激活码", "免费领取", "加群", "引流", "代充", "私信",
            "翻墙机场", "机场推荐", "梯子", "免备案", "博彩", "下注",
        ],
        "blacklist_repos": ["awesome-", "curated-list"],
    },

    "llm": {
        "enabled": True,
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key": "",          # 留空则自动读 ~/.dsh/.credentials.yaml 的 DEEPSEEK_API_KEY
        "batch_size": 8,
        "max_candidates": 32,
        "min_score": 5,         # 模型打分低于此值不进报告
        "temperature": 0.2,
        "timeout": 120,
    },

    "report": {
        "dir": "reports",
        "keep_latest_copy": True,
        "title_prefix": "DSH 插件周报",
    },

    "state": {
        "path": "_cache/state.json",
        "resend_after_days": 30,   # 老条目多久后允许再出现一次
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str | Path | None = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else ROOT / "config.json"
    user = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8-sig") as f:
            user = json.load(f)
    return _deep_merge(DEFAULTS, user)


def resolve_api_key(cfg: Dict[str, Any]) -> str:
    """LLM key：先看配置，再看环境变量，最后读 DSH 凭据文件。"""
    key = (cfg.get("llm") or {}).get("api_key") or ""
    if key:
        return key.strip()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    cred = Path(os.path.expanduser("~")) / ".dsh" / ".credentials.yaml"
    if cred.exists():
        try:
            import re
            text = cred.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"DEEPSEEK_API_KEY:\s*[\"']?([\w\-]+)", text)
            if m:
                return m.group(1)
        except Exception:
            pass
    return ""
