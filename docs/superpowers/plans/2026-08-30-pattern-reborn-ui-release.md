# Pattern Reborn UI Redesign and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved rice-paper, ink-green, cinnabar, and restrained-gold six-step experience with project-scoped state and restored results.

**Architecture:** Keep Streamlit as the renderer but split the 700-line studio into a thin router, shared components, state helpers, result presenters, and step modules. Use the approved screenshots and existing project assets as visual references, place all shared tokens in `theme.css`, and keep workflow logic in the service layer.

**Tech Stack:** Python 3.11, Streamlit 1.x, HTML/CSS injected through existing theme helpers, Pillow assets, pytest Streamlit AppTest, in-app browser visual QA

**Spec:** `docs/superpowers/specs/2026-08-30-pattern-reborn-hardening-ui-redesign.md`

## Global Constraints

- Preserve Streamlit; do not initialize a React/Sites template.
- Match the approved sidebar and extraction references; diagonal background lines are prohibited.
- Use real existing or generated raster assets for visible imagery; no emoji, placeholder boxes, CSS drawings, or new handcrafted SVG illustrations.
- Cinnabar is reserved for the active step and primary CTA; never use cinnabar body text directly on ink green.
- Primary viewports are 1440 × 900 and 1280 × 720.
- Advanced algorithm parameters start collapsed.
- Replace every deprecated `use_container_width` call with `width="stretch"` or `width="content"`.
- Every production change starts with a failing regression test and ends with a focused commit.

---

### Task 1: Introduce project-scoped UI state helpers

**Files:**
- Create: `src/pattern_reborn/ui/state.py`
- Modify: `src/pattern_reborn/ui/home.py`
- Modify: `src/pattern_reborn/ui/studio.py`
- Create: `tests/ui/test_state.py`
- Modify: `tests/ui/test_studio.py`
- Modify: `tests/ui/test_generation_controls.py`

**Interfaces:**
- Produces: `activate_project(session, project_id)`, `clear_active_project(session)`, `draft_key(project_id, provider)`, `get_project_draft`, `save_project_draft`, and provider-scoped credential helpers.
- Consumes: provider IDs and Streamlit-compatible mutable session mappings.

- [ ] **Step 1: Write failing project/provider isolation tests**

```python
def test_generation_drafts_are_scoped_by_project_and_provider():
    session = {}
    save_project_draft(session, "project-a", ProviderId.SEEDREAM, {"prompt": "A"})
    save_project_draft(session, "project-b", ProviderId.SEEDREAM, {"prompt": "B"})
    assert get_project_draft(session, "project-a", ProviderId.SEEDREAM)["prompt"] == "A"
    assert get_project_draft(session, "project-b", ProviderId.SEEDREAM)["prompt"] == "B"

def test_byok_secret_is_never_reused_for_another_provider():
    session = {}
    set_byok_secret(session, "project-a", ProviderId.SEEDREAM, SecretStr("seedream"))
    assert get_byok_secret(session, "project-a", ProviderId.QWEN) is None
```

- [ ] **Step 2: Run tests and verify global `unsaved`/`byok_secret` leak**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_state.py tests/ui/test_studio.py tests/ui/test_generation_controls.py -q`

Expected: FAIL because `state.py` does not exist and current keys are session-global.

- [ ] **Step 3: Implement one namespaced state tree**

```python
def _projects(session: MutableMapping[str, object]) -> dict[str, dict[str, object]]:
    value = session.setdefault("project_ui", {})
    if not isinstance(value, dict):
        value = {}
        session["project_ui"] = value
    return value

def draft_key(project_id: str, provider: ProviderId) -> str:
    return f"{project_id}:{provider.value}"

def set_byok_secret(session, project_id, provider, secret):
    session.setdefault("byok_credentials", {})[draft_key(project_id, provider)] = secret
