# Pattern Reborn Core Hardening Implementation Plan

> 历史文档（2026-10-21 标记）：本文记录比赛阶段的设计或实施计划，不再定义当前产品范围。请以[产品化基线](../../product/README.md)为准。原始内容保留供追溯；数据完整性、来源与密钥保护要求继续有效。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every local image-processing entry point bounded, deterministic, alpha-aware, and safely publishable.

**Architecture:** Add one framework-independent limits module and enforce it at domain boundaries before Pillow/OpenCV allocations. Keep preprocessing, segmentation, analysis, recomposition, vectorization, and mockup publication in their existing modules; connect them through `PatternRebornService` without putting safety logic in Streamlit.

**Tech Stack:** Python 3.11, Pydantic 2, Pillow, OpenCV, NumPy, pytest

**Spec:** `docs/superpowers/specs/2026-08-30-pattern-reborn-hardening-ui-redesign.md`

## Global Constraints

- Windows-first local application; no Docker, WSL, CUDA, database service, or global Python installation.
- Steps one through five and local export must remain usable with the network disabled.
- Validation must occur before Pillow/OpenCV allocation and expose typed Chinese errors.
- Existing APIs remain backward compatible unless this plan explicitly changes their signature.
- Every production change starts with a failing regression test and ends with a focused commit.

---

### Task 1: Central image allocation limits

**Files:**
- Create: `src/pattern_reborn/limits.py`
- Modify: `src/pattern_reborn/images.py`
- Modify: `src/pattern_reborn/patterns.py`
- Test: `tests/test_limits.py`
- Test: `tests/test_images.py`
- Test: `tests/test_patterns.py`

**Interfaces:**
- Produces: `ImageLimitError`, `require_bounded_size(width, height, *, label, max_edge, max_pixels) -> tuple[int, int]`, `require_scaled_size(width, height, scale, *, label, max_pixels) -> tuple[int, int]`.
- Consumes: no application services or UI state.

- [ ] **Step 1: Write failing tests for extreme, coerced, and non-finite sizes**

```python
def test_canvas_rejects_huge_product_before_allocation():
    with pytest.raises(PatternError, match="画布"):
        PatternRequest(layout=LayoutKind.MIRROR, canvas=(1_000_000_000, 1_000_000_000))

@pytest.mark.parametrize("scale", ["2", float("inf"), 1e308])
def test_pattern_rejects_unsafe_scale(scale):
    with pytest.raises((PatternError, ValidationError)):
        PatternRequest(layout=LayoutKind.MIRROR, canvas=(256, 256), scale=scale)
```

- [ ] **Step 2: Run the focused tests and verify they fail without allocating the requested canvas**

Run: `.venv\Scripts\python.exe -m pytest tests/test_limits.py tests/test_patterns.py -q`

Expected: FAIL because `limits.py` is missing or current validators accept the unsafe request.

- [ ] **Step 3: Add centralized limits and pre-allocation guards**

```python
MAX_SOURCE_PIXELS = 16_777_216
MAX_CANVAS_PIXELS = 16_777_216
MAX_CANVAS_EDGE = 8_192
MAX_INTERMEDIATE_PIXELS = 4_194_304
MAX_INTERMEDIATE_EDGE = 8_192

def require_bounded_size(width: object, height: object, *, label: str,
                         max_edge: int, max_pixels: int) -> tuple[int, int]:
    if isinstance(width, bool) or isinstance(height, bool):
        raise ImageLimitError(f"{label}必须为正整数。")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ImageLimitError(f"{label}必须为正整数。")
    if width > max_edge or height > max_edge or width * height > max_pixels:
        raise ImageLimitError(f"{label}超出安全上限。")
    return width, height
```

Use `mode="before"` validators in `PatternRequest`, probe decoded dimensions in `images.py`, and call `require_scaled_size` before `Image.transform` and expanded rotation.

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_limits.py tests/test_images.py tests/test_patterns.py -q`

Expected: PASS; the process remains responsive for every extreme case.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/limits.py src/pattern_reborn/images.py src/pattern_reborn/patterns.py tests/test_limits.py tests/test_images.py tests/test_patterns.py
git commit -m "fix: bound image and pattern allocations"
```

### Task 2: Bound preprocessing and connect it to extraction

