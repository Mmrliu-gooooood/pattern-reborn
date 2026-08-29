from pathlib import Path

from pattern_reborn.runtime import RuntimePaths


def test_runtime_paths_are_below_repository(tmp_path: Path) -> None:
    paths = RuntimePaths.from_root(tmp_path / "pattern-reborn")
    for path in paths.mutable_directories():
        assert path.is_relative_to(paths.root)
    assert paths.environment()["HF_HOME"] == str(paths.cache / "huggingface")
    assert paths.environment()["TEMP"] == str(paths.cache / "tmp")
