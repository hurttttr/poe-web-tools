#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FilterBlade MCP Server：用自然语言读写 FilterBlade 的自定义配置。

零第三方依赖。stdio 承载 MCP（JSON-RPC 2.0，换行分隔），另起一个只监听
127.0.0.1 的 HTTP 桥与浏览器扩展通信。

设计约束（详见 docs/AI-NOTES.md §8）：
  1. MCP 不凭空构造 changeGroups —— {changeType, changeValue} 的格式随站点版本变，
     只能读取站点自己生成的 simplifySaveStateContent()，做字段级修改后整体回写；
  2. optionFile 文件名哈希动态发现，不硬编码赛季 / 版本；
  3. 不触碰 OAuth、账号同步与站点后端接口，导出与确认由用户完成。

用法:
    python mcp/fb_mcp.py                 # stdio 模式，供 MCP 客户端拉起
    python mcp/fb_mcp.py --port 8765     # 指定本地桥端口
    python mcp/fb_mcp.py --self-test     # 离线自检，不启动服务
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESEARCH = ROOT / "research"
MCP_DIR = ROOT / "mcp"
DEFAULT_PORT = 8765
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "filterblade-control", "version": "0.1.0"}

SECTION_RE = re.compile(r'^\s*Section(?:Title)?\(\s*"([^"]+)"')

# Customizer 分组名里未被词典收录的高频词，人工补齐（英文小写 -> 中文）
OPTION_ZH = {
    "stacks": "堆叠", "stack": "堆叠", "large": "大型", "small": "小型",
    "general": "通用", "specific": "专属", "highlight": "高亮",
    "misc": "杂项", "exotic": "特殊", "rewards": "奖励", "campaign": "剧情",
    "maps": "地图", "map": "地图", "uniques": "暗金", "unique": "暗金",
    "gems": "宝石", "gem": "宝石", "divination": "命运卡", "cards": "卡片",
    "flasks": "药剂", "jewels": "珠宝", "weapons": "武器", "armour": "护甲",
    "currency": "通货", "tier": "层级", "tiers": "层级", "endgame": "终局",
    "leveling": "练级", "six-link": "六连", "6-link": "六连", "links": "连",
    "rare": "稀有", "magic": "魔法", "normal": "普通", "socketed": "插槽",
    "editor": "编辑器", "rules": "规则", "overrides": "覆写", "styles": "样式",
    "sounds": "音效", "colors": "配色", "colors&sounds": "配色与音效",
}


def log(*parts: object) -> None:
    print("[fb-mcp]", *parts, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# 配置树索引：从 optionFile*.options 抽取可配项，用现有词典做中文映射
# --------------------------------------------------------------------------
class OptionIndex:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.source: str = ""

    def build(self) -> None:
        files = sorted(RESEARCH.glob("optionFile*.options"))
        if not files:
            raise RuntimeError(
                "未找到 research/optionFile*.options，请先运行 python tools/fetch_site_assets.py"
            )
        dictionary: dict[str, str] = {}
        dict_path = DATA / "dictionary.json"
        if dict_path.exists():
            dictionary = json.loads(dict_path.read_text(encoding="utf-8"))

        self.source = ", ".join(p.name for p in files)
        self.items = []
        for path in files:
            stack: list[str] = []
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                match = SECTION_RE.match(line)
                if match:
                    name = match.group(1).strip()
                    path_str = " / ".join(stack + [name])
                    self.items.append({
                        "name": name,
                        "zh": self._translate(name, dictionary),
                        "path": path_str,
                        "file": path.name,
                        "line": lineno,
                        "is_group": line.rstrip().endswith("{"),
                    })
                    if line.rstrip().endswith("{"):
                        stack.append(name)
                else:
                    closes = line.count("}") - line.count("{")
                    for _ in range(max(0, closes)):
                        if stack:
                            stack.pop()

    @staticmethod
    def _translate(name: str, dictionary: dict[str, str]) -> str:
        if name in dictionary:
            return dictionary[name]
        pieces = name.replace("&", " ").replace("-", " ").split()
        out = []
        for piece in pieces:
            found = dictionary.get(piece) or OPTION_ZH.get(piece.lower())
            out.append(found or piece)
        return "".join(out)

    def search(self, query: str, limit: int = 12) -> list[dict]:
        q = (query or "").strip().lower()
        if not q:
            return self.items[:limit]
        scored: list[tuple[int, dict]] = []
        for item in self.items:
            name = item["name"].lower()
            zh = item["zh"].lower()
            path = item["path"].lower()
            if q == name:
                score = 100
            elif q in name:
                score = 70
            elif q in zh:
                score = 60
            elif q in path:
                score = 30
            else:
                continue
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["line"]))
        return [item for _, item in scored[:limit]]


