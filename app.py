# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from pattern_reborn.capabilities import Capabilities, detect_capabilities
from pattern_reborn.config import ProviderConfig, load_provider_config
from pattern_reborn.generation.service import build_generation_service
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.projects import ProjectRepository
from pattern_reborn.runtime import RuntimePaths
from pattern_reborn.ui.home import load_validated_demos, render_home
from pattern_reborn.ui.studio import render_studio
from pattern_reborn.ui.theme import render_shell_chrome
from pattern_reborn.workflow import PatternRebornService, WorkflowError

REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")


def _workspace_path(paths: RuntimePaths) -> Path:
    override = os.environ.get("PATTERN_REBORN_WORKSPACE")
    return Path(override) if override else paths.workspace


def _demo_root() -> Path:
    override = os.environ.get("PATTERN_REBORN_DEMO_ROOT")
    return Path(override) if override else REPO_ROOT / "data" / "demo"


def _use_resource_cache() -> bool:
    return not os.environ.get("PATTERN_REBORN_WORKSPACE")


class _LazyMobileSamSegmenter:
    def __init__(self, checkpoint: Path) -> None:
        self._checkpoint = checkpoint
        self._segmenter = None

    def segment(self, image, profile, hints):
        self.validate_available()
        return self._segmenter.segment(image, profile, hints)

    def validate_available(self) -> None:
        if self._segmenter is None:
            self._segmenter = self._load_segmenter()

    def _load_segmenter(self):
        try:
            if not self._checkpoint.is_file():
                raise FileNotFoundError(self._checkpoint)
            from mobile_sam import SamPredictor, sam_model_registry

            from pattern_reborn.segmentation import MobileSamSegmenter

            model = sam_model_registry["vit_t"](checkpoint=str(self._checkpoint))
            model.to(device="cpu")
            model.eval()
            return MobileSamSegmenter(SamPredictor(model))
        except Exception as error:
            raise WorkflowError("MobileSAM 当前不可用，请改用 OpenCV。") from error


def _optional_mobile_sam_segmenter(capabilities: Capabilities):
    if not capabilities.mobile_sam.available:
        return None
    return _LazyMobileSamSegmenter(REPO_ROOT / "models" / "mobile_sam" / "mobile_sam.pt")


@st.cache_resource
def _cached_capabilities():
    return detect_capabilities()


@st.cache_resource
def _cached_generation_bundle(output_dir: str):
    provider_config = load_provider_config(REPO_ROOT / "config" / "providers.json")
    generation = build_generation_service(
        config=provider_config,
        output_dir=Path(output_dir),
    )
    return generation, provider_config


def build_runtime(
    capabilities: Capabilities | None = None,
) -> tuple[PatternRebornService, KnowledgeCatalog, ProviderConfig]:
    active_capabilities = capabilities if capabilities is not None else detect_capabilities()
    paths = RuntimePaths.from_root(REPO_ROOT)
    for directory in paths.mutable_directories():
        directory.mkdir(parents=True, exist_ok=True)
    repository = ProjectRepository(_workspace_path(paths))
    knowledge = KnowledgeCatalog.load(REPO_ROOT / "data" / "knowledge")
    output_dir = paths.outputs / "generation-cache"
    if _use_resource_cache():
        generation, provider_config = _cached_generation_bundle(str(output_dir))
    else:
        provider_config = load_provider_config(REPO_ROOT / "config" / "providers.json")
        generation = build_generation_service(config=provider_config, output_dir=output_dir)
    service = PatternRebornService(
        repository,
        knowledge=knowledge,
        generation=generation,
        export_root=paths.outputs,
        mobile_sam_segmenter=_optional_mobile_sam_segmenter(active_capabilities),
    )
    return service, knowledge, provider_config


def main() -> None:
    st.set_page_config(
        page_title="纹启新生",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_shell_chrome()
    capabilities = _cached_capabilities() if _use_resource_cache() else detect_capabilities()
    service, knowledge, provider_config = build_runtime(capabilities)
    if st.session_state.get("route") == "studio":
        render_studio(service, knowledge, capabilities, provider_config)
        return
    render_home(
        service,
        knowledge,
        capabilities,
        load_validated_demos(_demo_root()),
    )


main()
