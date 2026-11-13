#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成运行时站点文案词典 data/site_terms.json。

与早期「按清单序号配对」的做法不同，本脚本只使用**英文原文 -> 中文**的稳定映射，
因此词典增删、站点赛季更新都不会让译文错位。

输入：
  data/site_manual.json   人工译文累积库 {"terms": {"English": "中文"}}（主要维护文件）
  data/site_extra.json    可选，增量补词，格式同上（优先级高于 site_manual）
  data/faq_zh.json        FAQ 问题译文，按 faqContent.json 的 questionList 序号配对
  research/faqContent.json.out  站点 FAQ 数据源

历史文件 data/site_zh_1~3.json 是 2026-11-13 首轮按序号批量填写的记录，
其内容已固化到 site_manual.json，不再参与构建。

用法: python tools/merge_site_terms.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESEARCH = ROOT / "research"


def load_terms(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    terms = raw.get("terms", raw) if isinstance(raw, dict) else {}
    return {str(k): str(v).strip() for k, v in terms.items() if v and str(v).strip()}


def main() -> int:
    terms: dict[str, str] = {}
    sources = {}

    for name in ("site_manual.json", "site_extra.json"):
        part = load_terms(DATA / name)
        sources[name] = len(part)
        terms.update(part)

    faq_count = 0
    faq_src = RESEARCH / "faqContent.json.out"
    faq_zh = DATA / "faq_zh.json"
    if faq_src.exists() and faq_zh.exists():
        questions = json.loads(faq_src.read_text(encoding="utf-8"))["questionList"]
        qa_zh = json.loads(faq_zh.read_text(encoding="utf-8"))
        for key, value in qa_zh.items():
            i = int(key)
            if value and str(value).strip() and 0 <= i < len(questions):
                terms[questions[i]["question"]] = str(value).strip()
                faq_count += 1
    sources["faq_zh.json"] = faq_count

    out = {
        "meta": {
            "source": "FilterBlade 站点静态文案（.options / index.html / faqContent 等）人工翻译",
            "entries": len(terms),
            "by_source": sources,
            "note": "译文以英文原文为键；增补请编辑 data/site_manual.json 或 data/site_extra.json",
        },
        "terms": dict(sorted(terms.items(), key=lambda kv: kv[0].lower())),
    }
    (DATA / "site_terms.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"合并完成: {len(terms)} 条  {sources}")
    print(f"-> {DATA / 'site_terms.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
