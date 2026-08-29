# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import streamlit as st

from pattern_reborn.capabilities import Capabilities
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.workflow import PatternRebornService


@dataclass(frozen=True, slots=True)
class DemoCase:
    id: str
    title_zh: str
    source_path: Path


def load_validated_demos(demo_root: Path) -> list[DemoCase]:
    manifest_path = demo_root / "manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list):
        return []
    try:
        root = demo_root.resolve()
    except OSError:
        return []
    validated: list[DemoCase] = []
    for item in cases:
        if not isinstance(item, dict):
            continue
        case_id = item.get("id")
        title = item.get("title_zh")
        source = item.get("source")
        if not isinstance(case_id, str) or not isinstance(title, str) or not isinstance(source, str):
            continue
        if not case_id.strip() or not title.strip() or not source.strip():
            continue
        try:
            source_path = (root / source).resolve()
        except OSError:
            continue
        if not source_path.is_relative_to(root) or not source_path.is_file():
            continue
        validated.append(DemoCase(id=case_id, title_zh=title, source_path=source_path))
    return validated


def render_studio(_service: PatternRebornService) -> None:
    st.markdown("创作工坊")
    if st.button("返回首页"):
        st.session_state["route"] = "home"
        st.session_state.pop("project_id", None)
        st.rerun()


def render_home(
    service: PatternRebornService,
    knowledge: KnowledgeCatalog,
    capabilities: Capabilities,
    demos: list[DemoCase],
) -> None:
    st.markdown("# 纹启新生")
    st.markdown("非遗纹样智能提取与再设计平台")
    if st.button("开始新创作", type="primary"):
        st.session_state["route"] = "studio"
        st.rerun()

    st.markdown("## 最近项目")
    recent = service.repository.list_recent(limit=3)
    if recent:
        for project in recent:
            if st.button(project.name, key=f"recent-{project.id}"):
                st.session_state["route"] = "studio"
                st.session_state["project_id"] = project.id
                st.rerun()
    else:
        st.markdown("暂无本地项目。")

    st.markdown("## 品类入口")
    columns = st.columns(3)
    for index, category in enumerate(knowledge.categories):
        with columns[index % 3]:
            if st.button(category.display_name_zh, key=f"category-{category.id.value}"):
                st.session_state["route"] = "studio"
                st.session_state["selected_category"] = category.id.value
                st.rerun()

    if demos:
        st.markdown("## 示例项目")
        demo_columns = st.columns(min(3, len(demos)))
        for index, demo in enumerate(demos):
            with demo_columns[index % len(demo_columns)]:
                st.markdown(f"**{demo.title_zh}**")
                st.image(str(demo.source_path), use_container_width=True)

    link_columns = st.columns(2)
    with link_columns[0]:
        if st.button("知识目录"):
            st.session_state["show_knowledge"] = True
    with link_columns[1]:
        if st.button("设置"):
            st.session_state["show_settings"] = True

    if st.session_state.get("show_knowledge"):
        notes = "、".join(category.display_name_zh for category in knowledge.categories)
        st.markdown(f"知识目录已加载九个品类：{notes}。")
    if st.session_state.get("show_settings"):
        st.markdown("设置保存在本地。平台访问凭证只从本机环境读取，不会显示密钥。")

    st.markdown("## 运行状态")
    if capabilities.opencv.available:
        st.markdown("本地处理可用")
    else:
        st.markdown(capabilities.opencv.reason_zh)
    if capabilities.api_credentials.seedream or capabilities.api_credentials.qwen:
        st.markdown("平台 API 已配置")
    else:
        st.markdown("平台 API 未配置")
    if capabilities.offline:
        st.markdown("当前离线，本地流程仍可使用。")
    if capabilities.vtracer.reason_zh:
        st.markdown(capabilities.vtracer.reason_zh)
    if capabilities.mobile_sam.reason_zh:
        st.markdown(capabilities.mobile_sam.reason_zh)
    if capabilities.canvas.reason_zh:
        st.markdown(capabilities.canvas.reason_zh)
