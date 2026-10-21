"""Build an allow-listed local SOURCE bundle, never a standalone executable.

No Git mutations, model downloads, user data, credentials or virtualenv binaries.
Run with the validated project's Python after rebuilding web/dist/client.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys
import tomllib
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("src", "scripts", "tests", "docs", "data", "assets",
               "web/src", "web/public", "web/scripts", "web/tests", "web/dist/client")
FILES = ("app.py", "pyproject.toml", "README.md", "CLAUDE.md", "design-qa.md", "THIRD_PARTY_NOTICES.md",
         ".gitignore", ".env.example", ".streamlit/config.toml", "config/providers.json", "web/package.json",
         "web/package-lock.json", "web/index.html", "web/vite.config.js", "web/vite.config.mjs")
BLOCKED = {"__pycache__", ".cache", "node_modules", ".git", ".venv", "workspace", "outputs", "models"}


def source_files(root: Path) -> dict[str, bytes]:
    files = {}
    candidates = [root / name for name in FILES]
    for directory in DIRECTORIES:
        start = root / directory
        if start.is_dir():
            candidates.extend(start.rglob("*"))
    for path in candidates:
        relative = path.relative_to(root)
        if any(part in BLOCKED for part in relative.parts) or path.is_symlink():
            continue
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError("Source path escapes bundle root")
        name = path.name.lower()
        if (name.startswith(".env") and name != ".env.example") or name == "secrets.toml" or name.endswith((".pyc", ".bak", ".patch", ".tmp")):
            continue
        if relative.as_posix() == "config/providers.json":
            from pattern_reborn.config import load_provider_config
            from urllib.parse import urlparse
            config = load_provider_config(path, environ={})
            if any(urlparse(provider.base_url).username or urlparse(provider.base_url).password or urlparse(provider.base_url).query for provider in config.providers):
                raise ValueError("Provider config contains URL credentials/query; use clean public endpoints before packaging.")
        if name == ".env.example":
            for line in path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    if any(token in key.upper() for token in ("API_KEY", "SECRET", "TOKEN", "PASSWORD")) and value.strip().strip("\"'"):
                        raise ValueError("Example environment file contains a nonempty credential field; packaging stopped.")
        files[relative.as_posix()] = path.read_bytes()
    return files


def licenses_and_versions(root: Path) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    notices, versions = {}, []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        version = distribution.version
        if name.lower().replace("_", "-") == "pattern-reborn":
            continue
        versions.append({"name": name, "version": version})
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{name}-{version}")
        for item in distribution.files or ():
            if not any(part.endswith(".dist-info") for part in item.parts):
                continue
            if not any(token in item.name.lower() for token in ("license", "notice", "copying")):
                continue
            path = Path(distribution.locate_file(item))
            if path.is_file():
                key = "licenses/python/" + safe + "/" + "/".join(item.parts[1:])
                notices[key] = path.read_bytes()
    module_root = root / "web/node_modules"
    if module_root.is_dir():
        for path in module_root.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.name.lower().startswith(("license", "notice", "copying")):
                if path.resolve().is_relative_to(module_root.resolve()):
                    notices["licenses/frontend/" + path.relative_to(module_root).as_posix()] = path.read_bytes()
    return notices, sorted(versions, key=lambda item: item["name"].lower())


def build(root: Path, output: Path) -> Path:
    root, output = root.resolve(), output.resolve()
    if not (root / "web/dist/client/index.html").is_file():
        raise ValueError("Build web/dist/client before packaging; this script never downloads dependencies.")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"pattern-reborn-{version}-local-{stamp}-{uuid4().hex[:6]}"
    files = source_files(root)
    licenses, versions = licenses_and_versions(root)
    files.update(licenses)
    files["Start-Workspace.cmd"] = b'@echo off\r\ncd /d "%~dp0"\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\start-local.ps1"\r\nif errorlevel 1 pause\r\n'
    files["requirements-release.txt"] = ("# Exact dependency versions from the validated build environment; Python 3.11 Windows x64.\n" +
        "\n".join(f'{item["name"]}=={item["version"]}' for item in versions if item["name"].lower() not in {"pip", "setuptools", "wheel"}) + "\n").encode()
    files["LOCAL-BUNDLE-README.txt"] = (
        f"纹启新生 {version} 本地源码包（不是独立 EXE）\n"
        "需要 Windows x64 + Python 3.11。已含构建后的前端；正常安装和启动不需要 Node。\n"
        "首次安装：powershell -ExecutionPolicy Bypass -File scripts\\install-local.ps1\n"
        "启动：双击 Start-Workspace.cmd，浏览器访问 http://127.0.0.1:8510\n"
        "首次安装默认联网下载 Python 依赖；安装后核心创作离线。AI 生成由用户主动触发，会请求远程供应商。\n"
        "源码包不含个人项目、成果、模型、密钥或虚拟环境；项目备份 ZIP 与程序源码包用途不同。\n"
        "详见 docs/product/local-release.md 与 THIRD_PARTY_NOTICES.md、licenses/。\n"
        "当前仓库未提供项目自身 LICENSE；此包用于已授权的本地使用，不能据此推定公开再分发权利。\n"
    ).encode("utf-8")
    manifest = {"format": "pattern-reborn-local-source-v1", "version": version,
                "built_at": stamp, "python": sys.version.split()[0], "requires_python": ">=3.11,<3.12",
                "standalone_executable": False, "project_license": "not-specified",
                "dependencies": versions, "files": {key: {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)} for key, value in sorted(files.items())}}
    files["release-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    target = output / (name + ".zip")
    partial = output / (name + ".zip.partial")
    with ZipFile(partial, "x", ZIP_DEFLATED, compresslevel=6) as archive:
        for relative, data in sorted(files.items()):
            archive.writestr(name + "/" + relative, data)
    with ZipFile(partial) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP verification failed; partial bundle retained for inspection.")
    partial.rename(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="ascii")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/local")
    args = parser.parse_args()
    print(build(ROOT, args.output))