# --------------------------------------------------------------------------
# 存档包装：外层是官方 save-file 格式，内层是站点生成的 simplify 对象
# --------------------------------------------------------------------------
def count_changes(inner: dict) -> int:
    return sum(
        len(group.get("groupChanges") or [])
        for group in (inner.get("changeGroups") or [])
        if isinstance(group, dict)
    )


def validate_inner(state: object) -> str | None:
    if not isinstance(state, dict):
        return "state 必须是对象"
    if "changeGroups" not in state or not isinstance(state["changeGroups"], list):
        return "state 缺少 changeGroups 数组（应来自 fb_get_state，不要手工编造）"
    for group in state["changeGroups"]:
        if not isinstance(group, dict) or "groupChanges" not in group:
            return "changeGroups 里的元素缺少 groupChanges"
        if group.get("changeGroupVersion", 4) < 4:
            return "存档格式过旧（changeGroupVersion < 4），请先在站点里另存一次"
    return None


def wrap_save_file(inner: dict, name: str = "MCP 配置", game_type: str = "Poe1") -> dict:
    """包成站点 Advanced -> Upload filter 能直接吃下的 save-file JSON。"""
    return {
        "display_name": name,
        "is_preset": False,
        "date_modified": int(time.time() * 1000),
        "saveStateContent": json.dumps(inner, ensure_ascii=False, separators=(",", ":")),
        "meta_json_string": {
            "lastGameType": game_type,
            "changeCount": count_changes(inner),
        },
        "tags": [],
    }


def parse_save_file(path: Path) -> dict:
    """解析用户从 Advanced -> Download 拿到的官方存档，抽出内层状态与改动模板。"""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc, list) and doc:
        doc = doc[0]
    content = doc.get("saveStateContent") if isinstance(doc, dict) else None
    if isinstance(content, str):
        if content.startswith("noUpdate"):
            content = content[8:]
        inner = json.loads(content)
    elif isinstance(content, dict):
        inner = content
    else:
        inner = doc
    if inner.get("saveStateContent"):
        inner = parse_save_file_inline(inner)
    problem = validate_inner(inner)
    if problem:
        raise ValueError(problem)
    return {
        "inner": inner,
        "display_name": doc.get("display_name") if isinstance(doc, dict) else None,
        "templates": [
            {"changeType": c.get("changeType"), "changeValue": c.get("changeValue")}
            for g in inner.get("changeGroups", [])
            for c in g.get("groupChanges", [])
        ],
    }


def parse_save_file_inline(inner: dict) -> dict:
    content = inner.get("saveStateContent")
    return json.loads(content) if isinstance(content, str) else content


