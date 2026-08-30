# Task 4 Report: Route optional MobileSAM without weakening offline fallback

## Scope

- Added the strict string-valued `SegmentationBackend` enum with `opencv` and `mobile_sam` values.
- Added `ExtractCommand.backend`, defaulting to `SegmentationBackend.OPENCV`, with exact Python/JSON string-boundary support and rejection of invalid strings, numbers, booleans, and null values.
- Generalized the existing OpenCV constructor injection to the `Segmenter` protocol and added the optional `mobile_sam_segmenter: Segmenter | None = None` keyword.
- Routed every extraction explicitly through the selected backend and raised `WorkflowError("MobileSAM 当前不可用，请改用 OpenCV。")` when MobileSAM is selected without a wired segmenter.
- Persisted the selected backend at `pending_extraction.backend` while leaving Task 2 preprocessing provenance and Task 3 source-alpha/mask ordering unchanged.
- Added a startup-wired lazy MobileSAM proxy. Capability detection and ordinary app startup construct only the proxy; MobileSAM/Torch imports, checkpoint loading, and predictor construction occur only on the first MobileSAM `segment()` call.
- Added the minimal studio selector only when `Capabilities.mobile_sam.available` and the service has a wired MobileSAM segmenter. Otherwise the studio visibly reports an OpenCV baseline fallback and submits OpenCV explicitly.
- Did not change later redesign styling, dependency declarations, plan/spec/ledger documents, generation logic, or unrelated persistence behavior.

## Files changed

Implementation commit:

- Modified `app.py`
- Modified `src/pattern_reborn/workflow.py`
- Modified `src/pattern_reborn/ui/studio.py`
- Modified `tests/test_workflow.py`
- Modified `tests/test_capabilities.py`
- Modified `tests/ui/test_studio.py`

Reporting:

- Created `.superpowers/sdd/2026-08-30-pattern-reborn-core-hardening/task-4-report.md`

## Baseline

The supplied worktree was clean on branch `codex/competition-release` at starting HEAD `9803c62e161553d46003015310618b71cc34f60c`.

Command:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Exact result:

```text
343 passed in 38.62s
```

Exit code: `0`.

## TDD RED evidence

Tests were added before production changes. The exact RED command from the brief was:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_capabilities.py tests/ui/test_studio.py -q
```

Exact summary:

```text
6 failed, 64 passed in 8.89s
```

Exit code: `1`.

Expected failing behaviors:

- `PatternRebornService` rejected the new `mobile_sam_segmenter` constructor keyword.
- `ExtractCommand` had no backend field or OpenCV default and rejected the valid `mobile_sam` command-boundary value as an extra field.
- The unavailable-MobileSAM request could not reach the required typed workflow error because command validation rejected the missing field first.
- The studio did not visibly call the OpenCV state a fallback and did not persist an explicit OpenCV backend.
- The studio did not render a MobileSAM selector when capability detection was available and the lazy route was wired.

The invalid backend cases already rejected under the old `extra="forbid"` behavior. They were retained as preservation tests so accepting the new field could not weaken invalid-value rejection.

## TDD GREEN evidence

The first GREEN attempt preserved all new behavior but exposed one existing copy contract: fallback text still needed to say `OpenCV 基线`.

Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_capabilities.py tests/ui/test_studio.py tests/smoke/test_app_startup.py -q
```

First-attempt exact summary:

```text
1 failed, 73 passed in 11.24s
```

Only the fallback caption was adjusted to retain `OpenCV 基线`; routing and tests were not weakened.

Final focused GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_capabilities.py tests/ui/test_studio.py tests/smoke/test_app_startup.py -q
```

Exact result:

```text
74 passed in 10.65s
```

Exit code: `0`.

## Full-suite result

The full suite was run once after the final production change.

Command:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Exact result:

```text
356 passed in 40.79s
```

Exit code: `0`.

## Validation results

Compile command:

```powershell
.venv\Scripts\python.exe -m compileall -q app.py src tests scripts
```

Result: no output; exit code `0`.

Dependency command:

```powershell
.venv\Scripts\python.exe -m pip check
```

Exact result:

```text
No broken requirements found.
```

Exit code: `0`.

Whitespace command:

```powershell
git diff --check
```

Result: exit code `0`; no whitespace errors. Git emitted only the repository's expected Windows LF-to-CRLF normalization warnings for the six modified Python files.

## Self-review

- Backend contract: `SegmentationBackend` is a real enum, not a free-form string. The pre-validator accepts enum instances and exact plain-string serialization only; assignment validation remains enabled.
- Routing: OpenCV remains the constructor/default path. MobileSAM selection uses only the injected optional segmenter and cannot silently fall back to a different algorithm.
- Error contract: selecting an unwired MobileSAM route raises the exact typed Chinese `WorkflowError` before optional imports or image processing.
- Provenance: backend selection is stored beside the pending extraction's algorithm version, mask, parameters, hints, and warnings.
- Task 2 preservation: `enhance(rgb, command.preprocess)` still runs immediately before whichever segmenter is selected, and preprocessing metadata remains under `pending_extraction.parameters.preprocess`.
- Task 3 preservation: source RGBA is still retained separately; strokes are replayed before `combine_with_source_alpha`; final extraction still uses original source RGB with the alpha-constrained mask.
- Startup laziness: capability detection remains based on `find_spec`; top-level startup modules contain no Torch/MobileSAM import; model imports and checkpoint/predictor construction are inside the lazy proxy's first segmentation call.
- UI gating: the selector requires both the capability signal and a non-null wired service segmenter. The fallback path renders no backend selector, states the OpenCV fallback visibly, and records `opencv` after submission.
- Scope: the implementation commit contains exactly the six Task 4 source/test files. No dependency, redesign styling, generation, plan/spec, ledger, or unrelated persistence files changed.
- Hygiene: focused tests, startup smoke, full suite, compileall, dependency check, staged diff check, and worktree status were reviewed before the implementation commit.

## Commit

Focused implementation commit:

```text
0803c898dcfb5381bd1a52b2e0fd70ed415262b1
```

Commit message:

```text
feat: route optional MobileSAM with OpenCV fallback
```

## Residual risks

- The environment does not include or execute the real optional MobileSAM/Torch stack, so the package's real predictor construction and checkpoint compatibility remain an installation-time integration risk. The loader maps any import/model/checkpoint failure to the typed OpenCV guidance instead of breaking normal startup.
- First MobileSAM use intentionally pays model-import and checkpoint-load latency. Normal startup and all default OpenCV extraction remain free of that cost.