```

`activate_project` clears widget keys that belong to the previous project, restores `current_step`, and leaves other project drafts in their namespace. `clear_active_project` removes active identifiers and in-memory credentials without deleting persisted projects.

- [ ] **Step 4: Run state and generation UI tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_state.py tests/ui/test_studio.py tests/ui/test_generation_controls.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/state.py src/pattern_reborn/ui/home.py src/pattern_reborn/ui/studio.py tests/ui/test_state.py tests/ui/test_studio.py tests/ui/test_generation_controls.py
git commit -m "fix: isolate project and provider UI state"
```

### Task 2: Build reusable shell and studio components

**Files:**
- Create: `src/pattern_reborn/ui/components.py`
- Modify: `src/pattern_reborn/ui/theme.py`
- Modify: `src/pattern_reborn/ui/assets/theme.css`
- Reuse: `src/pattern_reborn/ui/assets/ruyi_cloud.svg`
- Modify: `tests/ui/test_theme.py`
- Create: `tests/ui/test_components.py`

**Interfaces:**
- Produces: `render_brand_lockup()`, `render_step_rail(active_step)`, `render_step_header(number, title, mode)`, `render_status_chip`, `render_image_panel`, `render_bottom_actions`.
- Consumes: six `StepId` values and the approved brand copy.

- [ ] **Step 1: Write failing visual-token and component tests**

```python
def test_theme_defines_approved_tokens_and_no_diagonal_background():
    css = load_theme_css()
    assert "--ink-green" in css and "--rice-paper" in css and "--cinnabar" in css
    assert "linear-gradient" not in css
    assert "repeating-linear-gradient" not in css

def test_sidebar_lockup_contains_full_bilingual_brand(app_test):
    assert "纹启新生" in app_test.markdown[0].value
    assert "PATTERN REBORN" in app_test.markdown[0].value
```

- [ ] **Step 2: Run theme/component tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_theme.py tests/ui/test_components.py -q`

Expected: FAIL on missing components and incomplete lockup.

- [ ] **Step 3: Implement the approved shell and token system**

```css
:root {
  --ink-green: #173f35;
  --ink-green-soft: #245447;
  --rice-paper: #f4efe3;
  --paper-card: #fbf8ef;
  --cinnabar: #b83a2d;
  --gilded-gold: #caa85e;
  --ink: #23332d;
  --muted-ink: #6c746e;
  --hairline: rgba(120, 98, 52, 0.22);
  --shadow: 0 18px 48px rgba(29, 45, 39, 0.10);
}
```

```python
def render_step_header(number: int, title: str, mode: str) -> None:
    st.markdown(
        f'<header class="step-header"><p>第{number}步</p><h1>{escape(title)}</h1>'
        f'<span>{escape(mode)}</span></header>', unsafe_allow_html=True,
    )
```

The sidebar uses the existing approved ruyi-cloud asset at low opacity, the full lockup, `非遗纹启` seal inscription, a gold rail, and a bottom history entry. Use paper grain through low-opacity radial/noise raster treatment, not diagonal lines.

- [ ] **Step 4: Run component tests and check contrast constants**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_theme.py tests/ui/test_components.py -q`

Expected: PASS; paper/green and white/cinnabar text combinations satisfy WCAG AA in the test helper.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/components.py src/pattern_reborn/ui/theme.py src/pattern_reborn/ui/assets/theme.css tests/ui/test_theme.py tests/ui/test_components.py
git commit -m "feat: build heritage studio visual system"
```

### Task 3: Redesign the home page around judge entry points

**Files:**
- Modify: `src/pattern_reborn/ui/home.py`
- Modify: `src/pattern_reborn/ui/assets/theme.css`
- Modify: `tests/ui/test_home.py`

**Interfaces:**
- Produces: hero, three-card recent history, nine-category grid, and six validated demo cards.
- Consumes: `activate_project`, `DemoCase.rights`, and shared components.

- [ ] **Step 1: Write failing hierarchy and navigation tests**

```python
def test_home_orders_hero_history_categories_and_six_demos(app_test):
    text = "\n".join(item.value for item in app_test.markdown)
    assert text.index("让传统纹样进入当代设计") < text.index("最近项目")
    assert text.index("最近项目") < text.index("九类非遗纹样")
    assert len([button for button in app_test.button if button.key.startswith("demo-open-")]) == 6

