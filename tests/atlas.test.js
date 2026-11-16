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

  console.log(`\n通过 ${passed} 项`);
  preview.window.close();
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
