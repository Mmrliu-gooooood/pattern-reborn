# Pattern Reborn Competition Hardening and UI Redesign Specification

> 历史文档（2026-10-21 标记）：本文记录比赛阶段的设计或实施计划，不再定义当前产品范围。请以[产品化基线](../../product/README.md)为准。原始内容保留供追溯；数据完整性、来源与密钥保护要求继续有效。

Date: 2026-08-30

Status: selected direction approved; written specification pending review

Supersedes: only the implementation details that conflict with `2026-08-29-pattern-reborn-design.md`

## 1. Objective

Upgrade the existing Streamlit application into a reliable, presentation-ready entry for the 2026 iCAN innovation track while preserving its working offline image-processing pipeline and six-step creation workflow.

The release must achieve four outcomes:

1. A judge can complete the principal flow with any of the six bundled examples without encountering a broken or ambiguous state.
2. Image processing, project persistence, provenance, exports, and paid generation calls fail safely under malformed, extreme, or interrupted inputs.
3. The interface presents a coherent Chinese intangible-cultural-heritage identity: rice paper, ink green, cinnabar seal red, restrained gilding, and ruyi-cloud line art.
4. The application remains a local Windows-first Streamlit product with no Docker, WSL, CUDA, or database-service dependency.

## 2. Delivery scope

### 2.1 Included

- Repair every confirmed priority-one defect from the 2026-08-30 audit.
- Repair priority-two defects that affect competition demonstration reliability, copyright and provenance, project integrity, or paid generation APIs.
- Include adjacent low-cost validation and accessibility repairs when the same surface is already being changed.
- Redesign the home page, global navigation, and all six studio steps in the approved visual direction.
- Preserve both generation credential modes and explicit model switching:
  - platform-default Seedream;
  - platform-default Qwen Image;
  - user-provided provider-specific API credentials.
- Preserve the nine supported heritage categories and six bundled demonstration cases.
- Preserve offline OpenCV/Pillow operation for steps one through four and exporting.

### 2.2 Explicitly excluded

- Rewriting the application in React or replacing Streamlit.
- Mobile-specific layouts; the judged target is a Windows laptop browser.
- Training or fine-tuning a local foundation model.
- Professional restoration of severely damaged artifacts, automatic scholarly interpretation of cultural symbolism, or guaranteed studio-grade extraction from arbitrary photographs.
- A cloud proxy, user-account system, database server, or deployment platform.
- New heritage categories beyond the nine already specified.

## 3. Product experience

### 3.1 Global shell

The application uses a fixed ink-green sidebar and a warm rice-paper main canvas. The main background must use subtle paper grain rather than diagonal lines.

The sidebar contains:

- the complete `纹启新生 / PATTERN REBORN` brand lockup;
- a restrained gilded ruyi-cloud watermark in the lower or middle negative space;
- `非遗纹启` as a small seal-like inscription;
- a six-step vertical progress rail;
- a light project-history entry at the bottom.

Only the active progress dot and primary call-to-action use cinnabar red. Completed nodes use muted gold, future nodes use a low-contrast outline, and all text on ink green must satisfy readable contrast. Cinnabar text must not be placed directly on ink green.

### 3.2 Home page

The home page contains, in this order:

1. A rice-paper hero with project statement, one primary `开始创作` action, and one secondary `查看演示案例` action.
2. A compact recent-project row showing project name, category, last update, and current step.
3. A nine-category entry grid with concise category labels and restrained imagery or texture.
4. Six demonstration-case cards using the validated local sample assets and their actual provenance metadata.

The page must not present placeholder assets, fake metrics, or unsupported cultural claims.

### 3.3 Guided studio

Each studio step uses the same composition:

- step eyebrow, semantic page heading, and one-sentence goal;
- a bounded left image workbench;
- a right control panel;
- optional controls inside collapsed `高级设置`;
- a bottom action bar containing previous, save/status, and next actions.

Images must be fitted into bounded work areas and may not push the main controls below the first screen at 1440 × 900. Result comparisons use side-by-side panels with consistent aspect treatment.

For an existing or demonstration project, step one shows its source preview, classification, rights, and provenance summary. It must not show a blank uploader and create-project form as if no project existed. Replacing a source or starting a new project must be an explicit separate action.