# --------------------------------------------------------------------------
# 本地桥：只监听 127.0.0.1，扩展来轮询命令并回传结果
# --------------------------------------------------------------------------
class Bridge:
    def __init__(self, port: int) -> None:
        self.port = port
        self.commands: queue.Queue = queue.Queue()
        self.results: dict[str, dict] = {}
        self.events: dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.last_poll = 0.0
        self.server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

            def _cors(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Cache-Control", "no-store")

            def _json(self, code: int, payload: object | None = None) -> None:
                body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                if payload is not None:
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_OPTIONS(self) -> None:
                self._json(204)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/status":
                    self._json(200, {
                        "ok": True,
                        "connected": bridge.connected(),
                        "pending": len(bridge.events),
                        "port": bridge.port,
                    })
                elif parsed.path == "/poll":
                    bridge.last_poll = time.time()
                    wait = float(parse_qs(parsed.query).get("wait", ["20"])[0])
                    try:
                        cmd = bridge.commands.get(timeout=max(0.1, min(wait, 25)))
                    except queue.Empty:
                        self._json(204)
                        return
                    self._json(200, cmd)
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/result":
                    self._json(404, {"error": "not found"})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                bridge.accept_result(payload)
                self._json(200, {"ok": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        log(f"本地桥已监听 http://127.0.0.1:{self.port}")

    def connected(self) -> bool:
        return time.time() - self.last_poll < 30

    def accept_result(self, payload: dict) -> None:
        cid = payload.get("id")
        if not cid:
            return
        with self.lock:
            self.results[cid] = payload
            event = self.events.get(cid)
        if event:
            event.set()

    def request(self, method: str, args: dict | None = None, timeout: float = 25) -> dict:
        cid = uuid.uuid4().hex
        event = threading.Event()
        with self.lock:
            self.events[cid] = event
        self.commands.put({"id": cid, "method": method, "args": args or {}})
        arrived = event.wait(timeout)
        with self.lock:
            self.events.pop(cid, None)
            result = self.results.pop(cid, None)
        if not arrived or result is None:
            return {
                "ok": False,
                "error": f"扩展在 {int(timeout)} 秒内未响应：请确认 FilterBlade 标签页已打开、扩展已重新加载、本地桥已启动",
            }
        return result


# --------------------------------------------------------------------------
# MCP 工具定义：保持"薄"，语义判断交给对话里的模型
# --------------------------------------------------------------------------
TOOLS = [
    {
        "name": "fb_status",
        "description": "检查浏览器扩展是否已连上本地桥、FilterBlade 页面是否就绪。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "fb_search_options",
        "description": "按中文或英文关键词检索 FilterBlade Customizer 的可配项（来自 optionFile*.options），返回英文原名、中文名与菜单路径。用于把用户口语定位到具体配置项。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "中文或英文关键词，例如「通货堆叠」「Currency Stacks」「地图」"},
                "limit": {"type": "integer", "description": "返回条数，默认 12"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fb_get_state",
        "description": "从已打开的 FilterBlade 页面读取当前配置存档（strictness / style / changeGroups 等）。这是修改前的必读步骤：后续 fb_apply_state 必须基于它返回的 inner 对象。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "fb_apply_state",
        "description": "把修改后的完整配置写回 FilterBlade 并即时生效。必须传入 fb_get_state 返回的 inner 对象（只改动其中字段），不要自行构造 changeGroups。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "object", "description": "fb_get_state 返回的 inner 对象，按需改字段后整体传回"},
            },
            "required": ["state"],
        },
    },
    {
        "name": "fb_export_save_file",
        "description": "把配置导出成 FilterBlade 官方 save-file JSON，可在 Advanced -> Upload filter 里手动导入。不传 state 时自动从页面读取。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "object", "description": "可选，fb_get_state 的 inner 对象"},
                "path": {"type": "string", "description": "输出路径，默认 mcp/out/filterblade-save.json"},
                "name": {"type": "string", "description": "存档显示名"},
            },
        },
    },
    {
        "name": "fb_import_sample",
        "description": "解析用户从 Advanced -> Download 得到的官方存档，抽出真实 change 模板，供以后生成新改动时参考（避免猜测 changeValue 格式）。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "官方 save-file JSON 的本地路径"}},
            "required": ["path"],
        },
    },
]


def tool_result(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
            "isError": bool(payload.get("ok") is False)}


