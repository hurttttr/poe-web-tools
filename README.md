# PoE Web Tools · 流放之路网页工具（FilterBlade / poe.ninja）

> 项目代号 `poe-web-tools`：一个浏览器扩展 / 油猴脚本，管住流放之路常用网页。

一个扩展管两个流放之路常用网站：**FilterBlade**（<https://www.filterblade.xyz/?game=Poe1>）与 **poe.ninja**（<https://poe.ninja/>）。技术路线是**离线词典 + 浏览器端运行时注入**，交付物包括油猴脚本、Chrome/Edge 扩展（固定到工具栏后可在两个站点间跳转）、以及两个站点的离线预览页。

扩展固定到浏览器工具栏后，点击图标会弹出「站点快捷跳转」：FilterBlade / poe.ninja 两个卡片，点击在新标签打开；勾选「在当前标签跳转」则直接切换当前页面。下方仍是汉化开关、中文 / 双语 / 原文模式与统计。

---

## 一、方案怎么定的

先查了 FilterBlade 官方 FAQ，两条事实决定了实现方式：

- 站点**不开源，且明确表示不会开源**（只有过滤器本身和少量 Public Assets 开源）；
- 前端是托管在 S3/CloudFront 上的**纯静态 vanilla JS/HTML/CSS**，界面由自有领域语言（`.exo`）动态生成，后端是 AWS Lambda。

因此可选路线只有：

| 路线 | 结论 |
| --- | --- |
| Fork 源码加 i18n | 不可行，没有源码 |
| 本地代理 / 镜像站点改写静态资源 | 能做成，但要维护代理、处理 CDN 与版本参数，且用户每次都要走代理，太重 |
| **浏览器端运行时 DOM 注入** | ✅ 最快落地、不改服务端、随开随用、可一键还原，也符合社区已有实践 |

最终采用第三种，并针对社区脚本常见的两个痛点做了工程化处理：

1. **词典可复现、可随赛季更新**：不是手抄一份静态表，而是写脚本抓取编年史 `/cn/`（简中）与 `/us/`（英文）页面，按条目链接 slug 自动对齐生成对照表。
2. **不破坏站点功能**：站点部分交互会读取按钮 `innerText` 当物品基底名，翻成中文会报错。本方案在事件捕获阶段把相关容器临时还原为英文，站点逻辑读到的始终是原文，事件结束后自动恢复中文；同时提供「原文 / 双语」模式与中英对照查询，方便站内搜索。

poe.ninja 同为客户端动态渲染站点，且官方只提供繁體中文、没有简体，因此沿用**同一套引擎与同一个扩展**，只换词典来源（见「二·补2」）；扩展侧用一个 `content_scripts` 匹配两个域名，popup 负责站点跳转。

---

## 二、词典从哪来

最终词典 `data/dictionary.json` 共 **22004 条**，构建优先级：`overrides` > `manual` > `site_terms`（FilterBlade 原文精翻） > `gem_desc`（技能名与技能说明） > **编年史** > `mod_plain`（官方词缀 / 天赋整句） > `passive_names`（天赋树名称） > 社区 UI 底稿 > `ninja_terms`（poe.ninja 官方译文转简）。

另有一份 **`data/mod_templates.json`（7830 条带数值模板 + 8175 条整句）** 不参与整串匹配，由引擎按 `#` 占位回填实际数字，详见「二·补4」「二·补5」。

