# Task 2 Report: Bound preprocessing and connect it to extraction

## Implementation summary

- Kept the established `PreprocessSettings` fields exactly: `white_balance_strength`, `denoise_strength`, `clahe_clip_limit`, and `clahe_tile_grid_size`.
- Rejected string and bool coercion for those settings, including raw dictionary input entering `ExtractCommand`, while preserving valid instance/default construction.
- Converted malformed, non-finite, out-of-range, and enormous-integer preprocessing values into typed Chinese `PreprocessError` failures.
- Reused `require_bounded_size`, `MAX_INTERMEDIATE_EDGE`, and `MAX_INTERMEDIATE_PIXELS` from `pattern_reborn.limits`; no budget constant was duplicated.
- Guarded perspective output before target-buffer construction and `cv2.warpPerspective`, translating `ImageLimitError` to the established `PreprocessError` surface.
- Extended `ExtractCommand` backward-compatibly with a default `PreprocessSettings` instance.
- Applied deterministic preprocessing to the actual RGB array passed to segmentation while preserving the original RGB array for RGBA extraction.
- Persisted preprocessing provenance at `pending_extraction.parameters.preprocess`.

## Files changed

- Modified `src/pattern_reborn/preprocess.py`
- Modified `src/pattern_reborn/workflow.py`
- Modified `tests/test_preprocess.py`
- Modified `tests/test_workflow.py`
- Created `.superpowers/sdd/2026-08-30-pattern-reborn-core-hardening/task-2-report.md`

## Baseline

All commands used the required worktree-local interpreter from `D:\code\ican\pattern-reborn\.worktrees\competition-release`.

Command:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Output:

```text
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
........................................................................ [ 96%]
..........                                                               [100%]
298 passed in 48.94s
```

## TDD RED/GREEN evidence

### 1. Task 2 preprocessing bounds and extraction integration

The initial RED invocation also exposed an overly narrow test regex for already-correct bool rejection. The test assertion was corrected without changing production code, then RED was rerun so every recorded failure represented missing production behavior.

Corrected RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py tests/test_workflow.py -q
```

Relevant exact RED output:

```text
...........F.....F...F......FF..........                                 [100%]
FAILED tests/test_preprocess.py::test_perspective_rejects_oversized_output_before_warp
FAILED tests/test_preprocess.py::test_enhancement_settings_reject_string_and_bool_coercion[kwargs0]
FAILED tests/test_preprocess.py::test_enhancement_settings_reject_string_and_bool_coercion[kwargs4]
FAILED tests/test_workflow.py::test_extract_applies_preprocess_before_segmenting
FAILED tests/test_workflow.py::test_extract_persists_preprocess_settings - py...
5 failed, 35 passed in 3.88s
```

Failure causes were the expected missing behaviors:

- oversized output reached the `cv2.warpPerspective` allocation sentinel;
- numeric strings were accepted for `white_balance_strength` and `clahe_clip_limit`;
- `ExtractCommand.preprocess` was rejected as an extra field, so workflow dispatch and persistence were unavailable.

Additional malformed-grid RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py::test_enhancement_settings_reject_malformed_grid_with_typed_error -q
```

Relevant exact RED output:

```text
F                                                                        [100%]
E       TypeError: object of type 'int' has no len()
FAILED tests/test_preprocess.py::test_enhancement_settings_reject_malformed_grid_with_typed_error
1 failed in 0.16s
```

First GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py tests/test_workflow.py -q
```

Exact GREEN output:

```text
.........................................                                [100%]
41 passed in 3.93s
```

### 2. Strict `ExtractCommand` dictionary boundary

A boundary probe showed that Pydantic converted strings/bools before the standard dataclass `__post_init__`, bypassing direct `PreprocessSettings` strictness.

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion -q
```

Relevant exact RED output:

```text
FFFFFFFF                                                                 [100%]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess0]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess1]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess2]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess3]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess4]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess5]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess6]
FAILED tests/test_workflow.py::test_extract_command_rejects_preprocess_field_coercion[preprocess7]
8 failed in 0.19s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py tests/test_workflow.py -q
```

Exact GREEN output:

```text
.................................................                        [100%]
49 passed in 4.19s
```

### 3. Enormous integer conversion safety

Self-review reproduced raw `OverflowError` from `float(10**10000)` in both the perspective coordinate parser and strict settings parser.

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py::test_perspective_rejects_enormous_integer_output_with_typed_error tests/test_preprocess.py::test_enhancement_settings_reject_enormous_integer_with_typed_error -q
```

Relevant exact RED output:

```text
FF                                                                       [100%]
E           OverflowError: int too large to convert to float
E       OverflowError: int too large to convert to float
FAILED tests/test_preprocess.py::test_perspective_rejects_enormous_integer_output_with_typed_error
FAILED tests/test_preprocess.py::test_enhancement_settings_reject_enormous_integer_with_typed_error
2 failed in 0.18s
```

Final focused GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py tests/test_workflow.py -q
```

Exact GREEN output:

```text
...................................................                      [100%]
51 passed in 3.97s
```

## Verification

Fresh full-suite command after the final production change:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Exact output:

```text
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 67%]
........................................................................ [ 90%]
................................                                         [100%]
320 passed in 38.75s
```

Compile command:

```powershell
.venv\Scripts\python.exe -m compileall -q app.py src tests scripts
```

Output: none; exit code `0`.

Dependency command:

```powershell
.venv\Scripts\python.exe -m pip check
```

Exact output:

```text
No broken requirements found.
```

Whitespace command:

```powershell
git diff --check
```

Result: exit code `0`; no whitespace errors. Git emitted only the repository's Windows LF-to-CRLF normalization warnings for the four modified Python files.

## Self-review

- Requirements coverage: all Task 2 interfaces are implemented; no brightness, contrast, saturation, or other replacement settings were added.
- Centralization: perspective correction imports Task 1's exact intermediate edge/pixel budgets and `require_bounded_size`; no constants are repeated locally.
- Allocation ordering: output dimensions are parsed and bounded before target-point allocation, perspective transform creation, and `cv2.warpPerspective`.
- Error contract: limit, malformed-grid, non-finite, type-coercion, and enormous-integer failures remain typed Chinese errors at the preprocessing boundary; Pydantic wraps invalid command dictionaries as `ValidationError` containing the underlying Chinese message.
- Observable workflow behavior: the regression records the concrete RGB array received by the real segmenter, proves it equals deterministic `enhance(...)` output, and proves it differs from the source array.
- Provenance: a repository round trip confirms all four settings are stored under `pending_extraction.parameters.preprocess` in JSON-safe form.
- Backward compatibility: existing callers can continue omitting `preprocess`; the field has `default_factory=PreprocessSettings`. All pre-existing tests remain green.
- Test integrity: the OpenCV allocation sentinel replaces only the unsafe final warp; workflow uses the real enhancer and real segmenter, with the spy limited to recording the segmenter's input.
- Hygiene: full suite, compileall, dependency check, and diff check are clean. Only scoped implementation/tests and this report are present.

## Concerns

None.
