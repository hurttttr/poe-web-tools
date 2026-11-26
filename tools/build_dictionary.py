#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并各来源词条，生成运行时词典 data/dictionary.json。

优先级（高 -> 低）:
    overrides.json  >  manual_terms.json  >  poedb_items.json(编年史)  >  community_seed.json

同时完成：
  * 繁体 -> 简体统一（OpenCC t2s；未安装时给出警告并跳过）
  * 剔除过滤器语法关键字 / 代码标识（stoplist.json）
  * 脏数据过滤与校验
  * 输出编年史与社区底稿的译名冲突清单，便于人工复核

用法: python tools/build_dictionary.py
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

CJK = re.compile(r"[\u3400-\u9fff]")
BAD_KEY = re.compile(r"[{}<>;=\\\n\r\t]|https?://|\.js|\.css|\.png|\bpx\b|rgb\(")


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def valid(en: str, zh: str) -> bool:
    if not en or not zh or en == zh:
        return False
    # 站点说明段落可能很长，整段作为文本节点精确匹配，上限与引擎的 1200 保持一致
    if len(en) > 1200 or len(zh) > 800:
        return False
    if not re.search(r"[A-Za-z]", en) or CJK.search(en):
        return False
    if not CJK.search(zh):
        return False
    if BAD_KEY.search(en):
        return False
    if en.startswith(("/", "#", ".", "@", "$")):
        return False
    return True


def to_simplified(terms: dict[str, str]) -> tuple[dict[str, str], int]:
    try:
        from opencc import OpenCC
        cc = OpenCC("t2s")
    except ImportError:
        print("[warn] 未安装 opencc-python-reimplemented，跳过繁简统一", flush=True)
        return terms, 0
    changed = 0
    out = {}
    for en, zh in terms.items():
        converted = cc.convert(zh)
        if converted != zh:
            changed += 1
        out[en] = converted
    return out, changed