| 来源 | 条目 | 用途 |
| --- | --- | --- |
| 流放之路编年史 `poedb.tw/cn` 与 `/us` 对齐 | 7455 | 通货、基底、地图、命运卡、传奇、**技能/辅助宝石**、赛季物品等**道具译名**，简体中文 |
| `data/gem_desc.json` 编年史宝石详情页 `og:title` / `og:description` 对齐 | 1421 | **技能名 + 技能说明**（815 个宝石的静态描述短句），流派页技能提示直接命中 |
| 社区开源汉化脚本（GreasyFork #496758，MIT，Rayforward / GodParadise 公会） | 3687 | 界面文案、规则名、长说明的底稿 |
| `data/ninja_terms.json` poe.ninja 官方译文转简 | 942 | 物价表列头、筛选器、流派/天赋/图鉴页面文案、导航与页脚 |
| `data/site_terms.json` FilterBlade 静态文案精翻 | 505 | 3.29 新赛季说明、Overview 卡片、Customizer 规则名、首页 UI、FAQ 问题标题 |
| `data/manual_terms.json` 人工校对 | 297 | 导航、按钮、严格度、属性术语，**装备槽位 / 稀有度组合 / 宝石标签**，按编年史/国服口径统一 |
| 官方交易站词缀统计（`pathofexile.com` ↔ `poe.game.qq.com` 按 stat id 对齐） | 6432 | **物品词缀整句**与**星团珠宝天赋描述**，走精确匹配 |
| `data/overrides.json` | 24 | 最高优先级术语纠偏 |

对齐方式示例：`cn/Stackable_Currency` 的链接 `Chaos_Orb` 文本是「混沌石」，`us/Stackable_Currency` 同一链接文本是 `Chaos Orb` → 生成 `Chaos Orb → 混沌石`。共抓取 80 个分类页、13114 条对齐记录，去重后 8316 条。

构建时的质量控制：

- 编年史与社区底稿有 **59 条译名冲突，全部采用编年史**（清单见 `data/conflicts.json`，例如 `Rune Daggers → 符纹匕首`）；
- 繁体/异体统一 **315 条**（OpenCC t2s），最终词典繁体残留 0 条；
- 剔除 **52 个过滤器语法关键字**（`Show` / `Hide` / `Class` / `BaseType` / `SetFontSize` …），代码块与规则匹配不会被改写；
- 校验覆盖：键不含中文、译名含中文、无代码字符、16 条关键术语断言。

> 术语口径：编年史简中把 Unique 称作「传奇」，国服官方与主流中文社区称「暗金」。本工程默认采用国服习惯（暗金 / 暗金物品）。若要完全贴合编年史，把 `data/overrides.json` 里 `Unique`、`Uniques` 改成「传奇 / 传奇物品」，重新执行构建即可。

### 二·补　站点界面文案是怎么补齐的

第一版词典以「编年史道具名 + 社区 UI 底稿」为主，遇到 3.29 新赛季（Allflame）就出现明显缺口：卡片里的整段说明、全大写分区标题、`Current League: 3.29 Allflame`、`Search (Ctrl + K)`、`EXPORT` / `DISCORD` / `REPORT AN ISSUE` 等仍是英文。

于是直接从站点**真实文案源**抓取，而不是照截图手抄：

| 文件 | 内容 |
| --- | --- |
| `datafiles/optionfiles/StyleSummary.options` | Overview / Start 页的分区标题、说明、信息框（截图里那几段英文全在这里） |
| `datafiles/optionfiles/optionFile*.options` | Customizer 的规则名与说明（文件名哈希随版本变，脚本自动发现） |
| `datafiles/weighting/LootGenerator.options` | 掉落模拟器 |
| `datafiles_Shared/faqContent.json` | FAQ 的 questionList（78 个问题） |
| `datafiles/other/newsFile.txt`、`economies.json`、`index.html`、`filterblade.min.js` | 公告、经济组、静态 UI |

`extract_site_text.py` 会按 `<hr>` / HTML 标签切分（站点就是这么把文本拆成 DOM 节点的），生成未覆盖清单 `data/site_missing.json`。本轮人工精翻 **512 条**（含 78 个 FAQ 问题标题），累积库在 `data/site_manual.json`（英文原文 → 中文，稳定不依赖序号）。

新赛季术语按编年史/国服口径统一：`Allflame League → 不灭余烬联盟`、`Vestigial Uniques → 残遗暗金`、`Coral Reef Chart → 珊瑚礁海图`、`Enshrouding Crystals → 笼罩水晶`、`Ducats → 杜卡特`、`Regal Orb → 富豪石`、`Gemcutter's Prism → 宝石匠的棱镜`。

同时修了三个引擎问题：

