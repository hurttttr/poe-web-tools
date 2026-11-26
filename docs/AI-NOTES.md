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

**赛季换新的坑（3.30 Covens 实测）**：物品名来自站点 API 的游戏数据，**不在 Lingui 语言包里**，重抓 i18n 也补不到；每季新物品必须在 `data/ninja_ui_manual.json` 按英文原文人工补列（该文件同时承载界面文案与 ninja 站点专属物品名，只在 ninja 站点注入主词典的 `ninja_terms` 来源里）。译名一律取编年史简体页 `/cn/`，不要用官方繁中的「綢帶」硬转（国服口径是「丝线」）。注意区分同名旧机制：3.29 的 `Memory Strands` 是「记忆丝缕」，3.30 的 `Threads`（替代圣甲虫的新机制）是「丝线」，`Dextral/Sinistral Threads` 从旧一口径「右旋记忆丝缕」改为「右旋/左旋丝线」。抓取时 poe.ninja 主站有 Cloudflare（curl/urllib 全 403），但 `assets.poe.ninja/_astro/*.mjs` 静态资源可直连下载，语言包文件名由脚本从 chunk 动态解析。

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
| poe.ninja 表格列头、时间范围、新赛季物品名（丝线等 API 数据，不在语言包里） | `data/ninja_ui_manual.json` |
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

---

## 8. MCP 操控 FilterBlade（配置层，不模拟点击）

### 8.1 为什么不点 UI

用户嫌 Customizer 层层菜单复杂，想让 MCP 直接操控。§1 已确认站点不开源，但 `research/fb.min.js`（约 1.5 MB）**未混淆**，`FilterBlade.prototype` / `ChangeStorage.prototype` 都可读，因此可以从配置层介入，而不是模拟点击。

三个插入点：模拟 UI 点击（DOM 每赛季易变，且等于把复杂度搬进代码）、改 saveState（官方导入格式）、直接生成 `.filter`（最稳，但失去 FilterBlade「新赛季加载旧存档自动合并改动」的能力）。选第二条。

### 8.2 逆向得到的存档格式

| 位置 | 事实 |
| --- | --- |
| `ChangeStorage.prototype.updateAutoSave` | `localStorage.setItem("ChangeSave:0", JSON.stringify(e))` |
| `simplifySaveStateContent()` | 内层 = `{version:1, filterName, strictness, style, metaData, changeGroups}` |
| `ChangeGroup.prototype.simplifyChangeGroup` | `{presetMetaData, presetDataObj, groupChanges, isHidden, changeGroupVersion:4}`，且会 `delete presetDataObj.saveStateContent` |
| `AbstractChange.prototype.simplifyChange` | 单条 = `{changeType, changeValue}`；`readSimplifiedChange` 也接受 `[changeType, changeValue]` 简写 |
| `BackendFacade.createSimpleSaveStateObject` | 外层 = `{display_name, is_preset, date_modified, saveStateContent:"<内层 JSON 字符串>", meta_json_string, tags}` |
| Advanced → Upload filter | `case "saveFile"` = `JSON.parse → receiveProfileSaveState → updateAutoSave → loadSaveState`，官方自带「喂 JSON 即生效」入口 |
| 分享链接 | `?profile=X&saveState=Y` 是按 ID 从 Lambda 拉取、需登录，**本地造不出来** |
| 全局对象 | 顶层 `var gFilterBlade`，MAIN world 可见；`changeUI.loadAutoSave()` 走同一条路径 |

**关键教训**：`changeValue` 结构随 `changeType`（`tier` / `dynamic` / …）变化，`sanitizeValue` 各子类还不同。不要从 `optionFile` 反向臆造 change，否则会被 `prepareChangeGroups` 静默丢掉。工程上改成「读站点真实存档 → 只做字段级修改 → 整体回写」，格式永远由站点提供；要新建规则，先用 `fb_import_sample` 解析一份官方下载的 save-file 当模板。

### 8.3 桥接架构与两个坑

