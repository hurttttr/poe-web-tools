#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从社区开源汉化脚本（GreasyFork #496758, MIT, 作者 Rayforward / 原作 GodParadise 公会）
的 i18n1 / i18n2 中抽取界面文案词条，作为 UI 词典底稿。

物品/道具译名不会直接采用本底稿：构建词典时以编年史对齐结果为准并覆盖它。
输出: data/community_seed.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "research" / "community_mirtis.user.js"
OUT = ROOT / "data" / "community_seed.json"

PAIR_RE = re.compile(r'\[\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]')


def map_block(script: str, name: str) -> str:
    start = script.find(f"const {name} = new Map([")
    if start < 0:
        raise SystemExit(f"找不到 {name} 定义")
    end = script.find("\n]);", start)
    if end < 0:
        end = script.find("]);", start)
    return script[start:end]


def main() -> int:
    script = SRC.read_text(encoding="utf-8", errors="replace")
    terms: dict[str, str] = {}
    counts: dict[str, int] = {}
    for name in ("i18n1", "i18n2"):
        block = map_block(script, name)
        found = 0
        for en_raw, zh_raw in PAIR_RE.findall(block):
            try:
                en = json.loads(f'"{en_raw}"')
                zh = json.loads(f'"{zh_raw}"')
            except json.JSONDecodeError:
                continue
            if en and zh:
                terms.setdefault(en, zh)
                found += 1
        counts[name] = found
    result = {
        "meta": {
            "source": "GreasyFork #496758 filterblade汉化脚本 v2.7 (MIT), 作者 Rayforward / GodParadise 公会",
            "source_url": "https://greasyfork.org/zh-CN/scripts/496758",
            "note": "仅作 UI 文案底稿；道具译名在 build_dictionary.py 中由编年史数据覆盖",
            "counts": counts,
        },
        "terms": terms,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"抽取完成: {counts}, 合计 {len(terms)} 条 -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
