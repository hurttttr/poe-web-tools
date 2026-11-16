<div align="center">

<h1>PoE Web Tools</h1>

<p><b>流放之路网页汉化工具</b><br>
FilterBlade · poe.ninja · PoE Planner 异界天赋树，一个扩展全部搞定</p>

<p>
  <img alt="version" src="https://img.shields.io/badge/version-1.0.2-f0b429?style=flat-square">
  <img alt="entries" src="https://img.shields.io/badge/entries-22%2C004%2B908-7c3aed?style=flat-square">
  <img alt="sites" src="https://img.shields.io/badge/sites-FilterBlade%20%C2%B7%20poe.ninja%20%C2%B7%20PoE%20Planner-f0b429?style=flat-square">
  <img alt="manifest" src="https://img.shields.io/badge/Manifest-V3-4285F4?style=flat-square&amp;logo=googlechrome&amp;logoColor=white">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white">
</p>

<p>
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-功能">功能</a> ·
  <a href="#-词典">词典</a> ·
  <a href="#-维护">维护</a> ·
  <a href="CHANGELOG.md">更新日志</a> ·
  <a href="docs/AI-NOTES.md">开发笔记</a>
</p>

</div>

---

**离线词典 + 浏览器端运行时注入**，不改服务端、不联网、随开随用。一次交付三种形态：

| 形态 | 说明 |
| --- | --- |
| 🐒 **油猴脚本** | 单文件，装上即用，最省事 |
| 🧩 **Chrome / Edge 扩展** | 三个站点一键跳转，可固定到工具栏 |
| 🖥️ **离线预览页** | 不访问外网即可体验汉化效果（三张页面） |

> 汉化范围覆盖界面文案、道具 / 通货 / 地图 / 命运卡 / 传奇、技能名与说明、物品词缀、天赋与专精描述，以及 **PoE Planner 异界天赋树的 352 个天赋名与全部 338 条效果说明**；支持**中文 / 双语 / 原文**三种模式。

---

## 🚀 快速开始

### 方式 A · 油猴脚本

