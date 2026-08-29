# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st
from pydantic import SecretStr

from pattern_reborn.capabilities import Capabilities
from pattern_reborn.config import ProviderConfig
from pattern_reborn.domain import CategoryId, ProvenanceClass, StepId
from pattern_reborn.exporter import ExportSelection
from pattern_reborn.generation.base import (
    CredentialMode,
    GenerationFailure,
    GenerationRequest,
    ProviderId,
    StructureLevel,
    TargetApplication,
)
from pattern_reborn.knowledge import KnowledgeCatalog
from pattern_reborn.mockups import load_mockup_catalog
from pattern_reborn.patterns import LayoutKind, PatternRequest
from pattern_reborn.segmentation import MaskEditMode, MaskStroke, PromptPoint, SegmentHints
from pattern_reborn.workflow import (
    CreateProjectCommand,
    ExtractCommand,
    PatternRebornService,
    WorkflowError,
)

STEP_LABELS = [
    "上传与分类",
    "智能提取",
    "纹样分析",
    "参数化重组",
    "AI 创意生成",
    "导出与溯源",
]
STEP_BY_LABEL = {
    "上传与分类": StepId.UPLOAD,
    "智能提取": StepId.EXTRACTION,
    "纹样分析": StepId.ANALYSIS,
    "参数化重组": StepId.RECOMPOSITION,
    "AI 创意生成": StepId.GENERATION,
    "导出与溯源": StepId.EXPORT,
}
LABEL_BY_STEP = {step: label for label, step in STEP_BY_LABEL.items()}
PROVIDER_LABELS = {
    "Seedream": ProviderId.SEEDREAM,
    "Qwen Image 3.0 Pro": ProviderId.QWEN,
}
MODE_LABELS = {"平台默认": CredentialMode.PLATFORM, "自带密钥": CredentialMode.BYOK}
STRUCTURE_LABELS = {"低": StructureLevel.LOW, "中": StructureLevel.MEDIUM, "高": StructureLevel.HIGH}
TARGET_LABELS = {
    "包装": TargetApplication.PACKAGING,
    "书签": TargetApplication.BOOKMARK,
    "织物": TargetApplication.TEXTILE,
    "海报": TargetApplication.POSTER,
    "手机壳": TargetApplication.PHONE_CASE,
}
LAYOUT_LABELS = {
    "镜像": LayoutKind.MIRROR,
    "旋转": LayoutKind.ROTATION,
    "放射": LayoutKind.RADIAL,
    "边饰": LayoutKind.BORDER,
    "二方连续": LayoutKind.TWO_WAY,
    "四方连续": LayoutKind.FOUR_WAY,
}
PROVENANCE_LABELS = {
    "已核验的传统来源": ProvenanceClass.VERIFIED_ICH_SOURCE,
    "传统参考": ProvenanceClass.TRADITIONAL_REFERENCE,
    "用户提供（未核验）": ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
}
_CANVAS_FALLBACK_ZH = "未检测到可绘制画布组件，已回退为框选与提示点输入。"
_UNSAVED_KEYS = (
    "gen_prompt",
    "gen_size",
    "gen_structure",
    "gen_target",
    "gen_colors",
    "gen_negative",
    "gen_provider",
    "gen_mode",
)


def _load_drawable_canvas():
    from streamlit_drawable_konva import st_canvas

    return st_canvas


def render_studio(
    service: PatternRebornService,
    knowledge: KnowledgeCatalog,
    capabilities: Capabilities,
    provider_config: ProviderConfig,
) -> None:
    project = _load_current_project(service)
    _ensure_step_state(project)
    with st.sidebar:
        st.radio("创作步骤", STEP_LABELS, key="studio_step")
    if st.button("返回首页"):
        st.session_state["route"] = "home"
        st.session_state.pop("project_id", None)
        st.session_state.pop("studio_step", None)
        st.session_state.pop("byok_secret", None)
        st.session_state.pop("gen_byok_input", None)
        st.rerun()
    st.markdown("创作工坊")
    step = STEP_BY_LABEL.get(st.session_state.get("studio_step", STEP_LABELS[0]), StepId.UPLOAD)
    if project is not None:
        service.save_navigation_state(project.id, step)
    if step is StepId.UPLOAD:
        _render_upload(service, knowledge, project)
    elif step is StepId.EXTRACTION:
        _render_extraction(service, knowledge, capabilities, project)
    elif step is StepId.ANALYSIS:
        _render_analysis(service, project)
    elif step is StepId.RECOMPOSITION:
        _render_recomposition(service, project)
    elif step is StepId.GENERATION:
        _render_generation(service, knowledge, capabilities, provider_config, project)
    else:
        _render_export(service, project)


