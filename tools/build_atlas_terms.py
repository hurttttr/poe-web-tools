#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 poeplanner.com/atlas-tree 专用词典。

数据链路：
  1. 编年史 us / tw 版 Atlas_passive_skill 总览页按「条目 slug」精确对齐，
     得到 英文天赋名 -> 繁中天赋名、英文说明 -> 繁中说明；繁中转简后做术语纠偏。
  2. 带数值的说明用 # 占位（中英 # 数量必须一致，否则丢弃，宁可保持英文）。
  3. 合并人工补写：
       data/atlas_ui_manual.json   界面文案精翻
       data/atlas_extra.json      3.30 新增天赋效果精翻（键为小写 # 骨架）
  4. 站点专属词条写入 data/atlas_terms.json（由 build_dist.py 注入 poeplanner.com 作用域），
     # 模板写入 data/atlas_templates.json（合并进 FBZH_MOD_TPL，不覆盖已有骨架）。

用法: python tools/build_atlas_terms.py
依赖: python tools/fetch_poeplanner.py 先抓取素材；opencc-python-reimplemented
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / "research" / "poeplanner_cache"

CJK = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
BAD = re.compile(r"[{}<>\\\n\r\t]|https?://|\.js\b|\.css\b|undefined|NaN")
# Material Icons 的 ligature 文本：翻译会让图标消失。引擎已跳过 .v-icon，
# 这里再从词典侧兜一层，避免这些词被收录后污染其他位置的文本节点。
ICON_LIGATURES = {
    "add", "apply", "broken_image", "cancel", "clear", "close", "delete",
    "edit", "error", "expand_less", "expand_more", "folder", "folder_shared",
    "help", "info", "keyboard_backspace", "library_books", "link",
    "looks_one", "looks_two", "more_horiz", "person", "reset_all", "save",
    "search", "update", "warning", "arrow_back", "arrow_forward", "check",
    "chevron_left", "chevron_right", "content_copy", "open_in_new", "settings",
}

