/* =============================================================================
 * 引擎行为测试（需要 jsdom）
 *   cd tests && npm install jsdom --no-save --no-package-lock
 *   node tests/engine.test.js
 * 覆盖：初始翻译、短语替换、属性翻译、代码区隔离、动态节点、
 *       中/英/双语切换、点击交互还原、词典查询、未译文本导出。
 * ========================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const dict = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/dictionary.json'), 'utf8'));
const shortWords = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/short_words.json'), 'utf8')).terms;
const siteTerms = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/site_terms.json'), 'utf8')).terms;
const modTplDoc = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/mod_templates.json'), 'utf8'));
const modTpl = modTplDoc.templates;
const modPrefix = modTplDoc.prefix || {};
const engine = fs.readFileSync(path.join(ROOT, 'src/engine.js'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'src/style.css'), 'utf8');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let passed = 0;
function ok(name, fn) {
  try { fn(); passed++; console.log('  PASS ' + name); }
  catch (e) { console.error('  FAIL ' + name + '\n       ' + e.message); process.exitCode = 1; }
}

// 从词典里挑一条长说明文案用于「整句精确匹配」测试
const longKey = Object.keys(dict).find((k) => k.length > 60 && k.length < 200 && !k.includes('"'));
// 从站点精翻词条里挑一条 >200 字符的说明段落，验证整段 DOM 文本节点可命中
const siteLongKey = Object.keys(siteTerms).find((k) => k.length > 200 && k.length < 1000);
const faqQuestion = "I don't know where to start. How do I use FilterBlade? What even is it?";

const html = `<!doctype html><html><body>
  <nav>
    <a id="nav-start">Start</a>
    <a id="nav-custom">Customize</a>
    <a id="nav-sim">Simulate</a>
    <a id="nav-adv">Advanced</a>
    <span id="lootsim">Loot Simulator</span>
  </nav>
  <h2 id="strict-label">Strictness</h2>
  <button id="tierbtn">Semi-Strict</button>
  <div id="currency">Chaos Orb</div>
  <div id="card">The Doctor</div>
  <div id="base">Vaal Regalia</div>
  <div id="stack">Stack size: 6</div>
  <div id="combo">Evasion / Armour</div>
  <div id="long"></div>
  <div id="site-long"></div>
  <div id="faq-q"></div>
  <div id="gold">1000x Gold</div>
  <div id="mixed">亡者硫磺 Ducats and all kind of precious items</div>
  <div id="jewel-mods">
    <div id="mod-adds">Adds 5 Passive Skills</div>
    <div id="mod-req">Requires Level 54</div>
    <div id="mod-socket">1 Added Passive Skill is a Jewel Socket</div>
    <div id="mod-grant">Added Small Passive Skills grant: 10% increased Damage while affected by a Herald</div>
    <div id="mod-also">Added Small Passive Skills also grant: +3% to Fire Resistance</div>
    <div id="mod-regen">Added Small Passive Skills also grant: Regenerate 0.15% of Life per Second</div>
    <div id="mod-notable">1 Added Passive Skill is Endbringer</div>
    <div id="mod-herald">20% increased Effect of Herald Buffs on you</div>
    <div id="mod-range">Adds 5 to 10 Fire Damage</div>
    <div id="mod-desc">Place into an allocated Medium or Large Jewel Socket on the Passive Skill Tree. Added passives do not interact with jewel radii. Right click to remove from the Socket.</div>
    <div id="mod-mismatch">Requires 12 34 Level 54</div>
    <div id="mod-allocate">Allocates Avatar of Fire</div>
  </div>
  <input id="search" type="text" placeholder="Search (Ctrl + K)">
  <textarea id="ta">Show</textarea>
  <pre id="pre">Class "Currency"</pre>
  <div id="unknown">ZZZ Unknown Placeholder QQQ</div>
</body></html>`;

const dom = new JSDOM(html, {
  url: 'https://www.filterblade.xyz/?game=Poe1',
  runScripts: 'outside-only',
  pretendToBeVisual: true
});
const w = dom.window;
w.FBZH_DICT = dict;
w.FBZH_SHORT_WORDS = shortWords;
w.FBZH_MOD_TPL = modTpl;
w.FBZH_MOD_PREFIX = modPrefix;
w.FBZH_CSS = css;
w.eval(engine);
w.document.getElementById('long').textContent = longKey;
w.document.getElementById('site-long').textContent = siteLongKey;
w.document.getElementById('faq-q').textContent = faqQuestion;
w.FBZH.init();

const text = (sel) => w.document.querySelector(sel).textContent.trim();

async function main() {
  console.log('PoE Web Tools 汉化引擎测试\n');

  ok('导航 / 单词精确匹配', () => assert.strictEqual(text('#nav-start'), '开始'));
  ok('物品名以编年史译名为准', () => {
    assert.strictEqual(text('#currency'), '混沌石');
    assert.strictEqual(text('#card'), '疯医');
    assert.strictEqual(text('#base'), '瓦尔法衣');
  });
  ok('界面术语', () => {
    assert.strictEqual(text('#strict-label'), '过滤严格度');
    assert.strictEqual(text('#tierbtn'), '半严格');
    assert.strictEqual(text('#nav-sim'), '模拟');
    assert.strictEqual(text('#lootsim'), '掉落模拟器');
  });
  ok('长文本内短语替换', () => assert.strictEqual(text('#stack'), '堆叠数量: 6'));
  ok('组合标签精确匹配', () => assert.strictEqual(text('#combo'), '闪避 / 护甲'));
  ok('整句说明精确匹配', () => assert.strictEqual(text('#long'), dict[longKey]));
  ok('新赛季长说明整段命中', () => assert.strictEqual(text('#site-long'), siteTerms[siteLongKey]));
  ok('FAQ 问题标题命中', () => assert.strictEqual(text('#faq-q'), siteTerms[faqQuestion]));
  ok('数字＋英文混排短词替换', () => assert.strictEqual(text('#gold'), '1000x 金币'));
  ok('中文＋英文混排局部替换', () => assert.ok(text('#mixed').includes('杜卡特')));
  ok('placeholder 属性翻译', () =>
    assert.strictEqual(w.document.getElementById('search').getAttribute('placeholder'), '搜索（Ctrl + K）'));
  ok('textarea / pre 代码区不被改写', () => {
    assert.strictEqual(text('#ta'), 'Show');
    assert.strictEqual(text('#pre'), 'Class "Currency"');
  });
  ok('未登录词保持英文', () => assert.strictEqual(text('#unknown'), 'ZZZ Unknown Placeholder QQQ'));

  ok('词缀模板：数值占位回填', () => {
    assert.strictEqual(text('#mod-adds'), '增加 5 个天赋技能');
    assert.strictEqual(text('#mod-req'), '需求 等级 54');
    assert.strictEqual(text('#mod-regen'), '增加的小天赋还获得：每秒再生 0.15% 生命');
    assert.strictEqual(text('#mod-range'), '该装备附加 5 - 10 基础火焰伤害');
    assert.strictEqual(text('#mod-herald'), '你身上的捷增益效果提高 20%');
  });
  ok('词缀模板：小写骨架兼容站点大写', () =>
    assert.strictEqual(text('#mod-also'), '增加的小天赋还获得：+3% 火焰抗性'));
  ok('珠宝词缀整串命中', () => {
    assert.strictEqual(text('#mod-socket'), '其中 1 个增加的天赋为珠宝槽');
    assert.strictEqual(text('#mod-grant'), '增加的小天赋获得：受捷影响时，伤害提高 10%');
    assert.strictEqual(text('#mod-notable'), '其中 1 个增加的天赋为末日使者');
    assert.strictEqual(text('#mod-desc').includes('珠宝插槽'), true);
    assert.strictEqual(text('#mod-desc').includes('Place into'), false);
  });
  ok('占位符与数字数量不一致时保持原文', () =>
    assert.strictEqual(text('#mod-mismatch'), 'Requires 12 34 Level 54'));
  ok('前缀规则：Allocates + 天赋名', () =>
    assert.strictEqual(text('#mod-allocate'), '配置 火之化身'));
  ok('被翻译节点带 data-fbzh 标记', () =>
    assert.strictEqual(w.document.getElementById('currency').getAttribute('data-fbzh'), '1'));

  w.FBZH.setSettings({ mode: 'en' });
  ok('切换原文模式可完整还原', () => {
    assert.strictEqual(text('#nav-start'), 'Start');
    assert.strictEqual(text('#currency'), 'Chaos Orb');
    assert.strictEqual(w.document.getElementById('search').getAttribute('placeholder'), 'Search (Ctrl + K)');
  });

  w.FBZH.setSettings({ mode: 'both' });
  ok('双语模式同时保留中英', () => {
    assert.ok(text('#nav-start').includes('开始') && text('#nav-start').includes('Start'));
  });

  w.FBZH.setSettings({ mode: 'zh' });
  ok('切回中文模式重新翻译', () => assert.strictEqual(text('#currency'), '混沌石'));

  w.FBZH.setSettings({ enabled: false });
  ok('停用汉化还原原文', () => assert.strictEqual(text('#nav-start'), 'Start'));
  w.FBZH.setSettings({ enabled: true });

  // 动态插入节点（模拟 FilterBlade 异步渲染的 Tier List）
  const dyn = w.document.createElement('div');
  dyn.id = 'dyn';
  dyn.textContent = 'Exalted Orb';
  w.document.body.appendChild(dyn);
  await sleep(150);
  ok('MutationObserver 覆盖动态节点', () => assert.strictEqual(text('#dyn'), '崇高石'));

  // 点击交互还原：站点读取 innerText 时必须拿到英文
  const btn = w.document.getElementById('tierbtn');
  btn.dispatchEvent(new w.MouseEvent('mousedown', { bubbles: true }));
  ok('点击捕获阶段还原英文原文', () => assert.strictEqual(btn.textContent.trim(), 'Semi-Strict'));
  btn.dispatchEvent(new w.MouseEvent('mouseup', { bubbles: true }));
  await sleep(650);
  ok('交互结束后自动恢复中文', () => assert.strictEqual(btn.textContent.trim(), '半严格'));

  ok('中英对照查询', () => {
    const rows = w.FBZH.lookupTerm('混沌石', 10);
    assert.ok(rows.some((r) => r.en === 'Chaos Orb'));
  });
  ok('未译文本收集', () => {
    const list = w.FBZH.collectUntranslated();
    assert.ok(list.some((t) => t.includes('ZZZ Unknown')));
  });
  ok('状态统计可用', () => {
    const s = w.FBZH.getStatus();
    assert.strictEqual(s.entries, Object.keys(dict).length);
    assert.ok(s.stats.nodes > 0);
  });

  // 抽样：随机 150 条词条整串匹配不会漏翻
  const keys = Object.keys(dict);
  let sample = [];
  for (let i = 0; i < 150; i++) sample.push(keys[(i * 977) % keys.length]);
  const holder = w.document.createElement('div');
  holder.id = 'sample';
  sample.forEach((k, i) => {
    const s = w.document.createElement('span');
    s.id = 's' + i;
    s.textContent = k;
    holder.appendChild(s);
  });
  w.document.body.appendChild(holder);
  await sleep(200);
  ok('150 条词条抽样整串匹配', () => {
    let bad = [];
    sample.forEach((k, i) => {
      const got = w.document.getElementById('s' + i).textContent.trim();
      if (got !== dict[k] && !got.includes(dict[k])) bad.push(k + ' -> ' + got);
    });
    assert.strictEqual(bad.length, 0, '漏翻: ' + bad.slice(0, 5).join(' | '));
  });

  console.log(`\n通过 ${passed} 项`);
  w.close();
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
