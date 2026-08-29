# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from pattern_reborn.capabilities import detect_capabilities
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.runtime import RuntimePaths
from pattern_reborn.ui.home import load_validated_demos, render_home, render_studio
from pattern_reborn.ui.theme import render_shell_chrome
from pattern_reborn.workflow import PatternRebornService

REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")


def _workspace_path(paths: RuntimePaths) -> Path:
    override = os.environ.get("PATTERN_REBORN_WORKSPACE")
    return Path(override) if override else paths.workspace


def _demo_root() -> Path:
    override = os.environ.get("PATTERN_REBORN_DEMO_ROOT")
    return Path(override) if override else REPO_ROOT / "data" / "demo"


def build_runtime() -> tuple[PatternRebornService, KnowledgeCatalog]:
    paths = RuntimePaths.from_root(REPO_ROOT)
    for directory in paths.mutable_directories():
        directory.mkdir(parents=True, exist_ok=True)
    repository = ProjectRepository(_workspace_path(paths))
    knowledge = KnowledgeCatalog.load(REPO_ROOT / "data" / "knowledge")
    service = PatternRebornService(
        repository,
        knowledge=knowledge,
        export_root=paths.outputs,
    )
    return service, knowledge


def main() -> None:
    st.set_page_config(
        page_title="纹启新生",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_shell_chrome()
    service, knowledge = build_runtime()
    capabilities = detect_capabilities()
    if st.session_state.get("route") == "studio":
        render_studio(service)
        return
    render_home(
        service,
        knowledge,
        capabilities,
        load_validated_demos(_demo_root()),
    )


main()