CARD_SPLIT = re.compile(r'(?=<a class="PassiveSkills")')
CARD_HEAD = re.compile(
    r'<a class="PassiveSkills"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
MOD_RE = re.compile(r'<div class="implicitMod">(.*?)</div>', re.S)

try:
    from opencc import OpenCC
    CC = OpenCC("t2s")
except ImportError:  # pragma: no cover
    print("[error] 缺少 opencc-python-reimplemented，请先 pip install", file=sys.stderr)
    raise SystemExit(1)

# 编年史繁中版是台服译法，按项目默认口径（国服 / 编年史简体）统一术语。
# 顺序敏感：先长词后短词。
VOCAB_FIX = [
    ("机率", "几率"), ("機率", "几率"),
    ("盜賊流亡者", "盗贼流放者"), ("盗贼流亡者", "盗贼流放者"),
    ("盜賊流放者", "盗贼流放者"),
    ("荒林妖精", "野林鬼灵"), ("荒林鬼靈", "野林鬼灵"),
    ("生靈之力", "命能"), ("生灵之力", "命能"),
    ("聖潔獸群", "神圣兽群"), ("圣洁兽群", "神圣兽群"),
    ("精髓", "精华"), ("裂痕", "裂隙"), ("凋落", "菌潮"),
    ("綢帶", "记忆丝缕"), ("绸带", "记忆丝缕"),
    ("輿圖異常", "异界图鉴异象"), ("舆图异常", "异界图鉴异象"),
    ("穿越建師", "穿越建筑师"), ("穿越建师", "穿越建筑师"),
    ("祭祀神壇", "驱灵祭坛"), ("祭祀神坛", "驱灵祭坛"),
    ("神壇", "祭坛"), ("神坛", "祭坛"),
    ("頭目", "首领"), ("头目", "首领"),
    ("階級", "阶位"), ("阶级", "阶位"),
    ("總降", "总降"), ("總增", "总增"),
    ("巢穴", "蜂巢"), ("巢裔", "蜂巢"),
    ("異界圖鑑", "异界图鉴"), ("異界天賦", "异界天赋"),
    ("物品數量", "物品数量"),
]


def load(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"[error] 缺少 {path}，请先运行 python tools/fetch_poeplanner.py")
    return json.loads(path.read_text(encoding="utf-8"))


def clean(x: str) -> str:
    x = re.sub(r"<br\s*/?>", " ", x, flags=re.I)
    x = html.unescape(re.sub(r"<[^>]+>", "", x))
    return re.sub(r"\s+", " ", x).strip()


def t2s(s: str) -> str:
    out = CC.convert(s)
    for a, b in VOCAB_FIX:
        out = out.replace(a, b)
    # 台服习惯把「增加#%」放在句首，国服读作「#% 提高」更顺；# 数量不变，回填顺序不受影响
    out = re.sub(r"^增加\s*(#%)", r"\1 提高", out)
    out = re.sub(r"^減少\s*(#%)", r"\1 降低", out)
    out = re.sub(r"^减少\s*(#%)", r"\1 降低", out)
    return out


def skeleton(s: str) -> str:
    """数字统一替换为 #，并转小写（与 src/engine.js 的骨架比较口径一致）。"""
    return NUM.sub("#", s.replace("{0}", "#").replace("{1}", "#")).lower()


def parse_poedb(path: Path) -> dict[str, tuple[str, list[str]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, tuple[str, list[str]]] = {}
    for card in CARD_SPLIT.split(text)[1:]:
        m = CARD_HEAD.match(card)
        if not m:
            continue
        # 截断到下一张卡片，避免把邻居的说明算进来
        nxt = card.find('<div class="col"><div class="d-flex')
        body = card[:nxt] if nxt > 0 else card
        mods = [clean(x) for x in MOD_RE.findall(body)]
        out[m.group(1)] = (clean(m.group(2)), mods)
    return out


def valid_pair(en: str, zh: str) -> bool:
    if not en or not zh or en == zh:
        return False
    if BAD.search(en) or BAD.search(zh):
        return False
    if not re.search(r"[A-Za-z]{3}", en) or not CJK.search(zh):
        return False
    # 硬性规则：# 数量必须一致，否则宁可输出英文
    if en.count("#") != zh.count("#"):
        return False
    return True


def main() -> int:
    us = parse_poedb(CACHE / "poedb-us.html")
    tw = parse_poedb(CACHE / "poedb-tw.html")
    cn_path = CACHE / "poedb-cn.html"
    cn = parse_poedb(cn_path) if cn_path.exists() else {}
    if len(us) < 100 or len(tw) < 100:
        raise SystemExit("[error] 编年史页面解析异常，请重新抓取")
    common = set(us) & set(tw)
    print(f"编年史对齐：us {len(us)} 条，tw {len(tw)} 条，cn {len(cn)} 条，slug 交集 {len(common)} 条")

    terms: dict[str, str] = {}          # 整句精确匹配（站点专属）
    templates: dict[str, str] = {}      # 带 # 的数值模板
    search_nodes: dict[str, dict] = {}  # 英文节点名 -> 中文名 / 中文说明（供中文搜索桥使用）
    stat_names = 0
    stat_tpl = 0
    skipped = 0
    from_cn = 0

    for slug in sorted(common):
        en_name, en_mods = us[slug]
        tw_name, tw_mods = tw[slug]
        # 同一 slug 的简体页是国服口径，优先采用；繁中页负责补齐未翻译部分
        cn_name, cn_mods = cn.get(slug, ("", []))
        use_cn = bool(CJK.search(cn_name))
        zh_name = t2s(cn_name if use_cn else tw_name)
        if use_cn:
            from_cn += 1
        if valid_pair(en_name, zh_name) and "#" not in en_name:
            terms[en_name] = zh_name
            stat_names += 1
        # 描述按位置一一配对；顺序错位时宁可丢，不产出错误译文
        zh_mods = cn_mods if (use_cn and len(cn_mods) == len(en_mods)) else tw_mods
        # 中文搜索索引：说明文本不要求与英文逐条对齐（对不上只是少一条搜索结果），
        # 只要是有意义的中文句子就收进去，供 src/atlas-search.js 反查出英文节点名。
        search_lines = []
        for zh_raw in zh_mods:
            line = NUM.sub("#", t2s(clean(zh_raw)))
            if CJK.search(line) and not BAD.search(line) and len(line) <= 160:
                search_lines.append(line)
        entry: dict = {}
        if en_name in terms:
            entry["n"] = terms[en_name]
        if search_lines:
            entry["t"] = list(dict.fromkeys(search_lines))
        if entry:
            search_nodes[en_name] = entry
        if len(en_mods) != len(zh_mods):
            skipped += 1
            continue
        for en_raw, zh_raw in zip(en_mods, zh_mods):
            en = NUM.sub("#", clean(en_raw))
            zh = NUM.sub("#", t2s(clean(zh_raw)))
            if not valid_pair(en, zh):
                skipped += 1
                continue
            if "#" in en:
                # 骨架已由站点自己产出的模板覆盖时也保留（build_dist 会去重）
                templates.setdefault(en, zh)
                stat_tpl += 1
            else:
                terms.setdefault(en, zh)
    print(f"  其中 {from_cn} 条译名采用编年史简体页（国服口径）")

    # ---- 人工补写 ----
    ui = load(DATA / "atlas_ui_manual.json")
    extra = load(DATA / "atlas_extra.json")
    stoplist = set(load(DATA / "stoplist.json", {}).get("terms", []))
    if isinstance(stoplist, dict):
        stoplist = set(stoplist)

    # atlas_extra.json 的键是小写 # 骨架；整句词条必须用站点原文的大小写，
    # 否则 engine 的 exact 精确匹配命中不了。这里反查一份「骨架 -> 英文原文」。
    stat_raw = load(CACHE / "atlastranslations.strings.json", [])
    raw_by_skel: dict[str, str] = {}
    for raw in stat_raw:
        for line in [raw] + [x.strip() for x in raw.splitlines()]:
            line = line.strip()
            if not line:
                continue
            raw_by_skel.setdefault(skeleton(line), line)

    ui_count = 0
    for en, zh in ui.items():
        if en.startswith("_"):
            continue
        if en in stoplist:
            print(f"  [warn] 跳过语法关键字 {en!r}")
            continue
        if en in ICON_LIGATURES or (en == en.lower() and "_" in en):
            continue
        if valid_pair(en, zh) and "#" not in en:
            terms[en] = zh
            ui_count += 1

    extra_count = 0
    for en, zh in extra.items():
        if en.startswith("_"):
            continue
        if not valid_pair(en, zh):
            print(f"  [warn] 丢弃 # 数量不匹配的补写：{en!r}")
            continue
        if "#" in en:
            templates.setdefault(skeleton(en), zh)
        else:
            terms.setdefault(raw_by_skel.get(skeleton(en), en), zh)
        extra_count += 1

    # ---- 跨行说明 ----
    # poeplanner 的 bin 会把同一段说明拆成多行，DOM 里可能是一个含换行的文本节点。
    # 引擎 normalize() 会把空白折成单空格，所以额外产出一条「拼接后的整串」译文。
    extra_by_skel = {skeleton(k): v for k, v in extra.items() if not k.startswith("_")}
    merged = 0
    for raw in stat_raw:
        if "\n" not in raw:
            continue
        lines = [x.strip() for x in raw.splitlines() if x.strip()]
        if len(lines) < 2:
            continue
        parts = [extra_by_skel.get(skeleton(line)) for line in lines]
        if any(p is None for p in parts):
            continue
        en_orig = " ".join(lines)
        en_skel = skeleton(en_orig)
        zh = " ".join(parts)
        if not valid_pair(en_skel, zh) or en_skel.count("#") != zh.count("#"):
            continue
        if "#" in en_skel:
            templates.setdefault(en_skel, zh)
        else:
            terms.setdefault(en_orig, zh)
        merged += 1
    print(f"跨行说明合并 {merged} 条")

    # ---- 与现有词典比对，避免重复注入 ----
    dictionary = load(DATA / "dictionary.json")
    mod_doc = load(DATA / "mod_templates.json")
    existing_skel = {skeleton(k) for k in dictionary}
    existing_skel |= {skeleton(k) for k in mod_doc.get("templates", {})}
    existing_skel |= {skeleton(k) for k in mod_doc.get("plain", {})}

    # # 模板是全局表，只补「现有词典没有的骨架」，避免影响另外两个站点。
    templates = {
        k: v for k, v in templates.items()
        if skeleton(k) not in existing_skel
    }
    # 整句词条走 host 作用域：故意保留与主词典同名的键，让 poeplanner 站点
    # 用界面语境的译法覆盖它（例如主词典 Clear=清澈，这里 Clear=清除），
    # 其他站点仍用主词典，互不干扰。
    print(f"  host 作用域覆盖主词典 {sum(1 for k in terms if k in dictionary)} 条同名键")

    # ---- 覆盖率报告 ----
    # 与引擎 normalize() 对齐：连续空白折成单空格后再算骨架
    stats = sorted({skeleton(re.sub(r"\s+", " ", s)) for s in load(
        CACHE / "atlastranslations.strings.json", []) if len(s) >= 8})
    covered = [s for s in stats if s in existing_skel or s in {skeleton(k) for k in templates}
               or s in {skeleton(k) for k in terms}]
    print(f"天赋名 {stat_names} 条，说明 {stat_tpl} 条（丢弃 {skipped} 条）")
    print(f"界面文案 {ui_count} 条，人工补写 {extra_count} 条")
    print(f"输出：整句词条 {len(terms)} 条，# 模板 {len(templates)} 条")
    print(f"站点天赋效果覆盖率：{len(covered)}/{len(stats)} "
          f"({100 * len(covered) / max(1, len(stats)):.1f}%)")

    (DATA / "atlas_terms.json").write_text(
        json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "atlas_templates.json").write_text(
        json.dumps(templates, ensure_ascii=False, indent=1), encoding="utf-8")
    # 中文搜索索引：中文检索词 -> 英文节点名（站点搜索只认英文，见 src/atlas-search.js）
    (DATA / "atlas_search.json").write_text(
        json.dumps({
            "_meta": {
                "source": "编年史 us / cn / tw 异界天赋页按 slug 对齐后的中文天赋名与中文说明",
                "scope": "poeplanner.com",
                "note": "键为 poeplanner 的英文节点名；n 为中文天赋名，t 为中文说明（数字统一成 #）。"
                        "供 src/atlas-search.js 把中文检索词反查成英文节点名后喂给站点搜索。",
            },
            "nodes": search_nodes,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "atlas_report.json").write_text(json.dumps({
        "poedb_aligned": len(common),
        "node_names": stat_names,
        "poedb_descriptions": stat_tpl,
        "skipped_mismatch": skipped,
        "ui_manual": ui_count,
        "extra_manual": extra_count,
        "terms": len(terms),
        "templates": len(templates),
        "search_nodes": len(search_nodes),
        "stat_total": len(stats),
        "stat_covered": len(covered),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"中文搜索索引 {len(search_nodes)} 个节点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
