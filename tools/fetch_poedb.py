#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从流放之路编年史 (poedb.tw) 抓取简体中文版 /cn/ 与英文版 /us/ 页面，
按「条目链接 slug」对齐，生成 英文 -> 简体中文 对照表。

用法:
    python tools/fetch_poedb.py            # 使用本地缓存(若存在)，只抓缺失页面
    python tools/fetch_poedb.py --refresh # 强制重新抓取全部页面

输出: data/poedb_items.json
缓存: research/poedb_cache/<lang>_<slug>.html
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "research" / "poedb_cache"
OUT_FILE = ROOT / "data" / "poedb_items.json"

BASE = "https://poedb.tw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REQUEST_GAP = 0.25  # 对源站保持礼貌
TIMEOUT = 35

# 物品分类页。来自 https://poedb.tw/cn/Items 的物品区链接，
# 以及与过滤器 Tier List 强相关的通货/赛季物品页面。
CATEGORIES = [
    # 基底 / 装备
    "Claws", "Daggers", "Wands", "One_Hand_Swords", "One_Hand_Axes",
    "One_Hand_Maces", "Sceptres", "Rune_Daggers", "Thrusting_One_Hand_Swords",
    "Bows", "Staves", "Two_Hand_Swords", "Two_Hand_Axes", "Two_Hand_Maces",
    "Warstaves", "Fishing_Rods", "Quivers", "Shields", "Gloves", "Boots",
    "Body_Armours", "Helmets", "Amulets", "Rings", "Belts", "Trinkets",
    "Life_Flasks", "Mana_Flasks", "Utility_Flasks", "Tinctures",
    # 通货与赛季物品
    "Stackable_Currency", "Oil", "Fossil", "Vial", "Blessing", "Tattoo",
    "Runegraft", "Omen", "Essence", "Splinter", "Catalysts", "Scarab",
    "Delirium_Orb", "Incubators", "Corpses", "Embers_of_the_Allflame",
    "Resonator", "Cluster_Jewel", "Timeless_Jewel", "Jewels", "Abyss_Jewels",
    # 地图与卡片
    "Maps", "Map_Fragments", "Misc_Map_Items", "Expedition_Logbooks",
    "Breachstones", "Vault_Keys", "Sanctum_Research", "Relics", "Pieces",
    "Divination_Cards", "Hideout_Doodads", "Emblem", "Lure", "Astrolabe",
    # 宝石与契约
    "Skill_Gems", "Support_Gems", "Transfigured_Gems", "Trarthus_Gems",
    "Exceptional", "Contracts", "Blueprints", "Heist_Targets", "Heist_Gear",
    "Heist_Tools", "Heist_Cloaks", "Heist_Brooches",
    # 传奇与总览
    "Unique_item", "Replica_unique_item", "Foulborn", "Items",
]

# 页面里可能出现但不该进词典的链接文本前缀
BAD_TEXT = re.compile(r"^(?:GGG Tracker|Privacy|Patreon|Economy|Home|Login|Forum|News|Search|Reset|More|Details?|Show|Hide|Edit|Back|Next|Previous|Top|Wiki|PoEDB|Items|Unique|Currency|Maps?)$", re.I)
TAG_RE = re.compile(r"<[^>]+>")
LINK_RE = re.compile(r"<a\s[^>]*?href=\"(?:/(?:us|cn)/)?([A-Za-z0-9_\-]+)\"[^>]*?>(.*?)</a>", re.S | re.I)
CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def fetch(lang: str, slug: str, refresh: bool) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{lang}_{slug}.html"
    if path.exists() and not refresh and path.stat().st_size > 2000:
        return path.read_text(encoding="utf-8", errors="replace")

    url = f"{BASE}/{lang}/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            path.write_text(text, encoding="utf-8")
            print(f"  [fetch] {lang}/{slug}: {len(text):,} bytes", flush=True)
            time.sleep(REQUEST_GAP)
            return text
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            time.sleep(1.2)
    print(f"  [warn] {lang}/{slug} 抓取失败: {last_err}", file=sys.stderr, flush=True)
    return ""


def clean_text(raw: str) -> str:
    raw = TAG_RE.sub("", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def collect(page: str, want_cjk: bool) -> dict[str, str]:
    """提取 slug -> 显示名。中文页只要含汉字的文本，英文页只要纯拉丁文本。"""
    out: dict[str, str] = {}
    for slug, raw in LINK_RE.findall(page):
        text = clean_text(raw)
        if not text or len(text) > 90 or BAD_TEXT.match(text):
            continue
        if want_cjk:
            if not CJK_RE.search(text):
                continue
        else:
            if CJK_RE.search(text) or not LATIN_RE.search(text):
                continue
            if not re.fullmatch(r"[A-Za-z0-9'’\- .:()&,/+!%]+", text):
                continue
        # 跳过明显是说明文字而非名称的内容
        if text.count(" ") > 12:
            continue
        out.setdefault(slug, text)
    return out


def align(slug: str, cn_page: str, us_page: str) -> dict[str, str]:
    cn = collect(cn_page, want_cjk=True)
    us = collect(us_page, want_cjk=False)
    pairs: dict[str, str] = {}
    for key in cn.keys() & us.keys():
        en, zh = us[key], cn[key]
        if en == zh or not CJK_RE.search(zh):
            continue
        # 某些页面把英文名也塞进中文页（如 BaseType 行），避免误收
        if en.lower() == zh.lower():
            continue
        pairs[en] = zh
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="忽略缓存重新抓取")
    args = ap.parse_args()

    terms: dict[str, str] = {}
    by_category: dict[str, int] = {}
    class_terms: dict[str, str] = {}

    for slug in CATEGORIES:
        cn_page = fetch("cn", slug, args.refresh)
        us_page = fetch("us", slug, args.refresh)
        if not cn_page or not us_page:
            continue
        pairs = align(slug, cn_page, us_page)
        by_category[slug] = len(pairs)
        for en, zh in pairs.items():
            terms.setdefault(en, zh)
        if slug == "Items":
            # 分类名（如 Divination Cards -> 命运卡）也很有价值
            class_terms = pairs.copy()
        print(f"  [align] {slug}: {len(pairs)} 条", flush=True)

    result = {
        "meta": {
            "source": "流放之路编年史 / 流亡编年史 https://poedb.tw/cn/ (简体中文版), 与 /us/ 英文版按条目链接对齐",
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "categories": len(by_category),
            "aligned_entries": sum(by_category.values()),
            "unique_entries": len(terms) + len(class_terms),
        },
        "class_terms": class_terms,
        "terms": terms,
        "by_category": by_category,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成: {OUT_FILE}  词条 {len(terms)} + 分类 {len(class_terms)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
