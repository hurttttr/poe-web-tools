#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP Server 自检：stdio 握手、工具清单、本地桥 HTTP 协议。

用法: python tests/check_mcp.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))
import fb_mcp  # noqa: E402

FAILS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        FAILS.append(name)


def test_self_test() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "mcp" / "fb_mcp.py"), "--self-test"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    check("离线自检脚本退出码为 0", proc.returncode == 0, proc.stderr.strip()[:200])
    check("配置索引有内容", "配置索引：" in proc.stdout and "项" in proc.stdout)


def test_protocol() -> None:
    index = fb_mcp.OptionIndex()
    index.build()
    check("optionFile 动态发现到配置树", len(index.items) > 100, f"{len(index.items)} 项")
    check("中文检索命中通货类配置", any("通货" in r["zh"] for r in index.search("通货", 20)))
    check("英文检索命中 Currency", any("Currency" in r["name"] for r in index.search("Currency", 20)))

    bridge = fb_mcp.Bridge(0)
    bridge.start()
    port = bridge.server.server_address[1]
    base = f"http://127.0.0.1:{port}"

    def http(method: str, path: str, payload: dict | None = None, timeout: float = 8):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None

    status, body = http("GET", "/status")
    check("/status 返回 ok", status == 200 and body["ok"] is True)

    received: dict = {}

    def fake_extension() -> None:
        _, cmd = http("GET", "/poll?wait=5")
        received.update(cmd)
        http("POST", "/result", {
            "id": cmd["id"], "ok": True,
            "data": {"inner": {"changeGroups": []}},
        })

    worker = threading.Thread(target=fake_extension, daemon=True)
    worker.start()
    result = bridge.request("getState", timeout=8)
    worker.join(timeout=8)
    check("命令经 /poll 下发并被 /result 回收", result.get("ok") is True)
    check("命令方法名正确", received.get("method") == "getState")
    check("回传数据完整", (result.get("data") or {}).get("inner") is not None)

    bad = fb_mcp.validate_inner({"changeGroups": [{"groupChanges": []}]})
    check("合法内层状态通过校验", bad is None)
    check("编造的状态被拒绝", fb_mcp.validate_inner({}) is not None)
    wrapped = fb_mcp.wrap_save_file({"version": 1, "changeGroups": []})
    check("save-file 外层含 saveStateContent 字符串", isinstance(wrapped["saveStateContent"], str))
    check("save-file 外层含 meta_json_string.changeCount", "changeCount" in wrapped["meta_json_string"])

    bridge.server.shutdown()
    bridge.server.server_close()


def main() -> int:
    print("MCP Server 自检")
    test_self_test()
    test_protocol()
    print(f"\n结果：{'全部通过' if not FAILS else '失败 ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
