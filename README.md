# Pattern Reborn / 纹启新生

## 当前方向 / Product direction

自 2026-10-21 起，本项目转向可长期使用的**本地个人纹样创作工作台**，优先完善编辑、项目管理和导出，后续支持向其他用户分发及在线使用。比赛演示已不再是产品目标。

现有 Python / Streamlit 全流程保留。独立 React 创作工作台已覆盖本地项目管理、提取、分析、重组配色、版本比较恢复、AI 生成服务设置与任务状态、文创预览及导出，通过回环 FastAPI 复用处理核心。本轮本地功能已接通；尚未部署，也未实测真实付费生成或全新 Windows 系统安装。

新版入口与操作见 [本地创作工作台](docs/product/web-workspace.md)，安装、备份、升级与故障排查见 [本地使用与发行指南](docs/product/local-release.md)。程序源码 ZIP 已含构建后的前端，解压后运行 `scripts/install-local.ps1`，再双击 `Start-Workspace.cmd`，在 `http://127.0.0.1:8510` 使用。源码 ZIP 仍需要 Python 3.11 和项目 `.venv`，不是免环境 EXE。从 Git 源码启动还需先构建前端；下文原有 `run.ps1` 打开 Streamlit。

新版支持提取和构图草稿自动保存与恢复、命名版本的两份并排比较与恢复、项目复制、完整备份及回导；有效历史存在时可恢复损坏的项目记录。自动、OpenCV、选色、保留整图和可选 MobileSAM 提取均保留源透明度；重组和配色支持撤销重做。每次远程生图都需要明确同意发送参考图与可能付费，任务支持状态查询、重复请求防护和取消后丢弃结果。

- [当前产品基线](docs/product/README.md)
- [实施前审查与界面证据（历史）](docs/product/2026-10-21-assessment.md)
- [实施路线与验收门槛](docs/product/roadmap.md)

`docs/superpowers/` 和比赛验收资料属于历史记录；其中固定界面和比赛范围限制不再约束未来版本。来源保护、密钥保护和数据完整性要求继续有效。

## Current implementation

A Windows-local studio for extracting, analyzing, recomposing, optionally generating, mocking up, and exporting **traceable** Chinese traditional-pattern projects.

The application is offline-capable for every step except remote image generation, once dependencies are installed. Optional MobileSAM and VTracer SVG export can be absent without blocking startup. The optional Streamlit drawable canvas is separate from the React editor's built-in canvas.

## Prerequisites

- Windows 10/11 x64
- **Python 3.11** (3.12 is not supported; `requires-python = ">=3.11,<3.12"`)
- PowerShell

Do **not** install project packages globally. Do not require Docker, WSL, a database, a global Node toolchain, or a globally installed CUDA toolkit.

## Isolated bootstrap