def test_recent_project_card_restores_its_saved_step(app_test, project):
    app_test.button(key=f"recent-{project.id}").click().run()
    assert app_test.session_state["project_id"] == project.id
```

- [ ] **Step 2: Run home tests and capture expected failures**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_home.py -q`

Expected: FAIL on the new hierarchy/card semantics.

- [ ] **Step 3: Implement the home composition**

```python
st.markdown('<section class="home-hero"><p class="eyebrow">非遗纹样智能创作工坊</p>'
            '<h1>让传统纹样进入当代设计</h1>'
            '<p>从来源记录、智能提取到可追溯导出。</p></section>', unsafe_allow_html=True)
primary, secondary = st.columns([1, 1])
with primary:
    start = st.button("开始创作", type="primary", width="stretch")
with secondary:
    view_demos = st.button("查看演示案例", width="stretch")
```

Recent cards show name/category/update/current step. Category cards use the nine real catalog entries. Demo cards show actual image, title, institution/creator, and licence; opening one creates a fully attributed project.

- [ ] **Step 4: Run home UI tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_home.py tests/test_demo_assets.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/home.py src/pattern_reborn/ui/assets/theme.css tests/ui/test_home.py
git commit -m "feat: redesign the competition home page"
```

### Task 4: Split studio routing and add persistent presenters

**Files:**
- Modify: `src/pattern_reborn/ui/studio.py`
- Create: `src/pattern_reborn/ui/presenters.py`
- Create: `src/pattern_reborn/ui/steps/__init__.py`
- Create: `src/pattern_reborn/ui/steps/source.py`
- Create: `src/pattern_reborn/ui/steps/extraction.py`
- Create: `src/pattern_reborn/ui/steps/analysis.py`
- Create: `src/pattern_reborn/ui/steps/recomposition.py`
- Create: `src/pattern_reborn/ui/steps/generation.py`
- Create: `src/pattern_reborn/ui/steps/export.py`
- Modify: `tests/ui/test_studio.py`
- Create: `tests/ui/test_presenters.py`

**Interfaces:**
- Produces: one `render_*_step(context: StudioContext) -> None` per step; `load_analysis_view`, `current_pattern_paths`, `current_generation_records`, `current_mockup_paths`.
- Consumes: service/project/knowledge/capabilities/provider config through immutable `StudioContext`.

- [ ] **Step 1: Write failing persisted-result presenter tests**

```python
def test_analysis_presenter_reads_confirmed_json_after_rerun(service, analyzed_project):
    view = load_analysis_view(service.repository, analyzed_project)
    assert view.palette
    assert view.symmetry.vertical_score >= 0

def test_studio_renders_saved_pattern_without_pressing_recompose(studio_at_recomposition):
    assert any("重组结果" in image.caption for image in studio_at_recomposition.image)
```

- [ ] **Step 2: Run presenter/studio tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_presenters.py tests/ui/test_studio.py -q`

Expected: FAIL because results are currently rendered only inside button branches.

- [ ] **Step 3: Create a thin router and result presenters**

```python
@dataclass(frozen=True, slots=True)
class StudioContext:
    service: PatternRebornService
    project: ProjectRecord | None
    knowledge: KnowledgeCatalog
    capabilities: Capabilities
    provider_config: ProviderConfig

STEP_RENDERERS = {
    StepId.UPLOAD: render_source_step,
    StepId.EXTRACTION: render_extraction_step,
    StepId.ANALYSIS: render_analysis_step,
    StepId.RECOMPOSITION: render_recomposition_step,
    StepId.GENERATION: render_generation_step,
    StepId.EXPORT: render_export_step,
}
```

Presenters read only confirmed, non-stale artifacts and return typed view models. Step modules render result panels on every rerun, independently of whether an action button fired.

