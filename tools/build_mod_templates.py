#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「物品词缀 / 天赋说明」词典 data/mod_templates.json。

与 dictionary.json 的区别：
  * dictionary.json 只做「整串精确匹配」；
  * 这里的词缀带随机数值（如 "Adds 5 Passive Skills"、"+3% to Fire Resistance"），
    英文用 # 占位，运行时由引擎把实际数字按顺序填回中文模板。

来源（优先级 高 -> 低）:
    1. data/mod_manual.json                 人工补写的模板（Requires Level、珠宝说明等）
    2. 编年史星团珠宝总览页                 天赋 / 关键天赋的实际词缀（含数值）
    3. 官方交易站词缀统计（中英按 stat id 对齐，排除 pseudo / mercenary）

用法: python tools/build_mod_templates.py
依赖: 先跑 python tools/fetch_trade_stats.py（缓存 research/trade_cache/stats_*.json）
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / "research" / "trade_cache"
POEDB_CACHE = ROOT / "research" / "poedb_cache"
OUT = DATA / "mod_templates.json"

CJK = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
BAD = re.compile(r"[{}<>\\\n\r\t]|https?://|\.js\b|\.css\b")
SKIP_GROUPS = {"pseudo", "mercenary"}

# 编年史总览页里「天赋名 + 词缀」的版式
ANCHOR = re.compile(r'<a class="PassiveSkills"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
MOD_DIV = re.compile(r'<div class="implicitMod">(.*?)</div>', re.S)

try:
    from opencc import OpenCC
    _cc = OpenCC("t2s")
except ImportError:  # pragma: no cover
    _cc = None


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def t2s(s: str) -> str:
    return _cc.convert(s) if _cc else s


def strip_tags(s: str) -> str:
    return clean(html.unescape(re.sub(r"<[^>]+>", "", s)))


FRAGMENT_TAIL = re.compile(r"[,:;]$")


def looks_fragment(en: str) -> bool:
    """编年史有时会把一条长词缀按 <br> 折断，折断处的半句会被当成独立词条。

    这类半句（小写开头 / 逗号结尾）参与「短语替换」时会把半截文本换成中文，
    造成中英混杂的错误句子，所以直接不收录。
    """
    if en[:1].islower():
        return True
    return bool(FRAGMENT_TAIL.search(en))


def numbers(text: str) -> set[str]:
    return {n.lstrip("-").replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def usable(en: str, zh: str) -> bool:
    if not en or not zh or en == zh:
        return False
    if len(en) > 220 or len(zh) > 220:
        return False
    if CJK.search(en) or not LATIN.search(en):
        return False
    if not CJK.search(zh):
        return False
    if BAD.search(en):
        return False
    if looks_fragment(en):
        return False
    en_nums, zh_nums = numbers(en), numbers(zh)
    if en_nums and zh_nums and not (en_nums & zh_nums):
        return False       # 中英数字完全对不上，几乎肯定是配错了行
    return True


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 1. 人工模板

def from_manual() -> dict[str, str]:
    doc = load_json(DATA / "mod_manual.json", {}) or {}
    return {clean(k): clean(v) for k, v in (doc.get("terms") or {}).items()}


def manual_prefix() -> dict[str, str]:
    doc = load_json(DATA / "mod_manual.json", {}) or {}
    return {k: v for k, v in (doc.get("prefix") or {}).items()}


# ---------------------------------------------------------------- 2. 编年史

def parse_passive_page(page: str) -> dict[str, list[str]]:
    """slug -> 词缀行（去掉值 span 后仍保留数值文本）"""
    out: dict[str, list[str]] = {}
    marks = list(ANCHOR.finditer(page))
    for i, m in enumerate(marks):
        slug = m.group(1).rsplit("/", 1)[-1]
        end = marks[i + 1].start() if i + 1 < len(marks) else m.end() + 4000
        chunk = page[m.end():end]
        lines: list[str] = []
        for raw in MOD_DIV.findall(chunk):
            for seg in re.split(r"<br\s*/?>", raw):
                text = strip_tags(seg)
                if text:
                    lines.append(text)
        if lines:
            out[slug] = lines
    return out


def from_poedb() -> dict[str, str]:
    out: dict[str, str] = {}
    for slug in ("Cluster_Jewel",):
        us_page = POEDB_CACHE / f"us_{slug}.html"
        cn_page = POEDB_CACHE / f"cn_{slug}.html"
        if not (us_page.exists() and cn_page.exists()):
            print(f"[warn] 缺少编年史缓存 {us_page.name} / {cn_page.name}，跳过", file=sys.stderr)
            continue
        us = parse_passive_page(us_page.read_text(encoding="utf-8", errors="replace"))
        cn = parse_passive_page(cn_page.read_text(encoding="utf-8", errors="replace"))
        aligned = 0
        for key in us.keys() & cn.keys():
            en_lines, zh_lines = us[key], cn[key]
            if len(en_lines) != len(zh_lines):
                continue
            for en, zh in zip(en_lines, zh_lines):
                if usable(en, zh):
                    out.setdefault(en, t2s(zh))
                    aligned += 1
        print(f"  [poedb] {slug}: {aligned} 行词缀")
    return out


# ---------------------------------------------------------------- 3. 天赋树

def from_passive() -> dict[str, str]:
    """关键天赋 / 名人 / 专精 / 符文嫁接的说明（见 tools/fetch_passive_tree.py）。

    这些文本是官方天赋数据里的原文，poe.ninja 的天赋提示框会原样显示，
    交易站词缀统计里查不到，所以单独并入。
    """
    path = DATA / "passive_terms.json"
    if not path.exists():
        print("[warn] 缺少 data/passive_terms.json，跳过天赋说明（先跑 tools/fetch_passive_tree.py）",
              file=sys.stderr)
        return {}
    doc = load_json(path, {}) or {}
    out: dict[str, str] = {}
    # 带真实数值的整句：天赋 / 专精 / 符文嫁接的数值都是固定的，整句最稳
    for en, zh in (doc.get("pairs") or {}).items():
        en, zh = clean(en), clean(zh)
        if not usable(en, zh):
            continue
        out[en] = zh
    # # 占位模板：仅保留「中英数字顺序一致」的那些（抓取阶段已校验）
    templates = 0
    for en, zh in (doc.get("mods") or {}).items():
        en, zh = clean(en), clean(zh)
        if not usable(en, zh):
            continue
        if en.count("#") != zh.count("#"):
            continue
        out[en] = zh
        templates += 1
    print(f"  [passive] {len(out)} 条（整句 {len(out) - templates} / 模板 {templates}）")
    return out


# ---------------------------------------------------------------- 4. 交易站

def from_trade() -> dict[str, str]:
    en_doc = load_json(CACHE / "stats_en.json")
    zh_doc = load_json(CACHE / "stats_zh.json")
    if not en_doc or not zh_doc:
        print("[error] 缺少 research/trade_cache/stats_*.json，请先运行 tools/fetch_trade_stats.py",
              file=sys.stderr)
        raise SystemExit(1)

    def flat(doc):
        res = {}
        for group in doc.get("result", []):
            gid = group.get("id", "?")
            if gid in SKIP_GROUPS:
                continue
            for entry in group.get("entries", []):
                if entry.get("id") and entry.get("text"):
                    res[entry["id"]] = (gid, clean(entry["text"]))
        return res

    en, zh = flat(en_doc), flat(zh_doc)
    out: dict[str, str] = {}
    for sid in en.keys() & zh.keys():
        en_text, zh_text = en[sid][1], t2s(zh[sid][1])
        if not usable(en_text, zh_text):
            continue
        out.setdefault(en_text, zh_text)
    print(f"  [trade] {len(out)} 条")
    return out


# ---------------------------------------------------------------- 构建

def main() -> int:
    print("构建词缀模板词典")
    sources = [
        ("trade", from_trade()),
        ("poedb", from_poedb()),
        ("passive", from_passive()),
        ("manual", from_manual()),
    ]

    merged: dict[str, str] = {}
    origin: dict[str, str] = {}
    for name, table in sources:          # 后面的覆盖前面的
        for en, zh in table.items():
            merged[en] = zh
            origin[en] = name

    templates: dict[str, str] = {}
    plain: dict[str, str] = {}
    dropped = 0
    for en, zh in merged.items():
        if "#" in en:
            # 占位符数量必须一致，否则数字无法按序回填
            if en.count("#") != zh.count("#"):
                dropped += 1
                continue
            if en.startswith("#") is False and en.count("#") > 4:
                dropped += 1
                continue
            templates[en] = zh
        else:
            # 无占位符的整句词缀走精确匹配；太短的词组容易误伤界面文案，直接丢弃
            if len(en) < 6 or " " not in en:
                dropped += 1
                continue
            plain[en] = zh

    templates = dict(sorted(templates.items(), key=lambda kv: kv[0].lower()))
    plain = dict(sorted(plain.items(), key=lambda kv: kv[0].lower()))
    prefix = manual_prefix()

    doc = {
        "meta": {
            "source": ("官方交易站词缀统计（pathofexile.com 与 poe.game.qq.com 按 stat id 对齐）"
                       " + 编年史星团珠宝总览页天赋词缀 + 人工补写模板；数值统一用 # 占位"),
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "templates": len(templates),
            "plain": len(plain),
            "prefix": len(prefix),
            "dropped": dropped,
            "by_source": {n: sum(1 for k in merged if origin.get(k) == n) for n, _ in sources},
        },
        "templates": templates,
        "plain": plain,
        "prefix": prefix,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n模板 {len(templates)} 条，整句 {len(plain)} 条，丢弃 {dropped} 条 -> {OUT}")
    for key in ("Adds # Passive Skills",
                "1 Added Passive Skill is a Jewel Socket",
                "Requires Level #",
                "Herald Skills deal #% increased Damage",
                "#% increased Damage for each Herald affecting you"):
        hit = templates.get(key) or plain.get(key)
        print(f"  {key} -> {hit or '（缺失）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
