# -*- coding: utf-8 -*-
"""去重状态：记住已报过的条目，避免每周重复。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from .models import Item
from .util import now, TZ


class State:
    def __init__(self, path: Path, resend_after_days: int = 30):
        self.path = path
        self.resend_after_days = resend_after_days
        self.data: Dict[str, Any] = {"items": {}}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {"items": {}}
        self.data.setdefault("items", {})

    def filter_new(self, items: List[Item]) -> tuple[List[Item], List[Item]]:
        """返回 (新条目, 老条目)。超过 resend_after_days 的老条目会重新出现。"""
        fresh, old = [], []
        expire = now() - timedelta(days=self.resend_after_days)
        for it in items:
            rec = self.data["items"].get(it.key())
            if not rec:
                fresh.append(it)
                continue
            try:
                first = datetime.strptime(rec.get("first_seen", ""), "%Y-%m-%d").replace(tzinfo=TZ)
            except Exception:
                fresh.append(it)
                continue
            (old if first > expire else fresh).append(it)
        return fresh, old

    def mark(self, items: List[Item]) -> None:
        today = now().strftime("%Y-%m-%d")
        for it in items:
            k = it.key()
            rec = self.data["items"].setdefault(k, {"first_seen": today})
            rec["last_seen"] = today
            rec["title"] = it.title[:120]
            rec["source"] = it.source

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
