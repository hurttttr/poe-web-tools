/* =============================================================================
 * 离线预览页端到端测试：用真实打包产物 dist/preview.html 在 jsdom 里跑一遍，
 * 验证词典、引擎、面板、样式注入与 3.29 补齐项全部生效。
 *   node tests/preview.test.js
 * ========================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'dist/preview.html'), 'utf8');
const dom = new JSDOM(html, {
  url: 'https://www.filterblade.xyz/?game=Poe1',
  runScripts: 'dangerously',
  pretendToBeVisual: true
});

setTimeout(() => {
  const d = dom.window.document;
  const body = d.body.textContent;
  const checks = {
    '稀有通货长说明': body.includes('除了本身效果强大，高级通货'),
    '金币长说明': body.includes('金币在整个游戏中都能找到'),
    '残遗暗金长说明': body.includes('永恒冲突（军团）'),
    '海底掉落说明': body.includes('海底找到'),
    '联盟标题': body.includes('不灭余烬联盟'),
    '残遗暗金标题': body.includes('残遗暗金'),
    '当前联盟': body.includes('当前联盟：3.29 不灭余烬'),
    '珊瑚礁海图': body.includes('珊瑚礁海图'),
    '1000x Gold 短词替换': body.includes('1000x 金币'),
    '导航 EXPORT': body.includes('导出'),
    'DISCORD': body.includes('Discord 社区'),
    'REPORT AN ISSUE': body.includes('反馈问题'),
    '搜索 placeholder': d.querySelectorAll('input[type=text]')[0].getAttribute('placeholder') === '搜索（Ctrl + K）',
    '登录按钮': body.includes('使用 PoE 账号登录'),
    '代码块保持英文': d.querySelector('pre').textContent.includes('BaseType "Chaos Orb"'),
    '控制面板已注入': !!d.getElementById('fbzh-root'),
    '样式已注入': !!d.getElementById('fbzh-style')
  };
  console.log('离线预览页端到端测试：');
  Object.entries(checks).forEach(([k, v]) => console.log((v ? '  PASS ' : '  FAIL ') + k));
  const status = dom.window.FBZH && dom.window.FBZH.getStatus();
  console.log(`词条 ${status ? status.entries : '?'} 条，已翻译 ${status ? status.stats.nodes : '?'} 处文本`);
  dom.window.close();
  if (Object.values(checks).some((v) => !v)) process.exitCode = 1;
}, 800);
