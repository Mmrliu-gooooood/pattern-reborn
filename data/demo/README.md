# 演示素材（`data/demo`）

开发阶段允许空清单：`manifest.json` 的 `cases` 可以为 `[]`，应用可以启动。

```text
.\.venv\Scripts\python.exe scripts\validate_demo_assets.py data/demo
```

竞赛就绪必须**恰好**包含以下六个案例标识，且每条权利记录完整可核验：

```text
lotus-paper-cut
fish-lotus-blue-calico
peony-embroidery
scrolling-lotus-ceramic
new-year-picture-detail
architectural-cloud
```

```text
.\.venv\Scripts\python.exe scripts\validate_demo_assets.py data/demo --competition-ready
```

## 收录规则

1. **只复制主原图**为 `data/demo/<case-id>/source.*`（保留扩展名）。不要收录 `02-extract`、`03-recombine`、`04-mockup`、`05-api-generated`、补充原图、`_scripts` 或桌面案例包本身。
2. 每条案例必须有 `metadata.json`。校验器**从不自动填写**权利字段；缺项只报错。
3. **禁止**授权不明的搜索引擎配图（例如 `license=unknown` 或来源为搜索结果页）。必须能指向机构/作者页面或书目。
4. 不要把人工智能生成图标成历史文物或传统原件。源图须声明 `ai_involvement.source_is_ai_generated`。案例包中的提取/重组/样机（AI 辅助）与 API 图（AI 生成）若未收录，应在说明中写明。
5. 不要使用 `verified_ich_source` 来宣称官方非遗认定；本仓库演示默认 `traditional_reference`。

`manifest.json` 形状：`{ "cases": [ { "id", "title_zh", "source" } ] }`，其中 `source` 是相对于 `data/demo` 且真实存在的路径。

每份 `metadata.json` 必填：title、category、profile、source filename、SHA-256、creator/institution、source URL 或 bibliography、license、retrieval date、provenance（`verified_ich_source` | `traditional_reference` | `user_supplied_unverified`）、processing defaults、expected result、AI involvement。
