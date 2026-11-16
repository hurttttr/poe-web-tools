#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把词典 + 引擎 + 面板打包成两种可直接安装的产物：
  1. dist/poe-web-tools.user.js    油猴脚本（自包含，无需外部依赖）
  2. dist/extension/               Chrome / Edge Manifest V3 扩展目录

用法: python tools/build_dist.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DATA = ROOT / "data"
DIST = ROOT / "dist"
EXT_SRC = SRC / "extension"
EXT_DST = DIST / "extension"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def js_literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    dictionary = json.loads(read(DATA / "dictionary.json"))
    meta = json.loads(read(DATA / "dictionary.meta.json"))
    engine = read(SRC / "engine.js")
    panel = read(SRC / "panel.js")
    css = read(SRC / "style.css")

    short_words = json.loads(read(DATA / "short_words.json"))["terms"]
    mod_tpl_doc = json.loads(read(DATA / "mod_templates.json"))
    mod_tpl = dict(mod_tpl_doc["templates"])
    # poeplanner 专属 # 模板：只补现有词典没有的骨架，不覆盖另外两个站点的译文
    atlas_tpl_path = DATA / "atlas_templates.json"
    if atlas_tpl_path.exists():
        for _k, _v in json.loads(read(atlas_tpl_path)).items():
            mod_tpl.setdefault(_k, _v)
    mod_tpl_js = json.dumps(mod_tpl, ensure_ascii=False, separators=(",", ":"))
    mod_prefix_js = json.dumps(mod_tpl_doc.get("prefix", {}), ensure_ascii=False, separators=(",", ":"))
    host_terms = {
        k: v for k, v in json.loads(read(DATA / "host_terms.json")).items() if not k.startswith("_")
    }
    # poeplanner.com 专属整句词条（天赋名 / 界面文案），按 host 作用域注入，
    # 只在 poeplanner 生效，不污染 FilterBlade 与 poe.ninja。
    atlas_terms_path = DATA / "atlas_terms.json"
    host_terms["poeplanner.com"] = (
        json.loads(read(atlas_terms_path)) if atlas_terms_path.exists() else {}
    )
    host_js = json.dumps(host_terms, ensure_ascii=False, separators=(",", ":"))
    dict_js = (
        "window.FBZH_DICT = " + json.dumps(dictionary, ensure_ascii=False, separators=(",", ":")) + ";\n"
        + "window.FBZH_SHORT_WORDS = " + json.dumps(short_words, ensure_ascii=False, separators=(",", ":")) + ";\n"
        + "window.FBZH_HOST_DICT = " + host_js + ";\n"
        + "window.FBZH_MOD_TPL = " + mod_tpl_js + ";\n"
        + "window.FBZH_MOD_PREFIX = " + mod_prefix_js + ";\n"
    )
    # 版本号：命令行参数 -> 环境变量 BUILD_VERSION / GITHUB_REF_NAME -> manifest.json
    manifest_src = json.loads(read(EXT_SRC / "manifest.json"))
    version = str(manifest_src.get("version", "1.0.0"))
    if len(sys.argv) > 1 and sys.argv[1].strip():
        version = sys.argv[1].strip().lstrip("v")
    elif os.environ.get("BUILD_VERSION"):
        version = os.environ["BUILD_VERSION"].strip().lstrip("v")
    elif os.environ.get("GITHUB_REF_NAME") and os.environ.get("GITHUB_REF_TYPE") == "tag":
        version = os.environ["GITHUB_REF_NAME"].strip().lstrip("v")

    DIST.mkdir(parents=True, exist_ok=True)
    EXT_DST.mkdir(parents=True, exist_ok=True)

    # ---------- 1. 油猴脚本 ----------
    header = f"""// ==UserScript==
// @name         PoE Web Tools
// @name:zh-CN   PoE 网页工具 · FilterBlade / poe.ninja / PoE Planner
// @name:en      PoE Web Tools (FilterBlade, poe.ninja & PoE Planner)
// @namespace    poe-web-tools
// @version      {version}
// @description  FilterBlade / poe.ninja / PoE Planner 异界天赋树简体中文界面 + 站点快捷跳转；术语以流放之路编年史为准，支持中文 / 双语 / 原文切换，交互时自动还原英文。
// @description:zh-CN 流放之路常用网页工具集：FilterBlade、poe.ninja 与 PoE Planner 异界天赋树汉化、站点跳转，术语以编年史简体中文为准。
// @author       WorkBuddy
// @match        https://www.filterblade.xyz/*
// @match        https://filterblade.xyz/*
// @match        https://beta.filterblade.xyz/*
// @match        https://poe.ninja/*
// @match        https://poeplanner.com/*
// @run-at       document-idle
// @grant        none
// @noframes
// ==/UserScript==

"""
    user_js = (
        header
        + "/* 词典 " + str(meta["entries"]) + " 条，来源见项目 README */\n"
        + dict_js
        + "window.FBZH_CSS = " + js_literal(css) + ";\n\n"
        + engine + "\n\n" + panel + "\n"
    )
    (DIST / "poe-web-tools.user.js").write_text(user_js, encoding="utf-8")
    # 清理旧版本命名的产物，避免安装时选错文件
    for stale in ("poe-web-hans.user.js", "filterblade-zh.user.js"):
        legacy = DIST / stale
        if legacy.exists():
            legacy.unlink()

    # ---------- 2. 浏览器扩展 ----------
    ext_js = dict_js + "window.FBZH_CSS = '';\n\n" + engine + "\n\n" + panel + "\n"
    (EXT_DST / "content.js").write_text(ext_js, encoding="utf-8")
    shutil.copyfile(SRC / "style.css", EXT_DST / "content.css")
    shutil.copyfile(EXT_SRC / "popup.html", EXT_DST / "popup.html")
    shutil.copyfile(EXT_SRC / "popup.js", EXT_DST / "popup.js")
    # MCP 本地桥：主世界脚本 + 隔离世界转发 + background 降级路径
    for bridge_file in ("bridge-main.js", "bridge-content.js", "background.js"):
        shutil.copyfile(EXT_SRC / bridge_file, EXT_DST / bridge_file)
    icons_dst = EXT_DST / "icons"
    if icons_dst.exists():
        shutil.rmtree(icons_dst)
    shutil.copytree(EXT_SRC / "icons", icons_dst)

    manifest = dict(manifest_src)
    manifest["version"] = version
    (EXT_DST / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (EXT_DST / "安装说明.txt").write_text(
        "Chrome / Edge：打开 chrome://extensions（Edge 为 edge://extensions），开启「开发者模式」，"
        "点击「加载已解压的扩展程序」，选择本 extension 文件夹即可。\n"
        "把扩展固定到工具栏后，点击图标即可在三个站点之间跳转，"
        "并开关汉化 / 切换中文·双语·原文。\n"
        "支持站点：https://www.filterblade.xyz/?game=Poe1 、https://poe.ninja/ 、"
        "https://poeplanner.com/atlas-tree 。\n"
        "PoE Planner 的异界天赋树为 canvas 渲染，节点名与说明在悬浮提示中汉化；"
        "站内「搜索节点」按英文匹配，需要英文时按 Alt+Z 切到原文模式。\n"
        "页面右下角会出现「汉」按钮（中英对照查询、导出未译文本）。词典已内联，无需联网。\n"
        "\n"
        "【可选】MCP 本地桥：运行 python mcp/fb_mcp.py 后，扩展会自动连到 127.0.0.1:8765，\n"
        "让 AI 助手读取 / 修改 FilterBlade 配置。需要 Chrome 111+（MAIN world 支持）。\n"
        "未运行 MCP 时扩展功能不受影响，桥接脚本只是静默等待。\n",
        encoding="utf-8",
    )
    shutil.copyfile(DATA / "dictionary.json", DIST / "dictionary.json")

    # ---------- 3. 两个站点的离线效果预览页 ----------
    def render_preview(name: str, out_name: str) -> str:
        template = read(SRC / name)
        rendered = (
            template
            .replace("__DICT__", json.dumps(dictionary, ensure_ascii=False, separators=(",", ":")))
            .replace("__SHORT__", json.dumps(short_words, ensure_ascii=False, separators=(",", ":")))
            .replace("__HOST__", host_js)
            .replace("__MODTPL__", mod_tpl_js)
            .replace("__MODPREFIX__", mod_prefix_js)
            .replace("__CSS__", js_literal(css))
            .replace("__ENGINE__", engine)
            .replace("__PANEL__", panel)
        )
        (DIST / out_name).write_text(rendered, encoding="utf-8")
        return out_name

    render_preview("preview.template.html", "preview.html")
    render_preview("preview-ninja.template.html", "preview-ninja.html")
    if (SRC / "preview-atlas.template.html").exists():
        render_preview("preview-atlas.template.html", "preview-atlas.html")

    # ---------- 4. 打包 Chrome / Edge 扩展 zip ----------
    zip_name = f"poe-web-tools-v{version}-extension"
    zip_path = DIST / f"{zip_name}.zip"
    shutil.make_archive(str(DIST / zip_name), "zip", EXT_DST)
    # 同时保留一份统一命名的 extension.zip
    shutil.copyfile(zip_path, DIST / "poe-web-tools-extension.zip")
    # 升版本后清掉旧版本命名的 zip，避免安装时选错文件
    for old_zip in DIST.glob("poe-web-tools-v*-extension.zip"):
        if old_zip.name != zip_path.name:
            old_zip.unlink()

    print("打包完成")
    print(f"  {DIST / 'poe-web-tools.user.js'}  ({(DIST / 'poe-web-tools.user.js').stat().st_size:,} bytes)")
    print(f"  {EXT_DST}  (content.js {(EXT_DST / 'content.js').stat().st_size:,} bytes)")
    print(f"  {zip_path}  ({zip_path.stat().st_size:,} bytes)")
    print(f"  {DIST / 'preview.html'}  ({(DIST / 'preview.html').stat().st_size:,} bytes)")
    print(f"  {DIST / 'preview-ninja.html'}  ({(DIST / 'preview-ninja.html').stat().st_size:,} bytes)")
    if (DIST / "preview-atlas.html").exists():
        print(f"  {DIST / 'preview-atlas.html'}  ({(DIST / 'preview-atlas.html').stat().st_size:,} bytes)")
    print(f"  词典 {meta['entries']} 条，版本 {version}")
    if atlas_terms_path.exists():
        print(f"  poeplanner 专属词条 {len(host_terms['poeplanner.com'])} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