- MCP Server 是独立进程，**碰不到浏览器标签页**，必须有桥：`MCP(stdio) ↔ HTTP 127.0.0.1:8765 ↔ 扩展 ↔ window.postMessage ↔ MAIN world ↔ gFilterBlade`。
- MV3 三层：`bridge-main.js`（`world: MAIN`，唯一能看到 `gFilterBlade` 的一层）、`bridge-content.js`（ISOLATED，直连本地桥）、`background.js`（service worker，页面直连被 mixed content / CSP 拦下时降级代发，`chrome.alarms` 负责被回收后唤醒）。需 Chrome 111+。
- `loadSaveState` 开头检查 `isCurrentlyLoadingSaveState || getCurrentlyLoadedSaveState()`，重复调用直接 `return false` 并弹「Another filter is already loaded!」。回写前先 `clearStorage(false)` 清标记，并检查返回值 `=== false` 时立刻报错，别等 30 秒超时。
- 配置项索引从 `optionFile*.options` 的 `Section(...)` 抽取（当前 232 项），中文名复用 `dictionary.json` + 少量人工补词；文件名哈希动态发现，不硬编码。

### 8.4 当前能力边界与待验证项

能：读当前配置、改 `strictness` / `style` / 已有 change 的数值、导出官方 save-file、中文检索可配项、解析样本存档。

还不能：凭空新建任意 Customizer 规则（需要模板）；**回写链路 `fb_apply_state` 尚未在真实页面验证**（`clearStorage(false) + loadSaveState` 组合需实测）。读取链路已于 2026-11-15 晚跑通，见 §8.5。

### 8.5 首次实测（2026-11-15 晚）

- 桥接链路跑通：`fb_status` 返回 connected=true，`fb_get_state` 成功返回页面真实存档。MAIN world 对 `gFilterBlade` 可见，https 页面直连 `http://127.0.0.1` 也走通了，未触发 background 降级。
- **`strictness` 不是字符串**，是对象 `{name:"Semi-Strict", isCustom:false, description, version:1}`。用 `fb_apply_state` 改严格度要改 `state.strictness.name`，不要整个替换成字符串。
- `changeValue` 真实形态比预想复杂：`normal` 带 `identifier{identifier,mode,index,version,isReal}` + `newValue` + `items[].utilStats.cName/itemTag`；`conditional` 靠 `entryId` 关联到前面的 `tier add`；向导生成的规则名带 `wizardRule_` 前缀。`metaData.preConfigWizardCampaign` 标记是否走了练级向导。
- 一份向导配方实测 70 条改动：`normal 22 / conditional 39 / tier 6 / multi 1 / progression 1 / progressionAppearance 1`。数量看着吓人，实际只是 4 组语义 —— 总结配方时按 `entryId` / `itemTag` 聚合比逐条读有效得多。
- `displayName` 为 `"Untitled filter"` 时说明是本地未命名配置，不是账号存档；`optionFileVersion` 可能为 null，别依赖它判断页面就绪。

---

## 9. PoE Planner 异界天赋树汉化

### 9.1 站点结构（先摸清楚再动手）

`poeplanner.com/atlas-tree` 是 Vue 2 + Vuetify 的 SPA，HTML 只有 `<div id="app"></div>`，全部文案在两个 JS bundle（`app.<hash>.js` / `chunk-vendors.<hash>.js`）和 CDN 的二进制数据里。

- `app.<hash>.js`：界面文案，Vue 编译后藏在 `_v("...")` 调用里（约 336 条静态文本）。
- `https://cdn.poeplanner.com/json/versions.json`：版本清单，`atlasVersions[0].version` 给出数据目录（本次 61 / PoE 3.30.0）。**注意 `/json/versions.json` 在 poeplanner.com 主域会 fallback 成 index.html，必须走 cdn 子域。**
- `https://cdn.poeplanner.com/bin/<v>/atlastree.bin`：节点数据（坐标 + 字符串表）。
- `https://cdn.poeplanner.com/bin/<v>/atlastranslations.bin`：天赋效果英文原文（338 条，`{0}` 占位）。
- `readTranslations()` 只加载 `passivetreetranslations.bin` 之类的英文翻译表，**站点自己没有中文包**，所以中文必须外部找。

