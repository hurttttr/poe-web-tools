/* FilterBlade MCP 桥 · 隔离世界（ISOLATED world）
 * 优先直连 127.0.0.1 本地桥；若页面 CSP / mixed content 拦住了直连，
 * 自动降级为让 background service worker 代为收发。
 */
(() => {
  'use strict';

  const BASE = 'http://127.0.0.1:8765';
  const REQ = '__fb_mcp__/request';
  const RES = '__fb_mcp__/response';
  const pending = new Map();
  let directFailed = 0;
  let directStopped = false;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function callMain(method, args) {
    return new Promise((resolve) => {
      const id = Math.random().toString(36).slice(2) + '-' + Date.now();
      const timer = setTimeout(() => {
        pending.delete(id);
        resolve({ ok: false, error: '主世界脚本未响应，请确认扩展已重新加载（需 Chrome 111+）' });
      }, 32000);
      pending.set(id, { resolve, timer });
      window.postMessage({ type: REQ, id, method, args: args || {} }, '*');
    });
  }

  window.addEventListener('message', (event) => {
    if (event.source !== window || !event.data || event.data.type !== RES) return;
    const entry = pending.get(event.data.id);
    if (!entry) return;
    pending.delete(event.data.id);
    clearTimeout(entry.timer);
    entry.resolve({ ok: event.data.ok, data: event.data.data, error: event.data.error });
  });

  // background 降级路径会走这条消息；即使直连已停止也要能响应
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.__fb_mcp !== 'exec') return;
    callMain(msg.method, msg.args).then((result) => sendResponse({ id: msg.id, ...result }));
    return true;
  });

  async function postResult(payload) {
    await fetch(BASE + '/result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  function enableFallback() {
    if (directStopped) return;
    directStopped = true;
    try {
      chrome.runtime.sendMessage({ __fb_mcp: 'fallback' }, () => void chrome.runtime.lastError);
    } catch (_) { /* 扩展上下文失效时忽略 */ }
  }

  async function directLoop() {
    while (!directStopped) {
      let cmd = null;
      try {
        const resp = await fetch(BASE + '/poll?wait=20', { cache: 'no-store' });
        directFailed = 0;
        if (resp.status === 204) continue;
        if (!resp.ok) throw new Error('poll HTTP ' + resp.status);
        cmd = await resp.json();
      } catch (_) {
        directFailed += 1;
        if (directFailed >= 3) {
          enableFallback();
          return;
        }
        await sleep(2000);
        continue;
      }
      if (!cmd || !cmd.id) continue;
      const result = await callMain(cmd.method, cmd.args);
      try {
        await postResult({ id: cmd.id, ...result });
      } catch (_) {
        directFailed += 1;
        if (directFailed >= 3) {
          enableFallback();
          return;
        }
      }
    }
  }

  directLoop();
})();
