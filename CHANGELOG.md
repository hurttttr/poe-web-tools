# 更新日志

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
发布时由 `.github/workflows/release.yml` 自动抽取对应版本段落，写入 GitHub Release 说明。

## [1.0.3] - 2026-11-17

### 修复

- **异界天赋树右侧统计栏残留英文**：poeplanner 把统计数值包进 `<span class="textAugmented">` 再用 `v-html` 渲染，一条说明被切成多个文本节点（`Your Maps have ` + `<span>8%</span>` + ` chance to …`），逐节点匹配必然落空。引擎新增「整行级」翻译：对只含行内标签的容器按整行拼合后再查词典 / `#` 模板，并把译文里同位置的数值按原 class 包回去，数值高亮不丢；多条说明用 `\n` 拼接时逐行翻译。
- 站点整段重渲染（`v-html` 刷新、列表更新）后能重新整行翻译：MutationObserver 现在把被替换的容器（`rec.target`）一并纳入重扫，不再只处理新增节点。
- 统计栏分组标题补齐国服译名：Map Bosses / Atlas Bosses / Influenced Monsters / Scourge / Metamorph / Perandus / Tempest / Warbands / Torment / Bloodlines / Invasion / Nemesis / Domination / Anarchy / Misc。

### 新增

- **异界天赋树中文搜索**：`src/atlas-search.js` 在站点搜索框上叠一层输入框。输入中文时用 `data/atlas_search.json`（352 个节点的中文名 + 中文说明）反查出命中的英文节点名，拼成 `(?:A|B|…)` 写进站点真正的 input 并派发 `input` 事件 —— 站点仍按自己的正则高亮，逻辑零改动；英文输入原样透传。`8%` 这类数字检索按 `#` 占位匹配，回车 / `Esc` / `×` 可清除。
- 预览页新增两块演示：统计栏（数值被 `<span>` 包住）与中文搜索（输入「毁灭游戏」「跳跃点」「穿越」可看到站点收到的检索串与高亮结果）。

### 变更

- `tools/build_atlas_terms.py` 追加输出 `data/atlas_search.json`，构建报告新增 `search_nodes`。
- 测试：atlas 33 → 51 项（整行翻译 / 原文还原 / 高亮保留 / 交互容器不改写 / 中文搜索 / 数字检索）。
- 安装说明与 Release 文案同步：搜索不再要求按 `Alt+Z` 切原文模式。

### 已知边界

- 中文搜索只在异界天赋树页（路径含 `atlas`）启用，其他页面的搜索框保持站点原行为。
- 中文检索按「中文节点名 + 该节点中文说明」匹配并高亮整个节点；受限于站点只认英文，无法做到按中文词在说明里做局部高亮。

## [1.0.2] - 2026-11-17

### 新增

- **FilterBlade MCP Server**：`mcp/fb_mcp.py` 提供 `fb_status` / `fb_get_state` / `fb_apply_state` / `fb_search_options` / `fb_import_sample` / `fb_export_save_file` 六个工具，让 AI 直接读写 FilterBlade 过滤器配置；配套 `src/extension/bridge-*.js` 本地桥（仅 `127.0.0.1`，不碰 OAuth 与站点后端）。示例配置见 `mcp/mcp.example.json`，测试见 `tests/check_mcp.py`（13 项）。
- **过滤器构建辅助脚本**：`tools/build_scroll_highlight.py` 在 NeverSink 过滤器上增量插入「成堆卷轴高亮」段（删除该段即还原），`tools/build_sync_page.py` 把生成的 `.filter` 打包成可一键复制 / 下载的离线同步页。产物写入 `mcp/out/`（已加入 `.gitignore`）。
- **PoE Planner 异界天赋树汉化**：`https://poeplanner.com/atlas-tree` 纳入油猴脚本、Chrome / Edge 扩展与离线预览页，站点卡片可直接跳转。
- **站点专属词典**：`data/atlas_terms.json`（620 条天赋名 / 界面文案）与 `data/atlas_templates.json`（288 条带 `#` 占位的天赋说明），按 `poeplanner.com` 作用域注入，不污染另外两个站点。天赋效果覆盖率 338/338。
- **抓取与构建脚本**：`tools/fetch_poeplanner.py` 动态读取版本清单与 bundle 文件名，`tools/build_atlas_terms.py` 把编年史 `us / cn / tw` 三版异界天赋页按 slug 对齐（简体页国服译名优先、繁中页补齐），繁转简并做术语纠偏。
- **离线预览页** `dist/preview-atlas.html`：模拟 atlas-tree 界面、节点提示框与异步渲染，三个预览页顶部可互相切换。
- **`tests/atlas.test.js`**：33 项断言，覆盖天赋名 / `#` 模板回填 / 跨行说明 / 属性翻译 / 异步节点 / 三种模式 / 站点作用域隔离 / 图标隔离。

### 变更

- **引擎**：跳过 `.v-icon` / `.material-icons` 子树。Vuetify 用 ligature 文本渲染图标（`expand_more`、`folder` 等），翻译这些文本会让图标直接消失。
- **译名口径**：站点专属词条会覆盖主词典同名键（如 `Clear` 主词典为「清澈」，在 PoE Planner 语境下为「清除」）；其他站点仍走主词典。
- **扩展 popup**：新增第三张站点卡片，三站点两列布局。
- **文档**：README / AGENTS.md / AI-NOTES.md 同步三站点说明、构建链与踩坑记录。

### 已知边界

- PoE Planner 的天赋树本体是 canvas / WebGL 渲染，节点名与说明只出现在悬浮提示中；天赋「搜索节点」按英文匹配，需要英文时按 `Alt+Z` 切到原文模式。

## [1.0.1] - 2026-11-14

### 新增

- **扩展图标**：16 / 32 / 48 / 128 四种尺寸，深蓝渐变底 + 金色描边 + 「汉」字设计；32 / 16 采用简化母版（字号更大、去光晕与装饰），保证工具栏上仍可辨识。
- **图标生成脚本** `tools/make_icons.py`：基于 Pillow 超采样绘制，调整配色或字形后可一键重新生成全部尺寸。
- **`AGENTS.md`**：面向 AI 编码代理的项目入口，包含构建 / 测试命令、目录边界与硬性规则。
- **`docs/AI-NOTES.md`**：方案取舍、引擎设计约束、各数据源抓取细节、已修 Bug 回归清单与维护守则。
- **`CHANGELOG.md`**：版本更新记录。

### 变更

- **README 精简重写**：303 行压缩至 184 行，改为居中标题、徽章、锚点导航与折叠说明，使用信息更集中，实现细节移交 `docs/AI-NOTES.md`。
- **扩展 popup**：标题左侧显示 18px 图标，与工具栏图标视觉统一。
- **构建脚本**：`tools/build_dist.py` 的默认版本号改为读取 `manifest.json`，避免版本号多处硬编码漂移。
- **发布流程**：Release 说明自动从本文件抽取对应版本段落，发布时无需再手改工作流。

## [1.0.0] - 2026-11-13

### 新增

- 首个版本：FilterBlade 与 poe.ninja 简体中文界面汉化，提供油猴脚本、Chrome / Edge 扩展、离线预览页三种形态。
- 词典 22,004 条：编年史道具译名、官方交易站词缀、poe.ninja 官方繁中转简、社区开源底稿、人工校对。
- 中文 / 双语 / 原文三种模式，`Alt+Z` 快速切换，中英对照查询，未译文本导出。
- 交互时自动还原英文，站点逻辑不受影响；支持带随机数值的词缀模板回填。
