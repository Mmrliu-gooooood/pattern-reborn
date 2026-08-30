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

## Fix round 1

### Independent-review findings addressed

1. Perspective output bounds are now validated before `_as_rgb_uint8(image)`, so oversized grayscale and one-channel requests cannot reach `cv2.cvtColor` or `cv2.warpPerspective`.
2. `ExtractCommand` now accepts a JSON-style `clahe_tile_grid_size` array only when it contains exactly two plain integers, normalizes it to the tuple required by `PreprocessSettings`, and leaves range enforcement to the existing strict dataclass validation. Direct `PreprocessSettings` construction still rejects lists.

### Finding 1 RED: OpenCV allocation ordering

Exact command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py::test_perspective_rejects_oversized_output_before_opencv_allocation -q
```

Relevant exact output:

```text
F                                                                        [100%]
E       AssertionError: OpenCV allocation was attempted
FAILED tests/test_preprocess.py::test_perspective_rejects_oversized_output_before_opencv_allocation
1 failed in 0.14s
```

The failure occurred at `cv2.cvtColor` inside `_as_rgb_uint8`, before `_validate_output_size` was called.

### Finding 1 GREEN

Exact command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py::test_perspective_rejects_oversized_output_before_opencv_allocation -q
```

Exact output:

```text
.                                                                        [100%]
1 passed in 0.02s
```

### Finding 2 RED: JSON array normalization

Exact command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py::test_enhancement_settings_directly_reject_json_style_grid_list tests/test_workflow.py::test_extract_command_accepts_json_style_grid_list tests/test_workflow.py::test_extract_command_accepts_grid_array_from_json tests/test_workflow.py::test_extract_command_rejects_invalid_grid_arrays_from_json -q
```

Relevant exact output:

```text
.FF.......                                                               [100%]
FAILED tests/test_workflow.py::test_extract_command_accepts_json_style_grid_list
FAILED tests/test_workflow.py::test_extract_command_accepts_grid_array_from_json
2 failed, 8 passed in 0.19s
```

Both failures were the expected `ValidationError` caused by passing the valid `[4, 6]` array directly to strict `PreprocessSettings` construction. The eight passing cases proved that direct dataclass list rejection and invalid JSON-array rejection were already strict before normalization was added.

### Finding 2 GREEN

Exact command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py::test_enhancement_settings_directly_reject_json_style_grid_list tests/test_workflow.py::test_extract_command_accepts_json_style_grid_list tests/test_workflow.py::test_extract_command_accepts_grid_array_from_json tests/test_workflow.py::test_extract_command_rejects_invalid_grid_arrays_from_json -q
```

Exact output:

```text
..........                                                               [100%]
10 passed in 0.05s
```

The invalid JSON arrays cover bool, float, string, one-item and three-item lengths, zero, and the excessive value `17`.

### Focused covering verification

Exact command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_preprocess.py tests/test_workflow.py -q
```

Exact output:

```text
..............................................................           [100%]
62 passed in 4.14s
```

Per the fix-round instruction, the whole suite was not rerun. Both changed production paths are covered by the focused preprocessing and workflow suites.

### Fix-round self-review

- Allocation sentinel coverage: the new grayscale regression replaces both `cv2.cvtColor` and `cv2.warpPerspective` with failing sentinels, so either call before the bound rejection fails the test.
- Minimal ordering change: only `_validate_output_size(output_size)` moved; valid image normalization, point validation, and perspective math are unchanged.
- JSON compatibility: both direct command-dict construction and `model_validate_json(...)` accept `[4, 6]` and expose `(4, 6)` on `command.preprocess`.
- Strictness: normalization requires `type(item) is int`, excluding bool and integer-like coercions; wrong lengths are rejected before conversion; zero and excessive integers are converted to a tuple and rejected by unchanged `PreprocessSettings` bounds.
- Direct API: `PreprocessSettings(clahe_tile_grid_size=[8, 8])` remains a typed Chinese `PreprocessError`.
- Scope: only Task 2 preprocessing/workflow code, their focused tests, and this existing report changed.

### Fix-round concerns

None.