- [ ] **Step 4: Run studio, workflow, and presenter tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_presenters.py tests/ui/test_studio.py tests/test_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/studio.py src/pattern_reborn/ui/presenters.py src/pattern_reborn/ui/steps tests/ui/test_presenters.py tests/ui/test_studio.py
git commit -m "refactor: split studio steps and restore results"
```

### Task 5: Redesign source and extraction workbenches

**Files:**
- Modify: `src/pattern_reborn/ui/steps/source.py`
- Modify: `src/pattern_reborn/ui/steps/extraction.py`
- Modify: `src/pattern_reborn/ui/components.py`
- Modify: `src/pattern_reborn/ui/assets/theme.css`
- Modify: `tests/ui/test_studio.py`

**Interfaces:**
- Produces: existing-project summary card, explicit new/replace actions, bounded source/result comparison, collapsed extraction settings.
- Consumes: source-rights model, preprocessing/backend options, and persisted pending extraction.

- [ ] **Step 1: Write failing existing-project and bounded-workbench tests**

```python
def test_existing_project_source_step_has_summary_not_create_form(studio_existing_project):
    assert "来源与权利" in studio_existing_project.markdown_text
    assert not studio_existing_project.get("file_uploader")
    assert studio_existing_project.button(key="source-new-project")

def test_extraction_uses_side_by_side_bounded_panels(studio_at_extraction):
    assert "workbench-grid" in studio_at_extraction.markdown_text
    assert "高级设置" in [item.label for item in studio_at_extraction.expander]

def test_invalid_new_project_shows_actionable_error(studio_new_project):
    studio_new_project.button(key="source-create").click().run()
    assert any("请填写项目名称" in item.value for item in studio_new_project.error)
```

- [ ] **Step 2: Run studio tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_studio.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement the approved layouts**

```python
render_step_header(1, "上传与分类", "来源建档")
if context.project is not None:
    render_source_summary(context.project)
    left, right = st.columns(2)
    with left: st.button("新建项目", key="source-new-project")
    with right: st.button("替换来源", key="source-replace")
    return
```

Extraction uses `[1.35, 0.85]` workbench/control columns, source/result side-by-side inside the workbench, and puts crop, enhancement, backend, manual coordinates, and brush values in a collapsed advanced expander. The primary action reads `确认并分析 →`.

- [ ] **Step 4: Run source/extraction tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_studio.py tests/test_preprocess.py tests/test_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/steps/source.py src/pattern_reborn/ui/steps/extraction.py src/pattern_reborn/ui/components.py src/pattern_reborn/ui/assets/theme.css tests/ui/test_studio.py
git commit -m "feat: redesign source and extraction steps"
```

### Task 6: Redesign analysis and recomposition around persistent results

**Files:**
- Modify: `src/pattern_reborn/ui/steps/analysis.py`
- Modify: `src/pattern_reborn/ui/steps/recomposition.py`
- Modify: `src/pattern_reborn/ui/presenters.py`
- Modify: `src/pattern_reborn/ui/assets/theme.css`
- Modify: `tests/ui/test_studio.py`
- Modify: `tests/ui/test_presenters.py`

**Interfaces:**
- Produces: palette swatches, traditional-color matches, contour/symmetry cards, bounded recomposition preview, collapsed algorithm controls.
- Consumes: persisted analysis JSON and current non-stale pattern artifacts.

- [ ] **Step 1: Add failing restored-analysis and advanced-settings tests**

```python
def test_analysis_step_restores_palette_and_scores(studio_analyzed_project):
    assert "传统色匹配" in studio_analyzed_project.markdown_text
    assert "对称性" in studio_analyzed_project.markdown_text

def test_recomposition_advanced_controls_start_collapsed(studio_at_recomposition):
    advanced = next(item for item in studio_at_recomposition.expander if item.label == "高级设置")
    assert advanced.expanded is False
```

- [ ] **Step 2: Verify current button-only rendering fails**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_studio.py tests/ui/test_presenters.py -q`

Expected: FAIL.

- [ ] **Step 3: Render saved analysis/pattern first, actions second**

```python
view = load_analysis_view(context.service.repository, project)
if view is not None:
    render_palette_swatches(view.palette, view.color_matches)
    render_metric_cards(view.contours, view.symmetry)
else:
    st.info("尚未生成分析结果。")

pattern_paths = current_pattern_paths(context.service.repository, project)
if pattern_paths:
    render_image_panel(pattern_paths[0], "重组结果")