Analysis, recomposition, generation, and export results must restore from persisted project state after reruns, navigation, and application restart. Buttons initiate or replace work; they are not the sole place where results are rendered.

### 3.4 Responsive target and accessibility

The primary acceptance viewports are 1440 × 900 and 1280 × 720. At both sizes:

- primary actions, current status, and the active work result remain reachable without horizontal scrolling;
- keyboard focus is visible;
- controls have practical pointer targets;
- text contrast meets WCAG AA where applicable;
- every studio screen has a semantic H1;
- error messages identify the failing field or operation and provide a recovery action.

## 4. Visual system

### 4.1 Palette

- Ink green: global navigation and dark anchors.
- Rice paper: page and card backgrounds with subtle natural grain.
- Cinnabar: active state, seal marks, and primary actions only.
- Muted gold: progress, hairline borders, small highlights, and selected decorative details.
- Ink black and warm grey: body copy and secondary information.

Gold is an accent, not a large metallic gradient. Decorations must never compete with source imagery or analytical results.

### 4.2 Shape, type, and ornament

- Use restrained square-to-soft card corners and fine borders.
- Use a Chinese display face only for short titles and brand moments; use a legible system Chinese stack for controls and body text.
- Use real existing assets or generated raster assets for visible imagery. Do not synthesize cultural illustrations from CSS shapes, emoji, or placeholder boxes.
- The approved decorative motif is ruyi-cloud line art. It remains low contrast and is never tiled densely.
- The earlier diagonal background-line treatment is prohibited.

### 4.3 Motion

Motion is limited to short state transitions, progress feedback, and panel expansion. The app must respect reduced-motion preferences and avoid decorative continuous animation.

## 5. Processing safety and correctness

### 5.1 Bounded resources

All image entry points must share explicit pixel and edge budgets before allocation or transformation. The implementation plan will centralize these limits; acceptance requires at least:

- source decode budget and decompression-bomb protection;
- canvas width, height, and total-pixel limits;
- scaled and rotated tile intermediate limits;
- perspective-correction output limits;
- generated period/collage limits;
- safe mockup decoding.

Validation occurs before Pillow/OpenCV allocations. Pydantic coercion must not permit non-finite or out-of-range values to bypass these checks. User-facing failures are typed domain errors, not raw `OverflowError`, `MemoryError`, or OpenCV exceptions.

### 5.2 Pipeline correctness

- Enabled preprocessing must feed the extraction pipeline.
- Existing alpha transparency must constrain segmentation rather than being discarded.
- Horizontal and vertical symmetry scoring must handle mixed odd/even dimensions correctly.
- The optional MobileSAM route must be selectable only when available and must clip/validate prompt bounds; OpenCV remains the deterministic fallback.
- Vector export must reject source/destination aliasing that would overwrite the input.
- Tiny or degenerate images must fail with a clear validation message.

### 5.3 Artifact publication

Mockups and all paired provenance sidecars are published atomically. A failed write may leave neither artifact visible as current. Temporary files are scoped to the project workspace and cleaned safely.

## 6. Project, provenance, and export integrity

### 6.1 Versioned project schema

Add a backward-compatible schema migration for source and project metadata. At minimum, a project can retain:

- creator or collecting institution when known;
- source title and source URL;
- licence or rights statement;
- retrieval date;
- bibliography or notes;
- whether AI participated and at which stage;
- original filename, byte size, and SHA-256 digest.

Old projects load with explicit `unknown` or empty optional values rather than failing silently.

### 6.2 Source integrity

Before processing, mockup creation, or export, the stored source file is revalidated against its recorded digest and size. A mismatch blocks the operation, marks dependent outputs stale, and explains how to restore or replace the source. Exports may never silently combine changed bytes with an old digest.

### 6.3 Transactional state

- Failed project creation rolls back its directory and partial metadata.
- Generation artifact creation and confirmation are distinct transactional states.
- A failed confirmation cannot leave an unconfirmed generation as the current exportable artifact.
- Only confirmed, non-stale generated artifacts may feed mockups or exports.
- Export records retain selected artifacts, creation time, manifest digest, and staleness relationship.

### 6.4 Competition export

Export supports a `盲审模式` option that removes project names and original filenames from judge-facing filenames and visible report fields while retaining an internal integrity manifest. Normal export continues to include complete provenance.

Demo validation additionally enforces:

