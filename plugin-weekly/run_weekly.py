# -*- coding: utf-8 -*-
"""DSH 插件周报生成器 —— 主入口。

用法：
    python run_weekly.py                 # 正常跑一次，出本周报告
    python run_weekly.py --dry-run       # 只采集+筛选，不更新去重状态
    python run_weekly.py --days 14       # 临时放宽时间窗
    python run_weekly.py --no-llm        # 不调模型，纯关键词摘要
    python run_weekly.py --source github # 只跑某个来源（可重复）
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dpw import config as cfgmod
from dpw.collectors import bilibili, douyin, github
from dpw.filter import balance_by_source, llm_review, local_filter
from dpw.models import Item
from dpw.report import render_markdown, save_report
from dpw.state import State
from dpw.util import HttpClient, log, now


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="生成 DSH 插件周报")
    p.add_argument("--config", default=None, help="配置文件路径，默认项目内 config.json")
    p.add_argument("--days", type=int, default=None, help="回溯天数，默认读配置")
    p.add_argument("--dry-run", action="store_true", help="不更新去重状态，也不写 latest.md")
    p.add_argument("--no-llm", action="store_true", help="跳过模型复核，用关键词摘要")
    p.add_argument("--source", action="append", choices=["github", "bilibili", "douyin"],
                   help="只跑指定来源，可重复")
    p.add_argument("--out", default=None, help="报告输出目录")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = cfgmod.load(args.config)
    if args.days:
        cfg["lookback_days"] = args.days
    if args.no_llm:
        cfg.setdefault("llm", {})["enabled"] = False

    days = int(cfg.get("lookback_days", 7))
    period_end = now().strftime("%Y-%m-%d")
    period_start = (now() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")

    log("=" * 58)
    log(f"DSH 插件周报 · 周期 {period_start} ~ {period_end}")
    log("=" * 58)

    client = HttpClient(proxy=cfg.get("proxy"))
    log(f"网络：{'走代理 ' + client.proxy if client.proxy else '直连'}")

    # 默认跑所有在 config 里 enabled=true 的来源
    all_sources = ["github", "bilibili", "douyin"]
    if args.source:
        enabled = set(args.source)
    else:
        enabled = {s for s in all_sources if (cfg.get(s) or {}).get("enabled", True)}
    notes = []
    seen_urls: set = set()
    collected: list[Item] = []
    source_stats: dict = {}

    collectors = [("github", github.collect), ("bilibili", bilibili.collect),
                  ("douyin", douyin.collect)]
    for name, fn in collectors:
        if name not in enabled:
            continue
        log(f"[采集] {name}")
        # 抖音：平台强制登录，没配 Cookie 就跳过并如实标注
        if name == "douyin" and not (cfg["douyin"].get("cookie") or "").strip():
            source_stats.setdefault("douyin", {})["skipped"] = (
                "抖音搜索接口需登录，未配置 Cookie")
            notes.append("抖音：未配置 Cookie，本周期跳过采集（平台强制登录）")
            continue
        st = source_stats.setdefault(name, {})
        try:
            got = fn(cfg, client, seen_urls, st) or []
            collected.extend(got)
            st["collected"] = len(got)
        except Exception as e:
            msg = f"{name} 采集失败：{type(e).__name__}: {e}"
            log("  !! " + msg)
            traceback.print_exc()
            notes.append(msg)
            source_stats.setdefault(name, {})["skipped"] = f"采集出错：{type(e).__name__}"

    log(f"[采集] 合计 {len(collected)} 条原始候选")

    # 1) 本地过滤 + 各来源配额（防止 GitHub 挤掉视频来源）
    passed, dropped = local_filter(collected, cfg)
    log(f"[筛选] 本地过滤后 {len(passed)} 条（剔除 {len(dropped)} 条）")
    passed = balance_by_source(passed, int(cfg["filter"].get("per_source_quota", 14)))
    log(f"[筛选] 分来源配额后 {len(passed)} 条进入复核")

    # 2) 历史去重
    state_path = Path(cfg["state"]["path"])
    if not state_path.is_absolute():
        state_path = cfgmod.ROOT / state_path
    state = State(state_path, int(cfg["state"].get("resend_after_days", 30)))
    fresh, old = state.filter_new(passed)
    log(f"[去重] 新条目 {len(fresh)} 条，往期已报过 {len(old)} 条")

    # 3) 模型复核 + 写简介
    keep, note = llm_review(fresh, cfg, client)
    notes.append(note)
    log(f"[复核] 保留 {len(keep)} 条 — {note}")

    # 4) 出报告
    rep_cfg = cfg.get("report") or {}
    ctx = {
        "title_prefix": rep_cfg.get("title_prefix", "DSH 插件周报"),
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": now().strftime("%Y-%m-%d %H:%M"),
        "notes": notes,
        "dropped_summary": dropped,
        "source_stats": source_stats,
        "enabled_sources": [s for s in all_sources if s in enabled],
    }
    markdown = render_markdown(keep, ctx)

    def _resolve(p: str) -> Path:
        path = Path(os.path.expandvars(os.path.expanduser(str(p))))
        return path if path.is_absolute() else cfgmod.ROOT / path

    stamp = period_end + ("-dryrun" if args.dry_run else "")
    paths: dict = {}
    filename = rep_cfg.get("filename", "DSH插件周报")

    # 主输出：桌面 DSH-Reports/<日期>/ 下只放 docx（和该目录其他报告格式统一）
    main_dir = Path(args.out) if args.out else _resolve(rep_cfg.get("dir", "reports"))
    target_dir = main_dir / stamp if rep_cfg.get("dated_subfolder", True) else main_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    if rep_cfg.get("docx", True):
        try:
            from dpw.docx_report import render_docx
            docx_path = render_docx(keep, ctx, target_dir / f"{filename}-{stamp}.docx")
            paths["docx"] = str(docx_path)
        except Exception as e:
            log(f"  !! docx 生成失败（md 仍会保留）：{type(e).__name__}: {e}")
            notes.append(f"docx 生成失败：{type(e).__name__}")

    # 项目内备份：md + json + latest.md（不进桌面）
    local_dir = _resolve(rep_cfg.get("local_backup_dir") or "reports")
    if local_dir.resolve() != main_dir.resolve():
        paths.update(save_report(
            markdown, keep, ctx, local_dir,
            keep_latest=bool(rep_cfg.get("keep_latest_copy", True)) and not args.dry_run,
            dated=False,
            filename="weekly",
            stamp_override=stamp,
        ))

    if not args.dry_run:
        state.mark(keep)
        state.save()

    log("-" * 58)
    log(f"完成：{len(keep)} 条已写入")
    for k, v in paths.items():
        log(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("已中断")
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