```

Layout choice and a small set of primary controls stay visible; seed, spacing, scale, angle, palette substitution, and exact canvas values live in `高级设置` with safe UI maxima matching domain limits.

- [ ] **Step 4: Run analysis/recomposition tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_studio.py tests/ui/test_presenters.py tests/test_analysis.py tests/test_patterns.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/steps/analysis.py src/pattern_reborn/ui/steps/recomposition.py src/pattern_reborn/ui/presenters.py src/pattern_reborn/ui/assets/theme.css tests/ui/test_studio.py tests/ui/test_presenters.py
git commit -m "feat: redesign analysis and recomposition steps"
```

### Task 7: Redesign generation with provider-scoped credentials and uncertain state

**Files:**
- Modify: `src/pattern_reborn/ui/steps/generation.py`
- Modify: `src/pattern_reborn/ui/state.py`
- Modify: `src/pattern_reborn/ui/presenters.py`
- Modify: `tests/ui/test_generation_controls.py`
- Modify: `tests/ui/test_studio.py`

**Interfaces:**
- Produces: explicit provider/model cards in both credential modes; provider-specific password fields; generation confirmation summary; uncertain-operation recovery panel.
- Consumes: hardened generation service and lifecycle records.

- [ ] **Step 1: Write failing credential-switch and ambiguous-timeout tests**

```python
def test_switching_provider_changes_byok_widget_key(studio_at_generation):
    seedream_key = _password_key(studio_at_generation)
    _select_provider(studio_at_generation, "Qwen Image 3.0 Pro")
    assert _password_key(studio_at_generation) != seedream_key

def test_uncertain_operation_disables_plain_confirm_retry(studio_uncertain_generation):
    assert "可能已经产生费用" in studio_uncertain_generation.markdown_text
    assert not studio_uncertain_generation.button(key="generation-confirm")
    assert studio_uncertain_generation.button(key="generation-new-operation")
```

- [ ] **Step 2: Run generation UI tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_generation_controls.py tests/ui/test_studio.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement explicit provider/mode switching and confirmation states**

```python
credential_key = f"byok:{project.id}:{provider_id.value}"
entered = st.text_input("访问密钥", type="password", key=credential_key)

if uncertain_record is not None:
    st.warning("本次请求状态不确定，可能已经产生费用。请先核对平台记录。")
    st.button("明确发起一次新请求", key="generation-new-operation")
else:
    st.button("确认生成", type="primary", key="generation-confirm")
```

The model selector stays visible in both modes; Seedream and Qwen are manually switchable. Persisted confirmed images render on every visit with a visible `AI 生成` label and provider/model metadata.

- [ ] **Step 4: Run generation UI and service tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_generation_controls.py tests/ui/test_studio.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/steps/generation.py src/pattern_reborn/ui/state.py src/pattern_reborn/ui/presenters.py tests/ui/test_generation_controls.py tests/ui/test_studio.py
git commit -m "feat: redesign safe generation controls"
```

### Task 8: Redesign export, provenance, and bottom navigation

**Files:**
- Modify: `src/pattern_reborn/ui/steps/export.py`
- Modify: `src/pattern_reborn/ui/components.py`
- Modify: `src/pattern_reborn/ui/studio.py`
- Modify: `src/pattern_reborn/ui/assets/theme.css`
- Modify: `tests/ui/test_studio.py`
- Create: `tests/ui/test_export_controls.py`

**Interfaces:**
- Produces: current artwork/mockup gallery, traceable/blind export selector, export history, and consistent previous/save/next bar.
- Consumes: persisted `ExportRecord` and only confirmed non-stale artwork IDs.

- [ ] **Step 1: Write failing export and navigation tests**

```python
def test_export_step_offers_normal_and_blind_review_modes(studio_at_export):
    labels = [item.label for item in studio_at_export.radio]
    assert "导出模式" in labels
    assert {"完整溯源", "盲审模式"}.issubset(set(_radio_options(studio_at_export, "导出模式")))

