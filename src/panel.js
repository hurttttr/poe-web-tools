/* =============================================================================
 * PoE Web Tools - 悬浮控制面板
 * 依赖 engine.js 暴露的 window.FBZH，样式由 window.FBZH_CSS 注入。
 * ========================================================================== */
(function (global) {
  'use strict';

  var FBZH = global.FBZH;
  if (!FBZH) return;

  function injectStyle() {
    // 扩展版由 manifest 的 content_scripts.css 注入样式，这里无需重复
    if (!global.FBZH_CSS || document.getElementById('fbzh-style')) return;
    var style = document.createElement('style');
    style.id = 'fbzh-style';
    style.textContent = global.FBZH_CSS || '';
    (document.head || document.documentElement).appendChild(style);
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function copy(text) {
    if (global.navigator && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); });
    } else fallbackCopy(text);
    toast('已复制：' + text);
  }

  function fallbackCopy(text) {
    var ta = el('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    ta.remove();
  }

  var toastTimer;
  function toast(msg) {
    var box = document.getElementById('fbzh-toast');
    if (!box) return;
    box.textContent = msg;
    box.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.classList.remove('show'); }, 1600);
  }

  function build() {
    if (document.getElementById('fbzh-root')) return;
    var root = el('div', 'fbzh-ui');
    root.id = 'fbzh-root';

    var fab = el('button', 'fbzh-fab', '汉');
    fab.id = 'fbzh-fab';
    fab.title = 'PoE Web Tools 设置';
    fab.type = 'button';

    var panel = el('div', 'fbzh-panel');
    panel.id = 'fbzh-panel';
    panel.hidden = true;

    var head = el('div', 'fbzh-head');
    var host = location.hostname || '';
    var siteName = host.indexOf('poe.ninja') >= 0 ? 'poe.ninja'
      : (host.indexOf('filterblade') >= 0 ? 'FilterBlade' : 'POE');
    head.appendChild(el('strong', null, 'PoE Web Tools · ' + siteName));
    var headStat = el('span', 'fbzh-head-stat', '');
    headStat.id = 'fbzh-head-stat';
    head.appendChild(headStat);
    var close = el('button', 'fbzh-close', '×');
    close.type = 'button';
    close.onclick = function () { panel.hidden = true; };
    head.appendChild(close);
    panel.appendChild(head);

    /* 开关 */
    var row1 = el('div', 'fbzh-row');
    row1.appendChild(el('label', 'fbzh-label', '启用汉化'));
    var sw = el('input'); sw.type = 'checkbox'; sw.id = 'fbzh-enabled';
    sw.onchange = function () { FBZH.setSettings({ enabled: sw.checked }); };
    row1.appendChild(sw);
    panel.appendChild(row1);

    /* 模式 */
    panel.appendChild(el('div', 'fbzh-section', '显示模式'));
    var modes = el('div', 'fbzh-segment');
    [['zh', '中文'], ['both', '双语'], ['en', '原文']].forEach(function (pair) {
      var b = el('button', 'fbzh-seg', pair[1]);
      b.type = 'button'; b.dataset.mode = pair[0];
      b.onclick = function () { FBZH.setSettings({ mode: pair[0] }); };
      modes.appendChild(b);
    });
    panel.appendChild(modes);

    panel.appendChild(el('div', 'fbzh-hint', '原文模式用于站内搜索 / 新增规则；快捷键 Alt+Z 快速切换。'));

    /* 选项 */
    var opts = el('div', 'fbzh-options');
    [['attributes', '翻译提示文字（placeholder / title）'],
     ['phrase', '长文本内局部短语替换']].forEach(function (pair) {
      var label = el('label', 'fbzh-check');
      var input = el('input'); input.type = 'checkbox'; input.dataset.opt = pair[0];
      input.onchange = function () {
        var patch = {}; patch[pair[0]] = input.checked; FBZH.setSettings(patch);
      };
      label.appendChild(input);
      label.appendChild(el('span', null, pair[1]));
      opts.appendChild(label);
    });
    panel.appendChild(opts);

    /* 统计 */
    var stat = el('div', 'fbzh-stat', '');
    stat.id = 'fbzh-stat';
    panel.appendChild(stat);

    /* 中英对照查询 */
    panel.appendChild(el('div', 'fbzh-section', '中英对照查询（点击复制英文）'));
    var q = el('input', 'fbzh-input');
    q.id = 'fbzh-q'; q.type = 'text'; q.placeholder = '输入中文或英文，如：混沌石 / Chaos Orb';
    var results = el('div', 'fbzh-results');
    results.id = 'fbzh-results';
    function renderResults() {
      results.innerHTML = '';
      var rows = FBZH.lookupTerm(q.value, 20);
      if (!q.value.trim()) return;
      if (!rows.length) { results.appendChild(el('div', 'fbzh-empty', '词典中没有匹配项')); return; }
      rows.forEach(function (r) {
        var item = el('div', 'fbzh-result');
        item.appendChild(el('span', 'fbzh-en', r.en));
        item.appendChild(el('span', 'fbzh-arrow', '→'));
        item.appendChild(el('span', 'fbzh-zh', r.zh));
        item.title = '点击复制英文名';
        item.onclick = function () { copy(r.en); };
        results.appendChild(item);
      });
    }
    var qTimer;
    q.oninput = function () {
      clearTimeout(qTimer);
      qTimer = setTimeout(renderResults, 160);
    };
    panel.appendChild(q);
    panel.appendChild(results);

    /* 动作 */
    var actions = el('div', 'fbzh-actions');
    var b1 = el('button', 'fbzh-btn', '重新翻译');
    b1.type = 'button'; b1.onclick = function () { FBZH.retranslate(); toast('已重新翻译当前页面'); };
    var b2 = el('button', 'fbzh-btn', '导出未译文本');
    b2.type = 'button'; b2.onclick = function () {
      var list = FBZH.collectUntranslated();
      FBZH.download('filterblade-untranslated.json', JSON.stringify(list, null, 2));
      toast('已导出 ' + list.length + ' 条待补词条');
    };
    actions.appendChild(b1); actions.appendChild(b2);
    panel.appendChild(actions);

    panel.appendChild(el('div', 'fbzh-foot', '术语以流放之路编年史简体中文为准 · 点击交互元素时自动还原英文'));

    root.appendChild(fab);
    root.appendChild(panel);
    root.appendChild((function () { var t = el('div', 'fbzh-toast'); t.id = 'fbzh-toast'; return t; })());
    document.body.appendChild(root);

    fab.onclick = function () {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) renderResults();
    };

    FBZH.on(function (s) {
      sw.checked = s.enabled;
      Array.prototype.forEach.call(modes.children, function (b) {
        b.classList.toggle('active', b.dataset.mode === s.mode);
      });
      Array.prototype.forEach.call(opts.querySelectorAll('input[data-opt]'), function (i) {
        i.checked = !!s[i.dataset.opt];
      });
      headStat.textContent = s.entries.toLocaleString() + ' 条词条'
        + (s.templates ? ' · ' + s.templates.toLocaleString() + ' 条词缀模板' : '');
      stat.textContent = '已翻译文本 ' + s.stats.nodes + ' 处 · 提示 ' + s.stats.attributes + ' 处';
      root.classList.toggle('off', !s.enabled || s.mode === 'en');
    });
  }

  /* 扩展 popup 通过消息控制 */
  function installBridge() {
    if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.onMessage) return;
    chrome.runtime.onMessage.addListener(function (msg, sender, reply) {
      if (!msg || msg.channel !== 'fbzh') return;
      if (msg.type === 'set' && msg.patch) FBZH.setSettings(msg.patch);
      if (msg.type === 'status') reply && reply(FBZH.getStatus());
      if (msg.type === 'retranslate') FBZH.retranslate();
      if (msg.type === 'export') {
        var list = FBZH.collectUntranslated();
        FBZH.download('filterblade-untranslated.json', JSON.stringify(list, null, 2));
      }
      if (reply) reply(FBZH.getStatus());
      return true;
    });
  }

  function start() {
    injectStyle();
    FBZH.init();
    build();
    installBridge();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})(typeof window !== 'undefined' ? window : this);