def _ensure_step_state(project) -> None:
    if "studio_step" in st.session_state:
        return
    if project is not None:
        raw = project.processing_parameters.get("current_step")
        try:
            step = StepId(str(raw))
        except ValueError:
            step = StepId.UPLOAD
        st.session_state["studio_step"] = LABEL_BY_STEP.get(step, STEP_LABELS[0])
        return
    st.session_state["studio_step"] = STEP_LABELS[0]


def _load_current_project(service: PatternRebornService):
    project_id = st.session_state.get("project_id")
    if not project_id:
        return None
    try:
        return service.load_project(str(project_id))
    except Exception:
        st.session_state.pop("project_id", None)
        st.error("无法加载项目。")
        return None


def _advanced():
    return st.expander("高级设置", expanded=False)


def _restore_unsaved() -> None:
    unsaved = st.session_state.setdefault("unsaved", {})
    for key in _UNSAVED_KEYS:
        if key not in st.session_state and key in unsaved:
            st.session_state[key] = unsaved[key]


def _capture_unsaved() -> None:
    unsaved = st.session_state.setdefault("unsaved", {})
    for key in _UNSAVED_KEYS:
        if key in st.session_state:
            unsaved[key] = st.session_state[key]


def _category_names(knowledge: KnowledgeCatalog) -> dict[str, CategoryId]:
    return {category.display_name_zh: category.id for category in knowledge.categories}


def _render_upload(
    service: PatternRebornService,
    knowledge: KnowledgeCatalog,
    project,
) -> None:
    st.markdown("上传图像并记录品类与来源。")
    names = _category_names(knowledge)
    default_category = st.session_state.get("selected_category")
    category_index = 0
    name_list = list(names)
    if isinstance(default_category, str):
        for index, category_id in enumerate(names.values()):
            if category_id.value == default_category:
                category_index = index
                break
    name = st.text_input("项目名称", value=project.name if project is not None else "")
    category_name = st.selectbox("品类", name_list, index=category_index)
    provenance_name = st.selectbox("来源与权利", list(PROVENANCE_LABELS))
    uploaded = st.file_uploader(
        "上传图像",
        type=["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"],
    )
    with _advanced():
        subject = st.text_input("题材", value=project.subject if project is not None and project.subject else "")
        st.caption("确认后写入项目记录；算法参数在后续步骤中设置。")
    if st.button("创建项目", type="primary") and uploaded is not None and name.strip():
        try:
            source = _store_upload(service, uploaded)
            created = service.create_project(
                CreateProjectCommand(
                    name=name.strip(),
                    source=source,
                    category=names[category_name],
                    provenance=PROVENANCE_LABELS[provenance_name],
                    subject=subject.strip() or None,
                )
            )
            st.session_state["project_id"] = created.id
            st.success("项目已创建。")
            st.rerun()
        except (WorkflowError, OSError) as error:
            st.error(str(error))
    if project is not None:
        st.caption(f"当前项目：{project.name}")


def _store_upload(service: PatternRebornService, uploaded) -> Path:
    incoming = service.repository.workspace / ".incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    suffix = Path(getattr(uploaded, "name", "source.png")).suffix or ".png"
    destination = incoming / f"{uuid4().hex}{suffix}"
    destination.write_bytes(uploaded.getvalue())
    return destination


