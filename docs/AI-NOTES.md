# AI-NOTES · 试错记录与工程经验

> 本文是 [AGENTS.md](../AGENTS.md) 的延伸阅读：AGENTS.md 只放每次会话都要遵守的命令与硬性规则，这里放**为什么这么做、哪里踩过坑、以及完整的数据源细节**。
> README 讲「怎么用」，AGENTS.md 讲「必须怎么做」，本文讲「当初怎么试出来的」。
> 动 `src/engine.js`、`tools/*.py` 或词典数据之前先读本文；改完请把新踩的坑补到第 4、5 节。

---

## 1. 方案决策：为什么选运行时 DOM 注入

FilterBlade 官方 FAQ 给出两条关键事实：

- 站点**不开源，且明确不会开源**（只有过滤器本身和少量 Public Assets 开源）；
- 前端是托管在 S3 / CloudFront 的**纯静态 vanilla JS/HTML/CSS**，界面由自有领域语言 `.exo` 动态生成，后端是 AWS Lambda。

| 路线 | 结论 |
| --- | --- |
| Fork 源码加 i18n | ❌ 没有源码 |
| 本地代理 / 镜像站点改写静态资源 | ⚠️ 能做，但要维护代理、处理 CDN 与版本参数，用户每次都得走代理，太重 |
| **浏览器端运行时 DOM 注入** | ✅ 最快落地、不改服务端、随开随用、可一键还原 |

社区已有同类脚本，但普遍有两个痛点，本工程针对性解决了：

1. **词典可复现、可随赛季更新**：不手抄静态表，而是脚本抓编年史 `/cn/` 与 `/us/` 页面，按条目链接 slug 自动对齐。
2. **不破坏站点功能**：站点部分交互会读按钮 `innerText` 当基底名，翻成中文会报错。本方案在事件捕获阶段把相关容器临时还原为英文，站点逻辑始终读到原文，事件结束再恢复。

poe.ninja 同为客户端动态渲染，且官方**只有繁體中文、没有简体**，因此复用同一套引擎和同一个扩展，只换词典来源（见 3.3）；扩展用 `content_scripts` 匹配两个域名，popup 负责站点跳转。

---

## 2. 引擎设计约束（最容易踩坑的地方）

| 约束 | 原因 / 做法 |
| --- | --- |
| **交互瞬间还原英文** | 站点逻辑读 `innerText`。在 `mousedown` / 捕获阶段把容器还原英文，`mouseup` / 事件结束后恢复中文 |
| **过滤器语法关键字必须黑名单** | `Show` / `Hide` / `Class` / `BaseType` / `SetFontSize` 等被翻译后会改写生成规则。清单见 `data/stoplist.json` |
| **`Class` 的语义冲突** | poe.ninja 里是表头「职业」，FilterBlade 里是过滤器关键字。用 `data/host_terms.json`（→ `window.FBZH_HOST_DICT`）按域名并入，互不污染 |
| **中英混排不能整段跳过** | 早期遇到 `1000x Gold`、`亡者硫磺，Ducats …` 整段跳过，现在只替换其中的英文片段 |
| **短词需要受控白名单** | 数字＋英文等场景无法靠空格短语命中，用 `data/short_words.json`；刻意不含 `Tier` / `Class` / `Show` / `Hide` |
| **长段落按文本节点整段匹配** | 上限放宽到 1200 字符；`<hr>` 切分后的句子各自独立命中 |
| **数字占位符失败宁可保留英文** | 英文与中文模板的 `#` 数量不一致会错位，构建阶段直接丢弃；运行时骨架不匹配时输出原文，不输出错位译文 |
| **骨架统一小写** | 兼容站点 `per second` / `per Second` 混用 |
| **随机词根名字不翻** | 稀有装备 / 珠宝名（如 `Loathe Spark`）由词根随机拼接，中文客户端同样拼词根，硬译更难认 |

前缀规则：`Allocates Avatar of Fire → 配置 火之化身` 这类「固定前缀 + 名字」由 `data/mod_manual.json` 的 `prefix` 段处理，剩余部分继续走词典 / 短语替换。

