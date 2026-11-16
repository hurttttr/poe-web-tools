#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把生成好的 .filter 打包成一个离线 HTML「同步页」。

用途：PoE 官网的 item-filter 编辑器需要登录后手动粘贴脚本。这个页面把
完整过滤器全文、改动段、一键复制 / 下载都放在本地，复制后粘进官网编辑器
保存，即成为账号下的官方在线过滤器，游戏会自动下载同步。

页面自包含、无外部资源、file:// 直接打开可用。

用法:
    python tools/build_sync_page.py
    python tools/build_sync_page.py --filter <路径> --output <路径>
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_scroll_highlight import build_block  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILTER = Path(
    "D:/YY/Documents/My Games/Path of Exile/NeverSink-4verystr-scroll-highlight.filter"
)
DEFAULT_OUTPUT = ROOT / "mcp" / "out" / "filter-sync.html"
DEFAULT_EDITOR = "https://www.pathofexile.com/item-filter/create/GmXoTD"
FILTERBLADE = "https://www.filterblade.xyz/?game=Poe1"


def js_string(value: str) -> str:
    """安全嵌进 <script> 的字符串字面量。"""
    out = json.dumps(value, ensure_ascii=False)
    return out.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PoE 过滤器同步页 · 成堆卷轴高亮</title>
