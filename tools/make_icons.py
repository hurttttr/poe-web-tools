#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成扩展图标：深蓝底 + 金色描边 + 「汉」字，输出 128 / 48 / 32 / 16 四种尺寸。

用法: python tools/make_icons.py
输出: src/extension/icons/icon{128,48,32,16}.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "extension" / "icons"
S = 512  # 母版尺寸，最后缩小以获得抗锯齿

BG_TOP = (36, 47, 74)
BG_BOTTOM = (14, 19, 30)
GOLD = (255, 217, 128)
GOLD_DEEP = (217, 164, 65)

CN_FONTS = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
EN_FONTS = [
    "C:/Windows/Fonts/Dengb.ttf",
    "C:/Windows/Fonts/msyhbd.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def pick_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("找不到可用字体，请修改 CN_FONTS / EN_FONTS")


def vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    strip = Image.new("RGB", (1, size))
    px = strip.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return strip.resize((size, size), Image.BILINEAR)


def draw_letter_spaced(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    spacing: int,
) -> None:
    """逐字绘制以模拟 letter-spacing，整体水平居中于 xy[0]。"""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = xy[0] - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, xy[1]), ch, font=font, fill=fill, anchor="lm")
        x += w + spacing


def build_master(detail: bool = True) -> Image.Image:
    radius = 104
    margin = 10
    box = (margin, margin, S - margin, S - margin)

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)

    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    canvas.paste(vertical_gradient(S, BG_TOP, BG_BOTTOM).convert("RGBA"), (0, 0), mask)

    # 中心暖色光晕，让深色底不至于死板（小尺寸会糊，故仅细节版使用）
    if detail:
        halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse((76, 40, 436, 400), fill=(255, 196, 96, 30))
        halo = halo.filter(ImageFilter.GaussianBlur(80))
        canvas = Image.alpha_composite(
            canvas, Image.composite(halo, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask)
        )

    draw = ImageDraw.Draw(canvas)

    # 金色外框 + 内侧细线（小尺寸省略细线，避免糊边）
    draw.rounded_rectangle(box, radius=radius, outline=GOLD_DEEP + (255,), width=11 if detail else 15)
    if detail:
        draw.rounded_rectangle((30, 30, S - 30, S - 30), radius=84, outline=GOLD + (60,), width=3)

    # 主字：细节版带柔光；小尺寸用更大的字、不加光
    font_cn = pick_font(CN_FONTS, 232 if detail else 320)
    glyph = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text(
        (S / 2, 202 if detail else 256), "汉", font=font_cn, fill=GOLD + (255,), anchor="mm"
    )
    if detail:
        glow = glyph.filter(ImageFilter.GaussianBlur(16))
        glow = glow.point(lambda v: min(255, int(v * 1.25)))
        canvas = Image.alpha_composite(canvas, glow)
        canvas = Image.alpha_composite(canvas, glow)
    canvas = Image.alpha_composite(canvas, glyph)

    if not detail:
        return canvas

    draw = ImageDraw.Draw(canvas)

    # 分隔线 + POE 标记
    draw.rounded_rectangle((199, 352, 313, 356), radius=2, fill=GOLD_DEEP + (110,))
    font_en = pick_font(EN_FONTS, 38)
    draw_letter_spaced(draw, (S / 2, 392), "POE", font_en, GOLD_DEEP + (235,), spacing=10)

    return canvas


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    full = build_master(detail=True)
    compact = build_master(detail=False)
    for size in (128, 48, 32, 16):
        icon = (compact if size <= 32 else full).resize((size, size), Image.LANCZOS)
        path = OUT / f"icon{size}.png"
        icon.save(path, optimize=True)
        print(f"  {path.relative_to(ROOT)}  {size}x{size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
