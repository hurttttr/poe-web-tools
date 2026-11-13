/* =============================================================================
 * poe.ninja 离线预览页端到端测试（真实打包产物 dist/preview-ninja.html）
 *   node tests/ninja.test.js
 * ========================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'dist/preview-ninja.html'), 'utf8');
const dom = new JSDOM(html, {
  url: 'https://poe.ninja/poe1/economy/allflame/currency',
  runScripts: 'dangerously',
  pretendToBeVisual: true
});

setTimeout(() => {
  const d = dom.window.document;
  const body = d.body.textContent;
  const checks = {
    '导航 Economy': body.includes('经济'),
    '导航 Builds': body.includes('流派'),
    '导航 Atlas Trees': body.includes('异界天赋树'),
    '登录 Log in': body.includes('登录'),
    '列头 Chaos Value': body.includes('混沌石价值'),
    '列头 Divine Value': body.includes('神圣石价值'),
    '列头 Listings': body.includes('挂单量'),
    '列头 Price': body.includes('价格'),
    '列头 Change': body.includes('变动'),
    '列头 Confidence': body.includes('可信度'),
    'placeholder 筛选': d.querySelector('input[type=text]').getAttribute('placeholder') === '按名称筛选',
    '物品 Chaos Orb': body.includes('混沌石'),
    '物品 Divine Orb': body.includes('神圣石'),
    '物品 Mirror of Kalandra': body.includes('卡兰德的魔镜'),
    '命运卡 The Doctor': body.includes('疯医'),
    '技能 Spark': body.includes('电球'),
    '升华 Deadeye': body.includes('锐眼'),
    '时间范围 1 week': body.includes('1 周'),
    '最后更新': body.includes('最后更新'),
    '数据不足': body.includes('数据不足'),
    '低可信度长句': body.includes('低可信度。价格基于少量挂单。'),
    '页脚声明': body.includes('亦未获其认可'),
    '流派页 装备槽位 Rare Helmet': body.includes('稀有头部'),
    '流派页 装备槽位 Rare Body Armour': body.includes('稀有胸甲'),
    '流派页 魔法药剂 Magic Flask': body.includes('魔法药剂'),
    '流派页 稀有珠宝 Rare Jewel': body.includes('稀有珠宝'),
    '流派页 暗金名称 Kaom\'s Heart': body.includes('冈姆的壮志'),
    '流派页 技能 正义之火': body.includes('正义之火'),
    '流派页 技能 瓦尔：正义之火': body.includes('瓦尔：正义之火'),
    '流派页 技能 火焰陷阱': body.includes('火焰陷阱'),
    '流派页 基石天赋': body.includes('异灵之体'),
    '流派页 EHP 列头': body.includes('有效生命'),
    '流派页 装备提示前缀': body.includes('角色使用任意'),
    '流派页 宝石标签': body.includes('效果区域') && body.includes('持续时间'),
    '流派页 技能说明整段': body.includes('以魔法之火快速的燃烧自己及周围的敌人'),
    '流派页 Class 列头（站点专属词条）': [...d.querySelectorAll('table thead th')].some((th) => th.textContent.trim() === '职业'),
    '珠宝提示 需求等级': body.includes('需求 等级 54'),
    '珠宝提示 天赋数量': body.includes('增加 5 个天赋技能'),
    '珠宝提示 珠宝槽': body.includes('其中 1 个增加的天赋为珠宝槽'),
    '珠宝提示 小天赋获得': body.includes('增加的小天赋获得：受捷影响时，伤害提高 10%'),
    '珠宝提示 小天赋还获得（抗性）': body.includes('增加的小天赋还获得：+3% 火焰抗性'),
    '珠宝提示 小天赋还获得（回复）': body.includes('每秒再生 0.15% 生命'),
    '珠宝提示 天赋名': body.includes('其中 1 个增加的天赋为赋能使者') && body.includes('其中 1 个增加的天赋为末日使者'),
    '珠宝提示 天赋描述': body.includes('捷技能造成的伤害提高 40%')
      && body.includes('你身上的捷增益效果提高 20%')
      && body.includes('每有一个影响你的捷效果都使伤害提高 5%')
      && body.includes('受捷影响时，伤害提高 20%'),
    '珠宝提示 放置说明': (() => {
      const t = d.querySelector('.tip-desc').textContent;
      return t.includes('已配置的中型或大型珠宝插槽') && t.includes('右键点击以移出插槽') && !t.includes('Place into');
    })(),
    '专精 MASTERS 标题': d.querySelector('#passive-tip .tip-section').textContent.trim() === '专精',
    '专精名 Life Mastery': body.includes('生命专精'),
    '专精名 Projectile Mastery': body.includes('投射物专精'),
    '专精投射物说明': body.includes('投射物伤害按照每 16 点敏捷提高 1%'),
    '专精名 Reservation Mastery': body.includes('保留专精'),
    '专精心血说明（装备胸甲）': body.includes('若装备的胸甲没有生命词缀，生命上限提高 15%'),
    '专精光环/捷说明': body.includes('伤害按照你身上每种影响你的光环或捷提高 8%'),
    '关键天赋 苦痛灵曲': body.includes('苦痛灵曲') && body.includes('低血时法术伤害总增 30%'),
    '关键天赋 无视属性需求': body.includes('无上宣示') && body.includes('无视属性需求'),
    '符文嫁接说明': body.includes('法术附加等同于已装备双手武器物理伤害 30% 的法术伤害'),
    '控制面板': !!d.getElementById('fbzh-root'),
    '样式注入': !!d.getElementById('fbzh-style')
  };
  console.log('poe.ninja 预览页端到端测试：');
  Object.entries(checks).forEach(([k, v]) => console.log((v ? '  PASS ' : '  FAIL ') + k));
  const s = dom.window.FBZH && dom.window.FBZH.getStatus();
  console.log(`词条 ${s ? s.entries : '?'} 条，已翻译 ${s ? s.stats.nodes : '?'} 处文本`);
  dom.window.close();
  if (Object.values(checks).some((v) => !v)) process.exitCode = 1;
}, 800);