### 9.2 中文数据源：编年史三版按 slug 对齐

这是本次最关键的发现。编年史有 `https://poedb.tw/{us,cn,tw}/Atlas_passive_skill`：

| 版本 | 条目 | 用途 |
| --- | ---: | --- |
| `/us/` | 352 | 英文天赋名 + 英文说明（基准） |
| `/cn/` | 150 | **国服简体译名**，优先采用 |
| `/tw/` | 352 | 繁中，覆盖全部条目，补齐剩余并转简 |

每张卡片形如 `<a class="PassiveSkills" href="Slug">Name</a>` + 若干 `<div class="implicitMod">说明</div>`，**href 的 slug 是英文的、跨语言一致**，所以按 slug 对齐，绝不按页面顺序配对（cn 与 us 顺序完全不同）。

术语口径：`cn` 给「未行之路」「隐秘跳跃点」「毁灭游戏」，`tw` 给「未履之道路」「神秘大门」，差异明显。构建脚本优先 cn，tw 补齐，再做繁转简 + 术语纠偏（精髓→精华、裂痕→裂隙、綢帶→记忆丝缕、頭目→首领…），并把台服语序「增加#%…」改成「#% 提高…」。

### 9.3 二进制字符串提取

`atlastranslations.bin` 是「长度/标记字节 + NUL 结尾字符串」混合结构。用 `[ -~]{4,}` 正则直接抓会把前面的长度字节吞进正文（出现 `&#% chance...`、`=Immortal Syndicate...` 这类脏键）。

**正确做法**：按 `\x00` 切分，每段解码 ASCII 后从第一个字母或 `{` 开始截取。这样得到干净的 338 条效果描述。

### 9.4 三个必须同时处理的坑

1. **`#` 骨架的两套形态**：说明里的数字在 poeplanner 是 `{0}`、在编年史是实际值（如 `4%`）。统一 `数字 / {0} → #` 后比较，且**中英 `#` 数量必须一致**，否则丢弃（宁可保持英文）。覆盖率报告也要先把连续空白折成单空格，对齐引擎 `normalize()`。
2. **跨行说明**：bin 把一段说明拆成多行（如 Maven 的赌注加码 5 行）。DOM 里既可能是多个文本节点，也可能是一个含换行的节点。所以词典里要**同时有逐行片段译文和拼接后的整串译文**。构建脚本自动按行查 `atlas_extra.json` 拼接，本次合并出 24 条，覆盖率从 92.9% 提到 100%。
3. **Vuetify 图标 ligature**：`<i class="v-icon material-icons">expand_more</i>` 靠文本内容渲染图标。翻译它会让图标直接消失。引擎 `SKIP_SELECTOR` 加了 `.v-icon,.material-icons,[class*="v-icon"]`，构建脚本另设 `ICON_LIGATURES` 黑名单过滤 `folder` / `warning` / `search` 等小写图标词。**双保险，缺一不可**。

### 9.5 站点专属作用域，而不是塞进主词典

- 整句词条（635 条）写进 `atlas_terms.json`，由 `build_dist.py` 以 `{"poeplanner.com": {...}}` 注入 `FBZH_HOST_DICT`。引擎 `buildIndex()` 后处理 host 词条，因此**可以覆盖主词典同名键**：主词典 `Clear=清澈`（物品词缀语境），PoE Planner 用 `Clear=清除`；其他站点不受影响。
- 带数值的模板（289 条）合并进 `FBZH_MOD_TPL`，但**只补现有词典没有的骨架**（`setdefault`），因为模板表是全局的，覆盖会伤到 FilterBlade。
- `# 模板` 是全局表而 `host_terms` 是站点表的这个不对称，是刻意设计：模板键本身已经高度特化（句子级），撞车概率极低。

