#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词典质量校验：结构、术语一致性、繁简统一、语法关键字隔离、关键条目断言。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CJK = re.compile(r"[\u3400-\u9fff]")

REQUIRED = {
    "Chaos Orb": "混沌石",
    "Exalted Orb": "崇高石",
    "Divine Orb": "神圣石",
    "Orb of Alchemy": "点金石",
    "The Doctor": "疯医",
    "Headhunter": "猎首",
    "Vaal Regalia": "瓦尔法衣",
    "Divination Cards": "命运卡",
    "Energy Shield": "能量护盾",
    "Evasion Rating": "闪避值",
    "Semi-Strict": "半严格",
    "Uber Strict": "极严格",
    "Start": "开始",
    "Customize": "自定义",
    "Loot Simulator": "掉落模拟器",
    "Add Custom Currency Rules": "添加自定义通货规则",
}


def main() -> int:
    d = json.loads((DATA / "dictionary.json").read_text(encoding="utf-8"))
    stop = set(json.loads((DATA / "stoplist.json").read_text(encoding="utf-8"))["keys"])
    errors: list[str] = []

    if len(d) < 5000:
        errors.append(f"词条数偏少: {len(d)}")

    for en, zh in d.items():
        if not re.search(r"[A-Za-z]", en) or CJK.search(en):
            errors.append(f"非法键: {en!r}")
        if not CJK.search(zh):
            errors.append(f"译名缺少中文: {en!r} -> {zh!r}")
        if len(en) > 1200 or len(zh) > 800:
            errors.append(f"过长条目: {en!r}")
        if re.search(r"[\n\r\t{}<>;=]", en):
            errors.append(f"键含代码字符: {en!r}")
        if en in stop:
            errors.append(f"语法关键字未被剔除: {en!r}")

    for en, expect in REQUIRED.items():
        if d.get(en) != expect:
            errors.append(f"关键术语不符: {en!r} 期望 {expect!r}, 实际 {d.get(en)!r}")

    # 繁体残留（OpenCC 可用时）
    converted = 0
    try:
        from opencc import OpenCC
        cc = OpenCC("t2s")
        for zh in d.values():
            if cc.convert(zh) != zh:
                converted += 1
        if converted:
            errors.append(f"仍有 {converted} 条繁体/异体译名未统一")
    except ImportError:
        print("[warn] 未安装 OpenCC，跳过繁简检查")

    # 语法关键字隔离抽样
    leaks = [k for k in ("Show", "Hide", "Class", "BaseType", "Rarity", "SetFontSize", "PlayAlertSound") if k in d]
    if leaks:
        errors.append(f"过滤器语法关键字泄漏: {leaks}")

    # 词缀模板校验：# 占位符必须中英一一对应，否则运行时会输出错位译文
    tpl_doc = json.loads((DATA / "mod_templates.json").read_text(encoding="utf-8"))
    tpl = tpl_doc["templates"]
    tpl_bad = [k for k, v in tpl.items() if k.count("#") != v.count("#") or "#" not in k]
    if tpl_bad:
        errors.append(f"模板占位符不匹配: {tpl_bad[:3]}")
    tpl_leak = [k for k in tpl if not CJK.search(tpl[k]) or CJK.search(k)]
    if tpl_leak:
        errors.append(f"模板语种异常: {tpl_leak[:3]}")
    for key, expect in (
        ("Adds # Passive Skills", "增加 # 个天赋技能"),
        ("Requires Level #", "需求 等级 #"),
        ("Adds # to # Fire Damage", "该装备附加 # - # 基础火焰伤害"),
    ):
        if tpl.get(key) != expect:
            errors.append(f"关键模板不符: {key!r} 期望 {expect!r}, 实际 {tpl.get(key)!r}")

    meta = json.loads((DATA / "dictionary.meta.json").read_text(encoding="utf-8"))
    print("词典校验报告")
    print(f"  词条总数          : {len(d)}")
    print(f"  来源分布          : {meta['by_source']}")
    print(f"  繁简统一          : 构建时转换 {meta['traditional_to_simplified']} 条，残留 {converted} 条")
    print(f"  编年史/社区冲突   : {meta['conflicts_poedb_vs_community']} 条（已采用编年史）")
    print(f"  语法关键字剔除    : {len(stop)} 个")
    print(f"  词缀模板          : {len(tpl)} 条（数值占位 # 已对齐）")
    print(f"  关键术语断言      : {len(REQUIRED)} 条")

    if errors:
        print(f"\n发现 {len(errors)} 个问题:")
        for e in errors[:30]:
            print("  -", e)
        return 1
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
