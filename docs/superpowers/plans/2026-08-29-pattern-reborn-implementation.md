# Pattern Reborn MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-local, offline-capable six-step studio that extracts, analyzes, recomposes, generates, mockups, and exports traceable Chinese traditional-pattern projects.

**Architecture:** A thin Streamlit interface calls a framework-independent workflow service. The service coordinates typed domain models, an atomic JSON project repository, deterministic OpenCV/Pillow processing modules, optional MobileSAM/VTracer capabilities, and provider adapters for Seedream and Qwen Image. Source files are immutable; each confirmed stage produces a versioned artifact and invalidates dependent outputs when changed.

**Tech Stack:** Python 3.11, Streamlit, Pydantic 2, OpenCV, Pillow, NumPy, HTTPX, VTracer, optional MobileSAM, optional `streamlit-drawable-konva`, Pytest, Respx.

**Spec:** `docs/superpowers/specs/2026-08-29-pattern-reborn-design.md`

## Global constraints

- All commands run from `D:\code\ican\pattern-reborn` in PowerShell.
- Use only `.venv\Scripts\python.exe` and `.venv\Scripts\pip.exe`; do not install globally.
- Every launcher sets `PIP_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME`, `TEMP`, and `TMP` below the repository before invoking Python.
- Do not require Docker, WSL, a database service, a global CUDA toolkit, or a global Node installation.
- Work test-first: add one failing test, observe the intended failure, write the smallest implementation, rerun the focused test, then run the affected suite.
- Never put API keys in test fixtures, project JSON, logs, reports, generated manifests, screenshots, or committed files.
- Tests must not make live paid API calls.
- No third-party image enters `data/demo/` or `assets/mockups/` without source and license metadata.
- The OpenCV/manual extraction path remains complete when MobileSAM and the interactive canvas are unavailable.
- Commit after each task. Do not bundle unrelated user changes into a task commit.

## Planned file map

```text
pattern-reborn/
├── app.py                              # Streamlit entry point only
├── pyproject.toml                      # package, dependency, and test configuration
├── README.md                           # Windows setup, run, demo, and attribution guide
├── .env.example                       # secret variable names without values
├── config/providers.json              # editable provider endpoints and model presets
├── scripts/
│   ├── bootstrap.ps1                  # create isolated environment and install core deps
│   ├── install_optional_ai.ps1        # install MobileSAM extras into project venv
│   ├── run.ps1                        # start app with local caches
│   ├── test.ps1                       # run tests with local caches
│   └── validate_demo_assets.py        # reject untraceable or incomplete demo assets
├── src/pattern_reborn/
│   ├── domain.py                      # enums and persisted value objects
│   ├── runtime.py                     # repository-local paths and environment mapping
│   ├── config.py                      # non-secret/provider configuration loading
│   ├── projects.py                    # atomic project repository and stale propagation
│   ├── knowledge.py                   # category/profile/color catalogs
│   ├── images.py                      # validated immutable image I/O
│   ├── preprocess.py                  # orientation, resize, crop, perspective, enhancement
│   ├── segmentation.py               # OpenCV masks, edit strokes, optional predictor protocol
│   ├── analysis.py                   # palette, traditional colors, contour and symmetry
│   ├── patterns.py                   # deterministic transforms and repeat layouts
│   ├── vectorize.py                  # optional VTracer adapter
│   ├── mockups.py                    # rights-cleared template compositing
│   ├── exporter.py                   # package, manifest, attribution, and report output
│   ├── workflow.py                   # six-step application service
│   ├── generation/
│   │   ├── base.py                    # provider-neutral protocol and errors
│   │   ├── seedream.py                # Volcengine Ark request/response adapter
│   │   ├── qwen.py                    # Alibaba Model Studio request/response adapter
│   │   └── service.py                 # credential resolution, dispatch, immediate download
│   └── ui/
│       ├── theme.py                   # CSS/SVG loading
│       ├── home.py                    # new/history/category/demo home
│       ├── studio.py                  # six-step renderer and session coordination
│       └── assets/
│           ├── theme.css              # paper/ink/vermilion/gold design tokens
│           └── ruyi_cloud.svg         # original low-opacity navigation ornament
├── data/
│   ├── knowledge/
│   │   ├── categories.json            # nine categories and four profile mappings
│   │   └── traditional_colors.json    # curated names, RGB/Lab, and references
│   └── demo/
│       ├── manifest.json              # only validated and locally present demos
│       └── README.md                  # exact intake and rights requirements
├── assets/mockups/
│   ├── bookmark.png                   # team-created neutral templates
│   ├── tote_bag.png
│   └── phone_case.png
└── tests/                              # mirrors production modules plus integration/UI smoke
```

---

## Task 1: Isolated Python runtime and package skeleton

**Files:**

- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/pattern_reborn/__init__.py`
- Create: `src/pattern_reborn/runtime.py`
- Create: `scripts/bootstrap.ps1`
- Create: `scripts/run.ps1`
- Create: `scripts/test.ps1`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Add the test harness, package marker, and failing path-containment test**

Create `pyproject.toml` first with the declared `src` package, Python `>=3.11,<3.12`, the core/dev dependency groups listed below, and `testpaths = ["tests"]`. Create an empty `src/pattern_reborn/__init__.py`. This is test infrastructure only; do not create `runtime.py` yet.

```python
# tests/test_runtime.py
from pathlib import Path

from pattern_reborn.runtime import RuntimePaths


def test_runtime_paths_are_below_repository(tmp_path: Path) -> None:
    paths = RuntimePaths.from_root(tmp_path / "pattern-reborn")
    for path in paths.mutable_directories():
        assert path.is_relative_to(paths.root)
    assert paths.environment()["HF_HOME"] == str(paths.cache / "huggingface")
    assert paths.environment()["TEMP"] == str(paths.cache / "tmp")
