# Pattern Reborn Provenance and Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve complete rights metadata, detect source mutation, and make project, generation, mockup, and export state transactional and competition-safe.

**Architecture:** Migrate project JSON from schema version 1 to version 2 at the repository boundary, keeping domain models strict after migration. Centralize source-integrity checks in `ProjectRepository`, represent generation and export lifecycle explicitly in the domain, and make export derive only from confirmed non-stale records.

**Tech Stack:** Python 3.11, Pydantic 2, pathlib, hashlib, atomic filesystem replacement, pytest

**Spec:** `docs/superpowers/specs/2026-08-30-pattern-reborn-hardening-ui-redesign.md`

## Global Constraints

- Migrations must not overwrite the original project file until the migrated model validates.
- Old projects load with explicit empty/unknown optional rights fields.
- Changed source bytes must never be exported under a previously recorded digest.
- Only confirmed, non-stale generated artifacts may feed mockups or export.
- BYOK secrets never enter project JSON, logs, reports, or exports.
- Every production change starts with a failing regression test and ends with a focused commit.

---

### Task 1: Define schema-v2 provenance and lifecycle records

**Files:**
- Modify: `src/pattern_reborn/domain.py`
- Modify: `tests/test_projects.py`
- Modify: `tests/test_generation_base.py`
- Modify: `tests/test_exporter.py`

**Interfaces:**
- Produces: `SourceRights`, `GenerationStatus`, `ExportRecord`, schema-v2 `SourceRecord`, `GenerationRecord`, and `ProjectRecord`.
- Consumes: existing enums and UTC timestamp validators.

- [ ] **Step 1: Write failing model tests**

```python
def test_schema_v2_source_retains_competition_rights():
    source = SourceRecord(
        original_filename="lotus.jpg", relative_path="source/a.jpg",
        sha256="a" * 64, byte_size=12,
        rights=SourceRights(
            title="莲纹", creator_institution="某博物馆",
            license="CC BY 4.0", source_url="https://example.org/object/1",
            retrieval_date=date(2026, 8, 30), bibliography="",
            ai_involvement={"source_is_ai_generated": False},
        ),
    )
    assert source.rights.creator_institution == "某博物馆"

def test_unconfirmed_generation_is_not_current(project):
    record = GenerationRecord(
        id="gen-pending", operation_id="op-pending", provider="seedream",
        model="seedream-4", prompt="莲纹书签", artifact_path="generated/v1.png",
        created_at=datetime.now(UTC), confirmed_at=None,
        status=GenerationStatus.PENDING_CONFIRMATION,
    )
    project.generations.append(record)
    assert record.confirmed_at is None
```