1. **中英混排文本**原先整段跳过（`1000x Gold`、`亡者硫磺，Ducats …`），现在只替换其中的英文部分；
2. 增加**受控短词白名单**（`data/short_words.json`），处理数字＋英文等无法靠空格短语命中的情况；刻意不包含 `Tier` / `Class` / `Show` / `Hide` 等会被站点逻辑读取或属于过滤语法的词；
3. 长段落按 DOM 文本节点整段精确匹配，上限放宽到 1200 字符；`<hr>` 切分后的句子也能各自命中。

### 二·补2　poe.ninja 是怎么汉化的

poe.ninja 在 2026-10 上线了 10 种语言，但**只有繁體中文、没有简体**，译名也不完全贴合编年史。所以没有采用「自动跳到官方繁中版」这种会改 URL 的做法，而是把官方译文**转成简中词条**，继续用同一套 DOM 注入引擎：

1. `fetch_ninja_i18n.py` 遍历 26 个主要路由、递归下载 516 个 Astro 模块，并从 Lingui 运行时定位繁中语言包（`a.DrpfQUYW.mjs`，2180 条 id）；
2. `build_ninja_terms.py` 从模块里提取 `{id: ..., message: "English"}`，按 id 与繁中译文配对（1083 条纯文本），再叠加英文页/繁中页 SSR 文本节点对齐（43 条）；
3. OpenCC 繁转简 + 台湾用语→大陆用语（资料→数据、连结→链接、登入→登录、刊登→挂单…）+ 术语校正（传奇→暗金、舆图→异界）+ `ninja_ui_manual.json` 人工补的表格列头（`Chaos Value → 混沌石价值`、`Listings → 挂单量`、`Divine Value → 神圣石价值`）；
4. 生成的 `ninja_terms.json` 以**最低优先级**并入主词典，编年史译名始终优先；物品名/通货名/技能名则复用编年史词条。

因此 poe.ninja 的物价表、物品名、流派数据会显示中文，界面列头与导航也是中文；`Show`/`Hide`/`Class` 等语法关键字默认按黑名单剔除，只对确实需要翻译的站点用 `host_terms.json` 定向放开。

### 二·补3　流派页（Builds）的装备与技能

流派页左侧是「物品 + 主要技能」，这些不是界面文案，而是**游戏数据**，靠 UI 词典翻不到，所以单独补了两块：

| 内容 | 来源 | 做法 |
| --- | --- | --- |
| 装备槽位与稀有度标签 | `data/manual_terms.json` | 站点把稀有度与槽位拼成一个标签（`Rare Helmet`、`Magic Flask`），因此同时收录**单词**（`Helmet → 头部`）与**组合**（`Rare Helmet → 稀有头部`），两种 DOM 结构都能命中 |
| 装备提示语 | 同上 | 提示是模板句 `Character is using any {itemName}.`，变量被渲染成独立节点，因此按前缀 `Character is using any → 角色使用任意` 翻译 |
| 技能名 | `data/poedb_items.json` | 修正编年史链接正则（宝石页用绝对路径 `/us/Righteous_Fire`，旧规则只认相对路径，导致 620 个技能全部漏抓）后重新抓取，技能宝石 620、辅助宝石 311、变异宝石 230 |
| 技能说明 | `data/gem_desc.json` | `fetch_gem_desc.py` 抓 815 个宝石详情页，取 `og:description` 的**静态描述短句**（不含数值，正适合整串精确匹配），中英对齐 1421 条 |

装备名本身（暗金名、基底名）沿用编年史词条，例如 `Kaom's Heart → 冈姆的壮志`、`Chaos Inoculation → 异灵之体`。

另外，`Class` 这类词在两个站点语义相反：poe.ninja 是表头「职业」，FilterBlade 里却是过滤器语法关键字（已进黑名单）。为此引擎支持**按域名生效的站点专属词条**（`data/host_terms.json` → `window.FBZH_HOST_DICT`），只在匹配的 host 下并入索引，不会污染另一站点。

### 二·补4　物品词缀与珠宝提示（带随机数值）

