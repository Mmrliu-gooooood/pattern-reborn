# -*- coding: utf-8 -*-
"""Immutable per-render context handed to every step module."""

from __future__ import annotations

from dataclasses import dataclass

from pattern_reborn.capabilities import Capabilities
from pattern_reborn.config import ProviderConfig
from pattern_reborn.domain import ProjectRecord
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.workflow import PatternRebornService


@dataclass(frozen=True, slots=True)
class StudioContext:
    service: PatternRebornService
    project: ProjectRecord | None
    knowledge: KnowledgeCatalog
    capabilities: Capabilities
    provider_config: ProviderConfig