def main() -> int:
    poedb = load("poedb_items.json")
    seed = load("community_seed.json")
    community = seed["terms"]
    manual = load("manual_terms.json")["terms"]
    overrides = load("overrides.json")["terms"]
    site_file = DATA / "site_terms.json"
    site_terms = json.loads(site_file.read_text(encoding="utf-8"))["terms"] if site_file.exists() else {}
    ninja_file = DATA / "ninja_terms.json"
    ninja_terms = json.loads(ninja_file.read_text(encoding="utf-8"))["terms"] if ninja_file.exists() else {}
    gem_desc_file = DATA / "gem_desc.json"
    gem_desc_terms = json.loads(gem_desc_file.read_text(encoding="utf-8"))["terms"] if gem_desc_file.exists() else {}
    # 天赋树（关键天赋 / 名人 / 专精 / 符文嫁接）的名称：build_mod_templates 只用其中的说明，
    # 名称这类「无数字整串」适合直接进主词典做精确匹配。
    passive_file = DATA / "passive_terms.json"
    passive_names = json.loads(passive_file.read_text(encoding="utf-8"))["names"] if passive_file.exists() else {}
    # 官方词缀统计里的「无占位符整句」（如天赋描述、状态词缀）走精确匹配；
    # 带数值的模板由 mod_templates.json 的 templates 部分交给引擎按骨架匹配。
    mod_file = DATA / "mod_templates.json"
    mod_doc = json.loads(mod_file.read_text(encoding="utf-8")) if mod_file.exists() else {}
    mod_plain = mod_doc.get("plain", {})
    stop = set(load("stoplist.json")["keys"])
    stop_lower = {k.lower() for k in stop}

    # 编年史简体版绝大多数已是简体，但个别条目（如象棋装饰物）仍含繁体/异体字，
    # 因此合并后统一做一次繁简转换，保证整个词典口径一致。
    poedb_terms = {}
    poedb_terms.update({clean(k): clean(v) for k, v in poedb.get("class_terms", {}).items()})
    poedb_terms.update({clean(k): clean(v) for k, v in poedb.get("terms", {}).items()})
    community = {clean(k): clean(v) for k, v in community.items()}

    conflicts = []
    for en, zh in poedb_terms.items():
        if en in community and community[en] != zh:
            conflicts.append({"en": en, "poedb_cn": zh, "community": community[en], "chosen": zh})

    merged: dict[str, str] = {}
    origin: dict[str, str] = {}
    for source_name, source in (
        ("ninja_terms", ninja_terms),
        ("community", community),
        ("poedb", poedb_terms),
        ("mod_plain", mod_plain),
        ("passive_names", passive_names),
        ("gem_desc", gem_desc_terms),
        ("site_terms", site_terms),
        ("manual", manual),
        ("overrides", overrides),
    ):
        for en, zh in source.items():
            en, zh = clean(en), clean(zh)
            merged[en] = zh
            origin[en] = source_name

    merged, converted = to_simplified(merged)

    filtered = 0
    final: dict[str, str] = {}
    for en, zh in merged.items():
        if en in stop or en.lower() in stop_lower:
            filtered += 1
            continue
        if not valid(en, zh):
            filtered += 1
            continue
        final[en] = zh

    final = dict(sorted(final.items(), key=lambda kv: kv[0].lower()))
    (DATA / "dictionary.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    by_source: dict[str, int] = {}
    for en in final:
        by_source[origin.get(en, "?")] = by_source.get(origin.get(en, "?"), 0) + 1

    # 保留由其它构建脚本（如 build_atlas_terms.py）维护的段，避免本脚本重建时把它们冲掉。
    meta_path = DATA / "dictionary.meta.json"
    preserved: dict = {}
    if meta_path.exists():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
            preserved = {k: v for k, v in prev.items() if k not in {
                "generated_at", "entries", "by_source", "traditional_to_simplified",
                "filtered_out", "conflicts_poedb_vs_community", "sources", "policy",
            }}
        except (ValueError, OSError):
            preserved = {}

    meta = {
        **preserved,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "entries": len(final),
        "by_source": by_source,
        "traditional_to_simplified": converted,
        "filtered_out": filtered,
        "conflicts_poedb_vs_community": len(conflicts),
        "sources": {
            "poedb": poedb["meta"]["source"],
            "poedb_generated_at": poedb["meta"]["generated_at"],
            "community": seed["meta"]["source"],
            "manual": "人工校对的 FilterBlade 界面词条",
            "site_terms": "从站点 .options / index.html / faqContent 提取后人工翻译的界面文案（见 site_terms.json）",
            "gem_desc": "编年史宝石详情页 og:title / og:description 中英对齐的技能名与技能说明（见 gem_desc.json）",
            "mod_plain": "官方交易站词缀统计（国服中文版按 stat id 对齐）中不含数值占位符的整句词缀，以及编年史星团珠宝天赋描述（见 mod_templates.json 的 plain）",
            "passive_names": "编年史天赋树（关键天赋 / 名人 / 专精 / 符文嫁接）的译名（见 passive_terms.json 的 names）",
            "ninja_terms": "poe.ninja 官方繁體中文语言包按 Lingui id 与英文 message 配对、转简并校正术语（见 ninja_terms.json）",
        },
        "policy": "物品/道具译名以编年史简体中文为准；界面文案以站点原文精翻与人工校对表为准；overrides 优先级最高",
    }
    (DATA / "dictionary.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA / "conflicts.json").write_text(
        json.dumps(conflicts, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("词典构建完成")
    print(f"  最终词条      : {len(final)}")
    print(f"  来源分布      : {by_source}")
    print(f"  繁->简转换    : {converted} 条")
    print(f"  过滤/剔除     : {filtered} 条（含 {len(stop)} 个语法关键字）")
    print(f"  译名冲突      : {len(conflicts)} 条（已采用编年史）-> data/conflicts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
