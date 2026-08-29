import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from pattern_reborn.runtime import RuntimePaths


def test_runtime_paths_are_below_repository(tmp_path: Path) -> None:
    paths = RuntimePaths.from_root(tmp_path / "pattern-reborn")
    for path in paths.mutable_directories():
        assert path.is_relative_to(paths.root)
    assert paths.environment()["HF_HOME"] == str(paths.cache / "huggingface")
    assert paths.environment()["TEMP"] == str(paths.cache / "tmp")


@pytest.mark.skipif(os.name != "nt", reason="PowerShell launcher behavior is Windows-specific")
def test_bootstrap_sets_runtime_environment_before_python_probe(tmp_path: Path) -> None:
    project = tmp_path / "project"
    script = project / "scripts" / "bootstrap.ps1"
    script.parent.mkdir(parents=True)
    source_script = Path(__file__).parents[1] / "scripts" / "bootstrap.ps1"
    shutil.copy2(source_script, script)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    probe_log = project / "probe.log"
    probe_body = """@echo off
>> "%PROBE_LOG%" echo PIP_CACHE_DIR=%PIP_CACHE_DIR%
>> "%PROBE_LOG%" echo HF_HOME=%HF_HOME%
>> "%PROBE_LOG%" echo TORCH_HOME=%TORCH_HOME%
>> "%PROBE_LOG%" echo XDG_CACHE_HOME=%XDG_CACHE_HOME%
>> "%PROBE_LOG%" echo TEMP=%TEMP%
>> "%PROBE_LOG%" echo TMP=%TMP%
if exist "%PIP_CACHE_DIR%" (>> "%PROBE_LOG%" echo PIP_CACHE_DIR_EXISTS=yes) else (>> "%PROBE_LOG%" echo PIP_CACHE_DIR_EXISTS=no)
if exist "%HF_HOME%" (>> "%PROBE_LOG%" echo HF_HOME_EXISTS=yes) else (>> "%PROBE_LOG%" echo HF_HOME_EXISTS=no)
if exist "%TORCH_HOME%" (>> "%PROBE_LOG%" echo TORCH_HOME_EXISTS=yes) else (>> "%PROBE_LOG%" echo TORCH_HOME_EXISTS=no)
if exist "%XDG_CACHE_HOME%" (>> "%PROBE_LOG%" echo XDG_CACHE_HOME_EXISTS=yes) else (>> "%PROBE_LOG%" echo XDG_CACHE_HOME_EXISTS=no)
if exist "%TEMP%" (>> "%PROBE_LOG%" echo TEMP_EXISTS=yes) else (>> "%PROBE_LOG%" echo TEMP_EXISTS=no)
if exist "%TMP%" (>> "%PROBE_LOG%" echo TMP_EXISTS=yes) else (>> "%PROBE_LOG%" echo TMP_EXISTS=no)
exit /b 1
"""
    (fake_bin / "py.cmd").write_text(probe_body, encoding="utf-8")
    (fake_bin / "python.cmd").write_text(probe_body, encoding="utf-8")

    environment = os.environ.copy()
    environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
    environment["PROBE_LOG"] = str(probe_log)
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert probe_log.exists()
    values = dict(line.split("=", 1) for line in probe_log.read_text(encoding="utf-8").splitlines())
    expected_names = ("PIP_CACHE_DIR", "HF_HOME", "TORCH_HOME", "XDG_CACHE_HOME", "TEMP", "TMP")
    for name in expected_names:
        value = Path(values[name])
        assert value.is_relative_to(project.resolve())
        assert values[f"{name}_EXISTS"] == "yes"


@pytest.mark.skipif(os.name != "nt", reason="PowerShell launcher behavior is Windows-specific")
def test_bootstrap_rejects_existing_non_311_venv(tmp_path: Path) -> None:
    project = tmp_path / "project"
    script = project / "scripts" / "bootstrap.ps1"
    script.parent.mkdir(parents=True)
    source_script = Path(__file__).parents[1] / "scripts" / "bootstrap.ps1"
    shutil.copy2(source_script, script)

    venv_path = project / ".venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
    site_packages = venv_path / "Lib" / "site-packages"
    (site_packages / "sitecustomize.py").write_text(
        "import sys\nsys.version_info = (3, 12, 0, 'final', 0)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-PythonExe",
            sys.executable,
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )

    output = f"{result.stdout}\n{result.stderr}".lower()
    assert result.returncode != 0
    assert "existing virtual environment" in output
    assert "python 3.11" in output