def _render_extraction(
    service: PatternRebornService,
    knowledge: KnowledgeCatalog,
    capabilities: Capabilities,
    project,
) -> None:
    if project is None:
        st.info("请先创建项目。")
        with _advanced():
            st.caption("提取默认使用品类对应的处理档案。")
        return
    project_dir = service.repository.project_dir(project.id)
    source_path = project_dir / project.source.relative_path
    if source_path.is_file():
        st.image(str(source_path), caption="源图")
    canvas = _optional_canvas(capabilities, source_path)
    left = st.number_input("框选左", min_value=0, value=0, step=1)
    top = st.number_input("框选上", min_value=0, value=0, step=1)
    right = st.number_input("框选右", min_value=0, value=0, step=1)
    bottom = st.number_input("框选下", min_value=0, value=0, step=1)
    point_x = st.number_input("提示点 X", min_value=0, value=0, step=1)
    point_y = st.number_input("提示点 Y", min_value=0, value=0, step=1)
    keep_point = st.checkbox("提示点保留", value=True)
    st.radio("笔触模式", ["保留", "删除"], key="stroke_mode", horizontal=True)
    stroke_coords = st.text_input("笔触坐标", placeholder="x,y;x,y")
    with _advanced():
        stroke_width = st.number_input("笔触宽度", min_value=1, value=3, step=1)
        profile_names = {profile.display_name_zh: profile.id for profile in knowledge.profiles}
        default_profile = knowledge.profile_for(project.category)
        profile_index = list(profile_names.values()).index(default_profile.id)
        profile_name = st.selectbox("处理档案", list(profile_names), index=profile_index)
        st.caption("当前提取使用 OpenCV 基线；未调用 MobileSAM。框选与提示点可辅助提取。")
    if canvas is not None:
        st.caption("画布工具：点选、框选、保留笔刷、删除笔刷。")
    if st.button("添加笔触") and stroke_coords.strip():
        try:
            points = _parse_stroke_points(stroke_coords)
            mode = MaskEditMode.KEEP if st.session_state.get("stroke_mode") == "保留" else MaskEditMode.REMOVE
            strokes = list(st.session_state.get("mask_strokes") or [])
            strokes.append(MaskStroke(mode=mode, points=points, width=int(stroke_width)))
            st.session_state["mask_strokes"] = strokes
            st.success("已记录笔触。")
        except (ValueError, WorkflowError) as error:
            st.error(str(error))
    box = (int(left), int(top), int(right), int(bottom)) if right > left and bottom > top else None
    points = _manual_prompt_points(point_x, point_y, keep_point)
    canvas_hints, canvas_strokes = hints_from_canvas_objects(st.session_state.get("canvas_objects"))
    if canvas_hints.box is not None:
        box = canvas_hints.box
    points = tuple(canvas_hints.points) + points
    strokes = canvas_strokes + list(st.session_state.get("mask_strokes") or [])
    if st.button("提取", type="primary"):
        try:
            result = service.extract(
                project.id,
                ExtractCommand(
                    profile=profile_names[profile_name],
                    hints=SegmentHints(box=box, points=points),
                    strokes=strokes,
                ),
            )
            st.image(str(result.path), caption="提取结果")
            st.success("提取完成，请确认后进入下一步。")
            st.rerun()
        except (WorkflowError, ValueError) as error:
            st.error(str(error))
    pending = project.processing_parameters.get("pending_extraction")
    if isinstance(pending, dict) and pending.get("artifact_id"):
        pending_path = project_dir / str(pending["artifact_id"])
        if pending_path.is_file():
            st.image(str(pending_path), caption="提取结果")
        if st.button("确认提取"):
            try:
                service.confirm_extraction(project.id, str(pending["artifact_id"]))
                st.success("已确认提取结果。")
                st.rerun()
            except WorkflowError as error:
                st.error(str(error))


def hints_from_canvas_objects(raw: object) -> tuple[SegmentHints, list[MaskStroke]]:
    objects = _canvas_object_list(raw)
    box: tuple[int, int, int, int] | None = None
    points: list[PromptPoint] = []
    strokes: list[MaskStroke] = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("className") or "").lower()
        attrs = item.get("attrs") if isinstance(item.get("attrs"), dict) else item
        if not isinstance(attrs, dict):
            continue
        if kind in {"rect", "rectangle"}:
            parsed = _rect_box(attrs)
            if parsed is not None:
                box = parsed
        elif kind in {"circle", "point", "dot"}:
            parsed_point = _point_xy(attrs)
            if parsed_point is not None:
                points.append(PromptPoint(x=parsed_point[0], y=parsed_point[1], keep=True))
        elif kind in {"line", "freedraw"}:
            stroke = _stroke_from_line(attrs)
            if stroke is not None:
                strokes.append(stroke)
    return SegmentHints(box=box, points=tuple(points)), strokes


def _canvas_object_list(raw: object) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    payload = raw
    if not isinstance(payload, dict):
        json_payload = getattr(raw, "json", None)
        objects = getattr(raw, "objects", None)
        if isinstance(json_payload, dict):
            payload = json_payload
        elif isinstance(objects, list):
            return list(objects)
        else:
            return []
    nested = payload.get("json")
    if isinstance(nested, dict) and isinstance(nested.get("objects"), list):
        return list(nested["objects"])
    objects = payload.get("objects")
    return list(objects) if isinstance(objects, list) else []


