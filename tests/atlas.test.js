/* =============================================================================
 * PoE Planner / atlas-tree 汉化测试
 *   node tests/atlas.test.js
 *
 * A. 离线预览页端到端（真实打包产物 dist/preview-atlas.html）
 * B. 站点专属 host 作用域：poeplanner 生效、其他站点不污染
 * C. Vuetify / Material Icons ligature 文本隔离（引擎新增规则）
 * ========================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const json = (p) => JSON.parse(read(p));

let passed = 0;
function ok(name, fn) {
  try { fn(); passed++; console.log('  PASS ' + name); }
  catch (e) { console.error('  FAIL ' + name + '\n       ' + e.message); process.exitCode = 1; }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------------ A */
const preview = new JSDOM(read('dist/preview-atlas.html'), {
  url: 'file:///C:/preview-atlas.html',
  runScripts: 'dangerously',
  pretendToBeVisual: true
});

/* ------------------------------------------------------------------ B/C */
const dict = json('data/dictionary.json');
const shortWords = json('data/short_words.json').terms;
const hostTerms = Object.fromEntries(
  Object.entries(json('data/host_terms.json')).filter(([k]) => !k.startsWith('_'))
);
hostTerms['poeplanner.com'] = json('data/atlas_terms.json');
const modDoc = json('data/mod_templates.json');
const modTpl = Object.assign({}, modDoc.templates, json('data/atlas_templates.json'));
const modPrefix = modDoc.prefix || {};
const engine = read('src/engine.js');

