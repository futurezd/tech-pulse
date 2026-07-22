# tech-pulse · 每日值得关注的 10 件事（Codex Skill）

对话里说「看看今天值得关注的 10 件事 / 今日技术动态 / GitHub trending / AI 日报」等即可触发。聚合 **aihot + GitHub + 知乎日报 + 掘金 + Solidot** 五个互不重叠的源，由 Codex 跨源精选 10 件、附中文摘要，归档到 `docs/`。

## 数据源（已去重）
- **aihot**：`aihot.virxact.com`，中文 AI 行业聚合（一个源已含 Hacker News 中文翻译、公众号、OpenAI、HuggingFace、xAI、Cursor、IT之家 等）。
- **GitHub**：`api.github.com` 搜索 API，取近 14 天新建高 star 项目（trending 代理；github.com 网页常被墙，但 API 可达）。
- **知乎日报**：`news-at.zhihu.com` 官方 API。
- **掘金**：`api.juejin.cn` 推荐流，中文开发者文章。
- **Solidot**：`solidot.org/index.rss` RSS，中文硬科技新闻，免 key。
- 已移除：ArXiv（与 aihot 冗余）、V2EX/Reddit/HuggingFace/X（网络不可达或需 key）。各源独立，任一失败自动跳过，无需外部 LLM key（Codex 自己精选）。
- `fetch.py` 输出前做**跨源去重**：按归一化标题 + URL 去重，冲突时保留源优先级更高者（aihot>GitHub>知乎日报>掘金>Solidot）。

## 文件
- `SKILL.md` - 触发词、数据源与工作流
- `scripts/fetch.py` - 多源采集（含跨源去重），stdout 输出 JSON 候选
- `scripts/detail.py` - 源感知抓正文 + 相关链接（存 sidecar，供深挖）
- `scripts/build.py` - 归档生成（selection + 候选 + 详情 -> docs md/json/index）
- `scripts/requirements.txt` / `scripts/setup.ps1` - 依赖与 venv 初始化
- `docs/` - 每日归档：`YYYY-MM-DD.md`（精简日报）+ `YYYY-MM-DD.json`（sidecar：原文链接+正文）+ `index.md`

## 工作流
1. `fetch.py` 采候选（自动去重）-> `candidates.json`
2. Codex 跨源精选 10 条、写中文摘要 -> `selection.json`（`[{url, summary, related:[{text,url}]}]`）
3. `detail.py <10个URL>` 抓正文与相关链接 -> `details.json`
4. `build.py --date YYYY-MM-DD --theme "..." --candidates ... --details ... --selection ...` 生成 `docs/` 下 md + json + index

## 首次安装
```powershell
cd <本 skill 目录>
.\scripts\setup.ps1 -UseMirror   # 建 .venv 并装依赖（清华镜像）
```

## 展示约定
每条只显示「主链接 + 来源 + 摘要」；原始来源链接（x.com / IT之家 / Cursor Blog 等）与正文存入 sidecar JSON，按需深挖（如「7 具体查查」）时再取，不在日报中堆砌。
