"""Verify a local release, expand into a NEW folder and copy local data.

The old installation remains the backup. No files are deleted, no package is
installed, no service is started and no global configuration is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def upgrade(archive_path: Path, source: Path, destination: Path) -> Path:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Destination must be a new folder outside the current installation; no files were changed.")
    if not destination.parent.is_dir():
        raise ValueError("Destination parent must already exist.")
    with ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 20000 or sum(item.file_size for item in entries) > 512 * 1024 * 1024:
            raise ValueError("Release ZIP exceeds local source-bundle limits.")
        roots = set()
        normalized = {}
        for item in entries:
            name = PurePosixPath(item.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in item.filename or ":" in item.filename or len(name.parts) < 2:
                raise ValueError("Unsafe release ZIP path.")
            if stat.S_ISLNK(item.external_attr >> 16) or item.file_size > 64 * 1024 * 1024:
                raise ValueError("Unsafe release ZIP entry.")
            reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
            if item.is_dir() or any(part.endswith((".", " ")) or part.split(".")[0].upper() in reserved for part in name.parts):
                raise ValueError("Unsupported Windows release ZIP path.")
            roots.add(name.parts[0])
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            folded = relative.casefold()
            if folded in normalized:
                raise ValueError("Duplicate release ZIP entry.")
            normalized[folded] = relative
        if len(roots) != 1:
            raise ValueError("Release must have one application folder.")
        prefix = next(iter(roots)) + "/"
        manifest = json.loads(archive.read(prefix + "release-manifest.json"))
        if manifest.get("format") != "pattern-reborn-local-source-v1":
            raise ValueError("This ZIP is not a program source bundle. Project backups cannot upgrade the application.")
        expected = manifest["files"]
        if set(normalized.values()) != set(expected) | {"release-manifest.json"}:
            raise ValueError("ZIP entries differ from release manifest.")
        for name, details in expected.items():
            payload = archive.read(prefix + name)
            if len(payload) != details["bytes"] or hashlib.sha256(payload).hexdigest() != details["sha256"]:
                raise ValueError("Release manifest checksum mismatch.")
        # Validation above is complete before any destination file is created.
        destination.mkdir()
        for item in entries:
            relative = PurePosixPath(item.filename).parts[1:]
            target = destination.joinpath(*relative)
            if not target.resolve().is_relative_to(destination):
                raise ValueError("Destination path escapes new installation.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(archive.read(item))
    for name in ("workspace", "outputs", "models", "config", ".private"):
        directory = source / name
        if directory.is_dir():
            _copy_tree_without_links(directory, destination / name)
    for path in source.glob(".env*"):
        if path.name != ".env.example" and path.is_file() and not path.is_symlink():
            shutil.copy2(path, destination / path.name)
    secrets = source / ".streamlit/secrets.toml"
    if secrets.is_file() and not secrets.is_symlink():
        (destination / ".streamlit").mkdir(exist_ok=True)
        shutil.copy2(secrets, destination / ".streamlit/secrets.toml")
    return destination


def _copy_tree_without_links(source: Path, destination: Path) -> None:
    if _is_link(source):
        raise ValueError("Linked runtime data cannot be copied automatically; old installation remains intact.")
    destination.mkdir(exist_ok=True, parents=True)
    for path in source.iterdir():
        if _is_link(path):
            raise ValueError("Linked runtime data cannot be copied automatically; old installation remains intact.")
        target = destination / path.name
        if path.is_dir():
            _copy_tree_without_links(path, target)
        else:
            shutil.copy2(path, target)


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", type=Path, default=ROOT)
    args = parser.parse_args()
    print(upgrade(args.archive, args.source, args.destination))