function hostDom(url) {
  const dom = new JSDOM(`<!doctype html><html><body>
    <div id="collapse">Collapse all</div>
    <div id="clear">Clear</div>
    <div id="atlas">Atlas Tree</div>
    <div id="stat">Your Maps have 8% chance to be inhabited by a Mercenary</div>
    <i class="v-icon material-icons" id="icon">expand_more</i>
    <i class="v-icon material-icons" id="icon2">folder</i>
  </body></html>`, { url, runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.FBZH_DICT = dict;
  w.FBZH_SHORT_WORDS = shortWords;
  w.FBZH_HOST_DICT = hostTerms;
  w.FBZH_MOD_TPL = modTpl;
  w.FBZH_MOD_PREFIX = modPrefix;
  w.FBZH_CSS = '';
  w.eval(engine);
  w.FBZH.init();
  return dom;
}

async function main() {
  console.log('PoE Planner / atlas-tree 汉化测试\n');

  // 等待预览页的 MutationObserver 与异步节点渲染完成
  await sleep(900);
  const d = preview.window.document;
  // 预览页把整份词典内联在 <script> 里，body.textContent 会包含词典 JSON，
  // 直接拿它断言会造成假阳性/假阴性。这里只取可见文本。
  const visibleText = () => {
    const clone = d.body.cloneNode(true);
    clone.querySelectorAll('script,style,noscript,.fbzh-ui').forEach((n) => n.remove());
    return clone.textContent;
  };
  const body = visibleText();
  const txt = (sel) => {
    const el = d.querySelector(sel);
    return el ? el.textContent.trim() : '';
  };
  const tip = (i) => {
    const el = d.querySelectorAll('#tooltips .tip')[i];
    return el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  };

  console.log('A. 离线预览页');
  ok('控制面板与样式注入', () => {
    assert.ok(d.getElementById('fbzh-root'));
    assert.ok(d.getElementById('fbzh-style'));
  });
  ok('导航 My Builds / Changelog / Contact', () => {
    assert.ok(body.includes('我的构建'));
    assert.ok(body.includes('更新日志'));
    assert.ok(body.includes('联系我们'));
  });
  ok('导航 Atlas Tree / Privacy policy / Login', () => {
    assert.ok(body.includes('异界天赋树'));
    assert.ok(body.includes('隐私政策'));
    assert.ok(body.includes('登录'));
  });
  ok('工具栏 Notes / Import/Export', () => {
    assert.ok(body.includes('备注'));
    assert.ok(body.includes('导入 / 导出'));
  });
  ok('工具栏 Collapse all / Expand all', () => {
    assert.ok(body.includes('全部折叠'));
    assert.ok(body.includes('全部展开'));
  });
  ok('工具栏 clear / Reset / Save as new', () => {
    assert.ok(body.includes('清除'));
    assert.ok(body.includes('重置'));
    assert.ok(body.includes('另存为新构建'));
  });
  ok('搜索框 placeholder 与 aria-label', () => {
    const input = d.querySelector('input[type=text]');
    assert.strictEqual(input.getAttribute('placeholder'), '搜索天赋节点…');
    assert.strictEqual(input.getAttribute('aria-label'), '搜索天赋节点…');
  });
  ok('版本行与登录提示', () => {
    assert.ok(txt('.version').includes('异界天赋树版本'));
    assert.ok(txt('.version').includes('登录后即可保存构建'));
  });
  ok('点数行 Allocated Nodes', () => assert.ok(txt('.points').includes('已配置天赋点')));
  ok('节点 title 属性（Destructive Play）', () => {
    assert.strictEqual(d.querySelector('.nd[title]').getAttribute('title'), '毁灭游戏');
  });
  ok('天赋名 毁灭游戏 / 未行之路 / 隐秘跳跃点', () => {
    assert.ok(body.includes('毁灭游戏'));
    // 这两个节点只以 title 属性出现，验证属性翻译而非文本节点
    const titles = [...d.querySelectorAll('.nd[title]')].map((e) => e.getAttribute('title'));
    assert.ok(titles.includes('未行之路'));
    assert.ok(titles.includes('隐秘跳跃点'));
  });
  ok('天赋名 穿越怪物群大小 / 深渊怪物数量 / 核心天赋', () => {
    assert.ok(tip(1).includes('穿越怪物群大小'));
    assert.ok(tip(2).includes('深渊怪物数量'));
    assert.ok(tip(0).includes('核心天赋'));
  });
  ok('# 模板回填：Incursion Pack Size', () => {
    assert.ok(tip(1).includes('4%'));
    assert.ok(!tip(1).includes('Incursions in your Maps'));
    assert.ok(tip(1).includes('穿越怪物群规模'));
  });
  ok('# 模板回填：新增佣兵效果', () => {
    assert.ok(tip(2).includes('你的地图有 8% 几率出现佣兵'));
    assert.ok(!tip(2).includes('inhabited by a Mercenary'));
  });
  ok('跨行拆分说明整体汉化', () => {
    const t = tip(0);
    assert.ok(t.includes('贤主施放赌注加码，额外召唤 1 到 3 个异界首领'));
    assert.ok(t.includes('在目睹地图首领时'));
    assert.ok(t.includes('每张地图最终首领的词缀也会作用于这些被召唤的首领'));
    assert.ok(!t.includes('Up the Stakes'));
  });
  ok(' flavour 文本与节点分级', () => {
    assert.ok(tip(0).includes('异界图鉴铭记着每一场战斗'));
    assert.ok(tip(1).includes('显著天赋'));
    assert.ok(tip(2).includes('小型天赋'));
  });
  ok('侧栏 Pinned / Cumulative / Node Breakdown', () => {
    assert.ok(body.includes('固定显示的属性'));
    assert.ok(body.includes('累计属性'));
    assert.ok(body.includes('节点明细'));
  });
  ok('统计行：数值被 <span> 包住也整行汉化', () => {
    assert.ok(txt('#stat-line-1').includes('你的地图有 8% 几率出现佣兵'));
    const t2 = txt('#stat-line-2');
    assert.ok(t2.includes('来自已配置的显著异界天赋'), t2);
    assert.ok(!t2.includes('Allocated Notable'), t2);
  });
  ok('统计行：多条说明换行拼接时逐行翻译', () => {
    const t = txt('#stat-line-3');
    assert.ok(t.includes('你的地图有 8% 几率出现佣兵'), t);
    assert.ok(!t.includes('Abysses in your Maps'), t);
  });
  ok('统计行：数值高亮 span 被保留', () => {
    const sp = d.querySelector('#stat-line-1 span.textAugmented');
    assert.ok(sp, '翻译后仍应保留数值高亮 span');
    assert.ok(/\d/.test(sp.textContent), sp.textContent);
  });
  ok('侧栏节点分级 Keystone / Notable / Gateway / Mastery', () => {
    assert.ok(body.includes('跳跃点'));
    assert.ok(body.includes('专精'));
  });
  ok('导入导出与状态提示', () => {
    assert.ok(body.includes('GGG 已移除通过账号名导入异界天赋树的功能'));
    assert.ok(body.includes('异界天赋树保存成功'));
    assert.ok(body.includes('这里还没有异界天赋树'));
  });
  ok('异步插入节点被 MutationObserver 翻译', () => {
    assert.ok(d.getElementById('async-tip'));
    assert.ok(txt('#async-tip').includes('你的地图有 25% 几率包含升华试炼'));
  });
  ok('Vuetify 图标 ligature 保持英文', () => {
    const icons = [...d.querySelectorAll('.v-icon')].map((e) => e.textContent.trim());
    assert.ok(icons.includes('expand_more'));
    assert.ok(icons.includes('expand_less'));
    assert.ok(icons.includes('folder'));
    assert.ok(icons.includes('warning'));
    assert.ok(!icons.includes('文件夹'));
  });
  ok('原文模式还原英文（Alt+Z 等价）', () => {
    preview.window.FBZH.setSettings({ mode: 'en' });
    const t = visibleText();
    assert.ok(t.includes('Collapse all'));
    assert.ok(!t.includes('全部折叠'));
  });
  ok('切回中文模式重新翻译', () => {
    preview.window.FBZH.setSettings({ mode: 'zh' });
    assert.ok(visibleText().includes('全部折叠'));
  });
  ok('双语模式保留英文括注', () => {
    preview.window.FBZH.setSettings({ mode: 'both' });
    assert.ok(visibleText().includes('(Collapse all)'));
    preview.window.FBZH.setSettings({ mode: 'zh' });
  });
  ok('引擎状态包含 atlas 词条', () => {
    const s = preview.window.FBZH.getStatus();
    assert.ok(s.entries >= 22500, '词条数应包含 poeplanner 专属词典');
    assert.ok(s.templates >= 7800);
    assert.ok(s.stats.nodes > 50);
  });

  console.log('\nE. 左下角搜索框：中文检索桥');
  const siteInput = d.querySelector('.atlas-tree-toolbar input');
  const ovl = d.querySelector('.fbzh-atlas-search');
  const ovlInput = ovl && ovl.querySelector('input');
  const typeQuery = (v) => {
    ovlInput.value = v;
    ovlInput.dispatchEvent(new preview.window.Event('input', { bubbles: true }));
  };
  ok('中文搜索框接管站点输入框', () => {
    assert.ok(ovl, '叠层输入框应存在');
    assert.strictEqual(d.querySelector('.v-text-field').style.visibility, 'hidden');
    assert.ok(ovl.getAttribute('data-fbzh-skip'));
  });
  ok('中文「毁灭游戏」反查成英文节点名', () => {
    typeQuery('毁灭游戏');
    assert.strictEqual(siteInput.value, '(?:Destructive Play)', siteInput.value);
    assert.strictEqual(ovl.querySelector('.fbzh-as-hint').textContent, '匹配 1 个节点');
  });
  ok('预览页按站点正则高亮命中节点', () => {
    const hits = [...d.querySelectorAll('.nd.hit')].map((e) => e.getAttribute('data-node'));
    assert.deepStrictEqual(hits, ['Destructive Play']);
  });
  ok('中文「跳跃点」命中多个跳跃点节点', () => {
    typeQuery('跳跃点');
    assert.ok(siteInput.value.includes('Cryptic Gateway'), siteInput.value);
    assert.ok(siteInput.value.includes('Mortal Gateway'), siteInput.value);
  });
  ok('英文输入原样透传，站点行为不变', () => {
    typeQuery('Maven');
    assert.strictEqual(siteInput.value, 'Maven');
  });
  ok('无匹配中文给出永不匹配的正则', () => {
    typeQuery('完全不存在的天赋');
    assert.strictEqual(siteInput.value, '(?!)');
    assert.ok(ovl.querySelector('.fbzh-as-hint').textContent.includes('没有匹配'));
  });
  ok('清除按钮同时清空站点搜索', () => {
    ovl.querySelector('.fbzh-as-clear').click();
    assert.strictEqual(ovlInput.value, '');
    assert.strictEqual(siteInput.value, '');
  });
  ok('数字检索按实际数值匹配（# 占位）', () => {
    const names = preview.window.FBZHAtlasSearch.matchNames('8%');
    assert.ok(names.length > 0, '数字查询应有结果');
  });

  console.log('\nB. 站点专属 host 作用域');
  const planner = hostDom('https://poeplanner.com/atlas-tree');
  const pd = planner.window.document;
  ok('poeplanner：Collapse all 使用站点专属译法', () =>
    assert.strictEqual(pd.getElementById('collapse').textContent, '全部折叠'));
  ok('poeplanner：Clear 覆盖主词典的「清澈」', () =>
    assert.strictEqual(pd.getElementById('clear').textContent, '清除'));
  ok('poeplanner：Atlas Tree 仍为异界天赋树', () =>
    assert.strictEqual(pd.getElementById('atlas').textContent, '异界天赋树'));
  ok('poeplanner：新增天赋效果由 # 模板回填', () =>
    assert.strictEqual(pd.getElementById('stat').textContent, '你的地图有 8% 几率出现佣兵'));
  ok('poeplanner：图标 ligature 不被翻译', () => {
    assert.strictEqual(pd.getElementById('icon').textContent, 'expand_more');
    assert.strictEqual(pd.getElementById('icon2').textContent, 'folder');
  });
  planner.window.close();

  const fb = hostDom('https://www.filterblade.xyz/?game=Poe1');
  const fd = fb.window.document;
  ok('FilterBlade：站点专属词不生效', () =>
    assert.strictEqual(fd.getElementById('collapse').textContent, 'Collapse all'));
  ok('FilterBlade：Clear 仍用主词典口径', () =>
    assert.strictEqual(fd.getElementById('clear').textContent, '清澈'));
  ok('FilterBlade：图标同样保持英文', () =>
    assert.strictEqual(fd.getElementById('icon').textContent, 'expand_more'));
  fb.window.close();

  console.log('\nD. 整行翻译与还原（模拟统计栏 DOM）');
  const panelDom = new JSDOM(`<!doctype html><html><body>
    <div id="p1">Your Maps have <span class="textAugmented">8%</span> chance to be inhabited by a Mercenary</div>
    <div id="p2">Abysses in your Maps spawn <span class="textAugmented">8%</span> increased Monsters
Your Maps have <span class="textAugmented">8%</span> chance to be inhabited by a Mercenary</div>
    <div id="p3">Your Maps have <span class="textAugmented">8%</span> chance <button>ok</button></div>
  </body></html>`, { url: 'https://poeplanner.com/atlas-tree', runScripts: 'outside-only', pretendToBeVisual: true });
  const pw = panelDom.window;
  pw.FBZH_DICT = dict;
  pw.FBZH_SHORT_WORDS = shortWords;
  pw.FBZH_HOST_DICT = hostTerms;
  pw.FBZH_MOD_TPL = modTpl;
  pw.FBZH_MOD_PREFIX = modPrefix;
  pw.FBZH_CSS = '';
  pw.eval(engine);
  pw.FBZH.init();
  await sleep(160);
  const pdoc = pw.document;
  ok('跨 span 的统计行整行翻译', () =>
    assert.strictEqual(pdoc.getElementById('p1').textContent.trim(), '你的地图有 8% 几率出现佣兵'));
  ok('翻译后数值高亮 span 仍在', () => {
    const sp = pdoc.querySelector('#p1 span.textAugmented');
    assert.ok(sp && /\d/.test(sp.textContent), sp && sp.outerHTML);
  });
  ok('多条说明换行拼接时逐行翻译', () => {
    const t = pdoc.getElementById('p2').textContent;
    assert.ok(t.includes('你的地图有 8% 几率出现佣兵'), t);
    assert.ok(!/Abysses in your Maps/.test(t), t);
  });
  ok('含交互元素的容器不整体改写', () => {
    const el = pdoc.getElementById('p3');
    assert.ok(el.querySelector('button'), '按钮必须保留');
    assert.ok(el.textContent.includes('ok'));
  });
  ok('整行翻译计入统计', () => assert.ok(pw.FBZH.getStatus().stats.lines >= 2));
  pw.FBZH.setSettings({ mode: 'en' });
  await sleep(160);
  ok('原文模式还原原始 <span> 结构', () => {
    const html = pdoc.getElementById('p1').innerHTML;
    assert.ok(html.includes('Your Maps have'), html);
    assert.ok(html.includes('textAugmented'), html);
  });
  pw.FBZH.setSettings({ mode: 'zh' });
  await sleep(220);
  ok('切回中文后重新整行翻译', () =>
    assert.ok(pdoc.getElementById('p1').textContent.includes('你的地图有 8% 几率出现佣兵')));
  panelDom.window.close();

  console.log(`\n通过 ${passed} 项`);
  preview.window.close();
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