```

- [ ] **Step 2: Bootstrap only the repository virtual environment, then prove the test fails**

```powershell
py -3.11 -m venv .venv
$env:PIP_CACHE_DIR = "$PWD\.cache\pip"
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_runtime.py -q
```

Expected: collection fails because `pattern_reborn.runtime` does not exist.

- [ ] **Step 3: Add the minimal runtime implementation and launchers**

Complete `pyproject.toml` with core dependencies (`streamlit`, `pydantic`, `opencv-python-headless`, `Pillow`, `numpy`, `httpx`, `python-dotenv`, `vtracer`) and dev dependencies (`pytest`, `pytest-cov`, `respx`). Pin upper bounds to the next major version.

```python
# src/pattern_reborn/runtime.py
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    cache: Path
    models: Path
    workspace: Path
    outputs: Path

    @classmethod
    def from_root(cls, root: Path) -> "RuntimePaths":
        resolved = root.resolve()
        return cls(resolved, resolved / ".cache", resolved / "models",
                   resolved / "workspace", resolved / "outputs")

    def mutable_directories(self) -> tuple[Path, ...]:
        return (self.cache / "pip", self.cache / "huggingface",
                self.cache / "torch", self.cache / "xdg", self.cache / "tmp",
                self.models, self.workspace, self.outputs)

    def environment(self) -> dict[str, str]:
        return {
            "PIP_CACHE_DIR": str(self.cache / "pip"),
            "HF_HOME": str(self.cache / "huggingface"),
            "TORCH_HOME": str(self.cache / "torch"),
            "XDG_CACHE_HOME": str(self.cache / "xdg"),
            "TEMP": str(self.cache / "tmp"),
            "TMP": str(self.cache / "tmp"),
        }
```

The three PowerShell scripts calculate `$ProjectRoot` from `$PSScriptRoot`, create only the paths above, set the six environment variables, and invoke the project venv explicitly. `bootstrap.ps1` must stop if Python is not 3.11 and must never modify user/system `PATH`.

- [ ] **Step 4: Run focused and packaging checks**

```powershell
.\scripts\test.ps1 tests/test_runtime.py -q
.\.venv\Scripts\python.exe -c "import pattern_reborn; print(pattern_reborn.__name__)"
```

Expected: one passing test and `pattern_reborn` printed.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml .env.example scripts src/pattern_reborn/__init__.py src/pattern_reborn/runtime.py tests/test_runtime.py
git commit -m "build: isolate Pattern Reborn runtime"
```

---

## Task 2: Typed project schema and atomic repository

**Files:**

- Create: `src/pattern_reborn/domain.py`
- Create: `src/pattern_reborn/projects.py`
- Test: `tests/test_projects.py`

- [ ] **Step 1: Write repository behavior tests**

```python
# tests/test_projects.py
from pathlib import Path

from pattern_reborn.domain import CategoryId, ProvenanceClass, StepId
from pattern_reborn.projects import ProjectRepository


def test_create_copies_and_hashes_source_without_mutating_it(tmp_path: Path) -> None:
    source = tmp_path / "lotus.png"
    source.write_bytes(b"immutable-source")
    repo = ProjectRepository(tmp_path / "workspace")
    project = repo.create("莲纹实验", source, CategoryId.PAPER_CUTTING,
                          ProvenanceClass.USER_SUPPLIED_UNVERIFIED)
    assert source.read_bytes() == b"immutable-source"
    assert project.source.sha256
    assert (repo.project_dir(project.id) / project.source.relative_path).read_bytes() == b"immutable-source"


def test_reconfirming_extraction_marks_downstream_outputs_stale(tmp_path: Path) -> None:
    repo, project = make_project(tmp_path)
    project.confirmed_steps = [StepId.UPLOAD, StepId.EXTRACTION, StepId.ANALYSIS]
    project.artifacts.analysis = ["analysis/v1.json"]
    repo.save(project)
    updated = repo.confirm(project.id, StepId.EXTRACTION, ["masks/v2.png"])
    assert StepId.ANALYSIS not in updated.confirmed_steps
    assert "analysis/v1.json" in updated.stale_artifacts
```

Also cover newest-first history, unsupported schema version, corrupt JSON preservation, generated IDs, and absence of `*.tmp` after a successful save.

- [ ] **Step 2: Run the test to verify failure**

```powershell
.\scripts\test.ps1 tests/test_projects.py -q
```

Expected: import failure for missing domain/repository modules.

- [ ] **Step 3: Implement schema and repository**

Use `str, Enum` types for `CategoryId`, `ProfileId`, `ProvenanceClass`, `StepId`, and `ArtifactKind`. Define Pydantic models `SourceRecord`, `ArtifactIndex`, `GenerationRecord`, and `ProjectRecord` with `schema_version: Literal[1] = 1`. The repository public API is:

```python
class ProjectRepository:
    def __init__(self, workspace: Path) -> None: ...
    def project_dir(self, project_id: str) -> Path: ...
    def create(self, name: str, source: Path, category: CategoryId,
               provenance: ProvenanceClass) -> ProjectRecord: ...
    def load(self, project_id: str) -> ProjectRecord: ...
    def save(self, project: ProjectRecord) -> None: ...
    def list_recent(self, limit: int = 3) -> list[ProjectRecord]: ...
    def confirm(self, project_id: str, step: StepId,
                artifact_paths: list[str]) -> ProjectRecord: ...
```

Validate project IDs with `^[a-z0-9][a-z0-9-]{7,63}$`; reject resolved artifact paths that escape the project directory. Save UTF-8 JSON to `project.json.tmp`, flush and `os.fsync`, then `os.replace`. Copy source bytes once to `source/<sha256-prefix><extension>` and calculate SHA-256 while copying. `confirm` applies the dependency order upload → extraction → analysis → recomposition → generation → export and moves invalidated paths to `stale_artifacts` without deleting files.

- [ ] **Step 4: Run focused tests**

```powershell
.\scripts\test.ps1 tests/test_projects.py -q
```

Expected: all repository tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/domain.py src/pattern_reborn/projects.py tests/test_projects.py
git commit -m "feat: add atomic local project repository"
```

---

## Task 3: Nine-category knowledge catalog and four profiles

**Files:**

- Create: `data/knowledge/categories.json`
- Create: `data/knowledge/traditional_colors.json`
- Create: `src/pattern_reborn/knowledge.py`
- Test: `tests/test_knowledge.py`

- [ ] **Step 1: Write catalog contract tests**

```python
def test_catalog_contains_nine_categories_and_four_profiles(catalog) -> None:
    assert len(catalog.categories) == 9
    assert {item.profile for item in catalog.categories} == {
        ProfileId.SILHOUETTE, ProfileId.FLAT_COLOR,
        ProfileId.TEXTILE, ProfileId.ARTIFACT_PHOTO,
    }