def _rect_box(attrs: dict) -> tuple[int, int, int, int] | None:
    x = attrs.get("x", attrs.get("left"))
    y = attrs.get("y", attrs.get("top"))
    width = attrs.get("width")
    height = attrs.get("height")
    try:
        left = int(round(float(x)))
        top = int(round(float(y)))
        right = left + int(round(float(width)))
        bottom = top + int(round(float(height)))
    except (TypeError, ValueError, OverflowError):
        return None
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _point_xy(attrs: dict) -> tuple[int, int] | None:
    x = attrs.get("x", attrs.get("left"))
    y = attrs.get("y", attrs.get("top"))
    try:
        return int(round(float(x))), int(round(float(y)))
    except (TypeError, ValueError, OverflowError):
        return None


def _stroke_from_line(attrs: dict) -> MaskStroke | None:
    raw_points = attrs.get("points")
    parsed: list[tuple[int, int]] = []
    if isinstance(raw_points, (list, tuple)) and raw_points:
        if isinstance(raw_points[0], (list, tuple)) and len(raw_points[0]) == 2:
            for item in raw_points:
                try:
                    parsed.append((int(round(float(item[0]))), int(round(float(item[1])))))
                except (TypeError, ValueError, OverflowError, IndexError):
                    return None
        elif all(not isinstance(item, (list, tuple)) for item in raw_points):
            numbers = list(raw_points)
            for index in range(0, len(numbers) - 1, 2):
                try:
                    parsed.append(
                        (int(round(float(numbers[index]))), int(round(float(numbers[index + 1]))))
                    )
                except (TypeError, ValueError, OverflowError, IndexError):
                    return None
    if len(parsed) < 1:
        return None
    width = attrs.get("strokeWidth", attrs.get("width", 3))
    try:
        stroke_width = max(1, int(round(float(width))))
    except (TypeError, ValueError, OverflowError):
        stroke_width = 3
    mode = MaskEditMode.REMOVE if str(attrs.get("mode", "")).lower() in {"remove", "erase", "删除"} else MaskEditMode.KEEP
    return MaskStroke(mode=mode, points=parsed, width=stroke_width)


def _manual_prompt_points(point_x: object, point_y: object, keep_point: object) -> tuple[PromptPoint, ...]:
    x = int(point_x)
    y = int(point_y)
    keep = bool(keep_point)
    if x == 0 and y == 0 and keep:
        return ()
    return (PromptPoint(x=x, y=y, keep=keep),)


def _optional_canvas(capabilities: Capabilities, source_path: Path):
    if not capabilities.canvas.available:
        return None
    try:
        renderer = _load_drawable_canvas()
        tool = st.selectbox("画布工具", ["点选", "框选", "保留笔刷", "删除笔刷"])
        drawing_mode = {"点选": "point", "框选": "rect"}.get(tool, "freedraw")
        background = str(source_path) if source_path.is_file() else None
        result = renderer(
            drawing_mode=drawing_mode,
            key="studio_canvas",
            height=320,
            width=320,
            background_image=background,
        )
        st.session_state["canvas_objects"] = result
        return result
    except Exception:
        st.warning(_CANVAS_FALLBACK_ZH)
        return None


def _parse_stroke_points(raw: str) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for part in raw.replace("；", ";").split(";"):
        item = part.strip()
        if not item:
            continue
        x_text, y_text = item.replace("，", ",").split(",", 1)
        points.append((int(x_text.strip()), int(y_text.strip())))
    if not points:
        raise ValueError("笔触至少需要一个坐标。")
    return points


def _render_analysis(service: PatternRebornService, project) -> None:
    if project is None:
        st.info("请先创建项目。")
        with _advanced():
            st.caption("分析使用确认后的提取结果。")
        return
    if st.button("分析", type="primary"):
        try:
            report = service.analyze(project.id)
            for color in report.palette:
                st.markdown(f"{color.hex_value}（覆盖 {color.coverage:.2%}）")
            for match in report.color_matches:
                st.markdown(f"{match.palette_color.hex_value} → {match.traditional_color.name_zh}")
            st.markdown(
                f"轮廓 {report.contours.count}，对称 垂直 {report.symmetry.vertical_score:.2f}"
            )
        except WorkflowError as error:
            st.error(str(error))
    with _advanced():
        st.caption("调色板数量由处理档案默认值决定。")


