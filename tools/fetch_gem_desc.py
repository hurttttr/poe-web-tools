#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取编年史技能宝石详情页，提取「技能说明」（og:description），
生成 英文说明 -> 简体中文说明 对照表，供 poe.ninja 技能提示与站点技能面板使用。

说明文本是静态短句（不含数值），正适合按整串精确匹配。

用法:
    python tools/fetch_gem_desc.py            # 使用缓存，只抓缺失页
    python tools/fetch_gem_desc.py --refresh  # 强制重抓

输出: data/gem_desc.json
缓存: research/gem_cache/<lang>_<slug>.html
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import html
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "gem_cache"
PAGE_CACHE = ROOT / "research" / "poedb_cache"
OUT = ROOT / "data" / "gem_desc.json"

BASE = "https://poedb.tw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 30
WORKERS = 4
GAP = 0.12

GEM_PAGES = ["Skill_Gems", "Support_Gems", "Transfigured_Gems", "Trarthus_Gems", "Exceptional"]
SLUG_RE = re.compile(r'<a class="gem_[a-z]+"[^>]*href="/(?:us|cn)/([A-Za-z0-9_\-]+)"')
OG_DESC = re.compile(r'<meta\s+property="og:description"\s+content="(.*?)"\s*/?>', re.S | re.I)
OG_TITLE = re.compile(r'<meta\s+property="og:title"\s+content="(.*?)"\s*/?>', re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
CJK = re.compile(r"[\u3400-\u9fff]")


def clean(value: str) -> str:
    value = TAG_RE.sub("", html.unescape(value))
    return re.sub(r"\s+", " ", value).strip()


def slugs() -> list[str]:
    """从已缓存的宝石分类页里取 slug（中英页面链接一致）。"""
    found: dict[str, None] = {}
    for name in GEM_PAGES:
        path = PAGE_CACHE / f"us_{name}.html"
        if not path.exists():
            continue
        page = path.read_text(encoding="utf-8", errors="replace")
        for slug in SLUG_RE.findall(page):
            found.setdefault(slug, None)
    return list(found)


def fetch_one(lang: str, slug: str, refresh: bool) -> tuple[str, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{lang}_{slug}.html"
    if path.exists() and not refresh and path.stat().st_size > 2000:
        return slug, path.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(
        f"{BASE}/{lang}/{slug}",
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            path.write_text(text, encoding="utf-8")
            time.sleep(GAP)
            return slug, text
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1.2)
    return slug, ""


def parse(page: str) -> tuple[str, str]:
    title = OG_TITLE.search(page)
    desc = OG_DESC.search(page)
    return (clean(title.group(1)) if title else "", clean(desc.group(1)) if desc else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    targets = slugs()
    if not targets:
        print("找不到宝石分类页缓存，请先运行 tools/fetch_poedb.py", flush=True)
        return 1
    print(f"待抓取宝石 {len(targets)} 个，每语言 {len(targets)} 页", flush=True)

    jobs = [(lang, slug) for slug in targets for lang in ("us", "cn")]
    done = 0
    with futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for _slug, _page in pool.map(lambda a: fetch_one(a[0], a[1], args.refresh), jobs):
            done += 1
            if done % 200 == 0:
                print(f"  进度 {done}/{len(jobs)}", flush=True)

    # 统一从缓存解析，天然可重复、可断点续抓
    terms: dict[str, str] = {}
    skipped = 0
    for slug in targets:
        en_title, en_desc = ("", "")
        zh_title, zh_desc = ("", "")
        for lang in ("us", "cn"):
            path = CACHE / f"{lang}_{slug}.html"
            if not path.exists():
                continue
            title, desc = parse(path.read_text(encoding="utf-8", errors="replace"))
            if lang == "us":
                en_title, en_desc = title, desc
            else:
                zh_title, zh_desc = title, desc
        if not en_desc or not zh_desc:
            skipped += 1
            continue
        if en_desc == zh_desc or not CJK.search(zh_desc):
            skipped += 1
            continue
        if len(en_desc) > 600 or len(zh_desc) > 600:
            skipped += 1
            continue
        terms[en_desc] = zh_desc
        # 技能名也顺手补一份（编年史标题与列表页名称可能不同形）
        if en_title and zh_title and en_title != zh_title and CJK.search(zh_title):
            terms.setdefault(en_title, zh_title)

    out = {
        "meta": {
            "source": "流放之路编年史宝石详情页 og:title / og:description 中英对齐",
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "gems": len(targets),
            "entries": len(terms),
            "skipped": skipped,
        },
        "terms": dict(sorted(terms.items(), key=lambda kv: kv[0].lower())),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成: {OUT}  说明/名称 {len(terms)} 条，跳过 {skipped} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
