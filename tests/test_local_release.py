"""Source releases never include runtime data; upgrades leave old data intact."""
import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest


def script_module(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_bundle(path, files, extra=None):
    manifest = {"format": "pattern-reborn-local-source-v1", "files": {
        key: {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)} for key, value in files.items()}}
    with ZipFile(path, "w") as archive:
        for name, value in files.items():
            archive.writestr("release/" + name, value)
        archive.writestr("release/release-manifest.json", json.dumps(manifest))
        if extra:
            archive.writestr(*extra)


def test_source_selection_excludes_secrets_patch_and_runtime(tmp_path):
    module = script_module("package_local")
    for name in ["src/pkg/module.py", "src/pkg/__pycache__/thing.pyc", "config/.env",
                 "config/local.patch", "config/private-secret.json", "workspace/project.json", "outputs/picture.png",
                 ".env", ".env.example", ".private/provider-settings.json", "src/.private/secret.json", "p1-review.patch", "web/dist/client/index.html"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    files = module.source_files(tmp_path)
    assert set(files) == {"src/pkg/module.py", ".env.example", "web/dist/client/index.html"}


def test_nonempty_example_credentials_stop_packaging(tmp_path):
    module = script_module("package_local")
    (tmp_path / ".env.example").write_text("SEEDREAM_API_KEY=fake-sensitive-fixture")
    with pytest.raises(ValueError, match="credential"):
        module.source_files(tmp_path)


def test_verified_upgrade_copies_private_data_and_preserves_old_installation(tmp_path):
    module = script_module("upgrade_local")
    source = tmp_path / "old"
    for name in ["workspace/project/source.png", "outputs/export.png", "models/weights.bin", "config/providers.json", ".env", ".streamlit/secrets.toml", ".private/provider-settings.json"]:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private-local-data")
    archive = tmp_path / "program.zip"
    write_bundle(archive, {"app.py": b"new code", "config/providers.json": b"default config"})
    target = module.upgrade(archive, source, tmp_path / "new")
    assert (target / "app.py").read_bytes() == b"new code"
    assert (target / "workspace/project/source.png").read_text() == "private-local-data"
    assert (target / "config/providers.json").read_text() == "private-local-data"
    assert (target / ".env").read_text() == "private-local-data"
    assert (target / ".streamlit/secrets.toml").read_text() == "private-local-data"
    assert (target / ".private/provider-settings.json").read_text() == "private-local-data"
    assert (source / "outputs/export.png").read_text() == "private-local-data"


@pytest.mark.parametrize("unsafe", ["release/../../outside.txt", "release/C:/outside.txt", "release/CON.txt", "release/app.py "])
def test_unsafe_zip_fails_before_creating_destination(tmp_path, unsafe):
    module = script_module("upgrade_local")
    old = tmp_path / "old"
    old.mkdir()
    archive = tmp_path / "bad.zip"
    write_bundle(archive, {"app.py": b"code"}, (unsafe, b"bad"))
    with pytest.raises(ValueError):
        module.upgrade(archive, old, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_manifest_corruption_preserves_destination_and_source(tmp_path):
    module = script_module("upgrade_local")
    old = tmp_path / "old"
    old.mkdir()
    archive = tmp_path / "bad.zip"
    write_bundle(archive, {"app.py": b"code"})
    with ZipFile(archive, "a") as output:
        output.writestr("release/extra.py", b"unlisted")
    with pytest.raises(ValueError, match="manifest"):
        module.upgrade(archive, old, tmp_path / "new")
    assert not (tmp_path / "new").exists()
    assert old.is_dir()


def test_upgrade_refuses_existing_or_nested_target(tmp_path):
    module = script_module("upgrade_local")
    old = tmp_path / "old"
    old.mkdir()
    for target in (old, old / "new", tmp_path):
        with pytest.raises(ValueError, match="new folder"):
            module.upgrade(tmp_path / "unused.zip", old, target)