---

## 3. 词典构建：数据源与各自的坑

最终词典 `data/dictionary.json` 共 **22,004 条**（统计见 `data/dictionary.meta.json`）。

**优先级**：`overrides` > `manual` > `site_terms`（FilterBlade 原文精翻） > `gem_desc` > **编年史** > `mod_plain` > `passive_names` > 社区 UI 底稿 > `ninja_terms`。

### 3.1 编年史对齐（道具译名）

对齐方式：`cn/Stackable_Currency` 的链接 `Chaos_Orb` 文本是「混沌石」，`us/Stackable_Currency` 同一链接文本是 `Chaos Orb` → 生成 `Chaos Orb → 混沌石`。抓取 80 个分类页、13,114 条对齐记录，去重后 8,316 条，最终并入 6,480 条。

### 3.2 站点文案（单靠词典补不齐）

第一版以「编年史道具名 + 社区 UI 底稿」为主，3.29（Allflame）新赛季出现明显缺口：整段说明、全大写分区标题、`Current League: 3.29 Allflame`、`Search (Ctrl + K)`、`EXPORT` / `DISCORD` 等仍是英文。

**经验：不要照截图手抄，直接抓站点真实文案源。**

| 文件 | 内容 |
| --- | --- |
| `datafiles/optionfiles/StyleSummary.options` | Overview / Start 页的分区标题、说明、信息框 |
| `datafiles/optionfiles/optionFile*.options` | Customizer 规则名与说明（文件名哈希随版本变，脚本自动发现） |
| `datafiles/weighting/LootGenerator.options` | 掉落模拟器 |
| `datafiles_Shared/faqContent.json` | FAQ 的 questionList（78 个问题） |
| `datafiles/other/newsFile.txt`、`economies.json`、`index.html`、`filterblade.min.js` | 公告、经济组、静态 UI |

`extract_site_text.py` 会按 `<hr>` / HTML 标签切分（站点就是这么把文本拆成 DOM 节点的），生成未覆盖清单 `data/site_missing.json`。人工精翻 512 条（含 78 个 FAQ 问题标题），累积库在 `data/site_manual.json`（**英文原文 → 中文**，稳定不依赖序号）。

新赛季术语按编年史 / 国服口径：`Allflame League → 不灭余烬联盟`、`Vestigial Uniques → 残遗暗金`、`Coral Reef Chart → 珊瑚礁海图`、`Enshrouding Crystals → 笼罩水晶`、`Ducats → 杜卡特`、`Regal Orb → 富豪石`、`Gemcutter's Prism → 宝石匠的棱镜`。

### 3.3 poe.ninja 汉化（只有繁中）

2026-10 poe.ninja 上线 10 种语言，但只有繁體中文，译名也不完全贴合编年史。**没有**用「自动跳官方繁中版」这种改 URL 的做法，而是把官方译文转成简中词条，继续走同一套注入引擎：

1. `fetch_ninja_i18n.py` 遍历 26 个主要路由、递归下载 516 个 Astro 模块，从 Lingui 运行时定位繁中语言包（`a.DrpfQUYW.mjs`，2,180 条 id）；
2. `build_ninja_terms.py` 提取 `{id: ..., message: "English"}`，按 id 与繁中译文配对（1,083 条纯文本），再叠加英文页 / 繁中页 SSR 文本节点对齐（43 条）；
3. OpenCC 繁转简 + 台湾用语→大陆用语（资料→数据、连结→链接、登入→登录、刊登→挂单）+ 术语校正（传奇→暗金、舆图→异界）+ `ninja_ui_manual.json` 人工补列头（`Chaos Value → 混沌石价值`、`Listings → 挂单量`、`Divine Value → 神圣石价值`）；
4. 生成的 `ninja_terms.json` 以**最低优先级**并入，编年史译名始终优先；物品 / 通货 / 技能名复用编年史词条。

### 3.4 宝石技能名与说明（一个正则 bug）

