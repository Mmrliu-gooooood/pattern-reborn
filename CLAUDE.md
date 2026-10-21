# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current product direction (2026-10-21)

Read `docs/product/README.md` and `docs/product/roadmap.md`: a complete local personal creation workspace first, with later distribution and online access. Competition specifications and plans under `docs/superpowers/` are historical rather than the authority for future scope.

The commands, architecture and UI below describe the existing implementation. Current Windows/Python/Streamlit requirements apply when running it, not as a permanent prohibition on a designed frontend or deployment migration. Six steps, workbench proportions, fonts, colors, gradients and exact widget positions may change with the new design. Update affected UI tests alongside implementation; preserve meaningful behavior, persistence and safety tests.

The independent React frontend lives in `web/`, with a loopback FastAPI adapter in `src/pattern_reborn/web_api.py`; see `docs/product/web-workspace.md`. It now covers library/duplicate/backup/import, extraction and analysis, recomposition/palette undo-redo, draft autosave/recovery, named versions/compare/restore, provider settings and asynchronous generation jobs, mockups and exports. Keep the existing Streamlit workflow. Schema version 1 is unchanged; web metadata is namespaced under `processing_parameters.web_workspace`, and draft/snapshot/recovery sidecars live in each project's `.web-workspace/`. Preserve source immutability, path containment, resource limits, atomic publication and secret handling. This local implementation does not authorize deployment or test calls to paid providers.

For local delivery, read `docs/product/local-release.md`: install into project `.venv`, package allow-listed source plus the prebuilt frontend, diagnose without revealing secrets, and upgrade into a new directory while retaining the previous installation. The release ZIP requires Python 3.11 and dependencies; it is not a standalone EXE. Fresh Windows installs and real paid calls have not been tested. No project LICENSE has been specified; third-party notices do not grant permission to publish the project's own code.

## What this is

A Windows-local React/FastAPI workbench and retained Streamlit studio for **traceable** Chinese traditional-pattern projects: upload → extract → analyze → recompose → optionally AI-generate → mockup → export with provenance. After dependency installation, core creation runs offline; remote generation requires explicit per-request consent.

Current runtime constraints: **Windows x64, Python 3.11 only** (`requires-python = ">=3.11,<3.12"`). The current app needs no Docker/WSL/database/global Node; a future architecture may introduce project-local dependencies through an explicit migration. Never install into a global Python — always use `.venv`.

## Commands

The bootstrap/test/install wrappers direct their dependency caches and temporary files into drive-local `.cache\`; web startup also uses local temp storage. Run commands from the repository root. Do not install into global Python.

```powershell
# One-time bootstrap (requires Python 3.11; fails if .venv exists with another version)
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1

# Local React source release (prebuilt frontend); Python 3.11 x64 only
powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File scripts\diagnose-local.ps1
powershell -ExecutionPolicy Bypass -File scripts\release-local.ps1
# From Git sources: install .[web], npm ci in web, then run-web.ps1 -Build

# Full test suite (defaults to tests/ via pyproject testpaths)
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -q
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 --cov=pattern_reborn --cov-report=term-missing --cov-fail-under=85

# Single test / file
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 tests\ui\test_studio.py -q
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 tests\ui\test_studio.py::test_sidebar_has_six_steps_and_advanced_settings_start_collapsed -q

# Run the app (bind loopback so health checks work)
powershell -ExecutionPolicy Bypass -File scripts\run.ps1 --server.address 127.0.0.1 --server.port 8501

# Optional extras
powershell -ExecutionPolicy Bypass -File scripts\install_optional_ai.ps1   # CPU Torch + MobileSAM into .venv
.\.venv\Scripts\python.exe -m pip install -e ".[canvas]"                    # drawable Konva canvas

