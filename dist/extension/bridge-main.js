/* FilterBlade MCP 桥 · 页面主世界（MAIN world）
 * 只有主世界能看到页面顶层的 gFilterBlade。这里不碰 chrome.* API，
 * 通过 window.postMessage 与隔离世界的 bridge-content.js 通信。
 * 关键原则：改动格式一律由站点自己生成，不在这里手工拼 changeGroups。
 */
(() => {
  'use strict';

  const REQ = '__fb_mcp__/request';
  const RES = '__fb_mcp__/response';

  function fb() {
    if (window.gFilterBlade) return window.gFilterBlade;
    try {
      // eslint-disable-next-line no-undef
      return typeof gFilterBlade !== 'undefined' ? gFilterBlade : null;
    } catch (_) {
      return null;
    }
  }

  function storage() {
    const f = fb();
    if (!f || !f.changeStorage) return null;
    const cs = f.changeStorage;
    if (typeof cs.simplifySaveStateContent !== 'function') return null;
    if (typeof cs.loadSaveState !== 'function') return null;
    return cs;
  }

  function getState() {
    const f = fb();
    const cs = storage();
    if (!f || !cs) throw new Error('FilterBlade 尚未初始化完成，请等页面加载完再试');
    const inner = cs.simplifySaveStateContent();
    return {
      inner,
      gameType: typeof f.getGameType === 'function' ? f.getGameType() : 'Poe1',
      displayName: (cs.getCurrentlyLoadedSaveState() || {}).display_name || null,
      optionFileVersion: (f.loggedGlobals || {}).OptionFileVersion || null,
      note: 'inner 是站点自己生成的存档对象；修改后整体传给 fb_apply_state'
    };
  }

  function countChanges(inner) {
    return (inner.changeGroups || []).reduce(
      (n, g) => n + ((g && g.groupChanges || []).length), 0);
  }

  function applyState(state) {
    const f = fb();
    const cs = storage();
    if (!f || !cs) throw new Error('FilterBlade 尚未初始化完成');
    if (!state || typeof state !== 'object' || !Array.isArray(state.changeGroups)) {
      throw new Error('state 非法：必须是 fb_get_state 返回的 inner 对象');
    }
    for (const g of state.changeGroups) {
      if (!g || !Array.isArray(g.groupChanges)) {
        throw new Error('changeGroups 元素缺少 groupChanges，不要手工构造');
      }
      if ((g.changeGroupVersion || 4) < 4) {
        throw new Error('存档格式过旧（changeGroupVersion < 4），请先在站点另存一次');
      }
    }

    const outer = {
      display_name: 'MCP 配置',
      is_preset: false,
      date_modified: Date.now(),
      saveStateContent: JSON.stringify(state),
      meta_json_string: {
        lastGameType: typeof f.getGameType === 'function' ? f.getGameType() : 'Poe1',
        changeCount: countChanges(state)
      },
      tags: []
    };

    // 站点在 Advanced -> Upload filter 里走的就是同一条路径
    cs.updateAutoSave(outer);
    // 已加载过存档时 loadSaveState 会拒绝，先清掉 activeSaveState 标记
    if (cs.isCurrentlyLoadingSaveState) {
      throw new Error('站点正在加载另一份存档，请稍候几秒再试或刷新页面');
    }
    if (cs.getCurrentlyLoadedSaveState && cs.getCurrentlyLoadedSaveState()) {
      cs.clearStorage(false);
    }

    return new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          reject(new Error('站点加载存档超时，可刷新页面后在「Load Auto-Save?」提示中确认'));
        }
      }, 30000);
      try {
        const started = cs.loadSaveState(cs.getAutoSave(), () => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolve({
            ok: true,
            appliedChanges: countChanges(state),
            strictness: state.strictness,
            style: state.style,
            note: '配置已在当前页面生效'
          });
        }, true);
        if (started === false && !settled) {
          settled = true;
          clearTimeout(timer);
          reject(new Error('站点拒绝重复加载存档，请刷新页面后再试'));
        }
      } catch (err) {
        settled = true;
        clearTimeout(timer);
        reject(new Error(String((err && err.message) || err)));
      }
    });
  }

  window.addEventListener('message', async (event) => {
    if (event.source !== window || !event.data || event.data.type !== REQ) return;
    const { id, method, args } = event.data;
    let payload;
    try {
      let data;
      if (method === 'getState') data = getState();
      else if (method === 'applyState') data = await applyState(args && args.state);
      else if (method === 'ping') data = { ok: !!storage() };
      else throw new Error('未知方法：' + method);
      payload = { id, ok: true, data };
    } catch (err) {
      payload = { id, ok: false, error: String((err && err.message) || err) };
    }
    window.postMessage({ type: RES, ...payload }, '*');
  });

  window.__FB_MCP_READY__ = true;
})();