物品提示框里的词缀不是固定文案：`Adds 5 Passive Skills`、`+3% to Fire Resistance`、`Regenerate 0.15% of Life per Second` 每条数值都不一样，穷举不现实。做法是让**数据侧统一用 `#` 占位**，运行时把英文里的实际数字按顺序填回中文：

```
EN 模板  Adds # Passive Skills                ->  CN 模板  增加 # 个天赋技能
实际文本 Adds 5 Passive Skills                ->  译文     增加 5 个天赋技能
```

| 环节 | 说明 |
| --- | --- |
| 数据来源 | `tools/fetch_trade_stats.py` 抓 `pathofexile.com/api/trade/data/stats` 与 `poe.game.qq.com/api/trade/data/stats`，**按 stat id 对齐**得到 17503 条中英对照（国服简体，已是官方口径）；`tools/build_mod_templates.py` 再并入编年史星团珠宝总览页 879 行天赋词缀（如 `Endbringer`、`Empowered Envoy`），排除 `pseudo` / `mercenary` 分组 |
| 模板要求 | 英文与中文的 `#` 数量必须一致，否则运行时会错位，构建阶段直接丢弃 |
| 引擎实现 | 把文本里的数字统一换成 `#` 得到「骨架」，用 `Map<骨架, 模板>` 一次查表；骨架统一转小写，兼容站点把 `per second` 写成 `per Second`；占位符与数字个数不一致时**宁可保持英文**也不输出错位译文 |
| 前缀规则 | `Allocates Avatar of Fire → 配置 火之化身` 这类「固定前缀 + 名字」由 `data/mod_manual.json` 的 `prefix` 段处理，剩余部分继续走词典 / 短语替换 |
| 手写补充 | `Requires Level # → 需求 等级 #`、珠宝插槽说明段落、`1 Added Passive Skill is a Jewel Socket` 等交易站接口里没有的行，写在 `data/mod_manual.json` |

优先级：`mod_manual` > 编年史天赋页 > 交易站词缀统计。带 `#` 的进 `templates`，不带的整句进 `plain`（同时并入主词典，参与精确匹配）。

> 说明：稀有装备 / 珠宝的**名字**（如 `Loathe Spark`）是随机词根拼出来的，保留英文（中文客户端同样按词根拼，硬译反而更难认）。

### 二·补5　天赋 / 专精 / 符文嫁接说明

poe.ninja 流派页的**天赋提示框**（关键天赋、专精、符文嫁接）走的是游戏内的天赋数据，既不在站点界面文案里，也不在官方交易站词缀统计里（这些东西不能用来搜装备），所以前几轮的词典完全覆盖不到。

| 环节 | 说明 |
| --- | --- |
| 英文原文 | 编年史天赋树数据 `https://poedb.tw/data/passive-skill-tree/<版本>/data_us.json`（版本号从 `passive-skill-tree` 的脚本里读，不写死）。它是官方客户端数据，文本与游戏内 / poe.ninja 显示完全一致 |
| 中文译文 | 编年史 `/cn/Keystone`、`/cn/Notable`、`/cn/Runegraft` 与 `/cn/<专精名>_Mastery` 页面 |
| 配对难点 | ① 编年史会把一条长词缀用 `<br>` 折断，行数与官方不一致；② 中文页偶尔缺行，按顺序硬配会整体错位 |
| 配对做法 | 先试「官方行数 == 中文行数」直接顺序配对；再把折行（下一行小写开头）合并后重试；仍不行才按英文相似度贪心配对，且要求中英数字至少有一个交集，否则丢弃（防止配错成完全无关的句子） |
| 数值处理 | 天赋 / 专精 / 符文嫁接的数值是**固定**的，优先存「带真实数值的整句」；只有中英数字顺序完全一致时才额外存 `#` 模板，避免「10% more ... 至少 6 个」这类语序不同导致数值填错位 |
| 覆盖情况 | 天赋树 2269 行说明中 98% 以上可整句命中；专精 61 组 / 394 行、关键天赋 72 条（含永恒珠宝的替换天赋，如 `Supreme Ostentation → 无上宣示`）、符文嫁接 32 条 |