# Demo asset validation
.\.venv\Scripts\python.exe scripts\validate_demo_assets.py data\demo
.\.venv\Scripts\python.exe scripts\validate_demo_assets.py data\demo --competition-ready
```

Sanity checks: `.\.venv\Scripts\python.exe -m pip check` and `.\.venv\Scripts\python.exe -m compileall -q app.py src tests scripts`.

**Machine gotcha:** pytest's default temp root (`%LOCALAPPDATA%\Temp\pytest-of-<user>`) can raise `PermissionError` on this workstation, producing mass fixture errors. Either run through `scripts\test.ps1` (which redirects `TEMP`/`TMP` into `.cache\tmp`) or set `TEMP`/`TMP` to a repo-local path before invoking pytest directly.

**Git gotcha:** the working tree may be owned by a different Windows account, so `git` reports `detected dubious ownership`. Fix once with `git config --global --add safe.directory D:/code/ican/pattern-reborn`.

## Architecture

Layers, in dependency order (UI → service → processing/persistence → domain):

| Module | Owns |
|---|---|
| `app.py` | Streamlit composition root. Builds `RuntimePaths`, `ProjectRepository`, `KnowledgeCatalog`, `GenerationService`, lazy MobileSAM; dispatches home vs studio on `st.session_state["route"]`; calls `main()` at import. |
| `src/pattern_reborn/ui/` | Streamlit-only rendering; no processing logic. See *UI structure* below. |
| `web/src/` / `web_api.py` | React workbench and same-origin loopback routes; extraction/design preview-save-export adapters and revision guards. |
| `web_extraction.py` | Bounded auto/OpenCV/color/whole/local MobileSAM selection; optional cleanup before manual strokes, original RGB/alpha preservation and Chinese guidance. |
| `web_projects.py` | Disk drafts, immutable snapshots, two-version comparison data, backup-before-restore, project duplicate and complete ZIP import/export with path/hash/resource checks; corrupt-record recovery from valid snapshots. |
| `web_creative.py` | Analysis, local provider settings/keys, per-call paid consent, in-memory job status/dedup/cancellation, revision-safe generation publication, mockups and creative exports. |
| `workflow.py` | `PatternRebornService` — framework-independent six-step orchestration and all artifact I/O under a project dir. |
| `projects.py` | `ProjectRepository` — on-disk project folders, atomic `project.json`, source copy + SHA-256, `confirm()` stale-marking, path containment. |
| `domain.py` | Pure pydantic models/enums: `CategoryId`, `ProfileId`, `ProvenanceClass`, `StepId`, `ArtifactKind`, `ProjectRecord`, `SourceRecord`, `ArtifactIndex`, `GenerationRecord`. |
| `runtime.py` / `config.py` / `capabilities.py` | Path resolution + env mapping; provider config loading and env overrides; dependency/credential/network probing (never imports Torch/MobileSAM — uses `find_spec`). |
| `knowledge.py` | Validated `KnowledgeCatalog` (9 categories, 4 profiles, 12 traditional colors) from `data/knowledge/`. |
| `images.py` / `limits.py` / `preprocess.py` / `segmentation.py` / `analysis.py` / `patterns.py` / `vectorize.py` | Decode+atomic PNG save and allow-lists; pixel/edge budgets and typed limit errors; enhancement/crop/perspective; OpenCV + MobileSAM segmenters and mask strokes; deterministic palette/CIE-Lab/contour/symmetry analysis; `PatternRequest` layout composition; optional VTracer adapter. |
| `mockups.py` / `exporter.py` | Mockup catalog + transactional locked PNG+JSON sidecar publication; atomic provenance export packages with filename sanitization and secret redaction. |
| `generation/` | `base.py` provider-neutral contracts; `service.py` `GenerationService` + credential resolution; `http.py` error mapping; `seedream.py` / `qwen.py` / `custom.py` adapters; explicit OpenRouter Images and generic image protocols. |

### UI structure

The table below describes retained Streamlit modules. React composition is in `web/src/App.jsx`, with `Library`, `Editor`, `Workspace`, `Creative`, `Settings` and `ProjectTools`; `useDraft.js` synchronizes browser and disk draft copies. Drafts do not publish extraction/design artifacts; stale drafts require explicit handling. Keys never enter browser storage. Job/dedup/session state is in backend memory and does not survive restart; published artifacts do.

Use one backend process per workspace. The local `RLock` and revision checks do not provide cross-process locking with another FastAPI or Streamlit process. Cancellation prevents publishing generated results but cannot guarantee that an already submitted provider request stops or avoids billing.

| File | Owns |
|---|---|
| `ui/studio.py` | Router only: sidebar step rail, shared header, `STEP_RENDERERS` dispatch, session-key cleanup. Re-exports `hints_from_canvas_objects`, `STEP_LABELS`, `STEP_BY_LABEL`, `LABEL_BY_STEP` for compatibility. |
| `ui/home.py` | Hero, recent projects, nine-category grid, demos, readiness tiles. |
| `ui/labels.py` | Every Chinese display string keyed by domain enum (`STEP_LABELS`, `PROVENANCE_LABELS`, `CATEGORY_LABELS`, `mockup_templates()`, `artwork_label()`…). Both the UI and the tests read labels from here. |
| `ui/components.py` | Layout primitives: `two_panel_step`, `render_step_header`, `render_kicker`, `render_image_panel`, `render_metric_grid`, `render_palette`, `render_color_matches`, `render_empty_state`, `advanced`, `action_bar`, `flash`/`render_flash`, `escape`. |
| `ui/presenters.py` | Read-only views over persisted state (`load_analysis`, `current_artworks`, `current_generations`, `current_patterns`, `current_mockups`, `pending_extraction`, `confirmed_extraction`). No Streamlit imports, so they unit-test directly. |
| `ui/canvas.py` | Optional drawable-canvas renderer plus the pure object→hints mapping. The canvas package is imported lazily; absence degrades to numeric inputs. |
| `ui/steps/{source,extraction,analysis,recomposition,generation,export}.py` | One `render(context: StudioContext)` per step. |
| `ui/assets/theme.css` | Single `:root` token block, then shell → components → native widget surfaces → responsive. |

Three conventions matter when editing the UI:

1. **Results are re-rendered from disk on every rerun, never inside a button branch.** Streamlit reruns the whole script on each interaction, so `if st.button(...): st.image(...)` makes the result vanish as soon as anything else is touched. Use `ui/presenters.py` to rebuild panels, and `components.flash()` to queue a success message — `st.success` immediately before `st.rerun()` is never seen.
2. **Card and panel frames come from `st.container(key="…")`, not HTML wrappers.** Streamlit closes every `st.markdown` call inside its own element container, so `<div class="card">` can never wrap an `st.image`/`st.button`. A `key` becomes the CSS class `st-key-<key>`, and `theme.css` matches prefixes: `st-key-workbench-`, `st-key-controls-`, `st-key-action-bar-`, `st-key-recent-card-`, `st-key-category-card-`, `st-key-demo-card-`. Adding a prefix means adding a CSS rule; `tests/ui/test_components.py` checks both directions and also asserts no `st.markdown` block emits unbalanced HTML.
3. **Keep the workbench/control ratio and the bottom action bar.** `components.two_panel_step` and `components.action_bar` exist so the six steps cannot drift into six different arrangements.

### Step lifecycle

Order (`ProjectRepository._STEP_ORDER`): `upload → extraction → analysis → recomposition → generation → export`.

- Creating a project copies the source to `source/<sha256[:16]><suffix>` and confirms `upload`.
- `extract` writes `extracted/vN.png` + `masks/vN.png` and sets `processing_parameters["pending_extraction"]`, but does **not** confirm. `confirm_extraction(project_id, artifact_id)` validates the pending id and confirms `extraction`.
- `analyze` requires `extraction` confirmed, writes `analysis/vN.json` (`algorithm="opencv-baseline-1.0"`, `_PALETTE_SEED=20260829`), then auto-confirms `analysis`.
- `compose` requires `analysis` confirmed, writes `patterns/vN.png` (+ `patterns/vN.svg` only when VTracer is available), auto-confirms `recomposition`. It also stores the request under `processing_parameters["compose"]`.
- `generate` is gated on `extraction` (not recomposition), copies adapter output to `generated/vN.png`, appends a `GenerationRecord`, auto-confirms `generation`.
- `make_mockup` writes `mockups/<template>-vN.png` + `.json` sidecar; `export` builds the package then confirms `export` with `[]`.

`confirm(project_id, step, artifact_paths)` **marks every later step stale**: later artifacts move into `stale_artifacts` and their index lists are cleared; if `generation` is later, all `GenerationRecord.artifact_path` values are staled and `generations` is emptied; if `export` is later, `processing_parameters["current_mockups"]` is staled and reset. `stale_artifacts` is the single flat filter downstream code must respect.

### Invariants and gotchas

- **Enums:** `StepId` = `upload, extraction, analysis, recomposition, generation, export`. `ArtifactKind` = `source, mask, extracted, analysis, pattern, generation, mockup, export`. `ProviderId` = `seedream, qwen, openrouter, custom`; `CredentialMode` = `platform, byok`.
- **Category → profile** (`data/knowledge/categories.json`): paper_cutting/folk_crafts→silhouette, embroidery_brocade/dyeing_textile→textile, ceramic_ornament/metal_jewelry→artifact_photo, lacquer_ornament/folk_painting/architectural_ornament→flat_color. `KnowledgeCatalog` enforces exact set equality against the enum values.
- **Limits** (`limits.py`): source/canvas `MAX_*_PIXELS = 16_777_216`, `MAX_CANVAS_EDGE = 8_192`, intermediate 4_194_304 px. Enforced before Pillow/OpenCV allocation; violations surface as domain errors, never raw `MemoryError`/OpenCV exceptions.
- **Atomic publication everywhere:** `images.save_png_atomic`, `projects.save` (`project.json.tmp` + `os.replace`), `workflow._write_json_atomic`, `exporter` (temp dir + replace), `vectorize`, and `mockups.save_mockup_bundle_atomic` (journaled transaction). `make_mockup` wraps its read-modify-write in `mockup_project_publication_lock(project_dir)`.
- **Path containment:** `workflow._resolve_artifact`, `projects._contained_path`, `exporter._resolve_input` reject absolute paths, `..`, and anything escaping the project/destination root.
- **Secrets:** config stores env-var *names* only. Platform keys come from `SEEDREAM_API_KEY` / `QWEN_API_KEY`; overrides from `SEEDREAM_BASE_URL|MODEL` / `QWEN_BASE_URL|MODEL` (base URLs must be https). The retained Streamlit BYOK input is session-only. Web BYOK and endpoint/model/protocol/sizes/default provider persist under root `.private/provider-settings.json`; keys use Windows current-user DPAPI (no plaintext fallback), stay outside projects, backups, diagnostics and releases, and require explicit re-entry when the destination changes. Cookies own jobs only. Corrupt settings remain untouched and block updates until repaired or moved aside. Exports redact secret-shaped strings to `[REDACTED]`; `generation.base.redact_provider_code` keeps only HTTP status codes.
- **Optional dependencies never block startup:** missing VTracer → `VectorResult(available=False)`, PNG unaffected. Missing MobileSAM when selected → `WorkflowError("MobileSAM 当前不可用，请改用 OpenCV。")`. `generation=None` → `WorkflowError("生成服务未配置。")`. `PATTERN_REBORN_DISABLE_OPTIONAL=1` disables `mobile_sam` and `canvas` probing.
- **Strict pydantic:** nearly every model is `extra="forbid"`, most with `validate_assignment=True`; knowledge models add `strict=True`. Timestamps must be tz-aware and are normalized to UTC.
- **Env toggles:** `PATTERN_REBORN_WORKSPACE` overrides the workspace *and* disables `@st.cache_resource` caching; `PATTERN_REBORN_OUTPUTS` overrides the export/generation root (the UI test fixtures use it so tests never write into the repository's `outputs/`); `PATTERN_REBORN_DEMO_ROOT` overrides the demo directory. `.env` is loaded from the repo root.
- **Theme config:** `.streamlit/config.toml` carries the native palette (paper background, ink-green sidebar, cinnabar primary, KaiTi headings). Keep it in sync with the `:root` tokens in `ui/assets/theme.css`, which supplies what the config cannot express.

## Tests

`tests/` mirrors the module layout. Plain pytest; `respx` for provider HTTP fakes. Integration coverage lives in `tests/integration/test_offline_pipeline.py` (full offline create→export path) and `tests/smoke/` (launches a headless Streamlit child on loopback and polls `/_stcore/health`).

`tests/ui/` drives the real app through **Streamlit `AppTest`** (`AppTest.from_file(APP_PATH)`), not a browser. Fixtures in `tests/ui/conftest.py`: `studio_workspace` (sets `PATTERN_REBORN_WORKSPACE`/`_DEMO_ROOT` to `tmp_path`, clears API keys, stubs `probe_online` and `build_generation_service` with `FakeGenerationAdapter`s), `studio_test`, `studio_at_extraction`, `studio_at_generation`, `source_image`. Helpers `all_text`, `radio_option_labels`, `session_get`, `widget_disabled`.

Step modules and presenters also have focused tests: `tests/ui/test_source_step.py` (upload → create project), `test_presenters.py`, `test_components.py`, `test_canvas.py`, `test_state_helpers.py`, `test_export_controls.py`.

UI behavior pinned by tests — do not break without updating them:

- Sidebar `radio[0]` options must equal `STEP_LABELS` (six Chinese labels), and `expander[0]` must be `高级设置`, collapsed.
- Extraction keeps `number_input` labels `框选左/框选上/框选右/框选下/提示点 X/提示点 Y`, a stroke `text_input` whose label contains `笔触`, and a keep/remove radio — with or without the drawable canvas.
- Analysis: a button labelled `分析` produces text containing `轮廓`. Recomposition: `number_input` labels `画布宽度`/`画布高度`.
- Existing projects on the upload step must show `新建项目`, never `创建项目`.
- Generation: radios `生图模型` (`Seedream` default, `Qwen Image 3.0 Pro`) and `凭证方式` (`平台默认`/`自带密钥`); password `text_input` labelled with `密钥`; `提示词`, `输出尺寸`, `结构保留`, `目标应用`, `传统色彩`; buttons `生成` / `确认生成`; export `贴图纹样` + `生成贴图`; `AI 生成` / `AI 辅助` labels must be visible.
- Home: button `开始新创作`; markdown containing `最近项目` and `本地处理可用`; nine category buttons by `display_name_zh`; at most three recent-project buttons; demo creator/license text; project-name button opens the studio and shows `创作工坊`.
- `tests/ui/test_theme.py` statically requires: the string `--ink-green`, `--vermilion`, `--gilded-gold` present in `theme.css`; **exactly two** occurrences of `radial-gradient`; no `repeating-radial-gradient`, no `linear-gradient`, no `repeating-linear-gradient`, no `http://`/`https://`.