<style>
:root{--bg:#f6f7f5;--card:#fff;--line:#e2e6e1;--text:#20262a;--muted:#6b7280;--accent:#0f6e56;--soft:#e1f5ee;--blue:#185fa5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:30px 22px 64px}
h1{font-size:22px;font-weight:600;margin:0 0 6px}
h2{font-size:15px;font-weight:600;margin:0 0 12px}
.sub{color:var(--muted);margin:0 0 16px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:12px;color:var(--muted)}
.chip b{color:var(--text);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:16px}
.btns{display:flex;flex-wrap:wrap;gap:10px}
button,a.btn{font:inherit;font-size:13px;border-radius:8px;padding:9px 15px;border:1px solid var(--line);background:#fff;color:var(--text);cursor:pointer;text-decoration:none;display:inline-block}
button:hover,a.btn:hover{border-color:var(--accent)}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.primary:hover{opacity:.9}
button.link{color:var(--blue);border-color:#cfe0f3}
.status{min-height:20px;margin:10px 0 0;font-size:12px;color:var(--accent)}
ol,ul{margin:0;padding-left:22px}
li{margin:6px 0}
.note{color:var(--muted);font-size:12px;margin:12px 0 0}
pre{margin:0;background:#f8f9f7;border:1px solid var(--line);border-radius:8px;padding:14px;overflow:auto;font:12px/1.6 ui-monospace,Consolas,monospace;white-space:pre}
textarea{width:100%;height:210px;background:#f8f9f7;border:1px solid var(--line);border-radius:8px;padding:12px;font:12px/1.5 ui-monospace,Consolas,monospace;resize:vertical;color:var(--text)}
textarea.expanded{height:560px}
.warn{background:#fff8ec;border:1px solid #f3dfb8;border-radius:8px;padding:10px 14px;font-size:12px;color:#7a5410;margin-top:12px}
</style>
</head>
<body>
<div class="wrap">
  <h1>过滤器同步页</h1>
  <p class="sub">基于 NeverSink 4-Very-Strict，已加入「成堆回城卷轴 / 鉴定卷轴高亮」的完整过滤器。页面自包含，可离线打开。</p>
  <div class="chips" id="chips"></div>

  <section class="card">
    <h2>① 一键操作</h2>
    <div class="btns">
      <button class="primary" id="copyAll">复制全文</button>
      <button id="download">下载 .filter</button>
      <button id="copyCustom">只复制高亮规则段</button>
      <a class="btn link" href="__EDITOR__" target="_blank" rel="noopener">打开 PoE 官网编辑器</a>
      <a class="btn link" href="__FILTERBLADE__" target="_blank" rel="noopener">打开 FilterBlade</a>
    </div>
    <p class="status" id="status"></p>
  </section>

  <section class="card">
    <h2>② 同步到官方账号（推荐）</h2>
    <ol>
      <li>登录 pathofexile.com，点上面「打开 PoE 官网编辑器」（需已登录，否则会跳登录页）。</li>
      <li>点「复制全文」，粘贴进编辑器的脚本框，填一个名字（例如 <code>NS-VeryStrict-ScrollHL</code>）后保存。</li>
      <li>游戏内 选项 → 界面 → 物品过滤器 选中这份在线过滤器；重进游戏或切换一次过滤器即会下载生效。</li>
    </ol>
    <p class="note">文件开头的 <code>#Online Item Filter</code> / <code>#name:</code> / <code>#hash:</code> 等都是注释，粘贴进官网编辑器不会影响规则。</p>
    <div class="warn">备用路径：点「下载 .filter」→ FilterBlade → Advanced → Upload filter 上传 → Export to PoE。注意官方提示：本地上传的过滤器无法使用 My Filters 系统，跨赛季自动合并会受限。</div>
  </section>

  <section class="card">
    <h2>③ 这次新增的规则（可单独核对 / 复制）</h2>
    <pre id="custom"></pre>
    <p class="note">这段插在 <code>[[0100]]</code> 覆写区最前，优先级高于原配方所有规则；删掉整段即可还原。阈值 StackSize &gt;= __STACK__，回城卷轴蓝色 / 鉴定卷轴橙色。</p>
  </section>

  <section class="card">
    <h2>④ 过滤器全文 <button id="toggle" style="float:right;padding:4px 12px;font-size:12px">展开 / 收起</button></h2>
    <textarea id="full" readonly spellcheck="false"></textarea>
  </section>
</div>
<script>
const FULL = __JS_FULL__;
const CUSTOM = __JS_CUSTOM__;
const FILENAME = __JS_FILENAME__;
const STATS = __JS_STATS__;
const statusEl = document.getElementById('status');
function toast(msg){ statusEl.textContent = msg; setTimeout(()=>{statusEl.textContent='';},4000); }
async function copyText(text){
  try { await navigator.clipboard.writeText(text); return true; } catch(e) {}
  const ta=document.createElement('textarea'); ta.value=text;
  ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta);
  ta.select(); let ok=false; try{ ok=document.execCommand('copy'); }catch(e){}
  ta.remove(); return ok;
}
document.getElementById('copyAll').onclick = async ()=>{
  toast(await copyText(FULL) ? ('已复制全文（'+FULL.length.toLocaleString()+' 字符）') : '复制失败，请在下方全文本框里手动全选复制');
};
document.getElementById('copyCustom').onclick = async ()=>{
  toast(await copyText(CUSTOM) ? '已复制高亮规则段' : '复制失败，请在上方代码框里手动复制');
};
document.getElementById('download').onclick = ()=>{
  const blob=new Blob([FULL],{type:'text/plain;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=FILENAME;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(a.href),2000);
  toast('已下载 '+FILENAME);
};
document.getElementById('toggle').onclick = ()=>{
  document.getElementById('full').classList.toggle('expanded');
};
const chips=document.getElementById('chips');
STATS.forEach(([k,v])=>{ const s=document.createElement('span'); s.className='chip';
  s.innerHTML=k+' <b></b>'; s.querySelector('b').textContent=v; chips.appendChild(s); });
document.getElementById('custom').textContent=CUSTOM;
document.getElementById('full').value=FULL;
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 .filter 的离线同步网页")
    ap.add_argument("--filter", type=Path, default=DEFAULT_FILTER)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--editor", default=DEFAULT_EDITOR)
    args = ap.parse_args()

    if not args.filter.is_file():
        print(f"过滤器文件不存在：{args.filter}", file=sys.stderr)
        return 1
    raw = args.filter.read_bytes()
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    meta = {}
    for line in lines[:12]:
        m = re.match(r"#(\w+):(.*)", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()

    marker = re.search(r"(?m)^Show # %D8", text)
    head = text[:marker.start()] if marker else text[:8000]
    stack_match = re.search(r"(?m)^\s*StackSize >= (\d+)", head)
    stack = int(stack_match.group(1)) if stack_match else 5
    custom = build_block(stack, "PlayAlertSound" in head)

    blocks = len(re.findall(r"(?m)^(?:Show|Hide)\b", text))
    stats = [
        ("游戏版本", meta.get("version", "-")),
        ("过滤器版本", meta.get("filterVersion", "-")),
        ("更新时间", meta.get("lastUpdate", "-")[:10]),
        ("行数", f"{len(lines):,}"),
        ("规则块", f"{blocks:,}"),
        ("成堆阈值", f"≥ {stack}"),
        ("大小", f"{len(raw) / 1024:.0f} KB"),
    ]

    page = (PAGE
            .replace("__EDITOR__", html.escape(args.editor, quote=True))
            .replace("__FILTERBLADE__", html.escape(FILTERBLADE, quote=True))
            .replace("__STACK__", str(stack))
            .replace("__JS_FULL__", js_string(text))
            .replace("__JS_CUSTOM__", js_string(custom))
            .replace("__JS_FILENAME__", js_string(args.filter.name))
            .replace("__JS_STATS__", json.dumps(stats, ensure_ascii=False)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8", newline="\n")
    print("同步页已生成")
    print(f"  {args.output}  ({args.output.stat().st_size:,} bytes)")
    print(f"  内嵌过滤器 {len(lines):,} 行 / {blocks} 块 / 阈值 ≥{stack}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