> 典型修复：`30% more Spell Damage when on Low Life → 低血时法术伤害总增 30%`、`8% increased Damage for each of your Aura or Herald Skills affecting you → 伤害按照你身上每种影响你的光环或捷提高 8%`、`Spells have Added Spell Damage equal to 30% of Physical Damage of your Equipped Two handed Weapon → 法术附加等同于已装备双手武器物理伤害 30% 的法术伤害`。

---

## 三、快速开始

### 方式 A：油猴脚本（最省事）

1. 浏览器安装 Tampermonkey / Violentmonkey；
2. 打开 `dist/poe-web-tools.user.js`（可直接拖进扩展管理页，或复制内容新建脚本）；
3. 访问任一目标站点，右下角出现「汉」按钮即生效。

脚本自包含词典，不联网、不依赖任何外部库，匹配 `www.filterblade.xyz`、`filterblade.xyz`、`beta.filterblade.xyz`、`poe.ninja`。

### 方式 B：Chrome / Edge 扩展（推荐，带站点跳转）

1. 打开 `chrome://extensions`（Edge 为 `edge://extensions`），开启「开发者模式」；
2. 「加载已解压的扩展程序」→ 选择 `dist/extension` 文件夹；
3. 点击工具栏拼图图标，把「PoE Web Tools」**固定到工具栏**；
4. 之后点击图标即可看到两个站点卡片，点一下跳转（默认新标签，可勾选在当前标签跳转），下方还能开关汉化、切换模式。

> 项目文件夹改名后，扩展记录的路径会失效，需要在扩展页点「移除」再重新加载新路径下的 `dist/extension`。

### 方式 C：两个离线预览页

浏览器打开 `dist/preview.html`（FilterBlade 3.29 界面）或 `dist/preview-ninja.html`（poe.ninja 经济 / 流派界面），两页顶部有互相切换的链接。内置完整词典与引擎，可现场试中文 / 双语 / 原文切换、中英对照查询、点击还原，不需要访问外网。

---

## 四、怎么用

| 功能 | 说明 |
| --- | --- |
| 中文 / 双语 / 原文 | 面板或扩展弹窗切换；**原文模式**用于站内搜索、新增规则等需要用英文的场景 |
| `Alt+Z` | 快速在「中文 ↔ 原文」间切换 |
| 中英对照查询 | 面板输入中文或英文，列出对照，点击即复制英文名，可直接粘到站内搜索框 |
| 导出未译文本 | 导出当前页面仍是英文的文本清单（JSON），用来补词典 |
| 点击交互元素 | 鼠标按下瞬间自动还原英文，站点逻辑不受影响，松手后恢复中文 |
| 设置持久化 | 存于 `localStorage`（`fbzh.settings.v1`） |

**不会翻译**：`<script>` / `<style>` / `<textarea>` / `<pre>` / `<code>` / 代码块、输入框的值、下拉选项、广告 iframe，以及过滤器语法关键字。未登录词的文本保持英文，不会消失或报错。

**当前仍可能看到英文的地方**：FAQ 页的**答案长段落**（站点用 innerHTML 渲染、文本节点被 `<br>` / `<li>` 拆得很碎，本轮只翻了 78 个问题标题）、站点实时拼接的动态文案（例如带新赛季号的 `Current League: 3.30 …`，但 `Current League` 本身会翻）、流派页**装备词缀明细**（每件装备的随机词缀带具体数值，逐条命中率低）、以及未收录的新物品名。用面板「导出未译文本」即可拿到清单继续补。

---

## 五、目录结构