1. 安装 [Tampermonkey](https://www.tampermonkey.net/) 或 Violentmonkey；
2. 打开 `dist/poe-web-tools.user.js`（拖进扩展管理页，或复制内容新建脚本）；
3. 访问目标站点，右下角出现「汉」按钮即生效。

脚本自包含词典，不联网、无外部依赖。

### 方式 B · 浏览器扩展（推荐）

1. 打开 `chrome://extensions`（Edge 为 `edge://extensions`），开启**开发者模式**；
2. **加载已解压的扩展程序** → 选择 `dist/extension`；
3. 点工具栏拼图图标，把 **PoE Web Tools 固定到工具栏**；
4. 点击图标：三张站点卡片可直接跳转（默认新标签，可勾选当前标签），下方可开关汉化、切换模式。

> 项目文件夹改名或移动后，扩展记录的路径会失效 —— 在扩展页「移除」后重新加载新路径下的 `dist/extension`。

### 方式 C · 离线预览

直接用浏览器打开 `dist/preview.html`（FilterBlade 3.29）、`dist/preview-ninja.html`（poe.ninja 经济 / 流派）或 `dist/preview-atlas.html`（PoE Planner 异界天赋树）。三页顶部可互相切换，内置完整词典与引擎，可现场试模式切换、中英对照查询与点击还原。

> PoE Planner 预览页模拟了 atlas-tree 的界面、节点悬浮提示与异步渲染。真实站点的天赋树本体由 canvas / WebGL 绘制，节点名与说明在悬浮提示里汉化；**站内「搜索节点」按英文匹配**，需要英文时按 `Alt+Z` 切到原文模式。

---

## ✨ 功能

| 功能 | 说明 |
| --- | --- |
| 三种模式 | 中文 / 双语 / 原文；**原文模式**用于站内搜索、新增规则等需要英文的场景 |
| `Alt + Z` | 在「中文 ↔ 原文」间快速切换 |
| 中英对照查询 | 输入中文或英文，点击结果即复制英文名，可直接粘到站内搜索 |
| 导出未译文本 | 导出当前页面仍为英文的清单（JSON），用于补词典 |
| 交互保护 | 点击瞬间自动还原英文，站点逻辑读到原文，松手恢复中文 |
| 设置持久化 | 存于 `localStorage`（`fbzh.settings.v1`） |

<details>
<summary><b>不会翻译的内容 / 仍可能看到英文的地方</b></summary>

**不翻译**：`<script>` / `<style>` / `<textarea>` / `<pre>` / `<code>` 与代码块、输入框 value、下拉选项、广告 iframe、Vuetify 图标（`.v-icon` 的 ligature 文本）、过滤器语法关键字（`Show` / `Hide` / `Class` …）。未收录词的文本保持英文，不会消失或报错。

**仍可能英文**：FAQ 的答案长段落、实时拼接的动态文案（如 `Current League: 3.30 …`）、流派页装备词缀明细、未收录的新物品名、PoE Planner 的站点 flavor 文本。用面板「导出未译文本」拿清单继续补。

</details>

---

## 📚 词典

主词典 `data/dictionary.json` 共 **22,004 条**，优先级从高到低：

`overrides` › `manual` › `site_terms` › `gem_desc` › **编年史** › `mod_plain` › `passive_names` › 社区底稿 › `ninja_terms`

**站点专属词典**（按 `location.hostname` 生效，可覆盖主词典同名键）：`data/host_terms.json` + `data/atlas_terms.json`（620 条 PoE Planner 天赋名与界面文案）、`data/atlas_templates.json`（288 条带 `#` 占位的天赋说明）。PoE Planner 全部 338 条天赋效果 **100% 覆盖**。

| 来源 | 条目 | 内容 |
| --- | ---: | --- |
| 官方交易站词缀统计 | 8,125 | 物品词缀整句、星团珠宝天赋（按 stat id 中英对齐） |
| 流放之路编年史 `/cn` ↔ `/us` | 6,480 | 通货、基底、地图、命运卡、传奇、技能宝石等道具译名 |
| 社区开源汉化脚本（MIT） | 2,952 | 界面文案、规则名、长说明底稿 |
| 编年史宝石详情页 | 1,421 | 技能名 + 静态技能说明 |
| 编年史天赋树 | 1,261 | 关键天赋 / 专精 / 符文嫁接译名 |
| poe.ninja 官方繁中包 | 939 | 物价表列头、筛选器、页面文案（繁转简） |
| FilterBlade 站点文案精翻 | 505 | 赛季说明、Overview 卡片、规则名、FAQ 标题 |
| 人工校对 | 297 | 导航、按钮、严格度、槽位与稀有度组合 |
| 术语纠偏 | 24 | 最高优先级覆写 |

另有 `data/mod_templates.json`（7,830 条带 `#` 数值模板 + 8,175 条整句），运行时按 `#` 回填实际数字。

**PoE Planner 数据链路**：`tools/fetch_poeplanner.py` 从站点 HTML 动态发现 `app.<hash>.js`、从 `versions.json` 动态读取 atlas 数据版本（当前 3.30.0 / v61），下载 `atlastree.bin` 与 `atlastranslations.bin` 提取英文原文；`tools/build_atlas_terms.py` 把编年史 `us / cn / tw` 三版 `Atlas_passive_skill` 页按条目 slug 对齐（简体页 146 条国服译名优先，繁中页补齐全部 352 条），繁转简并做术语纠偏后，与 `data/atlas_ui_manual.json`、`data/atlas_extra.json` 的人工精翻合并。

> 术语口径：编年史称 Unique 为「传奇」，国服与主流社区称「暗金」。本工程默认用**国服口径**；要完全贴合编年史，改 `data/overrides.json` 中 `Unique` / `Uniques` 后重建即可。

---

## 🗂️ 目录结构

```
poe-web-tools/
├── src/
│   ├── engine.js               核心翻译引擎
│   ├── panel.js                悬浮控制面板
│   ├── preview*.template.html  三个离线预览页模板（含 preview-atlas）
│   └── extension/              manifest / popup / icons（图标由 tools/make_icons.py 生成）
├── data/                       词典与构建中间产物
│   ├── site_manual.json        FilterBlade 站点文案主维护文件
│   └── atlas_ui_manual.json / atlas_extra.json   PoE Planner 人工精翻
├── tools/                      抓取 / 合并 / 校验 / 打包脚本
├── tests/                      词典校验 + jsdom 引擎与预览页测试
├── dist/                       可直接使用的交付物（用户脚本 / 扩展 / 三张预览页）
├── AGENTS.md                   给 AI 代理的入口：构建 / 测试 / 硬性规则
├── docs/AI-NOTES.md            ⭐ 试错记录、数据源细节、Bug 回归清单
└── research/                   抓取缓存（可删除，重新抓取即可）
```

---

## 🔄 维护

新赛季更新译名与文案（Python 3.10+）：

```bash
python -m pip install opencc-python-reimplemented

# 1) 重新抓取
python tools/fetch_poedb.py --refresh         # 道具译名
python tools/fetch_site_assets.py --refresh   # FilterBlade 文案源
python tools/fetch_ninja_i18n.py --refresh    # poe.ninja 语言包
python tools/fetch_gem_desc.py --refresh      # 技能名与说明
python tools/fetch_poeplanner.py --refresh    # PoE Planner 素材（版本号 / bundle 名动态读取）
python tools/extract_site_text.py             # 生成未覆盖清单 site_missing.json

# 2) 补词：把清单里的英文按 "英文": "中文" 写进 data/site_manual.json
#    PoE Planner 补词写 data/atlas_ui_manual.json（界面）或 data/atlas_extra.json（天赋效果，键为 # 骨架）

# 3) 构建与打包
python tools/build_ninja_terms.py
python tools/merge_site_terms.py
python tools/build_atlas_terms.py             # 新增：生成 atlas_terms.json / atlas_templates.json
python tools/build_dictionary.py
python tools/build_dist.py
```

**只改少量译名**：编辑 `data/manual_terms.json` / `overrides.json` / `site_manual.json` / `ninja_ui_manual.json` / `atlas_ui_manual.json` / `atlas_extra.json`，然后执行第 3 步的构建命令，无需重新抓网页。

> ⚠️ `data/site_zh_1~3.json` 是按旧清单序号批量填写的历史记录，内容已固化。清单序号会随词典变化，**不要再按序号新增译文**，请直接以英文原文为键。

---

## 🧪 测试

```bash
python tests/check_dictionary.py              # 词典校验
cd tests && npm install jsdom --no-save --no-package-lock
node tests/engine.test.js                     # 引擎（30 项）
node tests/preview.test.js                    # FilterBlade 预览页（17 项）
node tests/ninja.test.js                      # poe.ninja 预览页（57 项）
node tests/atlas.test.js                      # PoE Planner 异界天赋树（33 项）
python tests/check_mcp.py                     # MCP Server 与本地桥（13 项）
```

覆盖精确匹配、短语替换、`#` 模板回填、前缀规则、新赛季长文案、FAQ 标题、中英混排、代码区隔离、Vuetify 图标隔离、站点专属 host 作用域、MutationObserver 动态节点、模式切换与还原、点击交互还原、对照查询等。

---

## ⚖️ 声明

- 本项目是**玩家自制的浏览器端显示层汉化**，不修改任何站点服务器、不修改生成的 `.filter` 文件与 `.bin` 天赋数据，与 Grinding Gear Games、FilterBlade、poe.ninja 及 PoE Planner 官方均无关联。
- 道具与异界天赋译名来自[流放之路编年史](https://poedb.tw/cn/)公开页面（`/us/`、`/cn/`、`/tw/` 三版按条目对齐），权利归原站所有，请仅作个人学习与非商业使用。
- UI 底稿来自 GreasyFork #496758（MIT，Rayforward / GodParadise 公会），已做繁简统一、去重与术语覆盖。
- poe.ninja 译文来自其官方繁體中文语言包，经繁转简与术语校正；本项目不修改其页面、URL 或服务端数据。
- PoE Planner 的英文原文来自站点公开的 `atlastree.bin` / `atlastranslations.bin` 与 `app.js`，仅用于生成本地对照词典，运行时不联网、不请求站点接口。
- 词缀译文来自官方交易站统计接口（`pathofexile.com` 与 `poe.game.qq.com`），权利归 Grinding Gear Games / 腾讯所有。

---

<div align="center">
<sub>遇到问题？先看 <a href="docs/AI-NOTES.md">docs/AI-NOTES.md</a> 的「已修复的典型 Bug」与「数据文件速查」。</sub>
</div>