def test_every_category_has_explicit_defaults_and_limitations(catalog) -> None:
    for category in catalog.categories:
        assert category.display_name_zh
        assert category.default_parameters.threshold_mode
        assert category.limitations_zh
```

Also assert color records have a unique slug, Chinese name, six-digit hex value, reference title, and reference URL or bibliography string.

- [ ] **Step 2: Observe the missing-catalog failure**

```powershell
.\scripts\test.ps1 tests/test_knowledge.py -q
```

- [ ] **Step 3: Implement strict loading**

`KnowledgeCatalog.load(knowledge_dir: Path)` validates both JSON files with Pydantic and fails with the source filename and JSON path. `profile_for(category: CategoryId) -> ProcessingProfile` returns explicit parameters, not implicit branches in the UI.

Populate all nine approved category IDs: `paper_cutting`, `embroidery_brocade`, `dyeing_textile`, `ceramic_ornament`, `lacquer_ornament`, `folk_painting`, `architectural_ornament`, `metal_jewelry`, and `folk_crafts`. Map them to the four approved profiles. Include a compact, cited starter palette of at least twelve colors; cultural notes must be descriptive and must not assert official ICH status.

- [ ] **Step 4: Run catalog tests and JSON parse checks**

```powershell
.\scripts\test.ps1 tests/test_knowledge.py -q
.\.venv\Scripts\python.exe -m json.tool data/knowledge/categories.json > $null
.\.venv\Scripts\python.exe -m json.tool data/knowledge/traditional_colors.json > $null
```

- [ ] **Step 5: Commit**

```powershell
git add data/knowledge src/pattern_reborn/knowledge.py tests/test_knowledge.py
git commit -m "feat: add traditional pattern knowledge catalog"
```

---

## Task 4: Validated image import and deterministic preprocessing

**Files:**

- Create: `src/pattern_reborn/images.py`
- Create: `src/pattern_reborn/preprocess.py`
- Create: `tests/fixtures/images.py`
- Test: `tests/test_images.py`
- Test: `tests/test_preprocess.py`

- [ ] **Step 1: Add image-contract tests**

```python
def test_working_copy_respects_max_edge_and_preserves_source(tmp_path, rgb_fixture) -> None:
    before = rgb_fixture.read_bytes()
    image = load_working_image(rgb_fixture, max_edge=512)
    assert max(image.size) == 512
    assert rgb_fixture.read_bytes() == before


def test_perspective_transform_returns_requested_size() -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)
    points = [(10, 10), (150, 15), (145, 110), (15, 105)]
    result = perspective_correct(source, points, output_size=(100, 80))
    assert result.shape == (80, 100, 3)
```

Also test EXIF orientation, PNG/JPEG/WebP/BMP/TIFF acceptance, malformed input, alpha preservation, crop bounds, and deterministic enhancement output.

- [ ] **Step 2: Run and verify missing-module failures**

```powershell
.\scripts\test.ps1 tests/test_images.py tests/test_preprocess.py -q
```

- [ ] **Step 3: Implement minimal public interfaces**

```python
def probe_image(path: Path) -> ImageInfo: ...
def load_working_image(path: Path, max_edge: int = 2048) -> Image.Image: ...
def save_png_atomic(image: Image.Image, destination: Path) -> None: ...

