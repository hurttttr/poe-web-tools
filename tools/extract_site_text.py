#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 FilterBlade 的静态界面文案源里提取「真正会渲染到 DOM 的英文文本」，
与现有词典比对，输出未覆盖清单 data/site_missing.json。

文案源（research/ 下，由 fetch_site_assets.py 下载）：
  StyleSummary.options      Overview / Start 页（截图所在页）的分区标题、说明、信息框
  optionFile085d.options    Customizer 的规则名与说明
  LootGenerator.options     Loot Simulator
  faqContent.json / newsFile.txt / economies.json / index.html

fb.min.js 是压缩代码，引号内容绝大多数是代码/CSS 碎片，不参与自动提取；
其中的少量静态 UI 文案放在本文件的 STATIC_UI 里手工维护。

用法: python tools/extract_site_text.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
DATA = ROOT / "data"

QUOTED = re.compile(r'"((?:[^"\\]|\\.){2,3000})"')
TAG = re.compile(r"<[^>]+>")

# 压缩 JS 里已知会显示、但无法从结构安全提取的界面文案
STATIC_UI = [
    "Login with PoE", "Search (Ctrl + K)", "Current League", "EXPORT", "DISCORD",
    "REPORT AN ISSUE", "Report Ad", "New here?", "Detailed explanation",
    "Please consider supporting us by disabling AdBlock.",
    "Initializing FilterBlade...", "Requesting files from server...",
]

SKIP_EXACT = {
    "skip", "Overview", "StyleSummary", "Searches", "BaseType", "Class", "Rarity",
    "Show", "Hide", "Continue", "S0", "S1", "S2", "S3", "S4", "S5", "S10",
    "Detailed explanation", "no items", "few items", "Has line",
}
CODE_RE = re.compile(r"[{};=]|=>|\bfunction\b|\bvar\b|\bawait\b|\bnull\b|\btrue\b|\bfalse\b|rgba?\(|\bpx\b|\bsolid\b|\bauto\b")
PATH_RE = re.compile(r"^[/#.]|https?://|\.(png|jpg|jpeg|webp|json|options|js|css|filter|txt)\b", re.I)
ID_RE = re.compile(r"^\w+([.;]\w+)+$")
NUM_RE = re.compile(r"^[\d\s.,%xX:+/-]+$")


def clean(s: str) -> str:
    s = s.replace("\\n", " ").replace('\\"', '"').replace("\\'", "'")
    s = TAG.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def is_ui(s: str) -> bool:
    if not s or len(s) < 8 or len(s) > 1200 or s in SKIP_EXACT:
        return False
    if not re.search(r"[A-Za-z]", s) or not re.search(r"\s", s):
        return False
    if PATH_RE.search(s) or CODE_RE.search(s):
        return False
    if ID_RE.match(s) or NUM_RE.match(s):
        return False
    return len(re.findall(r"[A-Za-z]{2,}", s)) >= 2


def split_hr(raw: str) -> list[str]:
    # <hr>/<br> 会把 DOM 文本拆成多个节点，必须在清理 HTML 之前切分，
    # 否则整段作为一个词条永远命中不了站点上的文本节点。
    parts = re.split(r"\s*<hr\s*/?>\s*|\s*<br\s*/?>\s*", raw, flags=re.I)
    out = []
    for p in parts:
        s = clean(p)
        if is_ui(s):
            out.append(s)
    return out


def from_options(text: str) -> list[str]:
    out: list[str] = []
    for raw in QUOTED.findall(text):
        out.extend(split_hr(raw))
    return out


def from_html_text(text: str) -> list[str]:
    out: list[str] = []
    for chunk in re.findall(r">([^<>]{4,300})<", text):
        s = clean(chunk)
        if is_ui(s):
            out.append(s)
    # title / placeholder / alt 等展示型属性
    for attr in ("placeholder", "title", "alt", "value"):
        for raw in re.findall(attr + r'\s*=\s*["\x27]([^"\x27]{4,120})["\x27]', text):
            s = clean(raw)
            if is_ui(s):
                out.append(s)
    return out


def from_json_text(text: str) -> list[str]:
    out: list[str] = []
    for raw in QUOTED.findall(text):
        out.extend(split_hr(raw))
    return out


def main() -> int:
    dictionary = json.loads((DATA / "dictionary.json").read_text(encoding="utf-8"))
    folded = {k.lower(): v for k, v in dictionary.items()}

    # optionFile 文件名带版本哈希，优先用当前版本，找不到时自动发现
    option_file = "optionFile085d.options"
    if not (RESEARCH / option_file).exists():
        found = sorted(RESEARCH.glob("optionFile*.options"))
        if found:
            option_file = found[0].name

    sources: dict[str, list[str]] = {}
    for name in ("StyleSummary.options", option_file, "LootGenerator.options"):
        path = RESEARCH / name
        if path.exists():
            sources[name] = from_options(path.read_text(encoding="utf-8", errors="replace"))
    for name in ("faqContent.json.out", "newsFile.txt.out", "economies.json"):
        path = RESEARCH / name
        if path.exists():
            sources[name] = from_json_text(path.read_text(encoding="utf-8", errors="replace"))
    index = RESEARCH / "index.html"
    if index.exists():
        sources["index.html"] = from_html_text(index.read_text(encoding="utf-8", errors="replace"))
    sources["STATIC_UI"] = STATIC_UI

    priority = ["StyleSummary.options", "STATIC_UI", "index.html", "economies.json",
                option_file, "LootGenerator.options", "newsFile.txt.out",
                "faqContent.json.out"]

    entries: dict[str, dict] = {}
    for name in priority:
        for s in sources.get(name, []):
            item = entries.setdefault(s, {"en": s, "sources": [], "priority": 9})
            if name not in item["sources"]:
                item["sources"].append(name)
            item["priority"] = min(item["priority"], priority.index(name))

    ordered = sorted(entries.values(), key=lambda x: (x["priority"], -len(x["en"])))
    covered = [e for e in ordered if e["en"].lower() in folded]
    missing = [e for e in ordered if e["en"].lower() not in folded]

    for name, items in sources.items():
        print(f"  {name}: {len(set(items))} 条候选")

    result = {
        "meta": {
            "note": "从 FilterBlade 静态文案源提取的可见英文文本；missing 为词典尚未覆盖的条目",
            "sources": priority,
            "candidates": len(ordered),
            "covered": len(covered),
            "missing": len(missing),
        },
        "missing": missing,
        "covered": [e["en"] for e in covered],
    }
    (DATA / "site_missing.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n候选 {len(ordered)} 条，已覆盖 {len(covered)}，未覆盖 {len(missing)}")
    print(f"-> {DATA / 'site_missing.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
