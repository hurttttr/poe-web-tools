#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 poe.ninja 的「英文 -> 简体中文」界面词条。

数据来源（由 fetch_ninja_i18n.py 抓取）：
  research/ninja_catalog_zh_tw.mjs   官方繁體中文 Lingui 语言包（id -> 译文）
  research/ninja_chunks/*.mjs        各页面 JS chunk，里面是 {id:`x`,message:`English`}
  research/ninja_*.html              英文页 / 繁中页 SSR 文本节点，用于补充导航等静态文案

流程：按 Lingui id 配对 -> 繁转简(OpenCC) -> 术语校正到编年史/国服口径
      -> 只保留现有词典尚未收录的键 -> data/ninja_terms.json

用法: python tools/build_ninja_terms.py
"""

from __future__ import annotations

import html as html_mod
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
DATA = ROOT / "data"

# 繁中官方译名 -> 编年史简体/国服通用译名（t2s 之后应用，按长度降序）
TERM_FIX = [
    ("傳奇", "暗金"),  # t2s 后是「传奇」，此处按简体匹配
    ("传奇", "暗金"),
    ("传奇物品", "暗金物品"),
    ("舆图天赋树", "异界天赋树"),
    ("舆图", "异界"),
    ("流亡黯道", "流放之路"),
    ("流亡之路", "流放之路"),
    ("神圣石", "神圣石"),
    ("崇高石", "崇高石"),
    ("混沌石", "混沌石"),
    ("通货", "通货"),
    # 台湾用语 -> 大陆通用（字形转换之外还要换词）
    ("天梯资料", "天梯数据"),
    ("资料", "数据"),
    ("资讯", "信息"),
    ("连结", "链接"),
    ("登入", "登录"),
    ("帐号", "账号"),
    ("帐户", "账户"),
    ("设定", "设置"),
    ("预设", "默认"),
    ("储存", "保存"),
    ("支援", "支持"),
    ("滑鼠", "鼠标"),
    ("萤幕", "屏幕"),
    ("档案", "文件"),
    ("网路", "网络"),
    ("伺服器", "服务器"),
    ("阶层", "阶层"),
    ("排序", "排序"),
    ("品质", "品质"),
    ("刊登", "挂单"),
    ("贩售", "出售"),
    ("贴上", "粘贴"),
    ("低可信度", "低可信度"),
]
TERM_FIX.sort(key=lambda x: -len(x[0]))

ID_MSG_RE = re.compile(
    r'id:\s*[`"\']([A-Za-z0-9_\-]{3,16})[`"\']\s*,\s*message:\s*[`"\']([^`"\']{1,220})[`"\']'
)
BAD_EN = re.compile(r"[{}<>$\\]|https?://|\.js\b|^\s*\d+\s*$", re.I)


class TextNodes(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip:
            return
        t = " ".join(html_mod.unescape(data).strip().split())
        if t:
            self.out.append(t)


def load_catalog() -> dict:
    path = RESEARCH / "ninja_catalog_zh_tw.mjs"
    if not path.exists():
        return {}
    src = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"JSON\.parse\(`(.*?)`\)", src, re.S)
    if not m:
        return {}
    return json.loads(m.group(1))


def plain_message(value) -> str | None:
    """只取不含插值变量的纯文本消息；含变量的消息渲染后与 key 不一致，跳过。"""
    if not isinstance(value, list) or not value:
        return None
    if any(isinstance(x, (list, dict)) for x in value):
        return None
    if not all(isinstance(x, str) for x in value):
        return None
    return "".join(value).strip()


def collect_id_to_en() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted((RESEARCH / "ninja_chunks").glob("*.mjs")):
        src = path.read_text(encoding="utf-8", errors="replace")
        for mid, msg in ID_MSG_RE.findall(src):
            out.setdefault(mid, msg)
    return out


def collect_ssr_pairs() -> list[tuple[str, str]]:
    """已下载的英文页 / 繁中页 SSR 文本节点对齐（导航、页脚等）。"""
    pairs = [
        ("ninja_home.html", "ninja_zh-tw.html"),
        ("ninja_poe1_economy_allflame_currency.html",
         "ninja_zh-tw_poe1_economy_allflame_currency.html"),
    ]
    out: list[tuple[str, str]] = []
    for en_name, zh_name in pairs:
        en_path, zh_path = RESEARCH / en_name, RESEARCH / zh_name
        if not (en_path.exists() and zh_path.exists()):
            continue
        a, b = TextNodes(), TextNodes()
        a.feed(en_path.read_text(encoding="utf-8", errors="replace"))
        b.feed(zh_path.read_text(encoding="utf-8", errors="replace"))
        if len(a.out) == len(b.out):
            out.extend(zip(a.out, b.out))
    return out


def to_simplified(s: str) -> str:
    try:
        from opencc import OpenCC
        s = OpenCC("t2s").convert(s)
    except ImportError:
        pass
    for a, b in TERM_FIX:
        s = s.replace(a, b)
    return s


def valid(en: str, zh: str) -> bool:
    if not en or not zh or en == zh:
        return False
    if len(en) > 200 or len(zh) > 220:
        return False
    if not re.search(r"[A-Za-z]{2}", en) or re.search(r"[\u3400-\u9fff]", en):
        return False
    if not re.search(r"[\u3400-\u9fff]", zh):
        return False
    if BAD_EN.search(en):
        return False
    if en.startswith(("/", "#", ".", "@")):
        return False
    return True


def main() -> int:
    catalog = load_catalog()
    id_en = collect_id_to_en()
    existing = json.loads((DATA / "dictionary.json").read_text(encoding="utf-8"))
    existing_lower = {k.lower() for k in existing}

    raw: dict[str, str] = {}

    # 1) Lingui id 配对
    matched = 0
    for mid, value in catalog.items():
        en = id_en.get(mid)
        zh_tw = plain_message(value)
        if not en or not zh_tw:
            continue
        zh = to_simplified(zh_tw)
        if valid(en, zh):
            raw.setdefault(en, zh)
            matched += 1

    # 2) SSR 文本节点对齐（繁中 -> 简中）
    ssr = 0
    for en, zh_tw in collect_ssr_pairs():
        zh = to_simplified(zh_tw)
        if valid(en, zh):
            raw.setdefault(en, zh)
            ssr += 1

    # 3) 人工校对的 poe.ninja 高频界面文案（列头 / 时间范围 / 导航），覆盖自动结果
    manual_path = DATA / "ninja_ui_manual.json"
    manual = json.loads(manual_path.read_text(encoding="utf-8"))["terms"] if manual_path.exists() else {}
    manual_count = 0
    for en, zh in manual.items():
        if valid(en, zh):
            raw[en] = zh
            manual_count += 1

    # 4) 不做差集过滤：主词典本身包含上一次的 ninja_terms 结果，
    #    在这里做差集会导致二次运行把词条删光。重复键交给 build_dictionary.py
    #    的来源优先级处理（ninja_terms 最低，编年史/人工校对始终优先）。
    terms = dict(sorted(raw.items(), key=lambda kv: kv[0].lower()))
    overlap = sum(1 for k in terms if k.lower() in existing_lower)

    out = {
        "meta": {
            "source": "poe.ninja 官方繁體中文 Lingui 语言包 + 英文 message 按 id 配对，OpenCC 转简、术语按编年史/国服口径校正",
            "catalog_entries": len(catalog),
            "id_en_pairs": len(id_en),
            "matched_pure_text": matched,
            "ssr_pairs": ssr,
            "manual_ui": manual_count,
            "new_terms": len(terms),
            "overlap_with_existing": overlap,
            "note": "重复键由 build_dictionary.py 的来源优先级裁决；ninja_terms 优先级最低，编年史/人工校对优先",
        },
        "terms": dict(sorted(terms.items(), key=lambda kv: kv[0].lower())),
    }
    (DATA / "ninja_terms.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("poe.ninja 词条构建完成")
    print(f"  语言包 id        : {len(catalog)}")
    print(f"  id -> 英文       : {len(id_en)}")
    print(f"  配对纯文本       : {matched}，SSR 对齐 {ssr}")
    print(f"  新增（未收录）   : {len(terms)} -> data/ninja_terms.json")
    for k, v in list(terms.items())[:12]:
        print(f"    {k[:52]} -> {v[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