For a local source release with a prebuilt frontend:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
```

The installer uses Python 3.11 x64 in project `.venv`; initial dependency installation normally needs network access. `-CheckOnly` checks an existing installation without downloads. Offline installation requires a complete compatible wheelhouse. See the [local guide](docs/product/local-release.md) for diagnostic reports, source bundle creation and upgrades into a new directory while preserving the previous installation and private configuration.

For Streamlit development, from the repository root:

```powershell
.\scripts\bootstrap.ps1
```

The launcher creates `.venv`, points `PIP_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME`, `TEMP`, and `TMP` at drive-local folders under `.cache\`, then installs the package with the project interpreter:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Copy secret **names** only, then fill values in an untracked file:

```powershell
Copy-Item .env.example .env
```

## Optional AI, canvas, and GPU

Core OpenCV extraction works without extras.

- **MobileSAM (optional):** `.\scripts\install_optional_ai.ps1` installs CPU Torch and MobileSAM **into `.venv`** and verifies the checkpoint under `models\mobile_sam\` (gitignored).
- **Drawable canvas (optional):** `.\.venv\Scripts\python.exe -m pip install -e ".[canvas]"`
- **GPU (optional, not required):** the MVP does not need a global CUDA toolkit. If you already have a local CUDA runtime and want a CUDA wheel, install it with the **venv** interpreter only, for example `.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124`. Never use a global `pip`.

## Start and test

Bind IPv4 loopback so health checks against `127.0.0.1` succeed:

```powershell
.\scripts\run.ps1 --server.address 127.0.0.1 --server.port 8501
```

```powershell
.\scripts\test.ps1 -q
.\scripts\test.ps1 --cov=pattern_reborn --cov-report=term-missing --cov-fail-under=85
```

## Project storage

Mutable data stays under the repository (all gitignored except tracked demos):

| Path | Role |
|---|---|
| `workspace\<project_id>\` | One project: immutable `source\`, masks, extracted, patterns, generated, mockups, `project.json` |
| `workspace\<project_id>\.web-workspace\` | Recoverable extraction/design drafts, immutable version snapshots and damaged-record recovery copies |
| `outputs\` | Provenance export packages |
| `models\` | Optional MobileSAM checkpoint |
| `.cache\` | pip / Hugging Face / Torch / temp |
| `.venv\` | Isolated interpreter and site-packages |

Complete project backups include project artifacts, disk drafts, version history and available export files; import creates an independent project. Program source ZIPs and artwork delivery ZIPs serve different purposes. Browser-only drafts, session keys and in-flight generation jobs are not a complete project backup. Use one process per workspace: revision checks and the current lock do not coordinate simultaneous Streamlit and Web writers.

## Nine categories and four profiles

Categories (from `data/knowledge/categories.json`): 剪纸; 刺绣与织锦; 印染织物; 陶瓷纹饰; 漆器纹饰; 年画与民间绘画; 建筑彩画与砖木雕; 金银与首饰纹饰; 风筝、皮影与面具.

Profiles: **轮廓优先** (silhouette), **平面设色** (flat color), **织物纹理** (textile), **器物照片** (artifact photo). The artifact profile is assistive; it does not unwrap curved surfaces or recover hidden geometry.

## Offline behavior

Upload, extraction, analysis, recomposition, mockup, and export work without a network. Step 5 (Seedream / Qwen Image) needs credentials and connectivity. Cached generation files already stored in the project remain selectable and exportable while offline, and stay labeled as AI-assisted.

## Seedream / Qwen: platform default and BYOK

Both providers remain available in Streamlit and the React workbench. React service settings accept a per-session key, model and HTTPS endpoint; platform configuration can use local environment variables. The app never automatically retries on the other paid provider.

1. **Platform default:** put keys in untracked `.env` as `SEEDREAM_API_KEY` and `QWEN_API_KEY`. Optional `SEEDREAM_BASE_URL` / `SEEDREAM_MODEL` / `QWEN_BASE_URL` / `QWEN_MODEL` override `config/providers.json`. The UI must not display the secret.
2. **Bring your own key:** session-only `SecretStr` in memory, password input. Not written to `project.json`, exports, logs, or Git.

React generation requires per-request paid consent, reports queued/running/succeeded/failed/cancelled states and deduplicates the same request ID in the current service session. Cancellation prevents publishing the result; a request already sent to a provider may continue and be billed. Service restart clears in-memory jobs and session credentials; already saved generated artifacts remain on disk. Current validation uses fake providers rather than real paid calls.

## Secret handling

- `.env` and `.streamlit/secrets.toml` are gitignored. Never commit keys.
- Tests use fake HTTP and placeholders such as `sk-secret-value`; they must not call live paid APIs.
- Exports redact secret-shaped strings to `[REDACTED]`.

## Demo intake

See `data/demo/README.md`. Validate without guessing rights metadata:

```powershell
.\.venv\Scripts\python.exe scripts\validate_demo_assets.py data/demo
.\.venv\Scripts\python.exe scripts\validate_demo_assets.py data/demo --competition-ready
```

Competition-ready mode requires exactly the six case IDs listed in that README, each with a complete rights record. Search-engine images with unclear reuse rights are rejected.

## Export format

Each export is a timestamped folder under `outputs\`:

- selected PNG (and SVG when VTracer is available)
- `manifest.json` (file inventory, hashes, AI flags)
- `attribution.md`
- `provenance.md` when the report is selected

The report distinguishes project-authored work, third-party components, traditional references, and AI-assisted outputs. Source bytes in `workspace\...\source\` remain unchanged.

## Known limitations

- No accounts, cloud sync, collaboration, model training, local Stable Diffusion, embroidery-machine files, full SVG node editing, mobile layout, or official ICH authentication.
- Missing MobileSAM disables that optional mode; automatic / color / OpenCV / whole-image extraction and manual strokes remain. Complex photographs and fine cutouts still require visual inspection.
- In Streamlit, missing optional canvas falls back to numeric rectangle and prompt-point inputs. React drawing does not require this extra.
- Missing VTracer disables SVG; PNG export continues.
- Live generation can fail (auth, quota, moderation, timeout); prompt and settings survive; the other provider is not selected automatically.
- Corrupt project recovery needs an intact snapshot and its referenced source/artifacts; it cannot reconstruct missing image bytes.
- Fresh Windows dependency installation and live paid requests have not been validated. Local source release ZIPs require Python and installed dependencies; the repository has no project LICENSE authorizing public redistribution.

## Historical competition presentation fallback

This section describes the previous competition release, not the current product roadmap or a new test result.

Do not depend on a successful live API call. Prepare:

1. The six validated demos on disk.
2. One offline path through export (fixture pipeline or a headed run).
3. Cached generation results, if shown, visibly labeled as AI-assisted.
4. OpenCV extraction if MobileSAM or the canvas is missing; PNG if SVG is unavailable.

Acceptance evidence: `docs/acceptance/competition-checklist.md`. Third-party notices: `THIRD_PARTY_NOTICES.md`.
