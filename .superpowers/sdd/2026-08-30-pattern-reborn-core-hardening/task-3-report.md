# Task 3 Report: Preserve source alpha and harden segmentation edge cases

## Scope

- Added the public `combine_with_source_alpha(mask, alpha)` segmentation helper with typed validation for a binary `uint8` mask, a two-dimensional `uint8` source-alpha array, and matching shapes.
- Preserved the original source RGBA/RGB pixels in workflow extraction while continuing to pass the preprocessed RGB array into segmentation.
- Applied source-alpha constraints after replaying mask strokes, preventing edits from restoring pixels that were fully transparent in the source.
- Rejected source images smaller than 2×2 at the workflow boundary before preprocessing/OpenCV work, and rejected direct OpenCV/MobileSAM segmentation inputs at their typed segmentation boundaries.
- Clipped MobileSAM boxes through the existing `_resolve_roi` helper and prompt points through the existing `_clip_point` helper.
- Preserved predictor coordinate conventions: boxes use exclusive right/bottom bounds up to `width`/`height`; point coordinates use valid pixel bounds up to `width - 1`/`height - 1`.
- Rejected a box that clips to an empty ROI with `SegmentationError` before calling `set_image` or `predict`.
- Did not change `PreprocessSettings`, dependency files, plan/spec documents, ledger files, UI, generation, or persistence code.

## Files changed

Implementation commit:

- Modified `src/pattern_reborn/segmentation.py`
- Modified `src/pattern_reborn/workflow.py`
- Modified `tests/test_segmentation.py`
- Modified `tests/test_mobile_sam_adapter.py`
- Modified `tests/test_workflow.py`

Reporting:

- Created `.superpowers/sdd/2026-08-30-pattern-reborn-core-hardening/task-3-report.md`

## Baseline

Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_workflow.py -q
```

Exact result:

```text
...........................................................              [100%]
59 passed in 4.26s
```

Exit code: `0`.

## TDD RED evidence

Tests were added before any production changes.

Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_workflow.py -q
```

Exact summary:

```text
....................FFFFFF.......FF.....FFFF...........................  [100%]
12 failed, 59 passed in 4.80s
```

Exit code: `1`.

Expected failing cases:

- `test_combine_with_source_alpha_clears_only_fully_transparent_pixels`
- Three `test_combine_with_source_alpha_rejects_invalid_alpha` cases
- Two `test_segmenter_rejects_images_smaller_than_two_by_two` cases
- `test_mobile_sam_clips_box_and_points_to_image_bounds`
- `test_mobile_sam_rejects_box_that_clips_to_empty_roi`
- `test_extract_never_restores_pixels_hidden_by_source_alpha`
- Three `test_extract_rejects_images_smaller_than_two_by_two` cases

The failures were caused by the missing helper, accepted tiny images, raw out-of-bounds MobileSAM hints, accepted clipped-empty ROI, and workflow restoration of a transparent source pixel.

## TDD GREEN evidence

The first GREEN attempt exposed one existing-contract regression because the 2×2 check was placed in the shared RGB validator used by safe `extract_rgba` calls.

Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_workflow.py -q
```

Exact first-attempt result:

```text
...................F...................................................  [100%]
FAILED tests/test_segmentation.py::test_extract_rgba_preserves_source_rgb_and_uses_binary_mask_as_alpha
1 failed, 70 passed in 4.73s
```

The guard was moved minimally to both actual segmenter entry points, leaving the general extraction helper backward compatible.

Final focused GREEN command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_segmentation.py tests/test_mobile_sam_adapter.py tests/test_workflow.py -q
```

Exact result:

```text
.......................................................................  [100%]
71 passed in 4.39s
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
343 passed in 42.21s
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

Result: exit code `0`; no whitespace errors. Git emitted only the repository's Windows LF-to-CRLF normalization warnings for the five modified Python files.

## Self-review

- Plan/brief coverage: every Task 3 behavior is represented by a regression test and implemented in the two scoped production modules.
- Alpha ordering: preprocessing receives a detached RGB view; final extraction receives source RGB; source alpha is combined only after optional strokes so transparent pixels cannot be restored.
- Alpha contract: the helper returns a new contiguous binary `uint8` mask, preserves partially/nonzero-alpha source pixels as eligible foreground per the plan, and does not mutate either input.
- Validation ordering: workflow checks dimensions immediately after safe image loading and before array conversion, enhancement, or segmentation; both segmenters check before profile algorithms, predictor image setup, or predictor execution.
- Hint conventions: clipped boxes retain right/bottom-exclusive coordinates accepted by array slicing and current predictor usage; clipped points are constrained to actual pixel indices.
- Empty ROI: MobileSAM reuses the same clipping and zero-area rejection path as OpenCV, and the test proves predictor state remains untouched.
- Provenance: `SegmentResult.hints` records clipped hints and warnings include `roi_clipped` and, when applicable, `prompt_points_clipped`.
- Backward compatibility: `extract_rgba` continues to support safe narrow arrays; `ExtractCommand.preprocess` and the Task 2 preprocessing/source-pixel behavior remain unchanged.
- Scope/hygiene: the implementation commit contains exactly the five planned source/test files; no generated runtime artifacts were present.

## Commit

Focused implementation commit:

```text
2c9ae2f1187f1e74e7b3365ead8c31d49f646bed
```

Commit message:

```text
fix: preserve alpha and validate segmentation hints
```

## Residual risks

- MobileSAM remains an injected optional predictor and is not exercised against a real model dependency in this task; Task 4 owns runtime routing. The adapter contract, coordinate arrays, clipped provenance, and no-call empty-ROI path are covered with the existing fake predictor.
- Source alpha intentionally constrains the binary mask by transparency presence (`alpha > 0`) as specified by the plan; it does not convert the binary extraction output into graded partial alpha.