### 9.6 统计栏为什么一直是英文（整行翻译）

右侧 Pinned / Cumulative Stats 的文案来自 `getTextsForStatValues(stats, "textAugmented")`：站点在 `getTextForValues()` 里把每个数值包成 `<span class="textAugmented">8%</span>`，再 `v-html` 塞进列表项。于是**一条说明被切成多个文本节点**：

```
"Your Maps have " + <span>8%</span> + " chance to be inhabited by a Mercenary"
```

逐文本节点查词典必然全部落空（左边半句、中间 `8%`、右边半句都不成句）。修法是引擎新增「整行级」翻译 `translateInlineLine()`：

1. 只处理「子元素全是行内标签」的容器（`LINE_TAGS`），且子元素数量 ≤ 12、整行长度 ≤ 240；
2. 含 `a/button/input/svg/img/.v-icon/.fbzh-ui` 的容器直接跳过（`LINE_BLOCKERS`），否则会把交互 / 图标 / 我们自己的面板一起抹掉；
3. 用 `textContent` 拼回整行再查词典 / `#` 模板，命中才改写；
4. 改写时把译文里同位置的数值按原 span 的 class 重新包回去，**数值高亮不丢**；
5. 存 `innerHTML` 到 `lineOriginal`，原文模式 / 点击交互时还原；存 `lineApplied` 判断站点是否重渲染过（`v-html` 刷新后要重新翻）。

配套改动：MutationObserver 的 `childList` 记录现在把 `rec.target`（被替换的容器）也纳入重扫，否则新增的子节点是文本 / `<span>`，容器本身永远不会被重新检查；`characterData` 记录也带上 `parentElement`。

### 9.7 中文搜索：只喂英文，不动站点

站点搜索实现是 `setSearchString(e) → treeRenderState.searchText → new RegExp(searchText, 'i')`，然后用这个正则去 `getNodeName()` / `getNodeText()`（都是英文）上测。输入中文永远匹配不到 —— 这**不是词典缺词**，改词典没用。

`src/atlas-search.js` 的做法：在站点搜索框上叠一个自己的输入框（隐藏原 input，但保留其尺寸用于对齐），用户输入中文时：

1. 用 `data/atlas_search.json`（英文节点名 → 中文名 / 中文说明，数字统一成 `#`）反查命中的英文节点名；
2. 拼成 `(?:NameA|NameB|…)` 写进站点真正的 input（`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set` + 派发 `input`），站点照旧用它的正则高亮；
3. 英文输入原样透传，站点行为不变；
4. 无命中时喂 `(?!)`（永不匹配），并提示「没有匹配的天赋节点」。

注意几个坑：`#` 与数字都要当成 `\d[\d,]*`（词典里数值是 `#` 占位）；节点名里的 `'` `,` `-` 必须转义；叠层 input 要带 `.fbzh-ui` / `data-fbzh-skip`，否则引擎会去翻它、交互保护也会误触发；站点重渲染换掉 input 时靠 `field.isConnected` + 定时 `syncBox()` 重新绑定。

### 9.8 已知边界

- 天赋树本体是 canvas / WebGL，节点名与说明只在悬浮提示（DOM）里，DOM 注入能覆盖。
- 中文搜索按「节点名 + 该节点说明」匹配后**高亮整个节点**，做不到在说明文本里做局部高亮；也只覆盖 `/atlas-tree` 页面。
- 整行翻译会把容器的子节点合成纯文本（数值按原 class 包回），如果站点依赖行内节点结构做样式以外的逻辑，需先确认再放行。

### 9.9 离线预览页的一个测试陷阱

预览页把整份词典内联在 `<script>` 里，`document.body.textContent` **包含词典 JSON 文本**。用它做断言会出现假阳性（词典里本来就有中文）和假阴性（切原文模式后 `Collapse all` 仍能在词典里找到）。测试必须先 clone body、移除 `script/style/noscript/.fbzh-ui` 再取 `textContent`。本次差点被这个坑误导。

