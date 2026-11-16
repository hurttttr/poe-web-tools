/* =============================================================================
 * poeplanner 异界天赋树 · 中文搜索桥
 * -----------------------------------------------------------------------------
 * 站点左侧「Search nodes...」把输入串**直接当正则**，只匹配英文节点名与英文说明
 *   setSearchString(e) -> treeRenderState.searchText -> new RegExp(searchText, 'i')
 * 所以中文输入永远搜不到东西。这里在搜索框上叠一层自己的输入框：
 *   1. 用户输入中文 -> 用 data/atlas_search.json（中文名 / 中文说明）反查出命中的英文节点名；
 *   2. 把这些英文名拼成正则 (?:A|B|C) 写进站点真正的 input 并派发 input 事件；
 *   3. 用户看到的是自己打的中文，站点拿到的仍是英文正则，高亮逻辑完全不用改。
 * 英文输入原样透传，不改变站点原有行为。
 * ========================================================================== */
(function (global) {
  'use strict';

  var INDEX = global.FBZH_ATLAS_SEARCH;
  if (!INDEX) return;
  var doc = global.document;
  var location = global.location || {};
  var host = location.hostname || '';
  var path = location.pathname || '';
  // 离线预览页（file://）用 FBZH_ATLAS_SEARCH_FORCE 打开，真实站点只在异界天赋树页启用
  var forced = !!global.FBZH_ATLAS_SEARCH_FORCE;
  if (!forced && !/poeplanner\.com$/.test(host)) return;
  if (!forced && !/atlas/i.test(path)) return;

  var CJK = /[\u3400-\u9fff]/;
  var ESCAPE_RE = /[.*+?^${}()|[\]\\]/g;

  var field = null;        // 站点自己的 input（被隐藏，但仍由 Vue 接管）
  var wrap = null;         // 站点 input 的 .v-text-field 容器
  var savedVisibility = '';
  var overlay = null;
  var input = null;
  var hintEl = null;
  var bound = false;
  var active = true;
  var composing = false;
  var syncTimer = null;
  var bindTimer = null;

  /* ----------------------------------------------------------- 中文 -> 英文 */

  // 每个节点压成一条可搜索文本：中文名 + 各条中文说明，数字占位 # 当成 0
  var entries = (function () {
    var nodes = INDEX.nodes || INDEX;
    var out = [];
    Object.keys(nodes).forEach(function (name) {
      var e = nodes[name];
      if (!e || !name) return;
      var parts = typeof e === 'string' ? [e] : [].concat(e.n || [], e.t || []);
      var text = parts.join('\u0001').replace(/#/g, '0');
      if (text) out.push({ name: name, text: text });
    });
    return out;
  })();

  function toRegExp(q) {
    var esc = q.replace(/\s+/g, ' ').replace(ESCAPE_RE, '\\$&');
    // 检索词里的数字与 # 都当作「任意数字」，这样 "8%" 能匹配说明里的 # 占位
    esc = esc.replace(/\d[\d,]*(?:\.\d+)?/g, '\\d[\\d,]*').replace(/#/g, '\\d[\\d,]*');
    try { return new RegExp(esc, 'i'); } catch (e) { return null; }
  }

  function matchNames(q) {
    var re = toRegExp(q);
    if (!re) return [];
    var out = [];
    for (var i = 0; i < entries.length; i++) {
      if (re.test(entries[i].text)) out.push(entries[i].name);
    }
    return out;
  }

  function toSitePattern(names) {
    if (!names.length) return '(?!)';     // 永久不匹配：清空高亮
    var list = names.slice(0, 200).map(function (n) { return n.replace(ESCAPE_RE, '\\$&'); });
    return '(?:' + list.join('|') + ')';
  }

  /* ------------------------------------------------------------------ DOM */

  // 异界天赋树页的工具栏是 .atlas-tree-toolbar，角色天赋树页是 .passive-tree-toolbar，
  // 两者复用同一个搜索框组件，所以两个类名都要认。
  var FIELD_SELECTOR = '.atlas-tree-toolbar input, .passive-tree-toolbar input';

  function findField() {
    var list;
    try { list = doc.querySelectorAll(FIELD_SELECTOR); } catch (e) { return null; }
    var fallback = null;
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      var type = el.getAttribute('type');
      if (type && type !== 'text' && type !== 'search') continue;
      var box = el.closest('.v-text-field') || el.parentElement;
      if (!box) continue;
      if (!fallback) fallback = { field: el, box: box };
      var label = box.querySelector('label, .v-label');
      var text = ((label && label.textContent) || '') + ' ' + (el.getAttribute('placeholder') || '');
      if (/search|搜索/i.test(text)) return { field: el, box: box };
    }
    return fallback;
  }

  var CSS = [
    '.fbzh-atlas-search{position:fixed;z-index:1200;display:flex;align-items:center;',
    'box-sizing:border-box;padding:0 8px;border-radius:4px;font-family:inherit;',
    'box-shadow:inset 0 -1px 0 rgba(255,255,255,.14)}',
    '.fbzh-atlas-search input{flex:1;min-width:0;border:0;outline:0;background:transparent;',
    'padding:0;margin:0;color:inherit;font:inherit}',
    '.fbzh-atlas-search .fbzh-as-hint{position:absolute;left:0;top:100%;margin-top:3px;',
    'padding:1px 6px;border-radius:3px;background:rgba(0,0,0,.72);color:#dfe6f2;',
    'font-size:11px;line-height:1.6;white-space:nowrap;pointer-events:none}',
    '.fbzh-atlas-search .fbzh-as-hint[hidden]{display:none}',
    '.fbzh-atlas-search .fbzh-as-clear{flex:none;border:0;background:transparent;color:inherit;',
    'opacity:.55;cursor:pointer;font-size:14px;line-height:1;padding:2px 4px}',
    '.fbzh-atlas-search .fbzh-as-clear:hover{opacity:1}'
  ].join('');

  function injectCSS() {
    if (doc.getElementById('fbzh-atlas-search-style')) return;
    var st = doc.createElement('style');
    st.id = 'fbzh-atlas-search-style';
    st.setAttribute('data-fbzh-skip', '1');
    st.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(st);
  }

  function buildOverlay() {
    var box = doc.createElement('div');
    box.className = 'fbzh-ui fbzh-atlas-search';
    box.setAttribute('data-fbzh-skip', '1');
    input = doc.createElement('input');
    input.type = 'text';
    input.spellcheck = false;
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('aria-label', '搜索天赋节点');
    hintEl = doc.createElement('span');
    hintEl.className = 'fbzh-as-hint';
    hintEl.hidden = true;
    var clear = doc.createElement('button');
    clear.type = 'button';
    clear.className = 'fbzh-as-clear';
    clear.title = '清除';
    clear.textContent = '\u00d7';
    box.appendChild(input);
    box.appendChild(hintEl);
    box.appendChild(clear);

    input.addEventListener('input', function () { if (!composing) apply(input.value); });
    input.addEventListener('compositionstart', function () { composing = true; });
    input.addEventListener('compositionend', function () { composing = false; apply(input.value); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); reset(); return; }
      // Alt 组合键交给引擎（Alt+Z 切原文模式），不要当输入处理
    });
    clear.addEventListener('click', function () { reset(); input.focus(); });
    return box;
  }

  function pushSite(value) {
    if (!field) return;
    var proto = global.HTMLInputElement && global.HTMLInputElement.prototype;
    var desc = proto && Object.getOwnPropertyDescriptor(proto, 'value');
    try {
      if (desc && desc.set) desc.set.call(field, value); else field.value = value;
    } catch (e) { field.value = value; }
    try {
      field.dispatchEvent(new global.Event('input', { bubbles: true }));
    } catch (e) { /* 老环境没有 Event 构造函数时忽略 */ }
  }

  function setHint(text) {
    if (!hintEl) return;
    if (!text) { hintEl.hidden = true; hintEl.textContent = ''; return; }
    hintEl.hidden = false;
    hintEl.textContent = text;
  }

  function apply(value) {
    var q = (value || '').trim();
    if (!q) { pushSite(''); setHint(''); return; }
    if (!CJK.test(q)) {            // 英文检索：原样透传，站点行为不变
      pushSite(q);
      setHint('');
      return;
    }
    var names = matchNames(q);
    pushSite(toSitePattern(names));
    setHint(names.length ? '匹配 ' + names.length + ' 个节点' : '没有匹配的天赋节点');
  }

  function reset() {
    if (input) input.value = '';
    pushSite('');
    setHint('');
  }

  function syncBox() {
    if (!active || !bound) return;
    if (!field || field.isConnected === false) { rebind(); return; }
    var label = wrap && wrap.querySelector('label, .v-label');
    var ph = ((label && label.textContent) || '').trim() || '搜索天赋节点…';
    if (input.getAttribute('placeholder') !== ph) input.setAttribute('placeholder', ph);
    var r;
    try { r = field.getBoundingClientRect(); } catch (e) { return; }
    if (!r || !r.width || !r.height) { overlay.style.display = 'none'; return; }
    overlay.style.display = 'flex';
    overlay.style.left = r.left + 'px';
    overlay.style.top = r.top + 'px';
    overlay.style.width = r.width + 'px';
    overlay.style.height = r.height + 'px';
    var cs = global.getComputedStyle(field);
    if (cs) {
      input.style.fontSize = cs.fontSize;
      input.style.fontFamily = cs.fontFamily;
      input.style.color = cs.color;
    }
    var ws = global.getComputedStyle(wrap);
    if (ws && ws.backgroundColor && ws.backgroundColor !== 'rgba(0, 0, 0, 0)') {
      overlay.style.background = ws.backgroundColor;
    }
  }

  function bind() {
    var found = findField();
    if (!found) return false;
    field = found.field;
    wrap = found.box;
    if (!overlay) overlay = buildOverlay();
    savedVisibility = wrap.style.visibility || '';
    wrap.style.visibility = 'hidden';      // 原输入框保留尺寸，只把可见性让给叠层
    wrap.setAttribute('data-fbzh-hidden', '1');
    (doc.body || doc.documentElement).appendChild(overlay);
    bound = true;
    overlay.style.display = 'none';
    syncBox();
    return true;
  }

  function unbind(clear) {
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (wrap && wrap.getAttribute('data-fbzh-hidden')) {
      wrap.style.visibility = savedVisibility;
      wrap.removeAttribute('data-fbzh-hidden');
    }
    if (clear !== false) pushSite('');
    bound = false;
    field = null;
    wrap = null;
  }

  function rebind() {
    if (!active) return;
    unbind(false);
    if (!bind()) scheduleRebind();
  }

  function scheduleRebind() {
    if (bindTimer) return;
    bindTimer = setInterval(function () {
      if (!active) { clearInterval(bindTimer); bindTimer = null; return; }
      if (bind()) { clearInterval(bindTimer); bindTimer = null; }
    }, 600);
  }

  function start() {
    if (!entries.length) return;
    injectCSS();
    if (!bind()) scheduleRebind();
    syncTimer = setInterval(syncBox, 500);
    global.addEventListener('resize', syncBox, true);
    global.addEventListener('scroll', syncBox, true);
    if (global.FBZH && global.FBZH.on) {
      global.FBZH.on(function (st) {
        if (!st.enabled) { active = false; unbind(true); if (syncTimer) clearInterval(syncTimer); }
        else if (!active) {
          active = true;
          rebind();
          if (!syncTimer) syncTimer = setInterval(syncBox, 500);
        }
      });
    }
    var status = global.FBZH && global.FBZH.getStatus && global.FBZH.getStatus();
    if (status && !status.enabled) { active = false; unbind(true); }
  }

  // 供预览页与测试使用
  global.FBZHAtlasSearch = {
    matchNames: matchNames,
    pattern: toSitePattern,
    apply: apply,
    reset: reset,
    entries: entries.length
  };

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start);
  else start();
})(typeof window !== 'undefined' ? window : this);
