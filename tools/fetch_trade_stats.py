#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取官方交易站「词缀统计」接口，把英文版与国服中文版（poe.game.qq.com）按 stat id 对齐。

这两份数据是游戏内 stat description 的原文，覆盖物品词缀、星团珠宝天赋、
技能描述等几乎所有「带数值的文本模板」，英文用 # 作为数值占位符。

用法:
    python tools/fetch_trade_stats.py            # 已有缓存则跳过
    python tools/fetch_trade_stats.py --refresh  # 强制重新抓取

输出: research/trade_cache/stats_en.json / stats_zh.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "research" / "trade_cache"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 60

SOURCES = {
    "en": "https://www.pathofexile.com/api/trade/data/stats",
    "zh": "https://poe.game.qq.com/api/trade/data/stats",
}


def fetch(url: str, path: Path, refresh: bool) -> dict:
    if path.exists() and not refresh and path.stat().st_size > 10000:
        return json.loads(path.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            print(f"  [fetch] {url}: {len(raw):,} bytes", flush=True)
            return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
    print(f"  [error] 抓取失败 {url}: {last}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def flatten(data: dict) -> dict[str, tuple[str, str]]:
    """stat id -> (分组, 文本)"""
    out: dict[str, tuple[str, str]] = {}
    for group in data.get("result", []):
        gid = group.get("id", "?")
        for entry in group.get("entries", []):
            sid = entry.get("id")
            text = (entry.get("text") or "").strip()
            if sid and text:
                out[sid] = (gid, text)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    en = flatten(fetch(SOURCES["en"], CACHE_DIR / "stats_en.json", args.refresh))
    zh = flatten(fetch(SOURCES["zh"], CACHE_DIR / "stats_zh.json", args.refresh))
    common = set(en) & set(zh)
    print(f"\n英文 {len(en)} 条，国服 {len(zh)} 条，按 id 对齐 {len(common)} 条")
    by_group: dict[str, int] = {}
    for sid in common:
        by_group[en[sid][0]] = by_group.get(en[sid][0], 0) + 1
    for gid, n in sorted(by_group.items(), key=lambda kv: -kv[1]):
        print(f"  {gid:<12} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