```
poe-web-tools/
├── README.md                    本说明
├── data/
│   ├── poedb_items.json         编年史对齐原始结果（含分类、来源、时间）
│   ├── community_seed.json      社区 MIT 脚本抽取的 UI 底稿
│   ├── manual_terms.json        人工校对的界面词条
│   ├── overrides.json           最高优先级术语覆写
│   ├── stoplist.json            过滤器语法关键字黑名单
│   ├── short_words.json         受控短词白名单（中英混排用）
│   ├── host_terms.json          站点专属词条（按域名生效，如 poe.ninja 的 Class 列头）
│   ├── gem_desc.json            编年史宝石详情页对齐的技能名与技能说明（1421 条）
│   ├── mod_templates.json       词缀模板（7830 条带 # 占位）+ 整句（8175 条）+ 前缀规则
│   ├── passive_terms.json       天赋树（关键天赋 / 名人 / 专精）+ 符文嫁接的中英对照
│   ├── mod_manual.json          人工补写的词缀模板 / 珠宝说明 / 前缀规则
│   ├── ninja_terms.json         poe.ninja 官方繁中译文转简（942 条进入主词典）
│   ├── ninja_ui_manual.json     poe.ninja 表格列头 / 时间范围等人工补词
│   ├── site_manual.json         站点文案人工译文累积库（英文原文 -> 中文）★主要维护文件
│   ├── site_extra.json          可选增量补词（格式同上）
│   ├── site_terms.json          合并后的站点文案词典（512 条）
│   ├── site_missing.json        当前仍未被词典覆盖的站点文案清单（诊断用）
│   ├── faq_zh.json              FAQ 78 个问题标题译文
│   ├── site_zh_1~3.json         首轮按序号批量填写的译文记录（已固化，仅供参考）
│   ├── dictionary.json          最终运行时词典（22004 条）
│   ├── dictionary.meta.json     构建统计与来源
│   └── conflicts.json           编年史 / 社区译名冲突清单
├── src/
│   ├── engine.js                核心翻译引擎
│   ├── panel.js                 悬浮控制面板
│   ├── style.css
│   ├── preview.template.html    FilterBlade 离线预览页模板
│   ├── preview-ninja.template.html  poe.ninja 离线预览页模板
│   └── extension/               manifest / popup（含两站点跳转）源码
├── tools/
│   ├── fetch_poedb.py           抓取编年史并生成对照表
│   ├── fetch_site_assets.py     下载 FilterBlade 的 .options / FAQ / 首页文案源
│   ├── fetch_ninja_i18n.py      抓 poe.ninja 页面模块与繁中语言包
│   ├── fetch_gem_desc.py        抓编年史宝石详情页，生成技能名与技能说明对照
│   ├── fetch_trade_stats.py     抓官方交易站词缀统计（中英按 stat id 对齐）
│   ├── fetch_passive_tree.py    抓编年史天赋树数据 + 天赋 / 专精 / 符文嫁接的中文页面
│   ├── build_mod_templates.py   生成词缀模板（交易站 + 编年史 + 天赋树 + 人工补写）
│   ├── extract_seed.py          抽取社区 UI 底稿
│   ├── extract_site_text.py     从 FilterBlade 文案源提取可见英文，输出未覆盖清单
│   ├── build_ninja_terms.py     按 Lingui id 配对、繁转简、术语校正 -> ninja_terms.json
│   ├── merge_site_terms.py      合并人工译文 + FAQ 问题 -> site_terms.json
│   ├── build_dictionary.py      合并、繁简统一、校验、生成词典
│   └── build_dist.py            打包脚本 / 扩展 / 两个预览页
├── tests/
│   ├── check_dictionary.py      词典质量校验
│   ├── engine.test.js           jsdom 引擎行为测试（30 项）
│   ├── preview.test.js          FilterBlade 预览页端到端（17 项）
│   └── ninja.test.js            poe.ninja 预览页端到端（57 项，含珠宝 / 天赋提示框）
├── dist/                        可直接使用的交付物（user.js / extension / 两个预览页）
└── research/                    抓取缓存与来源样本（可删除，重新抓取即可）
```

---

## 六、赛季更新 / 维护

新赛季出了新基底、新通货、新界面文案时（Python 3.10+，需 `opencc-python-reimplemented`）：