**Files:**
- Modify: `src/pattern_reborn/preprocess.py`
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `tests/test_preprocess.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Produces: `PreprocessSettings` with strict finite fields; `ExtractCommand.preprocess: PreprocessSettings`; bounded `perspective_correct`.
- Consumes: size guards from Task 1.

- [ ] **Step 1: Write failing tests for preprocessing types, output bounds, and workflow use**

```python
def test_extract_applies_preprocess_before_segmenting(app_service, source_fixture, spy_segmenter):
    command = ExtractCommand(
        profile=ProfileId.FLAT_COLOR,
        preprocess=PreprocessSettings(brightness=1.2, contrast=1.0, saturation=1.0),
    )
    app_service.extract(_project_id(app_service, source_fixture), command)
    assert spy_segmenter.last_rgb.mean() > spy_segmenter.original_rgb.mean()

def test_perspective_rejects_oversized_output_before_warp(image):
    with pytest.raises(PreprocessError, match="安全上限"):
        perspective_correct(image, VALID_POINTS, (100_000, 100_000))
```

- [ ] **Step 2: Run tests and verify the command currently lacks preprocessing**

Run: `.venv\Scripts\python.exe -m pytest tests/test_preprocess.py tests/test_workflow.py -q`

Expected: FAIL on the new `ExtractCommand.preprocess` field and unsafe perspective output.

- [ ] **Step 3: Implement strict settings and preprocessing dispatch**

```python
class ExtractCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True, validate_assignment=True)
    profile: ProfileId
    hints: SegmentHints | None = None
    strokes: list[MaskStroke] = Field(default_factory=list)
    preprocess: PreprocessSettings = Field(default_factory=PreprocessSettings)

# PatternRebornService.extract
rgb = np.ascontiguousarray(np.asarray(working.convert("RGB")), dtype=np.uint8)
processed = enhance(rgb, command.preprocess)
result = self._segmenter_for(command).segment(processed, command.profile, hints)
```

Persist `command.preprocess` in `pending_extraction.parameters`, and apply `require_bounded_size` before `cv2.warpPerspective`.

- [ ] **Step 4: Run focused workflow and preprocessing tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_preprocess.py tests/test_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/preprocess.py src/pattern_reborn/workflow.py tests/test_preprocess.py tests/test_workflow.py
git commit -m "fix: apply bounded preprocessing during extraction"
```

### Task 3: Preserve source alpha and harden segmentation edge cases

**Files:**
- Modify: `src/pattern_reborn/segmentation.py`
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `tests/test_segmentation.py`
- Modify: `tests/test_mobile_sam_adapter.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Produces: `combine_with_source_alpha(mask: np.ndarray, alpha: np.ndarray) -> np.ndarray`; validated/clipped MobileSAM hints.
- Consumes: `ExtractCommand` from Task 2.

- [ ] **Step 1: Write failing alpha, tiny-image, and MobileSAM bounds tests**

```python
def test_extract_never_restores_pixels_hidden_by_source_alpha(app_service, transparent_source):
    result = app_service.extract(PROJECT_ID, ExtractCommand(profile=ProfileId.SILHOUETTE))
    with Image.open(result.path) as image:
        assert image.getchannel("A").getpixel((0, 0)) == 0

def test_mobile_sam_clips_box_and_points_to_image(fake_predictor, image):
    MobileSamSegmenter(fake_predictor).segment(
        image, ProfileId.ARTIFACT_PHOTO,
        SegmentHints(box=(-8, -4, 999, 999), points=(PromptPoint(999, -5, True),)),
    )
    assert fake_predictor.box.tolist() == [0, 0, image.shape[1], image.shape[0]]
```

- [ ] **Step 2: Verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_workflow.py -q`

Expected: FAIL because workflow discards alpha and MobileSAM forwards invalid coordinates.

- [ ] **Step 3: Combine alpha after segmentation and validate degenerate images**

```python
source_rgba = np.asarray(working.convert("RGBA"), dtype=np.uint8)
rgb = np.ascontiguousarray(source_rgba[:, :, :3])
source_alpha = source_rgba[:, :, 3]
mask = np.where(source_alpha > 0, mask, 0).astype(np.uint8)
if mask.shape[0] < 2 or mask.shape[1] < 2:
    raise WorkflowError("图像尺寸过小，至少需要 2×2 像素。")
```

