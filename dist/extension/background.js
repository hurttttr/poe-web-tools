/* FilterBlade MCP 桥 · background service worker（降级路径）
 * 只有当页面侧 fetch 127.0.0.1 被 CSP / mixed content 拦下时才启用。
 * 扩展侧发起的请求不受页面 CSP 与混合内容限制。
 */
(() => {
  'use strict';

  const BASE = 'http://127.0.0.1:8765';
  const MATCHES = [
    'https://www.filterblade.xyz/*',
    'https://filterblade.xyz/*',
    'https://beta.filterblade.xyz/*'
  ];
  let enabled = false;
  let looping = false;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function execOnPage(cmd) {
    let tabs;
    try {
      tabs = await chrome.tabs.query({ url: MATCHES });
    } catch (_) {
      return { id: cmd.id, ok: false, error: '无法查询标签页' };
    }
    if (!tabs.length) {
      return { id: cmd.id, ok: false, error: '未找到已打开的 FilterBlade 标签页' };
    }
    return new Promise((resolve) => {
      chrome.tabs.sendMessage(tabs[0].id, {
        __fb_mcp: 'exec', id: cmd.id, method: cmd.method, args: cmd.args
      }, (response) => {
        void chrome.runtime.lastError;
        resolve(response || { id: cmd.id, ok: false, error: '页面无响应' });
      });
    });
  }

  async function loop() {
    if (looping) return;
    looping = true;
    let failures = 0;
    try {
      while (enabled) {
        let cmd = null;
        try {
          const resp = await fetch(BASE + '/poll?wait=20', { cache: 'no-store' });
          failures = 0;
          if (resp.status === 204) continue;
          if (resp.ok) cmd = await resp.json();
        } catch (_) {
          failures += 1;
          if (failures >= 5) break;
          await sleep(2000);
          continue;
        }
        if (!cmd || !cmd.id) continue;
        const result = await execOnPage(cmd);
        await fetch(BASE + '/result', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(result)
        }).catch(() => {});
      }
    } finally {
      looping = false;
    }
  }

  function enable() {
    enabled = true;
    loop();
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.__fb_mcp !== 'fallback') return;
    enable();
    sendResponse({ ok: true });
    return true;
  });

  // service worker 被回收后由 alarm 重新拉起循环
  try {
    chrome.alarms.create('fbMcpWake', { periodInMinutes: 0.5 });
    chrome.alarms.onAlarm.addListener((alarm) => {
      if (alarm.name === 'fbMcpWake' && enabled && !looping) loop();
    });
  } catch (_) { /* 权限缺失时仅依赖页面侧直连 */ }

  chrome.runtime.onStartup.addListener(() => { if (enabled) loop(); });
})();