```bash
python -m pip install opencc-python-reimplemented
python tools/fetch_poedb.py --refresh        # 编年史 /cn 与 /us 重新对齐（道具译名）
python tools/fetch_site_assets.py --refresh  # 重新下载 FilterBlade 的 .options / FAQ / 首页文案源
python tools/fetch_ninja_i18n.py --refresh  # 重新下载 poe.ninja 页面模块与繁中语言包
python tools/fetch_gem_desc.py --refresh     # 重新抓宝石详情页，更新技能名与技能说明
python tools/extract_site_text.py            # 生成 data/site_missing.json 诊断清单
# 按需把清单里的英文原文，以 "英文": "中文" 形式补进 data/site_manual.json
# （或单独放 data/site_extra.json，便于分批维护）
python tools/build_ninja_terms.py            # poe.ninja：按 id 配对 + 繁转简 + 术语校正
python tools/merge_site_terms.py             # 合并人工译文 + FAQ 问题
python tools/build_dictionary.py             # 合并 + 繁简统一 + 语法关键字剔除 + 校验
python tools/build_dist.py                   # 重新打包脚本 / 扩展 / 两个预览页
python tests/check_dictionary.py             # 词典校验
```

只想微调少量译名：改 `data/manual_terms.json`、`data/overrides.json`、`data/site_manual.json` 或 `data/ninja_ui_manual.json` → 执行 `build_ninja_terms.py` + `merge_site_terms.py` + `build_dictionary.py` + `build_dist.py`，无需重新抓网页。

界面上遇到没翻的英文：用悬浮面板「导出未译文本」拿到清单，把需要翻的按英文原文补进 `data/site_manual.json`（或 `data/site_extra.json`）再构建。

> 注意：`data/site_zh_1~3.json` 是首轮按「未覆盖清单序号」批量填写的历史记录，其内容已固化到 `site_manual.json`。清单序号会随词典变化，因此**不要再按序号新增译文**，请直接以英文原文为键补词。

---

## 七、测试

```bash
python tests/check_dictionary.py          # 词典：全部通过
cd tests && npm install jsdom --no-save --no-package-lock
node tests/engine.test.js                 # 引擎：30 项全部通过
node tests/preview.test.js                # FilterBlade 预览页：17 项端到端
node tests/ninja.test.js                 # poe.ninja 预览页：57 项端到端（含流派页装备 / 技能说明 / 珠宝与天赋提示框）
```

覆盖：精确匹配、编年史译名、短语替换、**带随机数值的词缀模板回填**（`#` 占位）、**前缀规则**、**新赛季长说明整段命中**、**FAQ 问题标题**、**数字/中文＋英文混排局部替换**、属性翻译、代码区隔离、动态节点（MutationObserver）、三种模式切换与完整还原、点击交互还原与恢复、中英对照查询、150 条词条抽样；两个预览页分别验证 FilterBlade 3.29 卡片与 poe.ninja 物价表列头、物品名、导航、时间范围、页脚声明。

---

## 八、声明

- 本项目是**玩家自制的浏览器端显示层汉化**，不修改 FilterBlade 服务器、不修改生成的 `.filter` 文件内容，与 Grinding Gear Games 及 FilterBlade 官方均无关联。
- 道具译名数据来自「流放之路编年史 / 流亡编年史」<https://poedb.tw/cn/> 公开页面，权利归原站所有；请仅作个人学习与非商业使用，勿用于大规模再分发。
- UI 文案底稿来自 GreasyFork #496758（MIT，作者 Rayforward，原作 GodParadise 公会），已做繁简统一、去重与编年史术语覆盖，来源记录见 `data/community_seed.json`。
- poe.ninja 的界面译文来自其官方繁體中文语言包（公开静态资源），经繁转简与术语校正后使用，权利归 poe.ninja 原站所有；本项目**不会**修改其页面、URL 或服务端数据。
- 物品词缀译文来自官方交易站词缀统计接口（`pathofexile.com` 与 `poe.game.qq.com`，按 stat id 对齐），权利归 Grinding Gear Games / 腾讯所有。
- 若词典或引擎有问题，优先检查 `data/conflicts.json` 与面板导出的未译文本清单。