Clip MobileSAM hints using existing `_clip_point` and `_resolve_roi`; reject a clipped-empty ROI with `SegmentationError`.

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/segmentation.py src/pattern_reborn/workflow.py tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_workflow.py
git commit -m "fix: preserve alpha and validate segmentation hints"
```

### Task 4: Route optional MobileSAM without weakening offline fallback

**Files:**
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `app.py`
- Modify: `src/pattern_reborn/ui/studio.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/ui/test_studio.py`
- Modify: `tests/test_capabilities.py`

**Interfaces:**
- Produces: `SegmentationBackend` selection recorded in extraction metadata; constructor keyword `mobile_sam_segmenter: Segmenter | None = None` on `PatternRebornService`.
- Consumes: validated MobileSAM adapter from Task 3 and existing `Capabilities.mobile_sam`.

- [ ] **Step 1: Write failing routing tests**

```python
def test_extract_routes_to_requested_mobile_sam_when_available(service_with_two_segmenters):
    service_with_two_segmenters.extract(PROJECT_ID, ExtractCommand(
        profile=ProfileId.ARTIFACT_PHOTO, backend="mobile_sam"
    ))
    assert service_with_two_segmenters.mobile.calls == 1

def test_extract_rejects_unavailable_mobile_sam_without_importing_torch(app_service):
    with pytest.raises(WorkflowError, match="不可用"):
        app_service.extract(PROJECT_ID, ExtractCommand(
            profile=ProfileId.FLAT_COLOR, backend="mobile_sam"
        ))
```

- [ ] **Step 2: Verify the tests fail because only OpenCV is wired**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_capabilities.py tests/ui/test_studio.py -q`

Expected: FAIL on missing backend field/routing.

- [ ] **Step 3: Add explicit backend selection with lazy optional construction**

```python
class SegmentationBackend(str, Enum):
    OPENCV = "opencv"
    MOBILE_SAM = "mobile_sam"

def _segmenter_for(self, command: ExtractCommand) -> Segmenter:
    if command.backend is SegmentationBackend.MOBILE_SAM:
        if self._mobile_sam_segmenter is None:
            raise WorkflowError("MobileSAM 当前不可用，请改用 OpenCV。")
        return self._mobile_sam_segmenter
    return self._segmenter
```

The studio selector appears only when the capability is available; otherwise show OpenCV as the active fallback. Do not import torch or MobileSAM during startup capability detection.

- [ ] **Step 4: Run routing and startup tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_capabilities.py tests/ui/test_studio.py tests/smoke/test_app_startup.py -q`

Expected: PASS with no top-level optional-model import.

- [ ] **Step 5: Commit**

```powershell
git add app.py src/pattern_reborn/workflow.py src/pattern_reborn/ui/studio.py tests/test_workflow.py tests/test_capabilities.py tests/ui/test_studio.py
git commit -m "feat: route optional MobileSAM with OpenCV fallback"
```

### Task 5: Correct symmetry and protect vector source files

**Files:**
- Modify: `src/pattern_reborn/analysis.py`
- Modify: `src/pattern_reborn/vectorize.py`
- Modify: `tests/test_analysis.py`
- Modify: `tests/test_vectorize.py`

**Interfaces:**
- Produces: parity-safe centered symmetry comparison; alias-safe `Vectorizer.vectorize`.
- Consumes: no new interfaces.

- [ ] **Step 1: Write failing mixed-parity and alias tests**

```python
def test_symmetry_is_perfect_for_mixed_parity_rectangle():
    mask = np.full((2, 3), 255, dtype=np.uint8)
    report = analyze_symmetry(mask)
    assert report.horizontal_score == pytest.approx(1.0)
    assert report.vertical_score == pytest.approx(1.0)

def test_vectorize_rejects_destination_aliasing_source(vectorizer, png):
    before = png.read_bytes()
    with pytest.raises(VectorizeError, match="不能覆盖"):
        vectorizer.vectorize(png, png)
    assert png.read_bytes() == before
```

- [ ] **Step 2: Verify both regressions fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_analysis.py tests/test_vectorize.py -q`

Expected: FAIL on the 2×3 symmetry score and same-path vector destination.