def call_tool(name: str, args: dict, index: OptionIndex, bridge: Bridge) -> dict:
    if name == "fb_status":
        return {"ok": True, "connected": bridge.connected(),
                "options": len(index.items), "source": index.source,
                "hint": "connected=false 时请打开 FilterBlade 标签页并重新加载扩展"}

    if name == "fb_search_options":
        query = str(args.get("query") or "")
        limit = max(1, min(50, int(args.get("limit") or 12)))
        return {"ok": True, "query": query, "count": len(index.items),
                "results": index.search(query, limit), "source": index.source}

    if name == "fb_get_state":
        result = bridge.request("getState")
        if result.get("ok"):
            result["hint"] = "修改 inner 后整体传给 fb_apply_state；不要新建 changeGroups"
        return result

    if name == "fb_apply_state":
        state = args.get("state")
        problem = validate_inner(state)
        if problem:
            return {"ok": False, "error": problem}
        return bridge.request("applyState", {"state": state}, timeout=35)

    if name == "fb_export_save_file":
        state = args.get("state")
        if state is None:
            pulled = bridge.request("getState")
            if not pulled.get("ok"):
                return pulled
            state = (pulled.get("data") or {}).get("inner")
        problem = validate_inner(state)
        if problem:
            return {"ok": False, "error": problem}
        target = Path(args.get("path") or (MCP_DIR / "out" / "filterblade-save.json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        game = ((args.get("_gameType") or "Poe1"))
        doc = wrap_save_file(state, str(args.get("name") or "MCP 配置"), game)
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(target), "changes": count_changes(state)}

    if name == "fb_import_sample":
        try:
            parsed = parse_save_file(Path(args["path"]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"解析失败：{exc}"}
        out = MCP_DIR / "out" / "change-templates.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(parsed["templates"], ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "display_name": parsed["display_name"],
                "templates": len(parsed["templates"]), "path": str(out),
                "hint": "changeGroups 需与 inner 一起回写，模板仅用于确认 changeValue 的真实格式"}

    return {"ok": False, "error": f"未知工具：{name}"}


# --------------------------------------------------------------------------
# MCP stdio（JSON-RPC 2.0，换行分隔）
# --------------------------------------------------------------------------
def handle_message(msg: dict, index: OptionIndex, bridge: Bridge) -> dict | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    if msg_id is None:
        return None
    base = {"jsonrpc": "2.0", "id": msg_id}
    if method == "initialize":
        base["result"] = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }
    elif method == "ping":
        base["result"] = {}
    elif method == "tools/list":
        base["result"] = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params") or {}
        try:
            payload = call_tool(params.get("name", ""), params.get("arguments") or {}, index, bridge)
        except Exception as exc:  # noqa: BLE001 - stdio 服务不能被单个工具异常打断
            log("tool error:", repr(exc))
            payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        base["result"] = tool_result(payload)
    elif method in ("resources/list", "prompts/list"):
        base["result"] = {"resources": []} if method == "resources/list" else {"prompts": []}
    else:
        base["error"] = {"code": -32601, "message": f"Method not found: {method}"}
    return base


def serve_stdio(index: OptionIndex, bridge: Bridge) -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line or line.lower().startswith("content-length:"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log("跳过无法解析的消息")
            continue
        if not isinstance(msg, dict):
            continue
        response = handle_message(msg, index, bridge)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


def self_test() -> int:
    index = OptionIndex()
    index.build()
    print(f"配置索引：{len(index.items)} 项，来源 {index.source}")
    for item in index.search("通货", 4):
        print(f"  {item['zh']} <- {item['name']}  [{item['path']}]")
    inner = {"version": 1, "filterName": "test", "strictness": "1-REGULAR",
             "style": "Normal", "metaData": {},
             "changeGroups": [{"presetDataObj": {}, "groupChanges": [
                 {"changeType": "tier", "changeValue": 3}], "isHidden": False,
               "changeGroupVersion": 4}]}
    assert validate_inner(inner) is None
    assert validate_inner({"changeGroups": []}) is None
    assert validate_inner({}) is not None
    wrapped = wrap_save_file(inner)
    assert isinstance(wrapped["saveStateContent"], str)
    assert json.loads(wrapped["saveStateContent"]) == inner
    assert wrapped["meta_json_string"]["changeCount"] == 1
    print(f"存档包装：OK（{len(wrapped['saveStateContent'])} 字符，改动 1 条）")

    class FakeBridge(Bridge):
        def __init__(self) -> None:
            super().__init__(0)

        def request(self, method: str, args: dict | None = None, timeout: float = 25) -> dict:
            return {"ok": True, "data": {"inner": inner}, "method": method}

    fake = FakeBridge()
    init = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, index, fake)
    assert init["result"]["serverInfo"]["name"] == "filterblade-control"
    listed = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, index, fake)
    assert [t["name"] for t in listed["result"]["tools"]] == [t["name"] for t in TOOLS]
    called = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "fb_search_options", "arguments": {"query": "currency"}}}, index, fake)
    assert called["result"]["isError"] is False
    print(f"MCP 握手 / tools/list / tools/call：OK（{len(TOOLS)} 个工具）")
    print("自检通过")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="FilterBlade MCP Server")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="本地桥端口")
    ap.add_argument("--self-test", action="store_true", help="离线自检，不启动服务")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

    index = OptionIndex()
    try:
        index.build()
    except RuntimeError as exc:
        log("配置索引加载失败：", exc)
        if args.self_test:
            return 1
        index.items = []

    if args.self_test:
        return self_test()

    bridge = Bridge(args.port)
    try:
        bridge.start()
    except OSError as exc:
        log(f"本地桥启动失败（端口 {args.port} 可能被占用）：{exc}")
        return 1
    log(f"MCP Server 就绪，工具 {len(TOOLS)} 个，配置项 {len(index.items)} 条")
    return serve_stdio(index, bridge)


if __name__ == "__main__":
    raise SystemExit(main())