def crop(image: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray: ...
def perspective_correct(image: np.ndarray, points: list[tuple[float, float]],
                        output_size: tuple[int, int]) -> np.ndarray: ...
def enhance(image: np.ndarray, settings: PreprocessSettings) -> np.ndarray: ...
```

Call `ImageOps.exif_transpose`, fully decode with `image.load()`, reject decompression-bomb warnings as a typed `ImageValidationError`, and normalize processing arrays to RGB `uint8`. Resizing uses Lanczos and never enlarges. White balance, denoise, and CLAHE are controlled by typed settings and default to conservative profile values.

- [ ] **Step 4: Verify contracts**

```powershell
.\scripts\test.ps1 tests/test_images.py tests/test_preprocess.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/images.py src/pattern_reborn/preprocess.py tests/fixtures tests/test_images.py tests/test_preprocess.py
git commit -m "feat: add safe image preprocessing"
```

---

## Task 5: OpenCV extraction, region guidance, and reversible mask edits

**Files:**

- Create: `src/pattern_reborn/segmentation.py`
- Test: `tests/test_segmentation.py`

- [ ] **Step 1: Write extraction and edit tests**

```python
def test_silhouette_keeps_outer_shape_and_inner_hole(ring_image) -> None:
    result = OpenCvSegmenter().segment(ring_image, ProfileId.SILHOUETTE,
                                       SegmentHints())
    assert result.mask.dtype == np.uint8
    assert result.mask[10, 10] == 0
    assert result.mask[40, 40] == 0
    assert result.mask[20, 40] == 255


def test_keep_and_remove_strokes_are_applied_in_order(blank_mask) -> None:
    edits = [MaskStroke(MaskEditMode.KEEP, [(10, 10), (20, 10)], 5),
             MaskStroke(MaskEditMode.REMOVE, [(15, 10)], 3)]
    edited = apply_mask_strokes(blank_mask, edits)
    assert edited[10, 10] == 255
    assert edited[10, 15] == 0
```

Also test flat-color, textile, artifact ROI-required behavior, box clipping, alpha extraction, minimum component filtering, and serialized stroke round-tripping.

- [ ] **Step 2: Observe failure**

```powershell
.\scripts\test.ps1 tests/test_segmentation.py -q
```

- [ ] **Step 3: Implement the fallback-first segmentation API**

```python
class Segmenter(Protocol):
    def segment(self, image: np.ndarray, profile: ProfileId,
                hints: SegmentHints) -> SegmentResult: ...

class OpenCvSegmenter:
    def segment(self, image: np.ndarray, profile: ProfileId,
                hints: SegmentHints) -> SegmentResult: ...

def apply_mask_strokes(mask: np.ndarray, strokes: Sequence[MaskStroke]) -> np.ndarray: ...
def extract_rgba(image: np.ndarray, mask: np.ndarray) -> Image.Image: ...
```

Use Otsu/adaptive threshold plus morphology for silhouettes, Lab-space color clustering for flat color, bilateral filtering plus controlled thresholding for textiles, and GrabCut initialized by a required rectangle for artifact photographs. Record profile, parameters, hints, algorithm version, and warnings in `SegmentResult`. Never mutate the input arrays.

- [ ] **Step 4: Verify deterministic masks**

```powershell
.\scripts\test.ps1 tests/test_segmentation.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/segmentation.py tests/test_segmentation.py
git commit -m "feat: add offline motif extraction and mask edits"
```

---

## Task 6: Palette, contour, and symmetry analysis

**Files:**

- Create: `src/pattern_reborn/analysis.py`
- Test: `tests/test_analysis.py`

- [ ] **Step 1: Write deterministic analysis tests**

```python
def test_palette_is_seeded_and_sorted_by_coverage(two_color_rgba) -> None:
    first = analyze_palette(two_color_rgba, count=2, seed=2026)
    second = analyze_palette(two_color_rgba, count=2, seed=2026)
    assert first == second
    assert first[0].coverage >= first[1].coverage


def test_bilateral_symmetry_scores_reflected_mask_high(symmetric_mask) -> None:
    report = analyze_symmetry(symmetric_mask)
    assert report.vertical_score > 0.95
    assert report.horizontal_score < report.vertical_score
```

Also test transparent-pixel exclusion, nearest traditional color in CIE Lab, empty-mask errors, contour count/perimeter/area, and rotational candidate ordering.

- [ ] **Step 2: Run and observe failure**

```powershell
.\scripts\test.ps1 tests/test_analysis.py -q
```

- [ ] **Step 3: Implement analysis**

```python
def analyze_palette(image: Image.Image, count: int, seed: int) -> list[PaletteColor]: ...
def match_traditional_colors(colors: Sequence[PaletteColor],
                             catalog: Sequence[TraditionalColor]) -> list[ColorMatch]: ...
def analyze_contours(mask: np.ndarray) -> ContourReport: ...
def analyze_symmetry(mask: np.ndarray) -> SymmetryReport: ...
```

Seed OpenCV k-means, exclude alpha-zero pixels, sort by measured coverage, and convert RGB to CIE Lab before distance matching. Symmetry scores use intersection-over-union against horizontal/vertical flips after centering the foreground bounding box; rotational candidates evaluate 2-, 3-, 4-, 6-, and 8-fold orders and return scores rather than cultural claims.

- [ ] **Step 4: Verify**

```powershell
.\scripts\test.ps1 tests/test_analysis.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/analysis.py tests/test_analysis.py
git commit -m "feat: analyze motif color contour and symmetry"
```

---

## Task 7: Parameterized recomposition and optional SVG

**Files:**

- Create: `src/pattern_reborn/patterns.py`
- Create: `src/pattern_reborn/vectorize.py`
- Test: `tests/test_patterns.py`
- Test: `tests/test_vectorize.py`

- [ ] **Step 1: Write transform and capability tests**

```python
@pytest.mark.parametrize("layout", list(LayoutKind))
def test_layout_is_repeatable_for_same_seed(layout, motif_rgba) -> None:
    request = PatternRequest(layout=layout, canvas=(512, 512), seed=17)
    assert compose_pattern(motif_rgba, request).tobytes() == \
           compose_pattern(motif_rgba, request).tobytes()


def test_vectorizer_reports_unavailable_without_breaking_png(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.vectorize.find_vtracer", lambda: None)
    result = Vectorizer().vectorize(Path("motif.png"), Path("motif.svg"))
    assert result.available is False
    assert result.reason_zh
```

Assert RGBA output and canvas dimensions for mirror, rotation, radial, border, two-way, and four-way layouts; assert seamless opposite edges for the repeat fixtures.

- [ ] **Step 2: Observe failures**

```powershell
.\scripts\test.ps1 tests/test_patterns.py tests/test_vectorize.py -q
```

- [ ] **Step 3: Implement composition and VTracer adapter**

```python
def compose_pattern(motif: Image.Image, request: PatternRequest) -> Image.Image: ...

class Vectorizer:
    def capability(self) -> CapabilityStatus: ...
    def vectorize(self, source_png: Path, destination_svg: Path,
                  settings: VectorSettings = VectorSettings()) -> VectorResult: ...
```

Use Pillow affine transforms and alpha compositing. Persist seed, layout, spacing, scale, angle, palette substitutions, and canvas size. For VTracer, import lazily and write to a temporary sibling before replacement; malformed or absent output returns a typed capability/result error and leaves PNG workflows intact.

- [ ] **Step 4: Verify**

```powershell
.\scripts\test.ps1 tests/test_patterns.py tests/test_vectorize.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/patterns.py src/pattern_reborn/vectorize.py tests/test_patterns.py tests/test_vectorize.py
git commit -m "feat: add deterministic pattern recomposition"
```

---

## Task 8: Rights-cleared mockups and provenance export

**Files:**

- Create: `src/pattern_reborn/mockups.py`
- Create: `src/pattern_reborn/exporter.py`
- Create: `assets/mockups/bookmark.png`
- Create: `assets/mockups/tote_bag.png`
- Create: `assets/mockups/phone_case.png`
- Create: `assets/mockups/metadata.json`
- Test: `tests/test_mockups.py`
- Test: `tests/test_exporter.py`

- [ ] **Step 1: Write compositing and report tests**

```python
def test_mockup_preserves_template_and_labels_ai_input(mockup_catalog, ai_pattern) -> None:
    result = compose_mockup(mockup_catalog["bookmark"], ai_pattern)
    assert result.image.size == mockup_catalog["bookmark"].canvas_size
    assert result.ai_assisted is True


def test_export_contains_manifest_report_and_selected_assets(project, tmp_path) -> None:
    package = Exporter().export(project, ExportSelection(patterns=True, report=True), tmp_path)
    assert (package / "manifest.json").exists()
    report = (package / "provenance.md").read_text(encoding="utf-8")
    assert project.source.sha256 in report
    assert "AI 辅助" in report
```

Also assert path containment, no secret-shaped fields, attribution inclusion, filename sanitization, and stable manifest schema.

- [ ] **Step 2: Observe failures**

```powershell
.\scripts\test.ps1 tests/test_mockups.py tests/test_exporter.py -q
```

- [ ] **Step 3: Create original templates and implementations**

Generate the three neutral templates from team-authored Pillow drawing code during implementation, then commit the resulting PNGs and `metadata.json` with `creator: "Pattern Reborn team"`, `license: "project-original"`, date, dimensions, and placement polygon. Do not download product photographs.

```python
def compose_mockup(template: MockupTemplate, artwork: ArtworkRef,
                   options: MockupOptions = MockupOptions()) -> MockupResult: ...

class Exporter:
    def export(self, project: ProjectRecord, selection: ExportSelection,
               destination_root: Path) -> Path: ...
```

The exporter creates a timestamped sibling directory atomically and writes copied assets, `manifest.json`, `attribution.md`, and `provenance.md`. It labels generated derivatives and mockups made from them as AI-assisted, includes model/provider/prompt/time but excludes credentials and raw authorization headers.

- [ ] **Step 4: Verify**

```powershell
.\scripts\test.ps1 tests/test_mockups.py tests/test_exporter.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add assets/mockups src/pattern_reborn/mockups.py src/pattern_reborn/exporter.py tests/test_mockups.py tests/test_exporter.py
git commit -m "feat: add cultural mockups and provenance export"
```

---

## Task 9: Provider-neutral generation contracts and secret safety

**Files:**

- Create: `config/providers.json`
- Create: `src/pattern_reborn/config.py`
- Create: `src/pattern_reborn/generation/__init__.py`
- Create: `src/pattern_reborn/generation/base.py`
- Test: `tests/test_generation_base.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write contract and redaction tests**

```python
def test_generation_request_serialization_never_contains_key(reference_png) -> None:
    request = make_generation_request(reference_png)
    dumped = request.model_dump_json()
    assert "api_key" not in dumped
    assert "Bearer" not in dumped


def test_provider_config_exposes_both_manual_choices(provider_config) -> None:
    assert provider_config.default_provider == ProviderId.SEEDREAM
    assert {p.id for p in provider_config.providers} == {
        ProviderId.SEEDREAM, ProviderId.QWEN,
    }
    assert provider_config.provider(ProviderId.QWEN).default_model == "qwen-image-3.0-pro"
```

Also test size/count validation, exactly one reference image, URL scheme validation, absent platform credentials, and redaction of arbitrary provider error text.

- [ ] **Step 2: Observe failures**

```powershell
.\scripts\test.ps1 tests/test_generation_base.py tests/test_config.py -q
```

- [ ] **Step 3: Implement neutral models and editable configuration**

```python
class GenerationAdapter(Protocol):
    provider: ProviderId
    def generate(self, request: GenerationRequest,
                 credential: SecretStr) -> RemoteGenerationResult: ...

class GenerationFailure(Exception):
    def __init__(self, kind: FailureKind, user_message_zh: str,
                 provider_code: str | None = None) -> None: ...
```

`GenerationRequest` includes prompt, local reference path, model, provider, output size, count constrained to `1`, structure level, target application, colors, and negative constraints. It contains no credential field. `providers.json` contains the two providers, editable base URLs, default models, size options, and environment-variable names only. `.env.example` documents `SEEDREAM_API_KEY`, `QWEN_API_KEY`, and optional model/endpoint overrides with empty values.

- [ ] **Step 4: Verify**

```powershell
.\scripts\test.ps1 tests/test_generation_base.py tests/test_config.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add config/providers.json .env.example src/pattern_reborn/config.py src/pattern_reborn/generation tests/test_generation_base.py tests/test_config.py
git commit -m "feat: define safe image generation contracts"
```

---

## Task 10: Seedream and Qwen adapters with immediate result capture

**Files:**

- Create: `src/pattern_reborn/generation/seedream.py`
- Create: `src/pattern_reborn/generation/qwen.py`
- Create: `src/pattern_reborn/generation/service.py`
- Test: `tests/test_seedream.py`
- Test: `tests/test_qwen.py`
- Test: `tests/test_generation_service.py`

- [ ] **Step 1: Write complete fake-response tests**

```python
def test_seedream_decodes_base64_result_without_exposing_key(respx_mock, request, tmp_path) -> None:
    respx_mock.post("https://ark.example/api/v3/images/generations").respond(
        json={"model": "seedream", "data": [{"b64_json": PNG_BASE64}], "usage": {}}
    )
    result = make_seedream(tmp_path).generate(request, SecretStr("secret-value"))
    assert result.local_files[0].read_bytes().startswith(b"\x89PNG")
    assert "secret-value" not in result.model_dump_json()


def test_qwen_downloads_temporary_url_before_success(respx_mock, request, tmp_path) -> None:
    respx_mock.post("https://qwen.example/generation").respond(json=QWEN_FULL_RESPONSE)
    download = respx_mock.get("https://temporary.example/result.png").respond(content=PNG_BYTES)
    result = make_qwen(tmp_path).generate(request, SecretStr("secret-value"))
    assert download.called
    assert result.local_files[0].exists()
```

Add tests for URL and base64 results, malformed bodies, auth/429/moderation/timeout mapping, non-image download, atomic output, prompt preservation on failure, explicit provider dispatch, and proof that one adapter failure never invokes the other adapter.

- [ ] **Step 2: Observe failures**

```powershell
.\scripts\test.ps1 tests/test_seedream.py tests/test_qwen.py tests/test_generation_service.py -q
```

- [ ] **Step 3: Implement injected-client adapters**

Seedream sends `POST {base_url}/api/v3/images/generations` with `model`, `prompt`, one image data URL, `size`, and `response_format`. Qwen sends `POST {base_url}/api/v1/services/aigc/multimodal-generation/generation` with `model`, `input.messages[0].content` containing image then text, and supported parameters. Base URLs and model IDs come only from `providers.json`/environment overrides.

```python
class GenerationService:
    def __init__(self, adapters: Mapping[ProviderId, GenerationAdapter],
                 credential_resolver: CredentialResolver) -> None: ...

    def generate(self, request: GenerationRequest, mode: CredentialMode,
                 byok: SecretStr | None = None) -> GenerationResult: ...
```

Inject `httpx.Client` for tests. Encode the local reference as a MIME-correct data URL. Download temporary URLs before returning success, validate content type and decoded image bytes with Pillow, then atomically store under `generated/`. Error messages expose only a mapped Chinese category and redacted provider code.

Official contract references to verify again at implementation time:

- Seedream: `https://www.volcengine.com/docs/82379/1541523`
- Qwen Image: `https://help.aliyun.com/zh/model-studio/qwen-image-api`

- [ ] **Step 4: Verify without network access**

```powershell
.\scripts\test.ps1 tests/test_seedream.py tests/test_qwen.py tests/test_generation_service.py -q
```

Expected: all fake-HTTP tests pass and no unmatched request is made.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/generation tests/test_seedream.py tests/test_qwen.py tests/test_generation_service.py
git commit -m "feat: integrate Seedream and Qwen image generation"
```

---

## Task 11: Optional MobileSAM capability without core coupling

**Files:**

- Modify: `src/pattern_reborn/segmentation.py`
- Create: `src/pattern_reborn/capabilities.py`
- Create: `scripts/install_optional_ai.ps1`
- Test: `tests/test_capabilities.py`
- Test: `tests/test_mobile_sam_adapter.py`

- [ ] **Step 1: Write degradation and fake-predictor tests**

```python
def test_missing_mobile_sam_reports_disabled_and_keeps_opencv(monkeypatch) -> None:
    monkeypatch.setattr("pattern_reborn.capabilities.find_spec", lambda name: None)
    status = detect_capabilities()
    assert status.mobile_sam.available is False
    assert status.opencv.available is True


def test_mobile_sam_adapter_accepts_box_and_points(fake_predictor, image) -> None:
    result = MobileSamSegmenter(fake_predictor).segment(
        image, ProfileId.ARTIFACT_PHOTO,
        SegmentHints(box=(5, 5, 40, 40), points=[PromptPoint(20, 20, True)]),
    )
    assert result.mask.shape == image.shape[:2]
```

- [ ] **Step 2: Observe failures**

```powershell
.\scripts\test.ps1 tests/test_capabilities.py tests/test_mobile_sam_adapter.py -q
```

- [ ] **Step 3: Implement lazy optional loading**

`detect_capabilities()` reports OpenCV, VTracer, MobileSAM, canvas, API credential, and offline status independently. `MobileSamSegmenter` accepts an injected predictor and has no top-level Torch/MobileSAM import. The optional install script uses the project venv and local caches, installs a pinned compatible Torch build and MobileSAM source, downloads the checkpoint only into `models/mobile_sam/`, calculates its expected SHA-256 from a committed metadata record, and aborts on mismatch. It must not install a global CUDA toolkit.

- [ ] **Step 4: Verify the core suite with optional packages absent**

```powershell
.\scripts\test.ps1 tests/test_capabilities.py tests/test_mobile_sam_adapter.py tests/test_segmentation.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/install_optional_ai.ps1 src/pattern_reborn/capabilities.py src/pattern_reborn/segmentation.py tests/test_capabilities.py tests/test_mobile_sam_adapter.py
git commit -m "feat: add optional MobileSAM capability"
```

---

## Task 12: Six-step workflow orchestration and offline integration

**Files:**

- Create: `src/pattern_reborn/workflow.py`
- Test: `tests/test_workflow.py`
- Test: `tests/integration/test_offline_pipeline.py`

- [ ] **Step 1: Write use-case and end-to-end tests**

```python
def test_offline_pipeline_reaches_export_without_generation(app_service, source_fixture) -> None:
    project = app_service.create_project(CreateProjectCommand(..., source=source_fixture))
    extraction = app_service.extract(project.id, ExtractCommand(profile=ProfileId.SILHOUETTE))
    app_service.confirm_extraction(project.id, extraction.artifact_id)
    analysis = app_service.analyze(project.id)
    pattern = app_service.compose(project.id, PatternRequest(layout=LayoutKind.RADIAL, seed=7))
    mockup = app_service.make_mockup(project.id, "bookmark", pattern.artifact_id)
    package = app_service.export(project.id, ExportSelection.all_offline())
    assert package.exists()
    assert analysis.palette
    assert mockup.path.exists()
```

Also test navigation-state persistence, prerequisite rejection, upstream invalidation, generation failure leaving prompt/settings intact, and cached generated assets remaining usable offline.

- [ ] **Step 2: Observe failure**

```powershell
.\scripts\test.ps1 tests/test_workflow.py tests/integration/test_offline_pipeline.py -q
```

- [ ] **Step 3: Implement the application service**

```python
class PatternRebornService:
    def create_project(self, command: CreateProjectCommand) -> ProjectRecord: ...
    def extract(self, project_id: str, command: ExtractCommand) -> ArtifactRef: ...
    def confirm_extraction(self, project_id: str, artifact_id: str) -> ProjectRecord: ...
    def analyze(self, project_id: str) -> AnalysisReport: ...
    def compose(self, project_id: str, request: PatternRequest) -> ArtifactRef: ...
    def generate(self, project_id: str, request: GenerationRequest,
                 mode: CredentialMode, byok: SecretStr | None) -> GenerationResult: ...
    def make_mockup(self, project_id: str, template_id: str,
                    artwork_id: str) -> ArtifactRef: ...
    def export(self, project_id: str, selection: ExportSelection) -> Path: ...
```

The service alone maps project-relative artifact IDs to contained paths, versions outputs, records algorithm/settings metadata, checks confirmed prerequisites, and persists results. It does not import Streamlit. Generation is the only method allowed to depend on network adapters.

- [ ] **Step 4: Run integration and full core tests**

```powershell
.\scripts\test.ps1 tests/test_workflow.py tests/integration/test_offline_pipeline.py -q
.\scripts\test.ps1 -q --ignore=tests/ui
```

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/workflow.py tests/test_workflow.py tests/integration
git commit -m "feat: orchestrate the offline creation workflow"
```

---

## Task 13: Home page, approved visual system, and history entry

**Files:**

- Create: `app.py`
- Create: `src/pattern_reborn/ui/__init__.py`
- Create: `src/pattern_reborn/ui/theme.py`
- Create: `src/pattern_reborn/ui/home.py`
- Create: `src/pattern_reborn/ui/assets/theme.css`
- Create: `src/pattern_reborn/ui/assets/ruyi_cloud.svg`
- Test: `tests/ui/test_home.py`
- Test: `tests/ui/test_theme.py`

- [ ] **Step 1: Write AppTest and static visual-contract tests**

```python
def test_home_shows_primary_action_recent_history_and_readiness(app_test) -> None:
    app_test.run()
    assert not app_test.exception
    assert any(button.label == "开始新创作" for button in app_test.button)
    markdown = [node.value for node in app_test.markdown]
    assert any("最近项目" in value for value in markdown)
    assert any("本地处理可用" in value for value in markdown)


def test_theme_has_no_diagonal_or_remote_background_assets() -> None:
    css = Path("src/pattern_reborn/ui/assets/theme.css").read_text(encoding="utf-8")
    assert "repeating-linear-gradient" not in css
    assert "http://" not in css and "https://" not in css
    assert "--ink-green" in css and "--vermilion" in css and "--gilded-gold" in css
```

Also assert nine category labels, maximum three recent projects, demo-card hiding for missing assets, and no exposed default API secret.

- [ ] **Step 2: Observe failure**

```powershell
.\scripts\test.ps1 tests/ui/test_home.py tests/ui/test_theme.py -q
```

- [ ] **Step 3: Implement the shell and approved styling**

`app.py` builds dependencies, sets Streamlit page config, and delegates to `render_home` or `render_studio`. CSS uses a warm paper base with two low-opacity, non-directional radial gradients; no diagonal/repeating lines. Editing surfaces use neutral gray/white. Sidebar uses ink green, vermilion selection, restrained gold markers, the original `ruyi_cloud.svg`, and a vertical “非遗纹启” seal rendered as text. The SVG consists only of project-authored paths and includes a source comment `Pattern Reborn original asset`.

The home page shows one primary action, three recent projects, category shortcuts, validated demos only, knowledge/settings links, and local/API capability indicators.

- [ ] **Step 4: Run UI tests and start smoke server**

```powershell
.\scripts\test.ps1 tests/ui/test_home.py tests/ui/test_theme.py -q
.\scripts\run.ps1 --server.headless true --server.port 8511
```

Expected: Streamlit reports a local URL, the home page loads without an exception, and Ctrl+C stops it.

- [ ] **Step 5: Commit**

```powershell
git add app.py src/pattern_reborn/ui tests/ui/test_home.py tests/ui/test_theme.py
git commit -m "feat: add heritage-inspired application shell"
```

---

## Task 14: Guided studio, advanced settings, and canvas degradation

**Files:**

- Create: `src/pattern_reborn/ui/studio.py`
- Modify: `app.py`
- Modify: `pyproject.toml`
- Test: `tests/ui/test_studio.py`
- Test: `tests/ui/test_generation_controls.py`

- [ ] **Step 1: Write six-step interaction tests**

```python
def test_sidebar_has_six_steps_and_advanced_settings_start_collapsed(studio_test) -> None:
    studio_test.run()
    assert [item.label for item in studio_test.radio[0].options] == [
        "上传与分类", "智能提取", "纹样分析", "参数化重组", "AI 创意生成", "导出与溯源"
    ]
    assert studio_test.expander[0].label == "高级设置"
    assert studio_test.expander[0].expanded is False


def test_generation_exposes_manual_seedream_and_qwen_switch(studio_at_generation) -> None:
    studio_at_generation.run()
    provider = next(widget for widget in studio_at_generation.radio if widget.label == "生图模型")
    assert provider.options == ["Seedream", "Qwen Image 3.0 Pro"]
    assert provider.value == "Seedream"
```

Also test default/BYOK modes, BYOK key input type `password`, prompt persistence after fake failure, confirmation summary with provider/model/size/count, disabled generation while offline, backward navigation state, manual box inputs when canvas is absent, and visible AI labels.

- [ ] **Step 2: Observe failure**

```powershell
.\scripts\test.ps1 tests/ui/test_studio.py tests/ui/test_generation_controls.py -q
```

- [ ] **Step 3: Implement the guided renderer**

Keep `st.session_state` limited to current project ID, current step, unsaved form values, an in-memory `SecretStr` BYOK value, and temporary canvas objects. Persist confirmed domain state through `PatternRebornService`.

Install `streamlit-drawable-konva==0.2.2` as a separately named optional dependency group `canvas`; import it lazily. When available, expose point, rectangle, keep brush, and remove brush interactions. When unavailable or incompatible, show numeric rectangle coordinates plus click-coordinate inputs and always retain keep/remove mask operations through uploaded/entered strokes. A canvas import or render failure must produce a warning and continue the studio.

Every algorithm section has concise defaults and a collapsed `高级设置` expander. Step 5 always shows both providers and both credential modes; Seedream starts selected, switching keeps all neutral request fields, and submitting first shows a cost-awareness confirmation summary. Never echo the entered key.

- [ ] **Step 4: Verify UI behavior**

```powershell
.\scripts\test.ps1 tests/ui/test_studio.py tests/ui/test_generation_controls.py -q
.\scripts\test.ps1 -q
```

- [ ] **Step 5: Commit**

```powershell
git add app.py pyproject.toml src/pattern_reborn/ui/studio.py tests/ui/test_studio.py tests/ui/test_generation_controls.py
git commit -m "feat: add guided six-step creation studio"
```

---

## Task 15: Traceable demo intake and six-case validation

**Files:**

- Create: `data/demo/manifest.json`
- Create: `data/demo/README.md`
- Create: `scripts/validate_demo_assets.py`
- Test: `tests/test_demo_assets.py`
- Modify later when supplied: `data/demo/<case-id>/source.*`
- Modify later when supplied: `data/demo/<case-id>/metadata.json`

- [ ] **Step 1: Write validator tests using temporary assets**

```python
def test_validator_accepts_complete_rights_record(tmp_path, demo_png) -> None:
    write_demo_case(tmp_path, source=demo_png, license="CC BY 4.0",
                    source_url="https://institution.example/object/1")
    assert validate_demo_root(tmp_path).errors == []


def test_validator_rejects_unclear_search_engine_image(tmp_path, demo_png) -> None:
    write_demo_case(tmp_path, source=demo_png, license="unknown",
                    source_url="https://images.example/search?q=lotus")
    result = validate_demo_root(tmp_path)
    assert any("授权" in error for error in result.errors)
```

Also test missing file, SHA-256 mismatch, missing author/institution, invalid provenance classification, AI-material label, manifest/file mismatch, and exactly six required case IDs when `--competition-ready` is passed.

- [ ] **Step 2: Observe failure**

```powershell
.\scripts\test.ps1 tests/test_demo_assets.py -q
```

- [ ] **Step 3: Implement deterministic intake rules**

The initial committed manifest is schema-valid and may contain zero cases so the app starts before the user's collection is ready. `--competition-ready` requires these IDs:

```text
lotus-paper-cut
fish-lotus-blue-calico
peony-embroidery
scrolling-lotus-ceramic
new-year-picture-detail
architectural-cloud
```

Each `metadata.json` requires title, category, profile, source filename, SHA-256, creator/institution, source URL or bibliography, license, retrieval date, provenance classification, processing defaults, expected result, and AI involvement. The validator updates no metadata automatically; it reports precise corrections so rights data cannot be guessed.

- [ ] **Step 4: Validate the empty development state, then ingest user-provided assets when available**

```powershell
.\scripts\test.ps1 tests/test_demo_assets.py -q
.\.venv\Scripts\python.exe scripts/validate_demo_assets.py data/demo
```

After the user supplies all six traceable assets and metadata:

```powershell
.\.venv\Scripts\python.exe scripts/validate_demo_assets.py data/demo --competition-ready
```

Expected: development validation passes immediately; competition-ready validation passes only after all six complete cases are present.

- [ ] **Step 5: Commit validator now; commit approved assets separately after intake**

```powershell
git add data/demo/manifest.json data/demo/README.md scripts/validate_demo_assets.py tests/test_demo_assets.py
git commit -m "feat: validate traceable competition demos"
```

---

## Task 16: Documentation, Windows smoke test, and acceptance evidence

**Files:**

- Create: `README.md`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `docs/acceptance/competition-checklist.md`
- Create: `tests/smoke/test_app_startup.py`
- Create: `tests/smoke/server.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write startup and documentation tests**

```python
def test_app_starts_without_optional_ai_or_canvas(free_port: int) -> None:
    env = os.environ.copy()
    env["PATTERN_REBORN_DISABLE_OPTIONAL"] = "1"
    with streamlit_server(Path("app.py"), free_port, env) as process:
        response = urlopen(f"http://127.0.0.1:{free_port}/_stcore/health", timeout=2)
        assert response.status == 200
        assert process.poll() is None
```

Implement `streamlit_server` in `tests/smoke/server.py` as a context manager using `subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(app), "--server.headless=true", f"--server.port={port}"])`. Poll `/_stcore/health` for at most 15 seconds; on exit, call `terminate()`, wait 5 seconds, and call `kill()` only if that exact child remains alive. Do not leave a server running. Add a static check that README commands use `.venv`/scripts and never recommend global `pip install`.

- [ ] **Step 2: Observe the documentation/smoke failure**

```powershell
.\scripts\test.ps1 tests/smoke/test_app_startup.py -q
```

- [ ] **Step 3: Write operator documentation and notices**

README covers: prerequisites, isolated bootstrap, optional GPU setup, start/test commands, project storage, nine categories/four profiles, offline behavior, Seedream/Qwen platform and BYOK configuration, secret handling, demo intake, export format, known limitations, and competition presentation fallback. `THIRD_PARTY_NOTICES.md` identifies dependency name, purpose, license, copyright owner, upstream URL, whether redistributed, and required notice action.

The acceptance checklist records dated evidence for:

1. clean Windows bootstrap and drive-local cache inspection;
2. full offline fixture pipeline;
3. six demo projects when assets are supplied;
4. manual Seedream/Qwen switching with mocked and one authorized live test per configured provider;
5. API outage/cached-result presentation;
6. BYOK key absence from repository search and exports;
7. canvas absent fallback;
8. MobileSAM absent fallback;
9. SVG unavailable fallback;
10. source/license/AI labels in generated report.

- [ ] **Step 4: Run final automated verification**

```powershell
.\scripts\test.ps1 -q
.\scripts\test.ps1 --cov=pattern_reborn --cov-report=term-missing --cov-fail-under=85
git grep -n -I -E "(sk-|Bearer [A-Za-z0-9]|api[_-]?key.{0,8}[=:].{8,})" -- ':!docs/superpowers/plans/*'
git diff --check
git status --short
```

Expected: all tests pass; coverage is at least 85%; secret scan has no real credential hit; diff check is clean. Review `git status` and retain unrelated user files unmodified.

- [ ] **Step 5: Run manual Windows acceptance**

```powershell
.\scripts\run.ps1 --server.headless false --server.port 8501
```

Complete one offline case through export, inspect the provenance package, switch both providers without submitting, test one authorized live call only if the user has placed credentials in untracked `.env`, then stop the server. Record results in `docs/acceptance/competition-checklist.md`; never record the credential.

- [ ] **Step 6: Commit**

```powershell
git add README.md THIRD_PARTY_NOTICES.md docs/acceptance tests/smoke .gitignore
git commit -m "docs: add Windows setup and acceptance guide"
```

---

## Final definition of done

- [ ] All automated commands in Task 16 pass from the repository-local venv.
- [ ] The repository is clean except for explicitly acknowledged user-supplied demo assets.
- [ ] A user can finish upload → extraction → analysis → recomposition → mockup → export while offline.
- [ ] Seedream and Qwen Image remain manually selectable in both platform-default and BYOK modes.
- [ ] Failed generation never switches providers automatically and never loses prompt/settings.
- [ ] No credential appears in files, logs, reports, tests, screenshots, or Git history.
- [ ] Source images remain byte-identical after all processing.
- [ ] MobileSAM, VTracer, and the canvas can each be absent independently without preventing app startup.
- [ ] The UI matches the approved paper-white, ink-green, vermilion, restrained-gold visual language and contains no diagonal-line background.
- [ ] Competition-ready mode validates exactly six traceable demo cases before presentation.
- [ ] The final provenance report distinguishes project-authored work, third-party components, traditional references, and AI-assisted outputs.
