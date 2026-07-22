---
name: tech-pulse
description: Produce a daily "今日值得关注的 10 件事" tech digest by aggregating aihot (AI 行业动态聚合, 已含 Hacker News 中文/公众号/OpenAI/HuggingFace/xAI 等)、GitHub 新晋高星项目、知乎日报、掘金、Solidot，then curating the 10 most noteworthy items with concrete Chinese summaries, a today's theme, and concise links (main + discussion) under each item. Use when the user asks for today's noteworthy tech things, GitHub trending, 今日值得关注的 10 件事, 今日技术动态, 每日技术速递, tech pulse, 每日值得关注的, AI 日报, or a daily digest of noteworthy open-source or tech items. Fetches candidates via a bundled Python script (cross-source dedup, each source independent; failures skip gracefully), fetches per-item article body and related links for concrete detail (stored in a sidecar JSON for on-demand deep-dive, not shown by default), then Codex curates 10 across sources and archives to docs/ via a build script.
---

# Tech Pulse · 每日值得关注的 10 件事

聚合 aihot（AI 行业动态聚合，一个源已含 Hacker News 中文翻译、公众号、OpenAI、HuggingFace、xAI、Cursor、IT之家 等）+ GitHub（新晋高星项目）+ 知乎日报 + 掘金，产出每日 10 件值得关注的事，每条带具体中文摘要与简洁链接（主链接 + 讨论）。Codex（你）做精选，无需外部 LLM key。

## 数据源（已去重，互不重叠）
- **aihot**：`aihot.virxact.com` 首页卡片（解析 `.m-row-title/.m-row-summary/.m-row-src/.m-score`），详情页含「精选理由 + AI 摘要 + 中文正文 + 原文链接」，天然覆盖 HN、公众号、OpenAI、HF、xAI 等。
- **GitHub**：`api.github.com` 搜索 API，取近 GITHUB_DAYS（默认 14）天新建且高 star 项目，作为 trending 代理。github.com 网页在国内常被墙，但 api.github.com 通常可达。
- **知乎日报**：`news-at.zhihu.com` 官方 API，每日精选知乎文章。
- **掘金**：`api.juejin.cn` 推荐流，中文开发者文章。
- **Solidot**：`solidot.org/index.rss` RSS，中文硬科技新闻，免 key。
- 已移除：ArXiv（与 aihot 论文聚合冗余）、V2EX/Reddit/HuggingFace/X（网络不可达或需 key）。
- 每个源独立，任一失败不影响其余。fetch.py 输出前会做**跨源去重**：按归一化标题 + URL 去重，冲突时保留源优先级更高（aihot>GitHub>知乎>掘金）或热度更高者，日志打印 `dedup: N -> M`。

## 前置依赖
Python 3 + `requests` + `beautifulsoup4`。若导入失败，先建 venv：
```powershell
cd <本 skill 目录>
.\scripts\setup.ps1 -UseMirror
```
之后脚本统一用 `.\.venv\Scripts\python.exe` 运行。

## 工作流
1. **采集候选**：运行 `.\.venv\Scripts\python.exe scripts\fetch.py --out candidates.json`。stdout 也可输出 JSON 候选数组（自动跨源去重），stderr 输出日志（含各源数量与 dedup 行）。每项：`{title, url, source, desc, metric, discuss, extra?}`。配置 env：`SOURCES`（默认 `aihot,github,zhihu,juejin,solidot`）、各源 `*_LIMIT`、`GITHUB_DAYS`。推荐用 `--out` 直接落盘 UTF-8（Windows PowerShell `>` 重定向默认写 UTF-16，会导致 build.py 解码失败）。精选时加 `--compact` 可在 stdout 打印精简索引（idx/来源/热度/标题/短摘要），省 token、避免输出截断；按 idx 选定后用小脚本从 `candidates.json` 取对应 url。默认各源限额已调低（aihot 12 / GitHub 8 / 知乎 6 / 掘金 6 / Solidot 6，约 38 条），可用 `*_LIMIT` env 覆盖。
2. **精选并写 selection.json**：跨所有源挑 10 件最值得关注的（创新性、实用性、影响力、热度），注意源多样性。记录一句「今日主题」。写 `selection.json`（数组）：`[{"url","summary","related":[{"text","url"}]}]`，每条 2-3 句中文摘要说清「是什么/干嘛的」，related 放原始来源链接（不显示，存 sidecar）。
3. **抓正文与相关链接**：对选中的 10 个 URL 运行 `.\.venv\Scripts\python.exe scripts\detail.py --out details.json <url1> <url2> ...`（同样用 `--out` 避免 PowerShell `>` 重定向编码问题）。每项：`{url, title, desc, firstp, links, source}`。aihot 走详情页取精选理由/AI 摘要/原文链接；GitHub 走 api.github.com 取 README；知乎日报走内容 API；掘金 detail API 失败则回退网页 meta；其余通用抓取。
4. **归档（build.py）**：运行
   ```
   .\.venv\Scripts\python.exe scripts\build.py --date YYYY-MM-DD --theme-file theme.txt \
       --candidates candidates.json --details details.json --selection selection.json
   ```
   生成 `docs\YYYY-MM-DD.md`（精简：主链接+讨论+来源+摘要）、`docs\YYYY-MM-DD.json`（sidecar：related+body）、并更新 `docs\index.md`（去重前置）。候选/详情缺失时自动回退，不报错。
5. **呈现**：内联展示日报（今日主题 + 10 条，每条含 来源/摘要/主链接/讨论）。不要堆相关链接。

## 按需深挖
当用户要求细看某条（如「7 具体查查」），读 `docs\YYYY-MM-DD.json`，取该条的 `related` 链接与 `body`，再抓取相关 URL（如经 raw.githubusercontent.com 取 GitHub README，或 aihot 详情页的原文链接）获取具体细节。相关链接正是为此而存，不在日报中显示。

## docs\YYYY-MM-DD.md 格式（build.py 生成）
```
# 今日值得关注的 10 件事 · YYYY-MM-DD

> 今日主题：<一句话>

## 1. <标题>
- 主链接：<url>
- 讨论：<讨论链接，若有>
- 来源：<来源> · <metric>
- 摘要：<2-3 句中文>

...(10 条)

---
*由 tech-pulse skill 生成 · <源列表> · YYYY-MM-DD*
```

## 备注
- 源独立：某源不可达时其余照常工作，汇报各源数量。
- detail.py 尽力而为：付费墙/纯 JS/被墙站点返回空 body/links，build.py 据标题+候选摘要兜底。
- 展示链接保持精简（主链接 + 讨论）。完整相关链接与正文存于 sidecar JSON 供深挖。
- 候选不足 10 条时，有几条精选几条。
- 缩窄源：设 env `SOURCES`（如 `aihot,github`）。
- Windows：`fetch.py`/`detail.py` 支持 `--out <file>` 直接写 UTF-8；勿用 PowerShell `>` 重定向（PS 5 默认 UTF-16，build.py 无法解码）。build.py 的 `_load` 已对 UTF-16/BOM 做容错。`build.py` 还支持 `--theme-file <file>`：把今日主题写进 UTF-8 文件传入，避免主题里的引号/空格在 PowerShell 命令行被误解析（仍可用 `--theme`）。
