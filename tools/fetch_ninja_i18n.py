#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 poe.ninja 的 i18n 资源，用于生成「英文 -> 简体中文」界面文案词典。

原理：
  * 站点用 Lingui，界面文案编译成 {id: `xxx`, message: `English`}，
    各语言译文在懒加载的 catalog 模块里（繁中为 zh-tw）。
  * 本脚本遍历主要页面 -> 收集 Astro chunk 入口 -> 递归下载 chunk，
    并从 Lingui 运行时里解析出 zh-tw catalog 文件名后下载。
  * 产物供 build_ninja_terms.py 配对生成 data/ninja_terms.json。

用法: python tools/fetch_ninja_i18n.py [--refresh]
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
CHUNKS = RESEARCH / "ninja_chunks"
BASE_PAGE = "https://poe.ninja"
BASE_ASSET = "https://assets.poe.ninja/_astro/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

PAGES = [
    "/", "/poe1/economy", "/poe1/economy/allflame/currency",
    "/poe1/economy/allflame/fragments", "/poe1/economy/allflame/divination-cards",
    "/poe1/economy/allflame/uniques", "/poe1/economy/allflame/maps",
    "/poe1/economy/allflame/scarabs", "/poe1/economy/allflame/gems",
    "/poe1/economy/allflame/allflame-embers",
    "/poe1/builds", "/poe1/atlas-trees", "/poe1/passive-skill-tree", "/poe1/pob",
    "/poe1/favorites", "/poe1/data",
    "/poe2/economy", "/poe2/builds", "/poe2/passive-skill-tree", "/poe2/pob",
    "/stats", "/docs", "/support", "/account", "/posts", "/privacy",
]

ASSET_RE = re.compile(r"https://assets\.poe\.ninja/_astro/([A-Za-z0-9_.\-]+\.mjs)")
IMPORT_RE = re.compile(r"(?:from\s*|import\()\s*[`\"']\./([A-Za-z0-9_.\-]+\.mjs)[`\"']")
CATALOG_RE = re.compile(r'"zh-tw"\s*:\s*\(\)\s*=>\s*[A-Za-z_$][\w$]*\(\(\)\s*=>\s*import\(`\./([A-Za-z0-9_.\-]+\.mjs)`\)')


def get(url: str, timeout: int = 35) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def download_chunk(name: str, refresh: bool) -> str:
    path = CHUNKS / name
    if path.exists() and path.stat().st_size > 0 and not refresh:
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        text = get(BASE_ASSET + name)
        path.write_text(text, encoding="utf-8")
        time.sleep(0.04)
        return text
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] {name}: {exc}")
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    CHUNKS.mkdir(parents=True, exist_ok=True)

    entries: set[str] = set()
    print("1) 扫描页面，收集 chunk 入口")
    for i, page in enumerate(PAGES, 1):
        try:
            html = get(BASE_PAGE + page, timeout=25)
            found = set(ASSET_RE.findall(html))
            entries.update(found)
            (RESEARCH / "ninja_pages").mkdir(exist_ok=True)
            (RESEARCH / "ninja_pages" / (page.strip("/").replace("/", "_") or "home")).write_text(html, encoding="utf-8")
            print(f"  [{i}/{len(PAGES)}] {page}: {len(found)} chunks", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] {page}: {exc}")
        time.sleep(0.08)

    print(f"2) 递归下载 chunk（入口 {len(entries)} 个）")
    seen: set[str] = set()
    queue = sorted(entries)
    for depth in range(5):
        nxt: set[str] = set()
        for name in queue:
            if name in seen:
                continue
            seen.add(name)
            text = download_chunk(name, args.refresh)
            if text:
                nxt.update(IMPORT_RE.findall(text))
        queue = sorted(nxt - seen)
        print(f"  depth {depth}: 累计 {len(seen)}，新增 {len(queue)}", flush=True)
        if not queue:
            break

    print("3) 定位并下载繁中语言包")
    catalog_name = None
    for p in CHUNKS.glob("*.mjs"):
        text = p.read_text(encoding="utf-8", errors="replace")
        m = CATALOG_RE.search(text)
        if m:
            catalog_name = m.group(1)
            print(f"  在 {p.name} 发现 {catalog_name}")
            break
    if not catalog_name:
        catalog_name = "a.DrpfQUYW.mjs"  # 2026-11 版本兜底
        print(f"  未动态发现，使用兜底 {catalog_name}")
    cat = download_chunk(catalog_name, args.refresh)
    if cat:
        (RESEARCH / "ninja_catalog_zh_tw.mjs").write_text(cat, encoding="utf-8")
        (RESEARCH / "ninja_catalog_name.txt").write_text(catalog_name, encoding="utf-8")
        print(f"  繁中语言包 {len(cat):,} bytes")
    print(f"完成：{len(seen)} 个 chunk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
