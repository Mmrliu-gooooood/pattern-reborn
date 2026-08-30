# Task 1 Report: Central image allocation limits

## Implementation summary

- Added centralized image allocation budgets and the public `ImageLimitError`, `require_bounded_size(...)`, and `require_scaled_size(...)` APIs.
- Enforced strict positive integer dimensions, finite numeric scale values, the exact source/canvas/intermediate limits from the brief, and Chinese typed errors.
- Changed `PatternRequest.canvas` and `PatternRequest.scale` to pre-coercion (`mode="before"`) validation. Direct construction of an unsafe canvas raises `PatternError` before `Image.new` can run.
- Probed Pillow-decoded source dimensions before `source.load()` and mapped limit failures to `ImageValidationError` without changing the public image API.
- Guarded source stamp conversion/copy, affine transform output, every expanded rotation, and mirror/four-way intermediate unit allocation before Pillow allocation.
- Added allocation sentinels in regression tests so unsafe RED cases fail before the requested Pillow pixel buffers can be allocated.

## Files changed

- Created `src/pattern_reborn/limits.py`
- Modified `src/pattern_reborn/images.py`
- Modified `src/pattern_reborn/patterns.py`
- Created `tests/test_limits.py`
- Modified `tests/test_images.py`
- Modified `tests/test_patterns.py`
- Created `.superpowers/sdd/2026-08-30-pattern-reborn-core-hardening/task-1-report.md`

## TDD RED/GREEN evidence

All commands used the required worktree-local interpreter from `D:\code\ican\pattern-reborn\.worktrees\competition-release`.

### 1. Strict bounded dimensions

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_limits.py -q
```

Relevant RED output:

```text
ModuleNotFoundError: No module named 'pattern_reborn.limits'
ERROR tests/test_limits.py
1 error in 0.29s
```

The first GREEN attempt correctly exposed a hand-derived fixture error: `4_097 * 4_095 == 16_777_215`, one pixel below the limit, so the test incorrectly expected rejection. Only the fixture was corrected to `4_097 * 4_096`; production code was unchanged.

Corrected GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_limits.py -q
```

Relevant GREEN output:

```text
1 passed in 0.02s
```

### 2. Safe scaled-size calculation

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_limits.py::test_scaled_size_rejects_coerced_non_finite_and_oversized_results -q
```

Relevant RED output:

```text
ImportError: cannot import name 'require_scaled_size' from 'pattern_reborn.limits'
ERROR tests/test_limits.py
1 error in 0.15s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_limits.py::test_scaled_size_rejects_coerced_non_finite_and_oversized_results -q
```

Relevant GREEN output:

```text
1 passed in 0.02s
```

### 3. Canvas validation before Pydantic coercion/allocation

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_pattern_request_rejects_unsafe_canvas_before_allocation -q
```

Relevant RED output:

```text
Failed: DID NOT RAISE <class 'pattern_reborn.patterns.PatternError'>
3 failed in 0.14s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_pattern_request_rejects_unsafe_canvas_before_allocation -q
```

Relevant GREEN output:

```text
3 passed in 0.02s
```

### 4. Scale validation before Pydantic coercion/transform

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_pattern_request_rejects_unsafe_scale_before_transform -q
```

Relevant RED output:

```text
Failed: DID NOT RAISE any of (PatternError, ValidationError)
2 failed, 1 passed in 0.18s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_pattern_request_rejects_unsafe_scale_before_transform -q
```

Relevant GREEN output:

```text
3 passed in 0.02s
```

### 5. Decoded source dimensions before Pillow pixel load

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_images.py::test_probe_rejects_oversized_decoded_dimensions_before_pixel_load -q
```

Relevant RED output:

```text
AssertionError: pixel allocation was attempted
1 failed in 0.20s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_images.py::test_probe_rejects_oversized_decoded_dimensions_before_pixel_load -q
```

Relevant GREEN output:

```text
1 passed in 0.04s
```

### 6. Affine output before `Image.transform`

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_scaled_stamp_before_transform -q
```

Relevant RED output:

```text
AssertionError: transform allocation was attempted
1 failed in 0.14s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_scaled_stamp_before_transform -q
```

Relevant GREEN output:

```text
1 passed in 0.02s
```

### 7. Expanded rotation before Pillow rotate allocation

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_expanded_rotation_before_rotate -q
```

Relevant RED output:

```text
AssertionError: expanded rotation allocation was attempted
3 failed in 0.20s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_expanded_rotation_before_rotate -q
```

Relevant GREEN output:

```text
3 passed in 0.05s
```

### 8. Source stamp before RGBA conversion/copy

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_source_stamp_before_rgba_copy -q
```

Relevant RED output:

```text
AssertionError: RGBA allocation was attempted
1 failed in 0.15s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_source_stamp_before_rgba_copy -q
```

Relevant GREEN output:

```text
1 passed in 0.03s
```

### 9. Mirror/four-way unit before `Image.new`

RED command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_composite_unit_before_image_new -q
```

Relevant RED output:

```text
AssertionError: composite unit allocation was attempted
2 failed in 0.17s
```

GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_patterns.py::test_compose_rejects_oversized_composite_unit_before_image_new -q
```

Relevant GREEN output:

```text
2 passed in 0.04s
```

## Verification

Focused command from the brief:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_limits.py tests/test_images.py tests/test_patterns.py -q
```

Initial relevant output:

```text
51 passed in 0.49s
```

Fresh pre-commit relevant output:

```text
51 passed in 0.90s
```

Full regression command:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Relevant output:

```text
296 passed in 46.71s
```

The full suite was not repeated after the status interruption because self-review made no production-code change and the user explicitly requested reuse of this completed full-suite result.

## Self-review

- Requirements coverage: all five exact constants and both required public validation interfaces are present; `PatternRequest` uses `mode="before"`; source dimensions are checked before `source.load()`; scaled and expanded-rotation dimensions are checked before Pillow allocation.
- Error contract: central failures are Chinese `ImageLimitError`s; image and pattern entry points preserve their established `ImageValidationError` and `PatternError` domain surfaces.
- Allocation-order audit: canvas validation precedes `Image.new`; source decode validation precedes pixel loading; intermediate checks precede convert/copy, transform, expanded rotate, transpose-backed four-way work, and composite-unit `Image.new`.
- Test integrity: expectations use literal boundaries. Allocation sentinels replace only the unsafe final Pillow call and tests assert the public domain error rather than mock call counts.
- Backward compatibility: valid request defaults and valid image/pattern behavior remain unchanged, confirmed by the complete regression suite.
- Scope: only the six implementation/test files named by Task 1 and this required report are included.
- Hygiene: `git diff --check` reported no whitespace errors; only the repository's existing Windows LF-to-CRLF normalization warnings appeared.

## Concerns

None.