- [ ] **Step 3: Compare parity-safe masks and reject resolved-path aliases**

```python
left = source.resolve()
right = destination.resolve()
if left == right:
    raise VectorizeError("SVG 目标路径不能覆盖源 PNG。")

# analysis: pad by the exact before/after deltas rather than symmetric floor division
pad_x = target_width - width
pad_y = target_height - height
centered = np.pad(mask, ((pad_y // 2, pad_y - pad_y // 2),
                         (pad_x // 2, pad_x - pad_x // 2)))
```

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_analysis.py tests/test_vectorize.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/analysis.py src/pattern_reborn/vectorize.py tests/test_analysis.py tests/test_vectorize.py
git commit -m "fix: correct symmetry and protect vector inputs"
```

### Task 6: Safely decode and atomically publish mockups

**Files:**
- Modify: `src/pattern_reborn/mockups.py`
- Modify: `src/pattern_reborn/images.py`
- Modify: `tests/test_mockups.py`

**Interfaces:**
- Produces: `save_mockup_bundle_atomic(result: MockupResult, destination: Path) -> None`.
- Consumes: safe decode and size limits from Task 1.

- [ ] **Step 1: Write failing decompression-bomb and rollback tests**

```python
def test_mockup_rejects_decompression_bomb(monkeypatch, template, artwork):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 4)
    with pytest.raises(MockupError, match="图像"):
        compose_mockup(template, artwork)

def test_mockup_bundle_rolls_back_when_sidecar_replace_fails(monkeypatch, result, destination):
    monkeypatch.setattr(os, "replace", fail_on_second_replace)
    with pytest.raises(MockupError):
        save_composed_mockup(result, destination)
    assert not destination.exists()
    assert not destination.with_suffix(".json").exists()
```

- [ ] **Step 2: Verify current direct decode and two-file publication fail the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mockups.py -q`

Expected: FAIL.

- [ ] **Step 3: Use the safe loader and stage the PNG/JSON bundle**

```python
staging = destination.parent / f".{destination.stem}.{uuid4().hex}.tmp"
staging.mkdir()
save_png_atomic(result.image, staging / destination.name)
_write_json_atomic(staging / destination.with_suffix(".json").name, result.provenance)
os.replace(staging, committed_bundle_dir)
```

Expose final PNG and sidecar from a single committed bundle or use a journaled rollback that guarantees neither final path remains after failure. Preserve the public artifact ID expected by workflow/export.

- [ ] **Step 4: Run mockup and workflow tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mockups.py tests/test_workflow.py tests/test_exporter.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/mockups.py src/pattern_reborn/images.py tests/test_mockups.py
git commit -m "fix: publish mockups as safe atomic bundles"
```

### Task 7: Core hardening checkpoint

**Files:**
- Modify only if verification exposes a regression in files changed by Tasks 1–6.

**Interfaces:**
- Produces: a green local-processing checkpoint for downstream plans.
- Consumes: all interfaces in this plan.

- [ ] **Step 1: Run the complete local-processing subset**

Run: `.venv\Scripts\python.exe -m pytest tests/test_limits.py tests/test_images.py tests/test_preprocess.py tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_analysis.py tests/test_patterns.py tests/test_vectorize.py tests/test_mockups.py tests/test_workflow.py tests/integration/test_offline_pipeline.py -q`

Expected: PASS.

- [ ] **Step 2: Run compile and dependency checks**

Run: `.venv\Scripts\python.exe -m compileall -q app.py src tests scripts`

Expected: exit code 0.

Run: `.venv\Scripts\python.exe -m pip check`

Expected: `No broken requirements found.`

- [ ] **Step 3: Verify the tree contains no generated test artifacts**

Run: `git status --short`

Expected: no untracked runtime image, cache, project, or output directories.

- [ ] **Step 4: Commit only if checkpoint fixes were required**

```powershell
git add src/pattern_reborn/limits.py src/pattern_reborn/images.py src/pattern_reborn/patterns.py src/pattern_reborn/preprocess.py src/pattern_reborn/segmentation.py src/pattern_reborn/analysis.py src/pattern_reborn/vectorize.py src/pattern_reborn/mockups.py src/pattern_reborn/workflow.py app.py tests
git commit -m "test: close core hardening regressions"
```
