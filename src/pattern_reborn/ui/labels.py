# -*- coding: utf-8 -*-
"""Chinese display labels for domain enums.

Kept in one module so the sidebar rail, the step header, and the tests all
refer to the same strings, and so ``theme`` never has to import ``studio``.
"""

from __future__ import annotations

from pattern_reborn.domain import CategoryId, ProfileId, ProvenanceClass, StepId
from pattern_reborn.generation.base import (
    CredentialMode,
    ProviderId,
    StructureLevel,
    TargetApplication,
)
from pattern_reborn.mockups import load_mockup_catalog
from pattern_reborn.patterns import LayoutKind
from pattern_reborn.segmentation import MaskEditMode

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

STEP_TITLES = {
    StepId.UPLOAD: "建立项目",
    StepId.EXTRACTION: "轮廓提取",
    StepId.ANALYSIS: "特征分析",
    StepId.RECOMPOSITION: "参数重组",
    StepId.GENERATION: "创意生成",
    StepId.EXPORT: "溯源导出",
}

STEP_GOALS = {
    StepId.UPLOAD: "上传纹样图像，记录工艺类别与来源权利。",
    StepId.EXTRACTION: "在保留原始图像的前提下，提取可编辑的纹样轮廓。",
    StepId.ANALYSIS: "识别主色、传统色映射、轮廓特征与对称关系。",
    StepId.RECOMPOSITION: "以可复现参数生成连续、镜像或放射纹样。",
    StepId.GENERATION: "以确认的提取结果为参考，创作明确标注的 AI 辅助图样。",
    StepId.EXPORT: "整理作品、贴图与完整的本地溯源记录。",
}


def step_eyebrow(step: StepId) -> str:
    """``03 / 06 · 特征分析``, derived so a step count change cannot go stale."""
    position = STEP_LABELS.index(LABEL_BY_STEP.get(step, STEP_LABELS[0])) + 1
    return f"{position:02d} / {len(STEP_LABELS):02d} · {STEP_TITLES.get(step, step.value)}"

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

LAYOUT_NOTES = {
    "镜像": "沿中轴镜像铺展，适合成对的剪纸与织锦单元。",
    "旋转": "以随机角度环绕重排，生成自然的错落节奏。",
    "放射": "由中心向外放射，适合团花与藻井式构图。",
    "边饰": "沿四边重复成环，适合织带与器物口沿。",
    "二方连续": "单向重复成带，适合腰线、门楣与书脊。",
    "四方连续": "双向重复成面，适合织物与包装满铺。",
}

PROVENANCE_LABELS = {
    "已核验的传统来源": ProvenanceClass.VERIFIED_ICH_SOURCE,
    "传统参考": ProvenanceClass.TRADITIONAL_REFERENCE,
    "用户提供（未核验）": ProvenanceClass.USER_SUPPLIED_UNVERIFIED,
}

CATEGORY_LABELS = {
    CategoryId.PAPER_CUTTING: "剪纸",
    CategoryId.EMBROIDERY_BROCADE: "刺绣与织锦",
    CategoryId.DYEING_TEXTILE: "印染织物",
    CategoryId.CERAMIC_ORNAMENT: "陶瓷纹饰",
    CategoryId.LACQUER_ORNAMENT: "漆器纹饰",
    CategoryId.FOLK_PAINTING: "年画与民间绘画",
    CategoryId.ARCHITECTURAL_ORNAMENT: "建筑彩画与砖木雕",
    CategoryId.METAL_JEWELRY: "金银与首饰纹饰",
    CategoryId.FOLK_CRAFTS: "风筝、皮影与面具",
}

PROFILE_LABELS = {
    ProfileId.SILHOUETTE: "轮廓优先",
    ProfileId.FLAT_COLOR: "平面设色",
    ProfileId.TEXTILE: "织物纹理",
    ProfileId.ARTIFACT_PHOTO: "器物照片",
}

STEP_SHORT_LABELS = {
    StepId.UPLOAD: "来源建档",
    StepId.EXTRACTION: "轮廓提取",
    StepId.ANALYSIS: "特征分析",
    StepId.RECOMPOSITION: "参数重组",
    StepId.GENERATION: "创意生成",
    StepId.EXPORT: "溯源导出",
}

# Mockup template labels. Unknown catalog ids fall back to the raw id so a newly
# added asset still appears, just without a Chinese name.
MOCKUP_TEMPLATE_LABELS = {
    "bookmark": "书签",
    "tote_bag": "帆布袋",
    "phone_case": "手机壳",
}

ARTWORK_SECTION_LABELS = {
    "patterns/": "重组纹样",
    "generated/": "AI 生成",
}

_AI_PREFIXES = ("generated/",)


def category_label(category: CategoryId) -> str:
    return CATEGORY_LABELS.get(category, category.value)


def provenance_label(provenance: ProvenanceClass) -> str:
    for label, value in PROVENANCE_LABELS.items():
        if value is provenance:
            return label
    return provenance.value


def profile_label(profile: ProfileId) -> str:
    return PROFILE_LABELS.get(profile, profile.value)


def step_label(step: StepId) -> str:
    return LABEL_BY_STEP.get(step, STEP_LABELS[0])


def step_short_label(step: StepId) -> str:
    return STEP_SHORT_LABELS.get(step, step.value)


def current_step_of(project) -> StepId:
    """Read the persisted step, falling back to ``UPLOAD`` for unknown values."""
    raw = project.processing_parameters.get("current_step")
    try:
        return StepId(str(raw))
    except ValueError:
        return StepId.UPLOAD


def mockup_template_label(template_id: str) -> str:
    return MOCKUP_TEMPLATE_LABELS.get(template_id, template_id)


def mockup_templates() -> dict[str, str]:
    """Map a Chinese template label to its catalog id."""
    return {mockup_template_label(template_id): template_id for template_id in load_mockup_catalog()}


def artwork_label(artifact_id: str) -> str:
    """Human label for a project-relative artwork path, AI outputs flagged."""
    section = next(
        (label for prefix, label in ARTWORK_SECTION_LABELS.items() if artifact_id.startswith(prefix)),
        "纹样",
    )
    return f"{section} · {artifact_id}"


def is_ai_artwork(artifact_id: str) -> bool:
    return artifact_id.startswith(_AI_PREFIXES)


def stroke_mode_label(mode: MaskEditMode) -> str:
    return "保留" if mode is MaskEditMode.KEEP else "删除"