- [ ] **Step 2: Run tests and verify schema-v1 models cannot represent the fields**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py tests/test_generation_base.py tests/test_exporter.py -q`

Expected: FAIL on missing models/fields.

- [ ] **Step 3: Add strict domain records**

```python
class GenerationStatus(str, Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"

class SourceRights(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    title: str = ""
    creator_institution: str = ""
    license: str = "unknown"
    source_url: str = ""
    retrieval_date: date | None = None
    bibliography: str = ""
    ai_involvement: dict[str, object] = Field(default_factory=dict)

class ExportRecord(BaseModel):
    id: str
    package_path: str
    selected_artifacts: list[str]
    manifest_sha256: str
    blind_review: bool
    created_at: datetime
    stale: bool = False
```

Set `ProjectRecord.schema_version: Literal[2] = 2`, add `exports: list[ExportRecord]`, and add `status`, `operation_id`, and `confirmed_at` to `GenerationRecord`.

- [ ] **Step 4: Run model tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py tests/test_generation_base.py tests/test_exporter.py -q`

Expected: new model tests PASS; legacy fixture tests may still fail until Task 2 migration is added.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/domain.py tests/test_projects.py tests/test_generation_base.py tests/test_exporter.py
git commit -m "feat: model provenance and artifact lifecycle"
```

### Task 2: Migrate schema-v1 projects safely

**Files:**
- Modify: `src/pattern_reborn/projects.py`
- Modify: `tests/test_projects.py`
- Create: `tests/fixtures/projects/schema_v1_minimal.json`

**Interfaces:**
- Produces: `_migrate_payload(payload: dict[str, object]) -> dict[str, object]` and repository loading of versions 1 and 2.
- Consumes: schema-v2 models from Task 1.

- [ ] **Step 1: Add failing migration and no-overwrite tests**

```python
def test_load_migrates_v1_in_memory_with_explicit_unknown_rights(repository, v1_project):
    loaded = repository.load(v1_project.id)
    assert loaded.schema_version == 2
    assert loaded.source.rights.license == "unknown"
    assert loaded.exports == []

def test_invalid_v1_migration_never_rewrites_original(repository, corrupt_v1_path):
    before = corrupt_v1_path.read_bytes()
    with pytest.raises(ProjectCorruptError):
        repository.load(corrupt_v1_path.parent.name)
    assert corrupt_v1_path.read_bytes() == before
```

- [ ] **Step 2: Run migration tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py -q`

Expected: FAIL because version 1 is currently the only accepted schema and version 2 fields are absent.

- [ ] **Step 3: Implement pure payload migration before validation**

```python
def _migrate_payload(payload: dict[str, object]) -> dict[str, object]:
    version = payload.get("schema_version")
    if version == 2:
        return payload
    if version != 1:
        raise UnsupportedProjectSchemaError("项目文件版本不支持，未对原文件作任何修改。")
    migrated = copy.deepcopy(payload)
    migrated["schema_version"] = 2
    migrated.setdefault("exports", [])
    source = dict(migrated.get("source") or {})
    source.setdefault("rights", SourceRights().model_dump(mode="json"))
    migrated["source"] = source
    for generation in migrated.get("generations", []):
        generation.setdefault("status", "confirmed")
        generation.setdefault("operation_id", generation.get("id", "legacy"))
        generation.setdefault("confirmed_at", generation.get("created_at"))
    return migrated
```

Validate the migrated copy with `ProjectRecord.model_validate`; persist it only on the next explicit `save`.

- [ ] **Step 4: Run project and workflow tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py tests/test_workflow.py tests/integration/test_offline_pipeline.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/projects.py tests/test_projects.py tests/fixtures/projects/schema_v1_minimal.json
git commit -m "feat: migrate local projects to schema v2"
```

### Task 3: Carry demo and upload rights into projects

**Files:**
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `src/pattern_reborn/ui/home.py`
- Modify: `src/pattern_reborn/ui/studio.py`
- Modify: `tests/ui/test_home.py`
- Modify: `tests/ui/test_studio.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Produces: `CreateProjectCommand.rights: SourceRights`; complete `DemoCase.rights: SourceRights`.
- Consumes: `SourceRights` from Task 1.

- [ ] **Step 1: Write failing demo-to-project provenance test**

```python
def test_opening_demo_preserves_all_rights_fields(app_test, service, demo):
    app_test.button(key=f"demo-open-{demo.id}").click().run()
    project = service.load_project(app_test.session_state["project_id"])
    assert project.source.rights.source_url == demo.rights.source_url
    assert project.source.rights.license == demo.rights.license
    assert project.source.rights.ai_involvement == demo.rights.ai_involvement
```

- [ ] **Step 2: Verify the current create command drops rights**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_home.py tests/ui/test_studio.py tests/test_workflow.py -q`

Expected: FAIL because only provenance enum/category are passed.

- [ ] **Step 3: Parse and persist complete rights metadata**

```python
class CreateProjectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    name: str
    source: Path
    category: CategoryId
    provenance: ProvenanceClass
    subject: str | None = None
    rights: SourceRights = Field(default_factory=SourceRights)

# repository.create / _copy_source
source_record = self._copy_source(project_dir, source).model_copy(update={"rights": rights})
```

`load_validated_demos` must read `title`, `creator_institution`, `license`, `source_url`, `retrieval_date`, `bibliography`, and `ai_involvement` from each metadata file. The manual upload form provides these fields in its provenance panel.

- [ ] **Step 4: Run focused UI and workflow tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_home.py tests/ui/test_studio.py tests/test_workflow.py tests/test_exporter.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/workflow.py src/pattern_reborn/projects.py src/pattern_reborn/ui/home.py src/pattern_reborn/ui/studio.py tests/ui/test_home.py tests/ui/test_studio.py tests/test_workflow.py
git commit -m "feat: preserve source rights in projects"
```

### Task 4: Roll back failed creation and verify source integrity

**Files:**
- Modify: `src/pattern_reborn/projects.py`
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `tests/test_projects.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_exporter.py`

**Interfaces:**
- Produces: `ProjectRepository.verify_source(project: ProjectRecord) -> Path`; `SourceIntegrityError`.
- Consumes: source digest and size from `SourceRecord`.

- [ ] **Step 1: Write failing rollback and mutation tests**

```python
def test_create_removes_partial_project_when_save_fails(repository, source, monkeypatch):
    before = set(repository.workspace.iterdir())
    monkeypatch.setattr(repository, "save", fail_save)
    with pytest.raises(ProjectRepositoryError):
        repository.create("name", source, CATEGORY, PROVENANCE, SourceRights())
    assert set(repository.workspace.iterdir()) == before

def test_changed_source_blocks_processing_and_marks_outputs_stale(app_service, project):
    source = app_service.repository.project_dir(project.id) / project.source.relative_path
    source.write_bytes(b"changed")
    with pytest.raises(WorkflowError, match="源文件.*变化"):
        app_service.analyze(project.id)
```

- [ ] **Step 2: Run tests and observe orphan/mutation failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py tests/test_workflow.py tests/test_exporter.py -q`

Expected: FAIL.

- [ ] **Step 3: Add recoverable project cleanup and digest verification**

```python
def verify_source(self, project: ProjectRecord) -> Path:
    path = self._validate_relative_path(self.project_dir(project.id), project.source.relative_path)
    digest, byte_size = _sha256_and_size(path)
    if digest != project.source.sha256 or byte_size != project.source.byte_size:
        raise SourceIntegrityError("项目源文件已变化，请恢复原文件或明确替换来源。")
    return path
```

Wrap create/copy/save in `try/except`, remove only the exact newly-created validated project directory on failure, and call `verify_source` before extraction, analysis, composition, mockup, and export. On mismatch, mark dependent artifact IDs and export records stale before returning the typed error.

- [ ] **Step 4: Run repository/workflow/export tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py tests/test_workflow.py tests/test_exporter.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/projects.py src/pattern_reborn/workflow.py tests/test_projects.py tests/test_workflow.py tests/test_exporter.py
git commit -m "fix: rollback projects and verify source integrity"
```

### Task 5: Make generated artifacts explicitly confirmable

**Files:**
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `src/pattern_reborn/projects.py`
- Modify: `src/pattern_reborn/exporter.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_exporter.py`

**Interfaces:**
- Produces: `PatternRebornService.confirm_generation(project_id: str, generation_id: str) -> ProjectRecord`; current-generation filter requiring `GenerationStatus.CONFIRMED`.
- Consumes: lifecycle records from Task 1.

- [ ] **Step 1: Write failing interrupted-confirmation tests**

```python
def test_failed_generation_confirmation_never_becomes_exportable(app_service, generated_result, monkeypatch):
    monkeypatch.setattr(app_service.repository, "confirm", fail_confirm)
    with pytest.raises(WorkflowError):
        app_service.generate(PROJECT_ID, REQUEST, CredentialMode.PLATFORM, None)
    project = app_service.load_project(PROJECT_ID)
    assert all(item.status is not GenerationStatus.CONFIRMED for item in project.generations)
    assert project.artifacts.generation == []

def test_mockup_rejects_pending_generation(app_service, pending_generation):
    with pytest.raises(WorkflowError, match="确认"):
        app_service.make_mockup(PROJECT_ID, "bookmark", pending_generation.artifact_path)
```

- [ ] **Step 2: Verify current append-before-confirm behavior fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_exporter.py -q`

Expected: FAIL.

- [ ] **Step 3: Stage, save, and confirm generation transactionally**

```python
record = GenerationRecord(
    id=generation_id, operation_id=operation_id,
    status=GenerationStatus.PENDING_CONFIRMATION,
    provider=result.provider.value, model=result.model, prompt=result.prompt,
    artifact_path=artifact_id, created_at=now, confirmed_at=None,
)
project.generations.append(record)
self.repository.save(project)

def confirm_generation(self, project_id: str, generation_id: str) -> ProjectRecord:
    project = self.repository.load(project_id)
    record = _require_pending_generation(project, generation_id)
    self.repository.confirm(project.id, StepId.GENERATION, [record.artifact_path])
    project = self.repository.load(project.id)
    _set_generation_status(project, generation_id, GenerationStatus.CONFIRMED, datetime.now(UTC))
    self.repository.save(project)
    return project
```

If any commit step fails, keep the record pending/failed and exclude it from `_current_generations` and `_current_mockup_artwork_ids`.

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_exporter.py tests/integration/test_offline_pipeline.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/workflow.py src/pattern_reborn/projects.py src/pattern_reborn/exporter.py tests/test_workflow.py tests/test_exporter.py
git commit -m "fix: require confirmation for generated artifacts"
```

### Task 6: Persist export history and implement blind-review packages

**Files:**
- Modify: `src/pattern_reborn/exporter.py`
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `tests/test_exporter.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Produces: `ExportSelection.blind_review: bool`; `ExportResult(package: Path, selected_artifacts: list[str], manifest_sha256: str)`; persisted `ExportRecord`.
- Consumes: schema-v2 `ExportRecord` and source-integrity verification.

- [ ] **Step 1: Write failing export-history and redaction tests**

```python
def test_blind_export_omits_project_identity_and_source_filename(project, exporter, tmp_path):
    result = exporter.export(project, ExportSelection(source=True, report=True, blind_review=True), tmp_path)
    combined = "\n".join(path.read_text("utf-8") for path in result.package.rglob("*.json"))
    assert project.name not in combined
    assert project.source.original_filename not in combined

def test_workflow_persists_export_manifest_digest(app_service, project):
    result = app_service.export(project.id, ExportSelection(report=True))
    saved = app_service.load_project(project.id)
    assert saved.exports[-1].manifest_sha256 == result.manifest_sha256
```

- [ ] **Step 2: Verify current exporter always emits identity and workflow records no artifacts**

Run: `.venv\Scripts\python.exe -m pytest tests/test_exporter.py tests/test_workflow.py -q`

Expected: FAIL.

- [ ] **Step 3: Add blind naming, internal digest, and export records**

```python
class ExportSelection(BaseModel):
    source: bool = False
    extracted: bool = False
    patterns: bool = False
    generations: bool = False
    mockups: bool = False
    svg: bool = False
    report: bool = False
    blind_review: bool = False

package_stem = "judge-package" if selection.blind_review else _sanitize_filename(project.name)
visible_project_id = "anonymous" if selection.blind_review else project.id
visible_source_name = "source" + Path(project.source.original_filename).suffix if selection.blind_review else project.source.original_filename
```

Return `ExportResult`, hash the committed `manifest.json`, append an `ExportRecord`, and mark previous records stale whenever an upstream step is reconfirmed.

- [ ] **Step 4: Run export, workflow, and integration tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_exporter.py tests/test_workflow.py tests/integration/test_offline_pipeline.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/exporter.py src/pattern_reborn/workflow.py tests/test_exporter.py tests/test_workflow.py tests/integration/test_offline_pipeline.py
git commit -m "feat: persist traceable and blind exports"
```

### Task 7: Tighten demo containment and category/profile mapping

**Files:**
- Modify: `scripts/validate_demo_assets.py`
- Modify: `tests/test_demo_assets.py`
- Modify: `src/pattern_reborn/ui/home.py`
- Modify: `tests/ui/test_home.py`

**Interfaces:**
- Produces: exact case-directory containment and `CATEGORY_PROFILE_MAP` validation.
- Consumes: nine category/four profile identifiers from the knowledge catalog contract.

- [ ] **Step 1: Write failing traversal and contradiction tests**

```python
@pytest.mark.parametrize("case_id", ["../outside", "C:/outside", "/outside"])
def test_validator_rejects_case_id_outside_demo_root(tmp_path, case_id):
    result = validate_demo_root(_demo_with_case(tmp_path, case_id))
    assert any("案例标识" in error for error in result.errors)

def test_validator_rejects_category_profile_contradiction(tmp_path):
    root = _demo_case(tmp_path, category="paper_cutting", profile="artifact_photo")
    assert any("品类与处理模式" in error for error in validate_demo_root(root).errors)
```

- [ ] **Step 2: Verify the contradictory pair is currently accepted**

Run: `.venv\Scripts\python.exe -m pytest tests/test_demo_assets.py tests/ui/test_home.py -q`

Expected: FAIL.

- [ ] **Step 3: Constrain IDs, metadata paths, and mappings**

```python
CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
CATEGORY_PROFILE_MAP = {
    "paper_cutting": {"silhouette"},
    "embroidery_brocade": {"textile"},
    "dyeing_textile": {"flat_color", "textile"},
    "ceramic_ornament": {"artifact_photo"},
    # include all nine categories explicitly
}
```

Resolve `case_dir` with `_contained_path(demo_root, case_id)` before reading metadata. Apply the same containment contract in `load_validated_demos` so the UI never accepts a case rejected by the CLI validator.

- [ ] **Step 4: Run validator and competition-ready command**

Run: `.venv\Scripts\python.exe -m pytest tests/test_demo_assets.py tests/ui/test_home.py -q`

Expected: PASS.

Run: `.venv\Scripts\python.exe scripts\validate_demo_assets.py data\demo --competition-ready`

Expected: `校验通过。`

- [ ] **Step 5: Commit**

```powershell
git add scripts/validate_demo_assets.py src/pattern_reborn/ui/home.py tests/test_demo_assets.py tests/ui/test_home.py
git commit -m "fix: enforce demo containment and profile mapping"
```

### Task 8: Persistence checkpoint

**Files:**
- Modify only if verification exposes a regression in files changed by this plan.

**Interfaces:**
- Produces: schema-v2 projects and competition-safe export as a stable dependency for generation/UI plans.
- Consumes: all tasks in this plan.

- [ ] **Step 1: Run persistence, workflow, export, and demo suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py tests/test_workflow.py tests/test_exporter.py tests/test_demo_assets.py tests/ui/test_home.py tests/integration/test_offline_pipeline.py -q`

Expected: PASS.

- [ ] **Step 2: Load a copied schema-v1 fixture and save it as schema v2**

Run: `.venv\Scripts\python.exe -m pytest tests/test_projects.py::test_load_migrates_v1_in_memory_with_explicit_unknown_rights -v`

Expected: PASS and no mutation of the checked-in fixture.

- [ ] **Step 3: Inspect working tree**

Run: `git status --short`

Expected: no runtime workspace, export package, or secret-bearing file appears.

- [ ] **Step 4: Commit only checkpoint repairs**

```powershell
git add src/pattern_reborn/domain.py src/pattern_reborn/projects.py src/pattern_reborn/workflow.py src/pattern_reborn/exporter.py src/pattern_reborn/ui/home.py src/pattern_reborn/ui/studio.py scripts/validate_demo_assets.py tests
git commit -m "test: close persistence regressions"
```
