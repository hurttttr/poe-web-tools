#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取「天赋树（关键天赋 / 名人 / 专精）」与「符文嫁接 Runegraft」的中英对照，
生成 data/passive_terms.json，供引擎做整串 / 模板匹配。

为什么需要单独的抓取：
    天赋说明（"30% more Spell Damage when on Low Life"）、专精说明
    （"8% increased Damage for each of your Aura or Herald Skills affecting you"）
    和符文嫁接的说明都不在官方交易站词缀统计里（它们不能用来搜索装备），
    所以词缀模板词典覆盖不到，poe.ninja 的天赋提示框会漏翻。

数据来源（两条互补）：
    1. 编年史天赋树数据 https://poedb.tw/data/passive-skill-tree/<版本>/data_us.json
       —— 官方英文原文，作为匹配用的 key（和游戏内 / poe.ninja 显示的完全一致）
    2. 编年史页面 /us|cn/Notable、/Keystone、/Runegraft、/<专精名>_Mastery
       —— 提供简体中文译文

对齐策略：
    先按「天赋名 / slug」对齐条目；条目内的多行说明再按文本相似度配对
    （数字统一换成 # 后做 difflib 比对），行数一致且相似度高时直接按顺序配。

用法:
    python tools/fetch_passive_tree.py            # 用缓存，只补缺失页
    python tools/fetch_passive_tree.py --refresh  # 强制重抓全部页面

输出: data/passive_terms.json
缓存: research/tree_us.json、research/poedb_cache/<lang>_<page>.html、
      research/mastery_cache/<lang>_<slug>.html
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import difflib
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESEARCH = ROOT / "research"
PAGE_CACHE = RESEARCH / "poedb_cache"
MASTERY_CACHE = RESEARCH / "mastery_cache"
TREE_CACHE = RESEARCH / "tree_us.json"
OUT = DATA / "passive_terms.json"

BASE = "https://poedb.tw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 45
WORKERS = 4
GAP = 0.1
DEFAULT_VERSION = "3.30"

CJK = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
TAG = re.compile(r"<[^>]+>")

ITEM_LINK = re.compile(
    r'<a class="[^"]*(?:PassiveSkills|item_currency)[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.S,
)
MOD_DIV = re.compile(r'<div class="(?:implicit|explicit)Mod">(.*?)</div>', re.S)
MASTERY_LI = re.compile(r"<li class=['\"]PassiveMastery['\"]>(.*?)</li>", re.S)
MASTERY_NAME = re.compile(r'<div class="itemName typeLine">\s*<span[^>]*>(.*?)</span>', re.S)


# ------------------------------------------------------------------ 基础工具

def clean(value: str) -> str:
    value = TAG.sub("", html.unescape(value))
    return re.sub(r"\s+", " ", value).strip()


def flatten(raw: str) -> list[str]:
    """把一段 HTML 拆成「一行一条」的纯文本（<br> 视为行分隔）。"""
    raw = re.sub(r"<br\s*/?>", "\n", raw)
    out: list[str] = []
    for seg in raw.split("\n"):
        text = clean(seg)
        if text:
            out.append(text)
    return out


def skeleton(text: str) -> str:
    """和引擎 src/engine.js 的 skeleton 保持一致：数字 -> #"""
    return NUM.sub("#", text)


def folded(text: str) -> str:
    return skeleton(text).lower()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, folded(a), folded(b)).ratio()


def usable(en: str, zh: str) -> bool:
    if not en or not zh or en == zh:
        return False
    if len(en) > 300 or len(zh) > 300:
        return False
    if CJK.search(en) or not LATIN.search(en):
        return False
    if not CJK.search(zh):
        return False
    if re.search(r"[{}<>\\]|https?://|\.js\b|\.css\b", en):
        return False
    return True


def fetch(url: str, path: Path, refresh: bool, min_size: int = 2000) -> str:
    if path.exists() and not refresh and path.stat().st_size > min_size:
        return path.read_text(encoding="utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    )
    last = ""
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            text = raw.decode("utf-8", errors="replace")
            path.write_text(text, encoding="utf-8")
            time.sleep(GAP)
            return text
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5)
    print(f"[warn] 抓取失败 {url} ({last})", file=sys.stderr)
    return ""


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 1. 天赋树数据