- case IDs and source paths remain inside the demo root;
- category/profile combinations are allowed;
- every asset has the required rights/provenance fields;
- competition-ready validation fails on contradiction, traversal, or missing evidence.

## 7. Generation API safety

### 7.1 Credential isolation

BYOK credentials are keyed by provider and project session. Switching providers must never reuse a credential entered for another provider. Secrets remain only in memory, are masked in UI/logging, and are never persisted to project JSON or exports.

Generation drafts are project-scoped. Switching, opening, or creating a project restores or clears the corresponding prompt, provider, model, mode, and advanced parameters without leaking values from another project.

### 7.2 Request fidelity

Provider adapters preserve the provider-neutral request semantics. Seedream requests must include the user's negative constraints in a supported field or in a clearly delimited prompt segment when the API exposes no dedicated field. The stored request records exactly what was sent after adapter composition.

### 7.3 HTTP and billing ambiguity

- Result downloads follow a small bounded number of redirects and still apply content-type, size, timeout, and safe-decode checks.
- Connectivity, timeout, authentication, quota, validation, and provider 5xx failures map to different user-facing errors.
- Each confirmed generation has a stable local operation ID; use a provider idempotency field when supported.
- After an ambiguous timeout, the UI must not offer an indistinguishable one-click retry that could duplicate a paid call. It shows the uncertain state and requires an explicit new confirmation or provider-status recovery.

Platform-default and BYOK modes keep the same visible provider/model selector. Platform-default credentials are read only from local configuration/environment and missing configuration degrades to a clear setup message.

## 8. Architecture constraints

- Keep the existing separation between UI, workflow service, domain models, processing modules, provider adapters, and persistence.
- Move shared limits and validation into domain/service modules rather than duplicating safety rules in Streamlit widgets.
- Keep rendering functions mostly declarative; session-state normalization and project-scoped draft logic belong in testable helpers.
- Migrate deprecated Streamlit `use_container_width` calls to the supported `width` API.
- Do not import optional CUDA/model dependencies at application startup.
- Keep all caches, temporary artifacts, model files, and virtual environments inside the project or an explicitly configured non-system drive path; do not modify the global Python environment.

## 9. Verification and acceptance

### 9.1 Test discipline

Every defect repair starts with a failing regression test. The release is accepted only when:

- all focused regression tests pass;
- the full existing suite plus new tests passes;
- `pip check` and Python compilation pass in the project virtual environment;
- demo assets pass competition-ready validation;
- no app-flow console error or deprecation warning remains;
- no test writes outside its temporary/project workspace.

Required negative tests include extreme dimensions/scales, malformed numeric values, decompression bombs, mixed-parity symmetry, alpha-aware extraction, changed source files, partial writes, provider credential switching, project switching, redirects, 5xx/network errors, and ambiguous generation timeouts.

### 9.2 End-to-end judge flow

For each of the six demonstrations:

1. Open the case from home.
2. Inspect source rights and category.
3. Run or restore extraction.
4. Run or restore analysis.
5. Create or restore a parameterized pattern.
6. Optionally generate with either provider when configured.
7. Produce a traceable export and, separately, a blind-review export.
8. Reopen the project and verify that state and outputs are restored.

Steps one through five and local export must work with network disabled.

### 9.3 Visual QA

Capture the same states and viewports before and after redesign. Compare the approved sidebar reference and extraction-screen reference together with the implementation screenshots, then fix visible differences in hierarchy, spacing, cropping, typography, borders, and contrast.

Mandatory visual states:

- home at 1440 × 900 and 1280 × 720;
- source/project step;
- extraction comparison;
- analysis with persisted result;
- recomposition with advanced settings collapsed and expanded;
- generation in platform-default and BYOK modes;
- export/provenance summary;
- error, loading, empty, stale-source, and ambiguous-timeout states.

## 10. Delivery checkpoints

Implementation will be split into reviewable checkpoints:

1. Safety and correctness regression tests and fixes.
2. Schema migration, source integrity, transactional artifacts, and export compliance.
3. Provider/session isolation and generation HTTP hardening.
4. Shared visual system and global shell.
5. Home and six-step studio redesign.
6. Full regression run, six-case judge flow, accessibility checks, and visual comparison.

No checkpoint is complete based solely on a screenshot or a passing unit test; both behavior and relevant visual state must be verified.
