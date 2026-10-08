# -*- coding: utf-8 -*-
"""Small pure helpers behind the studio shell and the upload staging area."""

from __future__ import annotations

from pathlib import Path

import pytest

from pattern_reborn.ui.labels import (
    LABEL_BY_STEP,
    STEP_BY_LABEL,
    STEP_LABELS,
    artwork_label,
    category_label,
    current_step_of,
    provenance_label,
    step_eyebrow,
    step_label,
    step_short_label,
)
from pattern_reborn.domain import CategoryId, ProvenanceClass, StepId
from pattern_reborn.ui.steps.source import _safe_upload_name


def test_step_tables_are_consistent_and_cover_every_step() -> None:
    assert len(STEP_LABELS) == 6
    assert set(STEP_BY_LABEL.values()) == set(StepId)
    assert {label: step for step, label in LABEL_BY_STEP.items()} == STEP_BY_LABEL
    for step in StepId:
        assert step_label(step) in STEP_LABELS
        assert step_short_label(step)


def test_step_eyebrow_is_derived_from_the_step_order() -> None:
    assert step_eyebrow(StepId.UPLOAD) == "01 / 06 · 建立项目"
    assert step_eyebrow(StepId.EXPORT) == "06 / 06 · 溯源导出"
    # A renamed step must not desynchronise the ordinal from the six labels.
    assert step_eyebrow(StepId.ANALYSIS).startswith("03 / 06")


def test_labels_fall_back_to_raw_values_for_unknown_enums() -> None:
    assert category_label(CategoryId.PAPER_CUTTING) == "剪纸"
    assert provenance_label(ProvenanceClass.TRADITIONAL_REFERENCE) == "传统参考"
    assert artwork_label("unknown/v9.png").startswith("纹样 · ")


def test_current_step_of_tolerates_a_missing_or_invalid_value() -> None:
    class _Project:
        def __init__(self, parameters):
            self.processing_parameters = parameters

    assert current_step_of(_Project({})) is StepId.UPLOAD
    assert current_step_of(_Project({"current_step": "nonsense"})) is StepId.UPLOAD
    assert current_step_of(_Project({"current_step": "analysis"})) is StepId.ANALYSIS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("莲纹.png", "莲纹.png"),
        ("莲纹.PNG", "莲纹.png"),
        ("../../etc/passwd", "passwd.png"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.png"),
        ("payload.exe", "payload.png"),
        ("script.svg", "script.png"),
        ("/absolute/path/motif.jpeg", "motif.jpeg"),
        ("no-extension", "no-extension.png"),
        ("", "source.png"),
        (None, "source.png"),
        ("a" * 200 + ".png", "a" * 60 + ".png"),
        ("wei rd**name?.png", "weirdname.png"),
    ],
)
def test_upload_staging_names_cannot_escape_or_break_the_source_record(
    raw: object, expected: str
) -> None:
    name = _safe_upload_name(raw)
    assert name == expected
    assert "/" not in name and "\\" not in name
    assert Path(name).name == name
    assert ".." not in name
