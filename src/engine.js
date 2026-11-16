/* =============================================================================
 * PoE Web Tools - 汉化引擎 (FBZH)
 * -----------------------------------------------------------------------------
 * 设计要点：
 *  1. 只改写「文本节点」与少量展示型属性，不改 DOM 结构、不改 value/代码。
 *  2. 每个节点的英文原文保存在 WeakMap 中，可随时一键还原，不污染 DOM。
 *  3. 站点部分交互会读取 innerText（例如点击基底矩阵调整 T 级），
 *     因此在事件捕获阶段把相关容器临时还原成英文，事件处理完再恢复中文。
 *  4. MutationObserver 覆盖异步渲染的界面；对 characterData 变化做防循环处理。
 *  5. 支持三种模式：中文 / 双语 / 原文；设置持久化在 localStorage。
 * ========================================================================== */
(function (global) {
  'use strict';

  var DICT = global.FBZH_DICT || {};
  var SETTINGS_KEY = 'fbzh.settings.v1';
  var SKIP_TAGS = /^(SCRIPT|STYLE|NOSCRIPT|TEXTAREA|CODE|PRE|SVG|CANVAS|IFRAME|INPUT|SELECT|OPTION|META|LINK)$/;
  // Vuetify / Material Icons 用 ligature 文本渲染图标（<i class="v-icon">expand_more</i>），
  // 改掉这些文本会让图标直接消失，因此整棵 .v-icon 子树都不参与翻译。
  var SKIP_SELECTOR = 'script,style,noscript,textarea,code,pre,svg,canvas,iframe,input,select,option,[contenteditable],[data-fbzh-skip],.CodeMirror,.ace_editor,.fbzh-ui,.v-icon,.material-icons,[class*="v-icon"]';
  var ATTRS = ['placeholder', 'title', 'aria-label'];
  var WHITESPACE = /\s+/g;
  // 一条说明被站点用行内标签（多半是给数值上色的 <span>）切开时，逐文本节点匹配必然落空
  // （"Your Maps have " + <span>8%</span> + " chance to ..."）。这些常量用于「整行级」补翻。
  var LINE_TAGS = /^(SPAN|B|STRONG|I|EM|SMALL|U|BR|SUB|SUP|FONT|MARK|WBR)$/;
  var LINE_HOSTS = 'div,span,p,li,td,th,label,small,b,strong,em,i,dd,dt,h1,h2,h3,h4,h5,h6';
  // 整行改写会替换容器内容，凡是可能承载交互 / 图形 / 我们自己的 UI 的容器一律不动
  var LINE_BLOCKERS = 'a,button,input,select,textarea,svg,canvas,img,iframe,video,' +
    '[contenteditable],[data-fbzh-skip],.fbzh-ui,.v-icon,.material-icons,[class*="v-icon"]';

  var state = {
    enabled: true,
    mode: 'zh',            // 'zh' | 'both' | 'en'
    attributes: true,      // 是否翻译 placeholder / title / aria-label
    phrase: true           // 是否允许长文本内的局部短语替换
  };

  var listeners = [];
  var exact = new Map();         // 原文(去空白) -> 译文
  var folded = new Map();        // 原文小写 -> 译文
  var phraseMap = new Map();     // 短语小写 -> 译文
  var phraseRegexes = [];
  var shortMap = new Map();      // 受控短词（Gold / Uniques 等）-> 译文
  var shortRegex = null;
  var tplMap = new Map();        // 数值骨架(数字->#) -> [{en, zh}]（物品词缀模板）
  var prefixRules = [];          // [{en, zh}] 前缀规则（"Allocates X" 这类「前缀 + 名字」）

  var originalText = new WeakMap();   // Text -> 英文原文
  var originalAttr = new WeakMap();   // Element -> {attr: 英文原文}
  var lineOriginal = new WeakMap();   // Element -> 整行改写前的 innerHTML
  var lineApplied = new WeakMap();    // Element -> 我们写入的 innerHTML（判断站点是否重渲染）
  var rewrittenLines = new Set();
  var translatedNodes = new Set();    // 便于整体还原
  var translatedElements = new Set();

  var suppress = false;
  var suppressTimer = null;
  var deferred = [];
  var deferredDiscard = false;
  var pending = new Set();
  var scheduled = false;
  var stats = { nodes: 0, attributes: 0, lines: 0 };

  /* ---------------------------------------------------------------- utils */

  function normalize(s) {
    return String(s).replace(WHITESPACE, ' ').trim();
  }

  function hasCJK(s) {
    return /[\u3400-\u9fff]/.test(s);
  }

  function looksTranslatable(s) {
    return /[A-Za-z]{2}/.test(s) && !hasCJK(s);
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function escapeHTML(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function loadSettings() {
    try {
      var saved = JSON.parse(global.localStorage.getItem(SETTINGS_KEY) || '{}');
      Object.keys(state).forEach(function (k) {
        if (typeof saved[k] === typeof state[k]) state[k] = saved[k];
      });
    } catch (e) { /* 隐私模式下 localStorage 可能不可用 */ }
  }

  function saveSettings() {
    try { global.localStorage.setItem(SETTINGS_KEY, JSON.stringify(state)); } catch (e) {}
    emit();
  }

  function on(fn) { listeners.push(fn); }
  function emit() {
    var snapshot = getStatus();
    listeners.forEach(function (fn) { try { fn(snapshot); } catch (e) {} });
  }

  /* ------------------------------------------------------------ dictionary */

  function hostTerms() {
    var map = global.FBZH_HOST_DICT || {};
    var host = (global.location && global.location.hostname) || '';
    var out = {};
    if (!host) return out;
    Object.keys(map).forEach(function (scope) {
      if (host.indexOf(scope) < 0) return;
      var terms = map[scope] || {};
      Object.keys(terms).forEach(function (en) { out[en] = terms[en]; });
    });
    return out;
  }

  function buildIndex() {
    exact.clear(); folded.clear(); phraseMap.clear(); phraseRegexes = [];
    var phrases = [];
    Object.keys(DICT).forEach(function (en) {
      var zh = DICT[en];
      if (!en || !zh || en === zh) return;
      var key = normalize(en);
      if (!key) return;
      exact.set(key, zh);
      folded.set(key.toLowerCase(), zh);
      // 只有含空格、长度合适的词条才参与长文本局部替换，
      // 避免 "Map" / "Tier" 这类短词误伤代码或拼接文本。
      if (state.phrase && /\s/.test(key) && key.length >= 6 && key.length <= 120) {
        phraseMap.set(key.toLowerCase(), zh);
        phrases.push(key);
      }
    });
    phrases.sort(function (a, b) { return b.length - a.length; });
    for (var i = 0; i < phrases.length; i += 350) {
      var chunk = phrases.slice(i, i + 350).map(escapeRegExp).join('|');
      try {
        phraseRegexes.push(new RegExp('(?<![A-Za-z0-9])(?:' + chunk + ')(?![A-Za-z0-9])', 'gi'));
      } catch (e) {
        // 极老浏览器不支持后行断言时退化为无后行断言版本
        phraseRegexes.push(new RegExp('(?:' + chunk + ')(?![A-Za-z0-9])', 'gi'));
      }
    }
    // 站点专属词条：只对匹配域名生效。
    // 有些词在 A 站是界面文案（poe.ninja 的 "Class" 列头），在 B 站却是语法关键字（FilterBlade 的 Class 过滤器），
    // 这类词不进主词典，改由 data/host_terms.json 按 host 范围注入。
    var hostExtra = hostTerms();
    Object.keys(hostExtra).forEach(function (en) {
      var zh = hostExtra[en];
      if (!en || !zh || en === zh) return;
      var key = normalize(en);
      if (!key) return;
      exact.set(key, zh);
      folded.set(key.toLowerCase(), zh);
    });

    // 受控短词：用于 "1000x Gold" 这类中英/数字混排文本，
    // 白名单由 data/short_words.json 维护，不把 Tier / Class 等语法词放进来。
    shortMap.clear();
    shortRegex = null;
    var sw = global.FBZH_SHORT_WORDS || {};
    var swKeys = Object.keys(sw).filter(function (k) { return /^[A-Za-z]{3,}$/.test(k); });
    swKeys.forEach(function (k) { shortMap.set(k.toLowerCase(), sw[k]); });
    swKeys.sort(function (a, b) { return b.length - a.length; });
    if (swKeys.length) {
      try {
        shortRegex = new RegExp('(?<![A-Za-z0-9])(?:' + swKeys.map(escapeRegExp).join('|') + ')(?![A-Za-z0-9])', 'gi');
      } catch (e) {
        shortRegex = new RegExp('(?:' + swKeys.map(escapeRegExp).join('|') + ')(?![A-Za-z0-9])', 'gi');
      }
    }

    // 词缀模板：用「数字统一替换成 #」的骨架做索引，一次查表即可命中，
    // 无需为每条模板编译正则。骨架统一转小写，兼容站点把句中单词首字母大写
    // 的写法（例如 "Regenerate 0.15% of Life per Second"）。
    tplMap.clear();
    var tpl = global.FBZH_MOD_TPL || {};
    Object.keys(tpl).forEach(function (en) {
      var zh = tpl[en];
      if (!en || !zh || en === zh || en.indexOf('#') < 0) return;
      var key = skeleton(normalize(en)).toLowerCase();
      var list = tplMap.get(key);
      if (!list) { list = []; tplMap.set(key, list); }
      list.push({ en: en, zh: zh });
    });

    prefixRules = [];
    var prefixTable = global.FBZH_MOD_PREFIX || {};
    Object.keys(prefixTable).forEach(function (en) {
      if (!en || !prefixTable[en]) return;
      prefixRules.push({ en: en, zh: prefixTable[en] });
    });
    prefixRules.sort(function (a, b) { return b.en.length - a.en.length; });
  }

  function lookup(raw) {
    if (state.mode === 'en' || !state.enabled) return null;
    var key = normalize(raw);
    if (!key || !looksTranslatable(key)) return null;
    var zh = exact.get(key) || folded.get(key.toLowerCase());
    if (!zh) return null;
    if (state.mode === 'both' && key.length <= 60) return zh + ' (' + key + ')';
    return zh;
  }

  function replacePhrases(text) {
    if (!state.phrase || phraseRegexes.length === 0) return text;
    // 允许中英混排：中文部分保留，只替换其中的英文短语
    if (!/[A-Za-z]{3}/.test(text)) return text;
    if (text.length > 1200) return text;   // 超长文本不处理，避免卡顿
    var out = text;
    for (var i = 0; i < phraseRegexes.length; i++) {
      var re = phraseRegexes[i];
      re.lastIndex = 0;
      out = out.replace(re, function (m) {
        var zh = phraseMap.get(normalize(m).toLowerCase());
        if (!zh) return m;
        return state.mode === 'both' && m.length <= 40 ? zh + ' (' + m + ')' : zh;
      });
    }
    if (shortRegex) {
      shortRegex.lastIndex = 0;
      out = out.replace(shortRegex, function (m) {
        return shortMap.get(m.toLowerCase()) || m;
      });
    }
    return out;
  }

  /* --------------------------------------------------- 词缀模板（数值占位） */

  // 物品词缀带随机数值（"Adds 5 Passive Skills" / "+3% to Fire Resistance"），
  // 逐条穷举不现实，因此数据侧用 # 占位，运行时把实际数字按顺序填回中文。
  function skeleton(s) {
    return s.replace(/\d[\d,]*(?:\.\d+)?/g, '#');
  }

  function fillTemplate(zhTpl, raw) {
    var nums = raw.match(/\d[\d,]*(?:\.\d+)?/g) || [];
    var i = 0;
    var overflow = false;
    var out = zhTpl.replace(/#/g, function () {
      if (i >= nums.length) { overflow = true; return '#'; }
      return nums[i++];
    });
    // 占位符与数字个数必须一一对应，否则宁可保持英文也不要输出错位译文
    if (overflow || i !== nums.length) return null;
    return out;
  }

  function lookupTemplate(raw) {
    if (!state.enabled || state.mode === 'en' || tplMap.size === 0) return null;
    var key = normalize(raw);
    if (!key || !/\d/.test(key) || !looksTranslatable(key)) return null;
    var candidates = tplMap.get(skeleton(key).toLowerCase());
    if (!candidates) return null;
    for (var i = 0; i < candidates.length; i++) {
      var zh = fillTemplate(candidates[i].zh, key);
      if (!zh || zh === key) continue;
      return state.mode === 'both' && key.length <= 60 ? zh + ' (' + key + ')' : zh;
    }
    return null;
  }

  /* ------------------------------------------------------------ 前缀规则 */

  // "Allocates Avatar of Fire" 这类写法：前半固定、后半是名字，
  // 用前缀表换掉开头，再把剩余部分交给词典 / 短语替换。
  function lookupPrefix(raw) {
    if (!state.enabled || state.mode === 'en' || !prefixRules.length) return null;
    var lower = raw.toLowerCase();
    for (var i = 0; i < prefixRules.length; i++) {
      var rule = prefixRules[i];
      if (lower.indexOf(rule.en.toLowerCase()) !== 0) continue;
      var rest = raw.slice(rule.en.length).trim();
      if (!rest) continue;
      var zh = exact.get(normalize(rest)) || replacePhrases(rest);
      if (!zh || zh === rest) continue;
      return rule.zh + zh;
    }
    return null;
  }

  // 统一入口：整串 -> 「按行拆开再逐行翻译」（poeplanner 的统计栏会把多条说明用 \n 拼在一起）
  function translateAny(raw) {
    var key = normalize(raw);
    if (!key) return null;
    var zh = lookup(key) || lookupTemplate(key) || lookupPrefix(key);
    if (zh) return zh;
    if (!/[\n\r]/.test(raw)) return null;
    var lines = raw.split(/[\n\r]+/).map(function (s) { return s.trim(); }).filter(Boolean);
    if (lines.length < 2) return null;
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var one = lookup(lines[i]) || lookupTemplate(lines[i]) || lookupPrefix(lines[i]);
      if (!one) return null;   // 有一行没覆盖就整段保持英文，避免半中半英
      out.push(one);
    }
    return out.join('\n');
  }

  /* --------------------------------------------------------------- walking */

  function isSkipped(el) {
    if (!el || el.nodeType !== 1) return false;
    if (SKIP_TAGS.test(el.tagName)) return true;
    try { return !!el.closest(SKIP_SELECTOR); } catch (e) { return false; }
  }

  // 属性翻译只排除代码/图形容器；输入框、下拉框的 placeholder/title 仍需翻译
  var ATTR_SKIP_TAGS = /^(SCRIPT|STYLE|NOSCRIPT|SVG|CANVAS|IFRAME|META|LINK)$/;
  function isAttrSkipped(el) {
    if (!el || el.nodeType !== 1) return true;
    if (ATTR_SKIP_TAGS.test(el.tagName)) return true;
    try { return !!el.closest('[data-fbzh-skip],.fbzh-ui'); } catch (e) { return false; }
  }

  function walkText(root, cb) {
    if (!root) return;
    if (root.nodeType === 3) { cb(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 11 && root.nodeType !== 9) return;
    if (root.nodeType === 1 && isSkipped(root)) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentElement;
        if (!p || isSkipped(p)) return NodeFilter.FILTER_REJECT;
        if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        if (originalText.has(node)) return NodeFilter.FILTER_REJECT;  // 已翻译
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(cb);
  }

  function walkElements(root, cb) {
    if (!root) return;
    if (root.nodeType === 1 && !isAttrSkipped(root)) cb(root);
    var scope = root.nodeType === 1 || root.nodeType === 9 || root.nodeType === 11 ? root : null;
    if (!scope || !scope.querySelectorAll) return;
    var all;
    try { all = scope.querySelectorAll('[placeholder],[title],[aria-label]'); } catch (e) { return; }
    for (var i = 0; i < all.length; i++) {
      if (!isAttrSkipped(all[i])) cb(all[i]);
    }
  }

  /* ------------------------------------------- 整行翻译（跨行内标签 / 跨行文本） */

  function walkLines(root, cb) {
    if (!root) return;
    // root 自身可能就是那个被整段替换的容器（MutationObserver 的 rec.target）
    if (root.nodeType === 1) cb(root);
    if (!root.querySelectorAll) return;
    var list;
    try { list = root.querySelectorAll(LINE_HOSTS); } catch (e) { return; }
    for (var i = 0; i < list.length; i++) cb(list[i]);
  }

  function translateInlineLine(el) {
    if (!el || el.nodeType !== 1) return;
    if (el.childElementCount === 0) return;          // 纯文本交给 translateTextNode
    if (el.childElementCount > 12) return;           // 子元素太多说明是布局容器，不是一行说明
    if (isSkipped(el)) return;
    // 已改写过：内容没变就跳过；站点重渲染过（innerHTML 变了）就当作全新内容再翻一次
    var applied = lineApplied.get(el);
    if (applied !== undefined) {
      if (el.innerHTML === applied) return;
      lineOriginal.delete(el);
      lineApplied.delete(el);
    }
    var raw = (el.textContent || '').trim();
    if (raw.length < 5 || raw.length > 240) return;
    if (hasCJK(raw) || !/[A-Za-z]{3}/.test(raw)) return;
    try { if (el.querySelector(LINE_BLOCKERS)) return; } catch (e) { return; }
    // 只处理「一行」：允许行内标签，出现块级子元素说明是布局容器，不该整体替换
    var kids = el.getElementsByTagName('*');
    for (var i = 0; i < kids.length; i++) {
      if (!LINE_TAGS.test(kids[i].tagName)) return;
    }
    var zh = translateAny(raw);
    if (!zh || zh === raw) return;
    lineOriginal.set(el, el.innerHTML);
    // 站点给数值单独上色（<span class="textAugmented">8%</span>）。
    // 整行改写成纯文本会丢掉这个高亮，这里把译文中同位置的数值按同样 class 包回去。
    var html = escapeHTML(zh);
    var cls = null;
    var spans = el.getElementsByTagName('span');
    for (var s = 0; s < spans.length; s++) {
      var t = (spans[s].textContent || '').trim();
      if (spans[s].className && /^[+\-]?\d[\d,]*(?:\.\d+)?%?$/.test(t)) {
        cls = spans[s].className;
        break;
      }
    }
    if (cls) {
      html = html.replace(/\d[\d,]*(?:\.\d+)?%?/g, function (m) {
        return '<span class="' + cls + '">' + m + '</span>';
      });
    }
    el.innerHTML = html;                             // 统一重写，避免出现半中半英
    lineApplied.set(el, el.innerHTML);
    el.setAttribute('data-fbzh', '1');
    rewrittenLines.add(el);
    stats.lines++;
  }

  function restoreLine(el) {
    var html = lineOriginal.get(el);
    if (html === undefined) return;
    runSuppressed(function () {
      try { el.innerHTML = html; } catch (e) {}
    });
    lineOriginal.delete(el);
    lineApplied.delete(el);
    rewrittenLines.delete(el);
    try { el.removeAttribute('data-fbzh'); } catch (e) {}
  }

  /* ------------------------------------------------------------ translating */

  function translateTextNode(node) {
    var raw = node.nodeValue;
    if (!raw || !raw.trim()) return;
    if (originalText.has(node)) return;
    // 中英混排文本（如 "1000x Gold"、"亡者硫磺，Ducats ..."）仍要处理其中的英文部分
    if (!/[A-Za-z]{2}/.test(raw)) return;
    var parent = node.parentElement;
    if (!parent || isSkipped(parent)) return;

    var trimmed = raw.trim();
    // 顺序很重要：整串词条 -> 词缀模板（会吃掉数值）-> 长文本局部短语替换。
    // 若先做短语替换，模板里剩下的英文数字句就再也匹配不上了。
    var zh = hasCJK(trimmed) ? null : translateAny(raw);
    if (!zh && state.phrase) {
      var mixed = replacePhrases(trimmed);
      if (mixed !== trimmed) zh = mixed;
    }
    if (!zh || zh === trimmed) return;

    originalText.set(node, raw);
    node.nodeValue = raw.replace(trimmed, zh);
    translatedNodes.add(node);
    if (parent) parent.setAttribute('data-fbzh', '1');
    stats.nodes++;
  }

  function translateAttributes(el) {
    if (!state.attributes || !el || el.nodeType !== 1) return;
    var saved = originalAttr.get(el) || {};
    ATTRS.forEach(function (attr) {
      var raw = el.getAttribute(attr);
      if (!raw || !looksTranslatable(raw)) return;
      if (saved[attr] !== undefined) return;
      var zh = lookup(raw) || replacePhrases(raw);
      if (!zh || zh === raw) return;
      saved[attr] = raw;
      el.setAttribute(attr, zh);
      el.setAttribute('data-fbzh', '1');
      stats.attributes++;
    });
    if (Object.keys(saved).length) {
      originalAttr.set(el, saved);
      translatedElements.add(el);
    }
  }

  function translate(root) {
    if (!state.enabled || state.mode === 'en') return;
    runSuppressed(function () {
      // 整行优先：站点把数值包进 <span> 时，单个文本节点永远匹配不上整句
      walkLines(root, translateInlineLine);
      walkText(root, translateTextNode);
      if (state.attributes) walkElements(root, translateAttributes);
    });
  }

  function runSuppressed(fn, discard) {
    // 抑制期间产生的 MutationRecord 不丢弃，延迟到宏任务再统一处理，
    // 否则「同一同步栈内新增的节点」会被永久漏翻。
    // discard=true 用于「点击时临时还原英文」：这些记录必须丢弃，
    // 否则会自动把中文写回去，站点异步 handler 就又读到中文了。
    suppress = true;
    if (discard) deferredDiscard = true;
    try { fn(); } finally {
      if (suppressTimer) clearTimeout(suppressTimer);
      suppressTimer = setTimeout(function () {
        suppress = false;
        suppressTimer = null;
        var batch = deferredDiscard ? [] : deferred.slice();
        deferred.length = 0;
        deferredDiscard = false;
        if (batch.length) handleMutations(batch);
      }, 0);
    }
  }

  /* --------------------------------------------------------------- restore */

  function restoreNode(node) {
    var raw = originalText.get(node);
    if (raw === undefined) return;
    runSuppressed(function () {
      try { node.nodeValue = raw; } catch (e) {}
    });
    originalText.delete(node);
    translatedNodes.delete(node);
  }

  function restoreElement(el) {
    var saved = originalAttr.get(el);
    if (!saved) return;
    runSuppressed(function () {
      Object.keys(saved).forEach(function (attr) {
        try { el.setAttribute(attr, saved[attr]); } catch (e) {}
      });
    });
    originalAttr.delete(el);
    translatedElements.delete(el);
  }

  function restoreAll() {
    runSuppressed(function () {
      Array.from(rewrittenLines).forEach(function (el) {
        var html = lineOriginal.get(el);
        if (html !== undefined) { try { el.innerHTML = html; } catch (e) {} }
        lineOriginal.delete(el);
        lineApplied.delete(el);
      });
      rewrittenLines.clear();
      Array.from(translatedNodes).forEach(function (n) {
        var raw = originalText.get(n);
        if (raw !== undefined) { try { n.nodeValue = raw; } catch (e) {} }
        originalText.delete(n);
      });
      translatedNodes.clear();
      Array.from(translatedElements).forEach(function (el) {
        var saved = originalAttr.get(el);
        if (saved) Object.keys(saved).forEach(function (a) {
          try { el.setAttribute(a, saved[a]); } catch (e) {}
        });
        originalAttr.delete(el);
      });
      translatedElements.clear();
      var marks = document.querySelectorAll('[data-fbzh]');
      for (var i = 0; i < marks.length; i++) marks[i].removeAttribute('data-fbzh');
    });
    stats.nodes = 0; stats.attributes = 0; stats.lines = 0;
  }

  function retranslate() {
    restoreAll();
    if (state.enabled && state.mode !== 'en') {
      buildIndex();
      translate(document.body || document.documentElement);
    }
    emit();
  }

  /* ------------------------------------------------- 交互时还原成英文原文 */

  function restoreHost(host) {
    if (!host || !host.querySelectorAll) return false;
    var changed = false;
    // 整行改写过（<span> 包数值的统计行）时，还原的是整个容器的 HTML
    Array.from(rewrittenLines).forEach(function (el) {
      if (el === host || (host.contains && host.contains(el))) {
        restoreLine(el);
        changed = true;
      }
    });
    runSuppressed(function () {
      Array.from(translatedNodes).forEach(function (n) {
        if (host === n || (host.contains && host.contains(n))) {
          var raw = originalText.get(n);
          if (raw !== undefined) {
            try { n.nodeValue = raw; } catch (e) {}
            // 清除翻译标记，让之后的 retranslateHost 能重新把这些节点翻回中文
            originalText.delete(n);
            translatedNodes.delete(n);
            changed = true;
          }
        }
      });
    }, true);   // discard：还原产生的记录不触发自动重翻译
    return changed;
  }

  function retranslateHost(host) {
    if (!host || !host.isConnected) return;
    translate(host);
  }

  function installInteractionGuard() {
    var restoreTimer = null;
    var hosts = [];
    function onDown(evt) {
      if (!state.enabled || state.mode === 'en') return;
      if (evt.target && evt.target.closest && evt.target.closest('.fbzh-ui')) return;
      var target = evt.target;
      var host = target && target.closest ? target.closest('[data-fbzh]') : null;
      if (!host) return;
      // 站点常见写法：读取 event 目标按钮的 innerText 作为物品基底名。
      // 捕获阶段先还原英文，站点 handler 就能拿到原始值。
      if (restoreHost(host)) {
        hosts.push(host);
        if (restoreTimer) clearTimeout(restoreTimer);
      }
    }
    function onUp() {
      if (!hosts.length) return;
      if (restoreTimer) clearTimeout(restoreTimer);
      var batch = hosts.slice();
      hosts = [];
      restoreTimer = setTimeout(function () {
        batch.forEach(retranslateHost);
        restoreTimer = null;
      }, 350);
    }
    document.addEventListener('pointerdown', onDown, true);
    document.addEventListener('mousedown', onDown, true);
    document.addEventListener('pointerup', onUp, true);
    document.addEventListener('mouseup', onUp, true);
    document.addEventListener('click', onUp, true);
    document.addEventListener('focusin', function (evt) {
      if (!state.enabled || state.mode === 'en') return;
      var host = evt.target && evt.target.closest ? evt.target.closest('[data-fbzh]') : null;
      if (host && restoreHost(host)) setTimeout(function () { retranslateHost(host); }, 500);
    }, true);
  }

  /* -------------------------------------------------------- MutationObserver */

  function schedule(root) {
    if (!root) return;
    pending.add(root);
    if (scheduled) return;
    scheduled = true;
    var run = function () {
      scheduled = false;
      var batch = Array.from(pending);
      pending.clear();
      batch.forEach(function (n) {
        if (n.isConnected === false && n !== document.body && n !== document.documentElement) return;
        translate(n);
      });
      emit();
    };
    // 固定用宏任务批处理，不依赖 requestIdleCallback（部分环境不触发，会导致界面永远不翻译）
    setTimeout(run, 16);
  }

  function handleMutations(records) {
    if (!state.enabled || state.mode === 'en') return;
    var roots = new Set();
    records.forEach(function (rec) {
      if (rec.type === 'childList') {
        rec.addedNodes.forEach(function (n) {
          if (n.nodeType === 1 || n.nodeType === 3) roots.add(n);
        });
        // 站点常用 v-html 整段替换容器内容（统计栏的数值 <span>），
        // 只有把容器本身也纳入重扫，「整行」才拼得回来。
        if (rec.target && rec.target.nodeType === 1) roots.add(rec.target);
      } else if (rec.type === 'characterData') {
        var node = rec.target;
        if (node && node.nodeType === 3 && !originalText.has(node)) {
          roots.add(node);
          if (node.parentElement) roots.add(node.parentElement);
        }
      } else if (rec.type === 'attributes') {
        if (!originalAttr.has(rec.target)) roots.add(rec.target);
      }
    });
    roots.forEach(schedule);
  }

  function installObserver() {
    var observer = new MutationObserver(function (records) {
      if (suppress) {
        for (var i = 0; i < records.length; i++) deferred.push(records[i]);
        return;
      }
      handleMutations(records);
    });
    observer.observe(document.documentElement, {
      childList: true, subtree: true, characterData: true,
      attributes: true, attributeFilter: ATTRS
    });
  }

  /* --------------------------------------------------------------- public */

  function getStatus() {
    return {
      enabled: state.enabled,
      mode: state.mode,
      attributes: state.attributes,
      phrase: state.phrase,
      entries: Object.keys(DICT).length,
      templates: tplMap.size,
      translatedNodes: translatedNodes.size,
      translatedLines: rewrittenLines.size,
      translatedAttributes: translatedElements.size,
      stats: { nodes: stats.nodes, attributes: stats.attributes, lines: stats.lines }
    };
  }

  function setSettings(patch) {
    var needRebuild = patch && typeof patch.phrase !== 'undefined' && patch.phrase !== state.phrase;
    Object.keys(patch || {}).forEach(function (k) {
      if (k in state && typeof patch[k] === typeof state[k]) state[k] = patch[k];
    });
    saveSettings();
    if (needRebuild) retranslate();
    else if (!state.enabled || state.mode === 'en') { restoreAll(); emit(); }
    else { retranslate(); }
  }

  function lookupTerm(query, limit) {
    var q = normalize(query).toLowerCase();
    if (!q) return [];
    var out = [];
    Object.keys(DICT).forEach(function (en) {
      if (out.length >= (limit || 30)) return;
      if (en.toLowerCase().indexOf(q) >= 0 || String(DICT[en]).indexOf(normalize(query)) >= 0) {
        out.push({ en: en, zh: DICT[en] });
      }
    });
    return out;
  }

  function collectUntranslated() {
    var out = new Set();
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var p = n.parentElement;
        if (!p || isSkipped(p)) return NodeFilter.FILTER_REJECT;
        var v = normalize(n.nodeValue || '');
        if (v.length < 3 || v.length > 160) return NodeFilter.FILTER_REJECT;
        if (!/[A-Za-z]{3}/.test(v) || !/\s/.test(v)) return NodeFilter.FILTER_REJECT;
        if (hasCJK(v)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    while (walker.nextNode()) out.add(normalize(walker.currentNode.nodeValue));
    return Array.from(out);
  }

  function download(filename, text) {
    var blob = new Blob([text], { type: 'application/json;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 1000);
  }

  function init() {
    loadSettings();
    buildIndex();
    if (state.enabled && state.mode !== 'en') translate(document.body || document.documentElement);
    installObserver();
    installInteractionGuard();
    document.addEventListener('keydown', function (evt) {
      if (evt.altKey && (evt.key === 'z' || evt.key === 'Z')) {
        evt.preventDefault();
        setSettings({ mode: state.mode === 'en' ? 'zh' : 'en' });
      }
    });
    emit();
  }

  global.FBZH = {
    init: init,
    on: on,
    getStatus: getStatus,
    setSettings: setSettings,
    lookupTerm: lookupTerm,
    collectUntranslated: collectUntranslated,
    download: download,
    retranslate: retranslate,
    dictionary: DICT
  };
})(typeof window !== 'undefined' ? window : this);