流派页左侧「物品 + 主要技能」不是界面文案，是游戏数据，UI 词典翻不到，单独补两块：

- **技能名**：编年史宝石页用**绝对路径** `/us/Righteous_Fire`，旧正则只认相对路径，导致 620 个技能全部漏抓。修正后重抓：技能宝石 620、辅助宝石 311、变异宝石 230。
- **技能说明**：`fetch_gem_desc.py` 抓 815 个详情页，取 `og:description` 的**静态描述短句**（不含数值，适合整串精确匹配），中英对齐 1,421 条。

**教训：抓取结果为 0 时先怀疑选择器/正则，不要以为是站点改版。**

### 3.5 交易站词缀（带随机数值）

`Adds 5 Passive Skills`、`+3% to Fire Resistance` 数值每条都不同，穷举不现实。做法是**数据侧统一 `#` 占位**，运行时回填：

```
EN 模板  Adds # Passive Skills   →  CN 模板  增加 # 个天赋技能
实际文本 Adds 5 Passive Skills   →  译文     增加 5 个天赋技能
```

- 来源：`tools/fetch_trade_stats.py` 抓 `pathofexile.com/api/trade/data/stats` 与 `poe.game.qq.com/api/trade/data/stats`，**按 stat id 对齐**得到 17,503 条（国服简体，官方口径）；`build_mod_templates.py` 并入编年史星团珠宝总览页 879 行天赋词缀，排除 `pseudo` / `mercenary` 分组。
- 产物：带 `#` 的进 `templates`（7,830 条），不带的整句进 `plain`（8,175 条，同时并入主词典参与精确匹配）。
- 手写补充：`Requires Level # → 需求 等级 #`、珠宝插槽说明、`1 Added Passive Skill is a Jewel Socket` 等接口没有的行，写在 `data/mod_manual.json`。

### 3.6 天赋 / 专精 / 符文嫁接（配对最难）

这些数据既不在站点文案里，也不在交易站词缀里，前几轮完全覆盖不到。

| 环节 | 说明 |
| --- | --- |
| 英文原文 | 编年史天赋树 `https://poedb.tw/data/passive-skill-tree/<版本>/data_us.json`，版本号从脚本里读，**不写死**。它是官方客户端数据，与游戏内 / poe.ninja 一致 |
| 中文译文 | 编年史 `/cn/Keystone`、`/cn/Notable`、`/cn/Runegraft` 与 `/cn/<专精名>_Mastery` |
| 配对难点 | ① 编年史用 `<br>` 折断长词缀，行数与官方不一致；② 中文页偶尔缺行，按顺序硬配会整体错位 |
| 配对策略 | 先试「官方行数 == 中文行数」顺序配对；再把折行（下一行小写开头）合并重试；仍不行才按英文相似度贪心配对，且要求中英数字至少一个交集，否则丢弃（防止配成无关句子） |
| 数值处理 | 天赋数值固定，优先存「带真实数值的整句」；只有中英数字顺序完全一致时才额外存 `#` 模板，避免「10% more … 至少 6 个」这类语序导致填错位 |
| 覆盖率 | 天赋树 2,269 行说明 98%+ 整句命中；专精 61 组 / 394 行、关键天赋 72 条、符文嫁接 32 条 |

典型修复：`30% more Spell Damage when on Low Life → 低血时法术伤害总增 30%`；`8% increased Damage for each of your Aura or Herald Skills affecting you → 伤害按照你身上每种影响你的光环或捷提高 8%`。

### 3.7 质量控制

- 编年史与社区底稿有 **59 条译名冲突，全部采用编年史**（清单 `data/conflicts.json`；`dictionary.meta.json` 里 `conflicts_poedb_vs_community: 95` 是检测数，口径不同）。
- 繁体 / 异体统一 **315 条**（OpenCC t2s），最终词典繁体残留 0。
- 剔除 **52 个过滤器语法关键字**（实际构建过滤 27 条）。
- 校验：键不含中文、译名含中文、无代码字符、16 条关键术语断言。
- 术语口径：编年史称 Unique 为「传奇」，国服与主流社区称「暗金」。本工程默认用国服口径；要贴合编年史就改 `data/overrides.json` 里 `Unique` / `Uniques` 后重建。

