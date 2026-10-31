# -*- coding: utf-8 -*-
"""统一条目结构。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass
class Item:
    source: str                      # github / bilibili / douyin
    kind: str                        # repo / video
    title: str
    url: str
    author: str = ""
    published_at: str = ""           # YYYY-MM-DD
    updated_at: str = ""
    popularity: int = 0              # stars / 播放量
    summary_raw: str = ""            # 原始描述或简介
    detail: str = ""                 # README 摘录 / 视频简介（给模型看）
    extra: Dict[str, Any] = field(default_factory=dict)

    # 由筛选阶段填写
    score: int = 0
    name: str = ""
    category: str = ""
    feature: str = ""

    def key(self) -> str:
        return f"{self.source}:{self.url}".lower()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Item":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})
