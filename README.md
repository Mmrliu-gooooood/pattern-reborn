# Pattern Reborn / 纹启新生

A Windows-local studio for extracting, analyzing, recomposing, optionally generating, mocking up, and exporting **traceable** Chinese traditional-pattern projects.

The application is offline-capable for every step except paid image generation. Optional MobileSAM, VTracer SVG export, and the drawable canvas can each be absent without blocking startup.

## Prerequisites

- Windows 10/11 x64
- **Python 3.11** (3.12 is not supported; `requires-python = ">=3.11,<3.12"`)
- PowerShell

Do **not** install project packages globally. Do not require Docker, WSL, a database, a global Node toolchain, or a globally installed CUDA toolkit.

## Isolated bootstrap

From the repository root:

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
| `outputs\` | Provenance export packages |
| `models\` | Optional MobileSAM checkpoint |
| `.cache\` | pip / Hugging Face / Torch / temp |
| `.venv\` | Isolated interpreter and site-packages |

## Nine categories and four profiles

Categories (from `data/knowledge/categories.json`): 剪纸; 刺绣与织锦; 印染织物; 陶瓷纹饰; 漆器纹饰; 年画与民间绘画; 建筑彩画与砖木雕; 金银与首饰纹饰; 风筝、皮影与面具.

Profiles: **轮廓优先** (silhouette), **平面设色** (flat color), **织物纹理** (textile), **器物照片** (artifact photo). The artifact profile is assistive; it does not unwrap curved surfaces or recover hidden geometry.

## Offline behavior

Upload, extraction, analysis, recomposition, mockup, and export work without a network. Step 5 (Seedream / Qwen Image) needs credentials and connectivity. Cached generation files already stored in the project remain selectable and exportable while offline, and stay labeled as AI-assisted.

## Seedream / Qwen: platform default and BYOK

Both providers stay visible in step 5. Seedream starts selected; switching keeps prompt and other neutral fields. The app never auto-retries on the other paid provider.

1. **Platform default:** put keys in untracked `.env` as `SEEDREAM_API_KEY` and `QWEN_API_KEY`. Optional `SEEDREAM_BASE_URL` / `SEEDREAM_MODEL` / `QWEN_BASE_URL` / `QWEN_MODEL` override `config/providers.json`. The UI must not display the secret.
2. **Bring your own key:** session-only `SecretStr` in memory, password input. Not written to `project.json`, exports, logs, or Git.

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
- Missing MobileSAM disables guided AI segmentation only; OpenCV / manual box and keep-remove strokes remain.
- Missing canvas shows numeric rectangle and click-point inputs (`未检测到可绘制画布组件，已回退为框选与提示点输入。`).
- Missing VTracer disables SVG; PNG export continues.
- Live generation can fail (auth, quota, moderation, timeout); prompt and settings survive; the other provider is not selected automatically.

## Competition presentation fallback

Do not depend on a successful live API call. Prepare:

1. The six validated demos on disk.
2. One offline path through export (fixture pipeline or a headed run).
3. Cached generation results, if shown, visibly labeled as AI-assisted.
4. OpenCV extraction if MobileSAM or the canvas is missing; PNG if SVG is unavailable.

Acceptance evidence: `docs/acceptance/competition-checklist.md`. Third-party notices: `THIRD_PARTY_NOTICES.md`.