---

## 4. 已修复的典型 Bug（回归清单）

1. **宝石页链接正则**只认相对路径 → 620 个技能全部漏抓。
2. **中英混排整段跳过** → 改为只替换英文片段。
3. **`per second` / `per Second`** 大小写导致模板不命中 → 骨架统一小写。
4. **`#` 数量不一致**导致数值错位 → 构建期丢弃，运行时兜底保留英文。
5. **`Class` 被当过滤器关键字**，poe.ninja 表头翻不出来 → `host_terms.json` 按域名生效。
6. **`site_zh_1~3.json` 按清单序号填写**：序号随词典变化，已废弃，**不要再按序号补词**。
7. **天赋中文页缺行**导致顺序配对整体错位 → 折行合并 + 数字交集校验。
8. **扩展路径失效**：项目文件夹改名 / 移动后，Chrome 记录的路径失效，需在扩展页移除后重新加载 `dist/extension`。

---

## 5. 维护 Do & Don't

**Do**

- 补词一律以**英文原文为键**写进 `data/site_manual.json`（或 `data/site_extra.json`），不要用清单序号。
- 改少量译名后跑：`build_ninja_terms.py` → `merge_site_terms.py` → `build_dictionary.py` → `build_dist.py`；不必重新抓网页。
- 词典条数、覆盖率等数字变化后，同步更新 README 与 `data/dictionary.meta.json`。
- 新增站点专属词先判断是否会被另一站点误用，必要时走 `host_terms.json`。
- 改引擎后至少跑 `engine.test.js` + 两个预览页测试。

**Don't**

- 不要把过滤器语法关键字加进任何词典 / 短词白名单。
- 不要手改 `dist/` 下的产物（会被 `build_dist.py` 覆盖）。
- 不要把带 `#` 但中英数量不一致的模板合进数据。
- 不要硬编码赛季版本号、`.options` 文件名哈希、天赋树版本号。
- 不要把 `research/` 下的抓取缓存当成数据源（可随时删除重抓）。

---

## 6. 数据文件速查：该改哪个

| 想改什么 | 改这里 |
| --- | --- |
| 单个术语纠偏（最高优先级） | `data/overrides.json` |
| 界面常用词、槽位、稀有度组合 | `data/manual_terms.json` |
| 站点长文案 / FAQ 标题 | `data/site_manual.json`（主维护文件） |
| poe.ninja 表格列头、时间范围 | `data/ninja_ui_manual.json` |
| 词缀模板 / 前缀规则 / 珠宝说明 | `data/mod_manual.json` |
| 过滤器关键字黑名单 | `data/stoplist.json` |
| 中英混排短词白名单 | `data/short_words.json` |
| 站点专属词条 | `data/host_terms.json` |
| 重新抓取的数据（自动生成，勿手改） | `poedb_items` / `gem_desc` / `mod_templates` / `passive_terms` / `ninja_terms` / `dictionary` |

---

## 7. 环境与已知边界

- Python 3.10+，需 `opencc-python-reimplemented`；测试需 `jsdom`（`cd tests && npm install jsdom --no-save --no-package-lock`）。
- `research/` 是抓取缓存与来源样本，已被 `.gitignore` 忽略大部分内容，可删除。
- 仍可能看到英文：FAQ **答案长段落**（innerHTML + `<br>` / `<li>` 碎片，只翻了问题标题）、实时拼接的动态文案（如 `Current League: 3.30 …`）、流派页**装备词缀明细**（逐条随机数值命中率低）、未收录的新物品名。用面板「导出未译文本」拿清单继续补。
- 不翻译：`<script>` / `<style>` / `<textarea>` / `<pre>` / `<code>` / 代码块、输入框 value、下拉选项、广告 iframe、过滤器语法。
