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

## 已收录（检索日期 2026-08-29）

只收录各案例包的 `01-original.jpg`，复制为 `source.jpg`。SHA-256 为仓库内复制件字节。

| Case ID | 标题 | License | SHA-256 |
|---|---|---|---|
| lotus-paper-cut | 剪纸莲花式团花 | CC BY-SA 4.0 | `fa5d35712480bac79f77fc25adda892044842aa668b74ac14f857dfdd5230173` |
| fish-lotus-blue-calico | 蓝印花布鱼莲纹 | Public Domain | `a90bbb81a53755d39659d8f03fea4989eabdce57575856db0e8367f735601994` |
| peony-embroidery | 刺绣牡丹 | CC0 / The Met Open Access | `702db0e13fa00ec3c9b9f23c05dcf2c2aace0a6d31b2487324721ad8c7206a3e` |
| scrolling-lotus-ceramic | 青花缠枝莲 | CC BY-SA 4.0 | `f63fc060abd4aad341a9b1b56b6d146536fa54e8cce14a11ed93c849e33c7f51` |
| new-year-picture-detail | 年画门神局部纹饰 | Public Domain | `b4193ae45267870fd9d674dd8f6d7af01c6da77643438b522ea6e0ac16b5f7f7` |
| architectural-cloud | 建筑彩画与剔犀云纹 | CC BY-SA 3.0 | `91da44e87a39a1cdcc349b7e636ec8d39d962e086eea0e947615351c60d46f6d` |

