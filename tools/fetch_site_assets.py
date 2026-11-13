#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载 FilterBlade 的静态界面文案源到 research/，供 extract_site_text.py 分析。

站点前端是纯静态资源，界面文案主要在这些文件里：
  datafiles/optionfiles/StyleSummary.options   Overview / Start 页（分区标题、说明、信息框）
  datafiles/optionfiles/optionFile*.options    Customizer 规则名与说明（文件名哈希随版本变化）
  datafiles/weighting/LootGenerator.options   Loot Simulator
  datafiles_Shared/faqContent.json            FAQ 问答
  datafiles/other/newsFile.txt / economies.json
  index.html / filterblade.min.js             静态 UI 与前端代码

用法: python tools/fetch_site_assets.py [--refresh]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
BASE = "https://www.filterblade.xyz"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

STATIC = {
    "index.html": "/?game=Poe1",
    "fb.min.js": "/filterblade.min.js",
    "StyleSummary.options": "/datafiles/optionfiles/StyleSummary.options",
    "LootGenerator.options": "/datafiles/weighting/LootGenerator.options",
    "faqContent.json.out": "/datafiles_Shared/faqContent.json",
    "newsFile.txt.out": "/datafiles/other/newsFile.txt",
    "economies.json": "/datafiles/other/economies.json",
    "bonusItemInfo.json": "/datafiles/other/bonusItemInfo.json",
}


def get(path: str) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", errors="replace")


def save(name: str, path: str, refresh: bool) -> None:
    target = RESEARCH / name
    if target.exists() and target.stat().st_size > 100 and not refresh:
        print(f"  [cache] {name}")
        return
    try:
        text = get(path)
        target.write_text(text, encoding="utf-8")
        print(f"  [fetch] {name}: {len(text):,} bytes")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] {name} 下载失败: {exc}", file=sys.stderr)
    time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    RESEARCH.mkdir(parents=True, exist_ok=True)

    print("下载站点静态文案源")
    for name, path in STATIC.items():
        save(name, path, args.refresh)

    # optionFile 文件名带版本哈希，从前端脚本里自动发现
    fb = (RESEARCH / "fb.min.js").read_text(encoding="utf-8", errors="replace")
    names = sorted(set(re.findall(r"optionfiles/([A-Za-z0-9_]+\.options)", fb)))
    print(f"发现 option 文件: {names}")
    for name in names:
        save(name, "/datafiles/optionfiles/" + name, args.refresh)

    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
