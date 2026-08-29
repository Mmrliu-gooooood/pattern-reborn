# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
import re
import socket
from urllib.request import urlopen

import pytest

from tests.smoke.server import streamlit_server

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def test_app_starts_without_optional_ai_or_canvas(free_port: int) -> None:
    env = os.environ.copy()
    env["PATTERN_REBORN_DISABLE_OPTIONAL"] = "1"
    with streamlit_server(Path("app.py"), free_port, env) as process:
        response = urlopen(f"http://127.0.0.1:{free_port}/_stcore/health", timeout=2)
        assert response.status == 200
        assert process.poll() is None


def test_readme_commands_use_venv_and_scripts_not_global_pip() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert ".venv" in readme
    assert "scripts\\bootstrap.ps1" in readme or "scripts/bootstrap.ps1" in readme
    assert "scripts\\run.ps1" in readme or "scripts/run.ps1" in readme
    assert "scripts\\test.ps1" in readme or "scripts/test.ps1" in readme
    for raw in readme.splitlines():
        line = raw.strip().lstrip("`").rstrip("`").strip()
        lowered = line.lower()
        if "pip install" not in lowered:
            continue
        assert ".venv" in line or "scripts\\" in line or "scripts/" in line
        assert "pip install -g" not in lowered
        command = line.lstrip(">").strip().lstrip("`")
        assert not command.lower().startswith("pip install")


def test_third_party_notices_table_has_required_columns() -> None:
    notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    header = notices.splitlines()[0:40]
    blob = "\n".join(header).lower()
    for column in (
        "name",
        "purpose",
        "license",
        "copyright",
        "upstream",
        "redistribut",
        "notice",
    ):
        assert column in blob, f"missing notices column marker: {column}"


def test_acceptance_checklist_has_ten_dated_items() -> None:
    text = (REPO_ROOT / "docs" / "acceptance" / "competition-checklist.md").read_text(
        encoding="utf-8"
    )
    for number in range(1, 11):
        assert re.search(rf"(?m)^\s*{number}[.\)]\s+\S", text), f"missing checklist item {number}"
    dates = re.findall(r"20\d{2}-\d{2}-\d{2}", text)
    assert len(dates) >= 10, "each of the ten checklist items must be dated"
