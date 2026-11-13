# AGENTS.md

> 给 AI 编码代理的项目说明。人类请先读 [README.md](README.md)。
> 这里只放**每次会话都必须遵守**的命令与硬性规则；决策依据、踩坑过程、数据源细节见 [docs/AI-NOTES.md](docs/AI-NOTES.md)。

## 项目是什么

浏览器端汉化 FilterBlade 与 poe.ninja：**离线词典 + 运行时 DOM 注入**，不改服务端、不联网。交付物在 `dist/`：油猴脚本、Chrome MV3 扩展、两个离线预览页。

## 环境与命令

- Python 3.10+，依赖 `opencc-python-reimplemented`：`python -m pip install opencc-python-reimplemented`
- 测试依赖 jsdom：`cd tests && npm install jsdom --no-save --no-package-lock`

```bash
python tests/check_dictionary.py       # 词典校验
node tests/engine.test.js              # 引擎（30 项）
node tests/preview.test.js             # FilterBlade 预览页（17 项）
node tests/ninja.test.js               # poe.ninja 预览页（57 项）
```

只改少量译名后的最小构建链（无需联网）：

```bash
python tools/build_ninja_terms.py
python tools/merge_site_terms.py
python tools/build_dictionary.py
python tools/build_dist.py
```

完整重建（含抓取）见 README「维护」一节。**提交前必须跑词典校验 + 三个 node 测试。**

## 目录边界

| 路径 | 能否修改 |
| --- | --- |
| `src/` 引擎 / 面板 / 预览页模板 / 扩展源码 | ✅ 可改 |
| `data/` 词典源与中间产物 | ⚠️ 只手工改 `manual_terms` / `overrides` / `site_manual` / `site_extra` / `ninja_ui_manual` / `mod_manual` / `stoplist` / `short_words` / `host_terms` |
| `tools/` 抓取与构建脚本 | ✅ 可改 |
| `tests/` 测试 | ✅ 可改；改引擎行为必须同步补断言 |
| `dist/` 构建产物 | ❌ **禁止手改**，由 `tools/build_dist.py` 生成 |
| `research/` 抓取缓存 | 🗑️ 可删，勿当数据源 |

## 硬性规则

1. **过滤器语法关键字**（`Show` / `Hide` / `Class` / `BaseType` / `SetFontSize` …）绝不可加入任何词典或短词白名单，清单见 `data/stoplist.json`。
2. **补词一律以英文原文为键**写进 `data/site_manual.json`（或 `site_extra.json`），禁止按 `site_missing.json` 的序号补词；`data/site_zh_1~3.json` 已废弃。
3. **`#` 占位模板**：中英 `#` 数量必须一致，否则构建期丢弃；运行时骨架不匹配时**宁可输出英文**，不得输出错位译文。骨架比较统一转小写。
4. **`Class` 语义冲突**：poe.ninja 是表头「职业」，FilterBlade 是语法关键字 —— 站点专属词放 `data/host_terms.json`，不要污染主词典。
5. **不硬编码**赛季号、`.options` 文件名哈希、天赋树版本号，全部从站点 / 脚本动态读取。
6. **交互保护不可移除**：站点逻辑会读按钮 `innerText`，引擎在事件捕获阶段临时还原英文、事件结束再恢复。改引擎时保留该机制。
7. **术语口径**默认国服（Unique → 暗金）；要贴合编年史只改 `data/overrides.json` 后重建。
8. 词条数、覆盖率等数字变化后，同步更新 `README.md` 与 `data/dictionary.meta.json`。

## 已知易错点

- 抓取结果为 0 时**先查选择器 / 正则**，不要先怀疑站点改版（历史上宝石页绝对路径导致 620 条全漏）。
- 译文数值错位 → 检查 `#` 数量与骨架大小写。
- 扩展路径失效 → 目录改名 / 移动后需在扩展页移除并重新加载 `dist/extension`。
- 新赛季长文案缺口 → 直接抓站点 `.options` / `faqContent.json` 真实文案源，不要照截图手抄。

## 需要背景时

| 想了解 | 读 |
| --- | --- |
| 为什么选 DOM 注入、三条路线取舍 | [docs/AI-NOTES.md §1](docs/AI-NOTES.md#1-方案决策为什么选运行时-dom-注入) |
| 引擎设计约束全表 | [docs/AI-NOTES.md §2](docs/AI-NOTES.md#2-引擎设计约束最容易踩坑的地方) |
| 各数据源抓取与配对细节 | [docs/AI-NOTES.md §3](docs/AI-NOTES.md#3-词典构建数据源与各自的坑) |
| 已修 Bug 回归清单 | [docs/AI-NOTES.md §4](docs/AI-NOTES.md#4-已修复的典型-bug回归清单) |
| 该改哪个数据文件 | [docs/AI-NOTES.md §6](docs/AI-NOTES.md#6-数据文件速查该改哪个) |