def test_bottom_bar_contains_previous_status_and_next(studio_at_analysis):
    assert studio_at_analysis.button(key="nav-previous")
    assert "已保存" in studio_at_analysis.markdown_text
    assert studio_at_analysis.button(key="nav-next")
```

- [ ] **Step 2: Run export/studio tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_export_controls.py tests/ui/test_studio.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement export summary and common bottom bar**

```python
mode = st.radio("导出模式", ["完整溯源", "盲审模式"], horizontal=True)
selection = ExportSelection(
    source=True, extracted=True, patterns=True, generations=True,
    mockups=True, svg=True, report=True,
    blind_review=mode == "盲审模式",
)
if st.button("生成导出包", type="primary", width="stretch"):
    result = context.service.export(project.id, selection)
    st.success(f"导出完成：{result.package.name}")
```

Render recent non-stale export records with time/mode/manifest digest. `render_bottom_actions` changes steps only after checking prerequisites and persists `current_step` through the service.

- [ ] **Step 4: Run export, navigation, and workflow tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_export_controls.py tests/ui/test_studio.py tests/test_exporter.py tests/test_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui/steps/export.py src/pattern_reborn/ui/components.py src/pattern_reborn/ui/studio.py src/pattern_reborn/ui/assets/theme.css tests/ui/test_export_controls.py tests/ui/test_studio.py
git commit -m "feat: redesign export and studio navigation"
```

### Task 9: Remove deprecations and verify semantic/accessibility basics

**Files:**
- Modify: `src/pattern_reborn/ui/home.py`
- Modify: `src/pattern_reborn/ui/components.py`
- Modify: `src/pattern_reborn/ui/steps/*.py`
- Modify: `src/pattern_reborn/ui/assets/theme.css`
- Modify: `tests/ui/test_theme.py`
- Modify: `tests/ui/test_home.py`
- Modify: `tests/ui/test_studio.py`
- Modify: `tests/smoke/test_app_startup.py`

**Interfaces:**
- Produces: zero `use_container_width` calls, semantic H1 per page, visible focus, safe control widths.
- Consumes: all redesigned screens.

- [ ] **Step 1: Add failing static and AppTest checks**

```python
def test_ui_source_has_no_removed_use_container_width_api():
    source = "\n".join(path.read_text("utf-8") for path in UI_ROOT.rglob("*.py"))
    assert "use_container_width" not in source

def test_every_studio_step_has_one_h1(studio_steps):
    for app in studio_steps:
        assert app.markdown_text.count("<h1") == 1
```

- [ ] **Step 2: Run UI/smoke tests and verify current deprecation usage fails**

Run: `.venv\Scripts\python.exe -m pytest tests/ui tests/smoke/test_app_startup.py -q`

Expected: FAIL until old image/button width arguments and headings are replaced.

- [ ] **Step 3: Migrate width API and add focus/reduced-motion CSS**

```css
:where(button, input, textarea, select, [tabindex]):focus-visible {
  outline: 3px solid var(--gilded-gold);
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
}
```

Use `st.image(str(image_path), width="stretch")` in bounded parents and `st.button("继续", width="stretch")` only where the component should fill its column.

- [ ] **Step 4: Run UI and startup tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui tests/smoke/test_app_startup.py -q`

Expected: PASS with no deprecation warning in captured startup output.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/ui tests/ui tests/smoke/test_app_startup.py
git commit -m "fix: remove UI deprecations and improve accessibility"
```

### Task 10: Full regression and six-case judge flow

**Files:**
- Modify: `tests/integration/test_offline_pipeline.py`
- Modify only production files if this verification identifies an in-scope defect.
- Update: `docs/acceptance/competition-checklist.md` with actual dated evidence.

**Interfaces:**
- Produces: verified release candidate before visual sign-off.
- Consumes: all prior plans.

- [ ] **Step 1: Add a failing six-demo offline judge-flow parametrization**

