#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 poeplanner.com/atlas-tree 汉化所需的原始素材。

数据来源（全部只读公开资源，缓存到 research/poeplanner_cache/）：
  1. https://poeplanner.com/atlas-tree          -> 解析出 app.<hash>.js 文件名（不硬编码哈希）
  2. https://cdn.poeplanner.com/json/versions.json -> 动态读取当前 atlas 数据版本（不硬编码赛季号）
  3. https://cdn.poeplanner.com/bin/<v>/atlastree.bin          节点名 / 静态说明
  4. https://cdn.poeplanner.com/bin/<v>/atlastranslations.bin   天赋效果英文原文（{0} 占位）
  5. https://poedb.tw/{us,tw}/Atlas_passive_skill               官方英文 / 繁中天赋名与说明

用法:
    python tools/fetch_poeplanner.py            # 已有缓存则跳过
    python tools/fetch_poeplanner.py --refresh # 强制重新抓取
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "poeplanner_cache"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 45


def get(url: str, binary: bool = False, lang: str = "en-US,en;q=0.9") -> bytes | str:
    headers = {"User-Agent": UA, "Accept-Language": lang}
    if not binary:
        headers["Accept"] = "text/html,application/json,*/*"
    last: Exception | None = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
            return raw if binary else raw.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.6)
    raise RuntimeError(f"抓取失败 {url}: {last}")


def cached(name: str, url: str, refresh: bool, binary: bool = False,
           lang: str = "en-US,en;q=0.9") -> bytes | str:
    path = CACHE / name
    if path.exists() and path.stat().st_size > 200 and not refresh:
        return path.read_bytes() if binary else path.read_text(encoding="utf-8", errors="replace")
    data = get(url, binary=binary, lang=lang)
    path.write_bytes(data if binary else data.encode("utf-8"))
    size = len(data) if binary else len(data.encode("utf-8"))
    print(f"  [fetch] {name}: {size:,} bytes", flush=True)
    time.sleep(0.15)
    return data


def extract_strings(data: bytes) -> list[str]:
    """bin 文件是「长度/标记字节 + NUL 结尾字符串」的混合结构。

    按 NUL 切分后取每段里第一个字母（或占位符 {）之后的纯 ASCII 文本，
    避免把前面的长度字节当成正文（例如 '&Final Map Boss...'）。
    """
    out: list[str] = []
    for seg in data.split(b"\x00"):
        try:
            text = seg.decode("ascii")
        except UnicodeDecodeError:
            continue
        m = re.search(r"[A-Za-z{]", text)
        if not m:
            continue
        text = text[m.start():].strip()
        if len(text) < 4 or not re.search(r"[A-Za-z]{3}", text):
            continue
        out.append(text)
    return list(dict.fromkeys(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)

    print("1) 解析站点入口，动态发现资源文件名")
    html = cached("index.html", "https://poeplanner.com/atlas-tree", args.refresh)
    m = re.search(r'src="(/js/app\.[0-9a-f]+\.js)"', html)
    if not m:
        print("  [error] 未能在 HTML 中找到 app.<hash>.js", file=sys.stderr)
        return 1
    app_path = m.group(1)
    print(f"  app bundle: {app_path}")
    app_js = cached("app.js", "https://poeplanner.com" + app_path, args.refresh)

    print("2) 动态读取当前 atlas 数据版本")
    versions = cached("versions.json", "https://cdn.poeplanner.com/json/versions.json", args.refresh)
    import json
    vmap = json.loads(versions)
    atlas_version = int(vmap["atlasVersions"][0]["version"])
    poe_version = vmap["atlasVersions"][0].get("poeVersion", "?")
    print(f"  atlas data version = {atlas_version} (PoE {poe_version})")

    print("3) 下载 atlas 数据与翻译二进制")
    base = f"https://cdn.poeplanner.com/bin/{atlas_version}/"
    tree_bin = cached("atlastree.bin", base + "atlastree.bin", args.refresh, binary=True)
    trans_bin = cached("atlastranslations.bin", base + "atlastranslations.bin", args.refresh, binary=True)

    tree_strings = extract_strings(tree_bin)
    trans_strings = extract_strings(trans_bin)
    (CACHE / "atlastree.strings.json").write_text(
        __import__("json").dumps(tree_strings, ensure_ascii=False, indent=1), encoding="utf-8")
    (CACHE / "atlastranslations.strings.json").write_text(
        __import__("json").dumps(trans_strings, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  节点数据 {len(tree_strings)} 条，效果描述 {len(trans_strings)} 条")

    print("4) 抓取编年史异界天赋中英总览页")
    # cn 是国服简体译名（约 150 条，优先采用）；tw 覆盖全部 352 条，用于补齐
    locales = {
        "us": "en-US,en;q=0.9",
        "cn": "zh-CN,zh;q=0.9,en;q=0.8",
        "tw": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    for lang, accept_lang in locales.items():
        cached(f"poedb-{lang}.html", f"https://poedb.tw/{lang}/Atlas_passive_skill", args.refresh,
               lang=accept_lang)

    print("5) 提取 app.js 中的静态界面文案（供人工补译参考）")
    ui = sorted(set(re.findall(r'_v\("((?:[^"\\]|\\.)*)"\)', app_js)))
    ui = [x.strip() for x in ui if 2 <= len(x.strip()) <= 90 and re.search(r"[A-Za-z]{3}", x)]
    (CACHE / "ui_strings.json").write_text(
        __import__("json").dumps(sorted(set(ui)), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  界面文本 {len(set(ui))} 条")

    (CACHE / "meta.json").write_text(
        __import__("json").dumps({
            "app_bundle": app_path,
            "atlas_version": atlas_version,
            "poe_version": poe_version,
            "tree_strings": len(tree_strings),
            "trans_strings": len(trans_strings),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