def _render_recomposition(service: PatternRebornService, project) -> None:
    if project is None:
        st.info("请先创建项目。")
        with _advanced():
            st.caption("重组使用确认后的提取结果。")
        return
    layout_name = st.selectbox("构图方式", list(LAYOUT_LABELS))
    width = st.number_input("画布宽度", min_value=32, value=256, step=16)
    height = st.number_input("画布高度", min_value=32, value=256, step=16)
    with _advanced():
        seed = st.number_input("随机种子", value=7, step=1)
        spacing = st.number_input("间距", min_value=0, value=0, step=1)
        scale = st.number_input("缩放", min_value=0.1, value=1.0, step=0.1)
        angle = st.number_input("角度", value=0.0, step=1.0)
    if st.button("重组", type="primary"):
        try:
            result = service.compose(
                project.id,
                PatternRequest(
                    layout=LAYOUT_LABELS[layout_name],
                    canvas=(int(width), int(height)),
                    seed=int(seed),
                    spacing=int(spacing),
                    scale=float(scale),
                    angle=float(angle),
                ),
            )
            st.image(str(result.path), caption="重组纹样")
        except (WorkflowError, ValueError) as error:
            st.error(str(error))


def _render_generation(
    service: PatternRebornService,
    knowledge: KnowledgeCatalog,
    capabilities: Capabilities,
    provider_config: ProviderConfig,
    project,
) -> None:
    if project is None:
        st.info("请先创建项目。")
        with _advanced():
            st.caption("生成需要已确认的提取参考图。")
        return
    _restore_unsaved()
    if capabilities.offline:
        st.info("当前离线探测未通过，仍可尝试生成；若接口不可达将在确认后提示。")
    provider_label = st.radio(
        "生图模型",
        list(PROVIDER_LABELS),
        key="gen_provider",
    )
    st.radio("凭证方式", list(MODE_LABELS), key="gen_mode")
    if st.session_state.get("gen_mode") == "自带密钥":
        entered = st.text_input("访问密钥", type="password", key="gen_byok_input")
        if entered:
            st.session_state["byok_secret"] = SecretStr(entered)
    st.text_area("提示词", key="gen_prompt")
    provider_id = PROVIDER_LABELS[str(provider_label)]
    settings = provider_config.provider(provider_id)
    size_options = list(settings.size_options)
    if "gen_size" not in st.session_state:
        st.session_state["gen_size"] = "1024x1024" if "1024x1024" in size_options else size_options[0]
    current_size = st.session_state.get("gen_size")
    if isinstance(current_size, str) and current_size not in size_options:
        st.session_state["gen_size"] = size_options[0]
    st.selectbox("输出尺寸", size_options, key="gen_size")
    st.selectbox("结构保留", list(STRUCTURE_LABELS), key="gen_structure")
    st.selectbox("目标应用", list(TARGET_LABELS), key="gen_target")
    color_names = {color.name_zh: color.slug for color in knowledge.colors}
    with _advanced():
        st.multiselect("传统色彩", list(color_names), key="gen_colors")
        st.text_input("负面约束", key="gen_negative")
        st.caption(f"当前模型：{settings.default_model}")
    extracted_id, _mask_id = _extraction_ids(project)
    if extracted_id:
        extracted_path = service.repository.project_dir(project.id) / extracted_id
        if extracted_path.is_file():
            st.image(str(extracted_path), caption="参考图")
    if st.button("生成"):
        st.session_state["generation_confirm_pending"] = True
    if st.session_state.get("generation_confirm_pending"):
        st.markdown("请确认本次生成（可能产生费用）：")
        st.markdown(f"提供商：{provider_label}")
        st.markdown(f"模型：{settings.default_model}")
        st.markdown(f"尺寸：{st.session_state.get('gen_size')}")
        st.markdown("数量：1")
        if st.button("确认生成", type="primary"):
            _dispatch_generation(
                service,
                project.id,
                extracted_id,
                provider_id,
                settings.default_model,
                knowledge,
            )
    _capture_unsaved()