```python
@pytest.mark.parametrize("case_id", COMPETITION_CASE_IDS)
def test_each_demo_reaches_traceable_export_offline(app_service, demo_root, case_id):
    case = load_demo_fixture(demo_root, case_id)
    project = create_demo_project(app_service, case)
    extraction = app_service.extract(project.id, case.extract_command)
    app_service.confirm_extraction(project.id, extraction.artifact_id)
    app_service.analyze(project.id)
    app_service.compose(project.id, case.pattern_request)
    exported = app_service.export(project.id, ExportSelection.all_offline())
    reopened = app_service.load_project(project.id)
    assert exported.package.is_dir()
    assert StepId.EXPORT in reopened.confirmed_steps
```

- [ ] **Step 2: Run the new integration test and verify unsupported fixtures or state restoration fail first**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_offline_pipeline.py::test_each_demo_reaches_traceable_export_offline -q`

Expected: FAIL until all six demo fixture helpers and restored export state satisfy the new contract.

- [ ] **Step 3: Add the six demo fixture loader and minimal production corrections**

```python
def load_demo_fixture(root: Path, case_id: str) -> DemoWorkflowFixture:
    case_dir = root / case_id
    metadata = json.loads((case_dir / "metadata.json").read_text(encoding="utf-8"))
    return DemoWorkflowFixture.from_metadata(case_dir, metadata)
```

Keep fixture parsing inside test support. Any production correction must be limited to a behavior already required by the approved specification.

- [ ] **Step 4: Run the entire test suite**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: all existing 280 tests plus new regression tests PASS.

- [ ] **Step 5: Run dependency, compilation, and demo checks**

Run: `.venv\Scripts\python.exe -m pip check`

Expected: `No broken requirements found.`

Run: `.venv\Scripts\python.exe -m compileall -q app.py src tests scripts`

Expected: exit code 0.

Run: `.venv\Scripts\python.exe scripts\validate_demo_assets.py data\demo --competition-ready`

Expected: `校验通过。`

- [ ] **Step 6: Execute the six-case offline judge-flow test**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_offline_pipeline.py -q --maxfail=1`

Expected: all six cases complete source → extraction → analysis → recomposition → traceable export with network disabled; reopening restores state.

- [ ] **Step 7: Update acceptance evidence and commit**

```powershell
git add docs/acceptance/competition-checklist.md src/pattern_reborn tests/integration/test_offline_pipeline.py
git commit -m "test: verify competition judge workflows"
```

### Task 11: Browser visual comparison and sign-off

**Files:**
- Modify only UI/CSS/assets implicated by visible differences.
- Save evidence outside the repository under the current Codex visualization directory.

**Interfaces:**
- Produces: final screenshots for home and all six steps at 1440 × 900 and 1280 × 720.
- Consumes: approved references and the running local app.

- [ ] **Step 1: Start the app using the project-isolated script**

Run: `powershell -ExecutionPolicy Bypass -File scripts\run.ps1`

Expected: Streamlit starts from `.venv` without installing or modifying global packages.

- [ ] **Step 2: Capture all mandatory visual states in the in-app browser**

Capture home, source summary, extraction comparison, restored analysis, recomposition collapsed/expanded, generation platform/BYOK, export/provenance, loading, error, stale-source, and uncertain-timeout at both target viewports.

- [ ] **Step 3: Compare each implementation capture with the approved references together**

Use these references in the visual comparison input:

```text
C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-a2c2eb2a-0f60-40b4-94bc-0ea43c0e6147.png
C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-3b611d34-986e-47f1-8476-afb6d8402393.png
```

Reject and repair: cropped images, controls below the intended workbench, inconsistent card padding, diagonal backgrounds, incomplete branding, poor text contrast, broken progress rail, wrong active color, or oversized ornament.

- [ ] **Step 4: Re-run UI and full tests after visual repairs**

Run: `.venv\Scripts\python.exe -m pytest tests/ui tests/smoke/test_app_startup.py -q`

Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit final visual corrections**

```powershell
git add src/pattern_reborn/ui tests/ui docs/acceptance/competition-checklist.md
git commit -m "style: finish competition visual polish"
```

- [ ] **Step 6: Request a final code review**

Use `superpowers:requesting-code-review` against the full diff from commit `1a1eb52`, address confirmed findings, then repeat the complete verification commands before declaring completion.