def tree_version(refresh: bool) -> str:
    """从编年史的天赋树脚本里读出当前版本号，失败就用默认值。"""
    page = fetch(f"{BASE}/us/passive-skill-tree/", PAGE_CACHE / "us_passive-skill-tree.html", refresh, 3000)
    bundle = re.search(r'src="(https://cdn\.poedb\.tw/js/passive-skill-tree\.[^"]+\.js)"', page or "")
    if not bundle:
        return DEFAULT_VERSION
    js_path = RESEARCH / "tree_bundle.js"
    js = fetch(bundle.group(1), js_path, refresh, 5000)
    found = re.search(r'poe1version:"([\d.]+)"', js or "")
    return found.group(1) if found else DEFAULT_VERSION


def load_tree(refresh: bool) -> dict:
    version = tree_version(refresh)
    url = f"{BASE}/data/passive-skill-tree/{version}/data_us.json?8"
    path = TREE_CACHE
    if refresh or not path.exists() or path.stat().st_size < 100_000:
        print(f"  下载天赋树数据 {version}", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
        path.write_bytes(raw)
    return json.loads(path.read_text(encoding="utf-8"))


def official_groups(tree: dict) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    """从天赋树数据里取 关键天赋 / 名人 / 专精（按分组、保持官方展示顺序）的名称与说明行。"""
    keystones: dict[str, list[str]] = {}
    notables: dict[str, list[str]] = {}
    masteries: dict[str, list[str]] = {}

    def lines_of(stats) -> list[str]:
        out: list[str] = []
        for block in stats or []:
            for seg in str(block).split("\n"):
                # 官方文本里的关键字标记：[DamageFaster|Faster] -> Faster，[Onslaught] -> Onslaught
                seg = re.sub(r"\[[^\]|]*\|([^\]]*)\]", r"\1", seg)
                seg = re.sub(r"\[([^\]]*)\]", r"\1", seg)
                seg = re.sub(r"\s+", " ", seg).strip()
                if seg:
                    out.append(seg)
        return out

    for node in tree.get("nodes", {}).values():
        name = (node.get("name") or "").strip()
        if node.get("isMastery"):
            if not name or not node.get("masteryEffects"):
                continue
            bucket = masteries.setdefault(name, [])
            for effect in node.get("masteryEffects") or []:
                for line in lines_of(effect.get("stats")):
                    if line not in bucket:
                        bucket.append(line)
            continue
        if not name:
            continue
        stats = lines_of(node.get("stats"))
        if not stats:
            continue
        if node.get("isKeystone"):
            keystones[name] = stats
        elif node.get("isNotable"):
            notables.setdefault(name, stats)
    return keystones, notables, masteries


# ------------------------------------------------------------------ 2. 编年史列表页

def parse_listing(page: str) -> dict[str, tuple[str, list[str]]]:
    """把 /us|cn/Notable 这类列表页解析成 slug -> (名称, [说明行])。"""
    out: dict[str, tuple[str, list[str]]] = {}
    marks: list[tuple[int, int, str, str]] = []
    for m in ITEM_LINK.finditer(page):
        name = clean(m.group(2))
        if not name or len(name) > 80:
            continue                     # 图标链接的 inner 只有 <img>，跳过
        marks.append((m.start(), m.end(), m.group(1).rsplit("/", 1)[-1], name))
    for i, (_, end, slug, name) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(page)
        lines: list[str] = []
        for raw in MOD_DIV.findall(page[end:stop]):
            lines.extend(flatten(raw))
        if lines:
            out.setdefault(slug, (name, lines))
    return out


def parse_mastery_page(page: str) -> tuple[str, list[str]] | None:
    start = page.find("masteryPassivePopup")
    if start < 0:
        return None
    block = page[start:start + 30000]
    name = MASTERY_NAME.search(block)
    lis = MASTERY_LI.findall(block)
    if not name or not lis:
        return None
    lines: list[str] = []
    for raw in lis:
        # 同一个 <li> 里可能用 <br> 塞了两条专精（编年史常见），按行拆开
        lines.extend(flatten(raw))
    return clean(name.group(1)), lines


# ------------------------------------------------------------------ 3. 对齐

def align_pair(official: list[str], us: list[str], zh: list[str]) -> list[tuple[str, str]]:
    """把官方英文行与中文行配对。返回 [(官方英文, 中文)]。

    编年史偶尔把一条长说明折成两行，也可能某一行在中文页缺失，
    所以不能简单地按顺序一一对应（会从缺失处开始整体错位）。
    做法：先把「单行」和「相邻两行拼起来的版本」都作为候选，
    再按英文相似度做贪心配对，避免一处缺失牵连后面所有行。
    """
    if not official or not us or not zh:
        return []
    if len(official) == len(us) == len(zh):
        if all(similarity(o, u) >= 0.82 for o, u in zip(official, us)):
            return list(zip(official, zh))

    candidates: list[tuple[str, str, int]] = []
    for idx, line in enumerate(us):
        candidates.append((line, zh[idx] if idx < len(zh) else "", idx))
        if idx + 1 < len(us) and idx + 1 < len(zh):
            # 折行拼接：英文加空格，中文直接相连
            candidates.append((line + " " + us[idx + 1], zh[idx] + zh[idx + 1], idx))

    used: set[int] = set()
    pairs: list[tuple[str, str]] = []
    for line in official:
        best, best_score = None, 0.0
        for en, cn, idx in candidates:
            if idx in used or not cn:
                continue
            score = similarity(line, en)
            if score > best_score:
                best, best_score = (en, cn, idx), score
        if best and best_score >= 0.78:
            used.add(best[2])
            pairs.append((line, best[1]))
    return pairs


def merge_wrapped(lines: list[str]) -> list[str]:
    """官方数据里一条词缀可能被换行折断（下一行以小写或标点开头），这里拼回一条。"""
    out: list[str] = []
    for line in lines:
        if out and (line[:1].islower() or line[:1] in ",.;:)"):
            out[-1] = out[-1] + " " + line
        else:
            out.append(line)
    return out


def pair_lines(official: list[str], us: list[str], zh: list[str]) -> list[tuple[str, str]]:
    """优先按「官方行数 == 中文行数」直接顺序配对。

    编年史页面里英文常被 <br> 多折一行（于是 us 比官方多），
    但中文一般不做同样的折行，所以「行数相等」时顺序配对最稳；
    行数不等才退回按英文相似度对齐。
    """
    if official and len(official) == len(zh):
        return list(zip(official, zh))
    merged = merge_wrapped(official)
    if merged and len(merged) == len(zh):
        return list(zip(merged, zh))
    return align_pair(merged, us, zh) or align_pair(official, us, zh)


def record(mods: dict[str, str], pairs: dict[str, str], en: str, zh: str) -> None:
    """同时登记「带真实数值的整句」与「# 占位模板」。

    编年史的中文是社区文本，语序可能与英文不同（例如
    "10% more Maximum Life if you have at least 6 Life Masteries allocated"
    的中文把 6 放在前面），这时 # 会按序填错位。
    因此只有「英文与中文的数字序列完全一致」时才保留模板，否则只留整句。
    """
    en_nums = {n.lstrip("-").replace(",", "") for n in NUM.findall(en)}
    zh_nums = {n.lstrip("-").replace(",", "") for n in NUM.findall(zh)}
    if en_nums and zh_nums and not (en_nums & zh_nums):
        return          # 数字完全对不上，几乎肯定是配错了行
    pairs[en] = zh
    if NUM.findall(en) == NUM.findall(zh):
        key, value = skeleton(en), skeleton(zh)
        if key.count("#") == value.count("#"):
            mods[key] = value


def collect(refresh: bool) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, int]]:
    names: dict[str, str] = {}
    mods: dict[str, str] = {}
    pairs: dict[str, str] = {}
    stats = {"keystone": 0, "notable": 0, "mastery": 0, "runegraft": 0, "skipped": 0}

    tree = load_tree(refresh)
    keystones, notables, mastery_groups = official_groups(tree)
    print(f"  天赋树: 关键天赋 {len(keystones)} / 名人 {len(notables)} / 专精分组 {len(mastery_groups)}（{sum(len(v) for v in mastery_groups.values())} 行）")

    # ---- 关键天赋 + 名人：列表页一次抓完
    for page, official in (("Keystone", keystones), ("Notable", notables)):
        us_page = fetch(f"{BASE}/us/{page}", PAGE_CACHE / f"us_{page}.html", refresh, 20000)
        cn_page = fetch(f"{BASE}/cn/{page}", PAGE_CACHE / f"cn_{page}.html", refresh, 20000)
        us = parse_listing(us_page)
        cn = parse_listing(cn_page)
        hit = 0
        for slug in us.keys() & cn.keys():
            en_name, en_lines = us[slug]
            zh_name, zh_lines = cn[slug]
            if en_name != zh_name and usable(en_name, zh_name) and len(en_name) <= 60:
                names.setdefault(en_name, zh_name)
            official_lines = official.get(en_name) or en_lines
            for en, zh in pair_lines(official_lines, en_lines, zh_lines):
                if not usable(en, zh):
                    stats["skipped"] += 1
                    continue
                record(mods, pairs, en, zh)
                hit += 1
        key = "keystone" if page == "Keystone" else "notable"
        stats[key] = hit
        print(f"  {page}: 收录 {hit} 行（页面对齐 {len(us.keys() & cn.keys())} 条）")

    # ---- 专精：每个分组一页
    groups = sorted(mastery_groups)
    print(f"  专精分组 {len(groups)} 个，抓取中…", flush=True)
    jobs = [(g, lang) for g in groups for lang in ("us", "cn")]

    def grab(job):
        group, lang = job
        slug = group.replace(" ", "_")
        page = fetch(f"{BASE}/{lang}/{slug}", MASTERY_CACHE / f"{lang}_{slug}.html", refresh, 3000)
        return group, lang, page

    pages: dict[tuple[str, str], str] = {}
    done = 0
    with futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for group, lang, page in pool.map(grab, jobs):
            pages[(group, lang)] = page
            done += 1
            if done % 40 == 0:
                print(f"    进度 {done}/{len(jobs)}", flush=True)

    mastery_hit = 0
    for group in groups:
        us_parsed = parse_mastery_page(pages.get((group, "us"), ""))
        cn_parsed = parse_mastery_page(pages.get((group, "cn"), ""))
        if not us_parsed or not cn_parsed:
            continue
        en_name, en_lines = us_parsed
        zh_name, zh_lines = cn_parsed
        if usable(en_name, zh_name) and len(en_name) <= 60:
            names[en_name] = zh_name
        official = mastery_groups.get(group, [])
        for en, zh in pair_lines(official, en_lines, zh_lines):
            if not usable(en, zh):
                stats["skipped"] += 1
                continue
            record(mods, pairs, en, zh)
            mastery_hit += 1
    stats["mastery"] = mastery_hit
    print(f"  专精说明: 收录 {mastery_hit} 行")

    # ---- 符文嫁接：替换天赋专精的消耗品，说明同样不在交易站词缀里
    us_page = fetch(f"{BASE}/us/Runegraft", PAGE_CACHE / "us_Runegraft.html", refresh, 20000)
    cn_page = fetch(f"{BASE}/cn/Runegraft", PAGE_CACHE / "cn_Runegraft.html", refresh, 20000)
    us = parse_listing(us_page)
    cn = parse_listing(cn_page)
    rune_hit = 0
    for slug in us.keys() & cn.keys():
        en_name, en_lines = us[slug]
        zh_name, zh_lines = cn[slug]
        if usable(en_name, zh_name) and len(en_name) <= 60:
            names.setdefault(en_name, zh_name)
        # 说明可能被 <br> 折成多行：英文按空格拼回，中文直接相连（中文本来就不用空格）
        en_text = " ".join(en_lines)
        zh_text = "".join(zh_lines)
        if not usable(en_text, zh_text):
            continue
        record(mods, pairs, en_text, zh_text)
        rune_hit += 1
    stats["runegraft"] = rune_hit
    print(f"  符文嫁接: 收录 {rune_hit} 条")

    return names, mods, pairs, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    print("抓取天赋树 / 专精 / 符文嫁接中英对照")
    names, mods, pairs, stats = collect(args.refresh)

    doc = {
        "meta": {
            "source": ("编年史天赋树数据 data_us.json（官方英文原文）"
                       " + 编年史 /us|cn/Notable、/Keystone、/Runegraft、/<专精名>_Mastery 页面（简体中文）"),
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "names": len(names),
            "mods": len(mods),
            "pairs": len(pairs),
            "stats": stats,
        },
        "names": dict(sorted(names.items(), key=lambda kv: kv[0].lower())),
        "mods": dict(sorted(mods.items(), key=lambda kv: kv[0].lower())),
        "pairs": dict(sorted(pairs.items(), key=lambda kv: kv[0].lower())),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n名称 {len(names)} 条，说明模板 {len(mods)} 条，整句 {len(pairs)} 条 -> {OUT}")

    for probe in ("30% more Spell Damage when on Low Life",
                  "Ignore Attribute Requirements",
                  "8% increased Damage for each of your Aura or Herald Skills affecting you"):
        hit = mods.get(skeleton(probe))
        print(f"  {probe}\n    -> {hit or '（缺失）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
