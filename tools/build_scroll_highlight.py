#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 NeverSink 在线过滤器（GmXoTD / NeverSink-4verystr-softcore）生成
一份「成堆回城卷轴 / 鉴定卷轴高亮」的本地过滤器。

设计要点：
  * 只在最高优先级的 [[0100]] 覆写区之前插入一段自包含规则，
    源文件其余每一行完全不变 —— 删掉这一段即可还原；
  * 只匹配成堆（StackSize >= N）的 Portal Scroll / Scroll of Wisdom。
    单个卷轴仍按原配方显示或隐藏，不改变原有的隐藏策略；
  * 原配方里成堆卷轴虽有 Show 规则，但只给了字号和很暗的底色，
    没有文字色 / 小地图图标 / 光效 / 音效，所以看起来「不高亮」；
  * 输出写在 PoE 主过滤器目录，不放回 OnlineFilters，避免被在线更新覆盖。

用法:
    python tools/build_scroll_highlight.py
    python tools/build_scroll_highlight.py --stack 3 --no-sound
    python tools/build_scroll_highlight.py --source <路径> --output <路径>
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

DEFAULT_SOURCE = Path("D:/YY/Documents/My Games/Path of Exile/OnlineFilters/GmXoTD")
DEFAULT_OUTPUT = Path(
    "D:/YY/Documents/My Games/Path of Exile/NeverSink-4verystr-scroll-highlight.filter"
)

BLOCK_KEYWORDS = {
    "Show", "Class", "BaseType", "StackSize",
    "SetFontSize", "SetTextColor", "SetBorderColor", "SetBackgroundColor",
    "MinimapIcon", "PlayEffect", "PlayAlertSound",
}
COLOR_KEYS = {"SetTextColor", "SetBorderColor", "SetBackgroundColor"}


def build_block(stack: int, sound: bool) -> str:
    bar = "#" + "=" * 111
    lines = [
        bar,
        "# [CUSTOM] 成堆回城卷轴 / 鉴定卷轴高亮  (由 tools/build_scroll_highlight.py 生成)",
        "# 来源: NeverSink-4verystr-softcore (GmXoTD)",
        f"# 条件: StackSize >= {stack} 的成堆卷轴；单个卷轴仍按原配方处理",
        "# 还原: 整段删除即可，其余行与源文件完全一致",
        bar,
        "",
        f"Show # [CUSTOM] 成堆回城卷轴高亮 (StackSize >= {stack})",
        '\tClass == "Stackable Currency"',
        '\tBaseType == "Portal Scroll"',
        f"\tStackSize >= {stack}",
        "\tSetFontSize 45",
        "\tSetTextColor 255 255 255 255",
        "\tSetBorderColor 90 170 255 255",
        "\tSetBackgroundColor 10 55 140 255",
        "\tMinimapIcon 1 Blue Circle",
        "\tPlayEffect Blue",
    ]
    if sound:
        lines.append("\tPlayAlertSound 2 300")
    lines += [
        "",
        f"Show # [CUSTOM] 成堆鉴定卷轴高亮 (StackSize >= {stack})",
        '\tClass == "Stackable Currency"',
        '\tBaseType == "Scroll of Wisdom"',
        f"\tStackSize >= {stack}",
        "\tSetFontSize 45",
        "\tSetTextColor 255 255 255 255",
        "\tSetBorderColor 255 175 70 255",
        "\tSetBackgroundColor 140 55 0 255",
        "\tMinimapIcon 1 Orange Circle",
        "\tPlayEffect Orange",
    ]
    if sound:
        lines.append("\tPlayAlertSound 2 300")
    lines += ["", ""]
    return "\n".join(lines) + "\n"


def find_insert_index(lines: list[str]) -> int:
    """第一条规则之前；并确认它确实落在 [[0100]] 覆写区。"""
    for i, line in enumerate(lines):
        if re.match(r"^(Show|Hide)\b", line):
            head = " ".join(lines[max(0, i - 12):i])
            if "[[0100]]" not in head:
                raise RuntimeError("第一条规则不在 [[0100]] 覆写区，插入位置不安全")
            return i
    raise RuntimeError("源文件里找不到任何 Show/Hide 规则")


def count_blocks(text: str) -> int:
    return len(re.findall(r"(?m)^(?:Show|Hide)\b", text))


def validate_block(block: str) -> None:
    """只校验新插入的段落：关键字、颜色数值、缩进。"""
    for n, line in enumerate(block.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith(("Show ", "Hide ")) or s in ("Show", "Hide"):
            continue
        if not line.startswith("\t"):
            raise ValueError(f"插入段第 {n} 行缺少 tab 缩进: {line!r}")
        key = s.split()[0]
        if key not in BLOCK_KEYWORDS:
            raise ValueError(f"插入段第 {n} 行有未知关键字: {key}")
        if key in COLOR_KEYS:
            parts = s.split()[1:]
            if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                raise ValueError(f"插入段第 {n} 行颜色值非法: {s}")
    if block.count("\r") or "\r\n" in block:
        raise ValueError("插入段必须是纯 LF 换行，与源文件一致")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成成堆卷轴高亮版的本地过滤器")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--stack", type=int, default=5,
                    help="成堆阈值，默认 5（原配方终局为 10，5~9 个原本被隐藏）")
    ap.add_argument("--no-sound", action="store_true", help="不加提示音，只保留视觉高亮")
    args = ap.parse_args()

    if args.stack < 1:
        print("--stack 必须 >= 1", file=sys.stderr)
        return 1
    if not args.source.is_file():
        print(f"源文件不存在：{args.source}", file=sys.stderr)
        return 1
    if args.output.resolve() == args.source.resolve():
        print("输出路径不能等于源文件（原文件不会被修改）", file=sys.stderr)
        return 1
    if not args.output.parent.is_dir():
        print(f"输出目录不存在：{args.output.parent}", file=sys.stderr)
        return 1

    raw = args.source.read_bytes()
    before_hash = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8-sig")
    if "\r\n" in text:
        print("源文件是 CRLF 换行，本脚本按 LF 生成，请先统一换行", file=sys.stderr)
        return 1

    lines = text.split("\n")
    insert_at = find_insert_index(lines)
    block = build_block(args.stack, not args.no_sound)
    validate_block(block)

    # 用「整段插入」而不是逐行改写，保证原有行一字不动
    prefix = "\n".join(lines[:insert_at]) + "\n"
    suffix = "\n".join(lines[insert_at:])
    output = prefix + block + suffix

    assert output.replace(block, "", 1) == text, "输出与源文件的差异不止插入段"
    assert count_blocks(output) == count_blocks(text) + 2, "规则块数量异常"
    assert hashlib.sha256(args.source.read_bytes()).hexdigest() == before_hash, "源文件被意外修改"

    args.output.write_text(output, encoding="utf-8", newline="\n")

    print("生成完成")
    print(f"  源  : {args.source}  ({len(text.splitlines())} 行, {count_blocks(text)} 块, 未改动)")
    print(f"  输出: {args.output}  ({len(output.splitlines())} 行, {count_blocks(output)} 块)")
    print(f"  插入: 第 {insert_at + 1} 行之前（[[0100]] 覆写区），新增 2 条 Show")
    print(f"  条件: StackSize >= {args.stack}，回城卷轴蓝色 / 鉴定卷轴橙色")
    print(f"  音效: {'关闭' if args.no_sound else 'PlayAlertSound 2 300'}")
    print("  校验: 插入段语法 / 颜色范围 / 差异范围 / 源文件完整性 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