def _dispatch_generation(
    service: PatternRebornService,
    project_id: str,
    extracted_id: str | None,
    provider_id: ProviderId,
    model: str,
    knowledge: KnowledgeCatalog,
) -> None:
    prompt = str(st.session_state.get("gen_prompt") or "").strip()
    if not prompt:
        st.error("请填写提示词。")
        return
    if not extracted_id:
        st.error("请先确认提取结果后再生成。")
        return
    color_names = {color.name_zh: color.slug for color in knowledge.colors}
    selected = st.session_state.get("gen_colors") or []
    slugs = [color_names[name] for name in selected if name in color_names]
    mode = MODE_LABELS[str(st.session_state.get("gen_mode") or "平台默认")]
    byok = None
    if mode is CredentialMode.BYOK:
        stored = st.session_state.get("byok_secret")
        raw = st.session_state.get("gen_byok_input")
        if isinstance(stored, SecretStr):
            byok = stored
        elif isinstance(raw, str) and raw.strip():
            byok = SecretStr(raw)
    try:
        result = service.generate(
            project_id,
            GenerationRequest(
                prompt=prompt,
                reference_path=Path(extracted_id),
                model=model,
                provider=provider_id,
                size=str(st.session_state.get("gen_size") or "1024x1024"),
                count=1,
                structure_level=STRUCTURE_LABELS[str(st.session_state.get("gen_structure") or "中")],
                target_application=TARGET_LABELS[str(st.session_state.get("gen_target") or "书签")],
                colors=slugs,
                negative_constraints=str(st.session_state.get("gen_negative") or ""),
            ),
            mode,
            byok,
        )
        st.session_state["generation_confirm_pending"] = False
        for path in result.local_files:
            st.image(str(path), caption="AI 生成")
        st.markdown("AI 生成")
    except (GenerationFailure, WorkflowError, ValueError) as error:
        message = getattr(error, "user_message_zh", str(error))
        st.error(message)


def _extraction_ids(project) -> tuple[str | None, str | None]:
    extracted = [
        path
        for path in project.artifacts.extraction
        if path.startswith("extracted/") and path.lower().endswith(".png")
    ]
    masks = [path for path in project.artifacts.extraction if path.startswith("masks/")]
    return (extracted[0] if extracted else None, masks[0] if masks else None)


def _artwork_option(project, artifact_id: str) -> str:
    generated = set(project.artifacts.generation) | {
        record.artifact_path for record in project.generations
    }
    if artifact_id in generated:
        return f"{artifact_id}（AI 生成）"
    return artifact_id


def _artwork_id(option: str) -> str:
    return option.split("（", 1)[0]


def _current_artwork_ids(project) -> list[str]:
    stale = set(project.stale_artifacts)
    ids: list[str] = []
    for path in (*project.artifacts.recomposition, *project.artifacts.generation):
        if path not in stale and path not in ids:
            ids.append(path)
    for record in project.generations:
        if record.artifact_path not in stale and record.artifact_path not in ids:
            ids.append(record.artifact_path)
    return ids


def _render_export(service: PatternRebornService, project) -> None:
    if project is None:
        st.info("请先创建项目。")
        with _advanced():
            st.caption("导出打包已确认的本地成果。")
        return
    catalog = load_mockup_catalog()
    artwork_ids = _current_artwork_ids(project)
    options = [_artwork_option(project, artifact_id) for artifact_id in artwork_ids]
    template_id = st.selectbox("贴图模板", list(catalog))
    artwork_label = st.selectbox("贴图纹样", options) if options else None
    if st.button("生成贴图") and artwork_label:
        try:
            artifact_id = _artwork_id(str(artwork_label))
            result = service.make_mockup(project.id, str(template_id), artifact_id)
            generated = artifact_id in set(project.artifacts.generation) or any(
                record.artifact_path == artifact_id for record in project.generations
            )
            caption = "AI 辅助" if generated else "贴图"
            st.image(str(result.path), caption=caption)
            if generated:
                st.markdown("AI 辅助")
        except WorkflowError as error:
            st.error(str(error))
    with _advanced():
        include_source = st.checkbox("导出原图", value=True)
        include_extracted = st.checkbox("导出提取", value=True)
        include_patterns = st.checkbox("导出重组", value=True)
        include_generations = st.checkbox("导出生成", value=True)
        include_mockups = st.checkbox("导出贴图", value=True)
        include_svg = st.checkbox("导出 SVG", value=True)
        include_report = st.checkbox("导出报告", value=True)
    if st.button("导出", type="primary"):
        try:
            package = service.export(
                project.id,
                ExportSelection(
                    source=include_source,
                    extracted=include_extracted,
                    patterns=include_patterns,
                    generations=include_generations,
                    mockups=include_mockups,
                    svg=include_svg,
                    report=include_report,
                ),
            )
            st.success(f"已导出到 {package}")
        except WorkflowError as error:
            st.error(str(error))
    for record in project.generations:
        if record.artifact_path not in project.stale_artifacts:
            st.markdown(f"AI 生成 · {record.artifact_path}")
