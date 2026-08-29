import json
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from pattern_reborn.domain import CategoryId, ProfileId


CatalogModel = TypeVar("CatalogModel", bound=BaseModel)


class CatalogLoadError(ValueError):
    """知识目录文件无法安全读取或验证。"""


class ProcessingParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    threshold_mode: str = Field(min_length=1)
    morphology_kernel: int = Field(ge=1, le=31)
    denoise_strength: int = Field(ge=0, le=10)
    palette_size: int = Field(ge=2, le=16)
    preserve_holes: bool
    manual_region_required: bool


class ProcessingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    id: ProfileId
    display_name_zh: str = Field(min_length=1)
    description_zh: str = Field(min_length=1)
    parameters: ProcessingParameters
    limitations_zh: str = Field(min_length=1)


class KnowledgeCategory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    id: CategoryId
    profile: ProfileId
    display_name_zh: str = Field(min_length=1)
    cultural_note_zh: str = Field(min_length=1)
    limitations_zh: str = Field(min_length=1)
    default_parameters: ProcessingParameters


class TraditionalColor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    name_zh: str = Field(min_length=1)
    hex_value: str = Field(pattern=r"^#[0-9A-F]{6}$")
    reference_title: str = Field(min_length=1)
    reference_url: str | None = None
    reference_bibliography: str | None = None
    digital_value_note_zh: Literal["数字色值为本平台近似，非通用标准。"]

    @model_validator(mode="after")
    def require_reference(self) -> "TraditionalColor":
        if not self.reference_url and not self.reference_bibliography:
            raise ValueError("传统色记录必须提供参考链接或参考书目。")
        return self


def _unique_ids(
    items: list[CatalogModel], attribute: str, label: str
) -> list[CatalogModel]:
    identifiers = [getattr(item, attribute) for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{label}不能重复。")
    return items


class _CategoryCatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    profiles: list[ProcessingProfile]
    categories: list[KnowledgeCategory]

    @field_validator("profiles")
    @classmethod
    def require_unique_profile_ids(
        cls, value: list[ProcessingProfile]
    ) -> list[ProcessingProfile]:
        return _unique_ids(value, "id", "处理档案标识")

    @field_validator("categories")
    @classmethod
    def require_unique_category_ids(
        cls, value: list[KnowledgeCategory]
    ) -> list[KnowledgeCategory]:
        return _unique_ids(value, "id", "类别标识")

    @model_validator(mode="after")
    def require_defined_profiles(self) -> "_CategoryCatalogFile":
        known_profiles = {profile.id for profile in self.profiles}
        if unknown_profiles := {category.profile for category in self.categories} - known_profiles:
            rendered = ", ".join(profile.value for profile in sorted(unknown_profiles))
            raise ValueError(f"类别引用了未定义的处理档案：{rendered}。")
        return self


class _ColorCatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    colors: list[TraditionalColor]

    @field_validator("colors")
    @classmethod
    def require_unique_color_slugs(cls, value: list[TraditionalColor]) -> list[TraditionalColor]:
        return _unique_ids(value, "slug", "传统色标识")


class KnowledgeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    categories: list[KnowledgeCategory]
    profiles: list[ProcessingProfile]
    colors: list[TraditionalColor]

    @classmethod
    def load(cls, knowledge_dir: Path) -> "KnowledgeCatalog":
        category_file = _read_catalog_file(knowledge_dir / "categories.json", _CategoryCatalogFile)
        color_file = _read_catalog_file(knowledge_dir / "traditional_colors.json", _ColorCatalogFile)
        return cls(
            categories=category_file.categories,
            profiles=category_file.profiles,
            colors=color_file.colors,
        )

    def profile_for(self, category: CategoryId) -> ProcessingProfile:
        category_record = next(
            (record for record in self.categories if record.id is category), None
        )
        if category_record is None:
            raise CatalogLoadError(f"知识目录不包含类别：{category.value}。")
        return next(profile for profile in self.profiles if profile.id is category_record.profile)


def _read_catalog_file(path: Path, model: type[CatalogModel]) -> CatalogModel:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise CatalogLoadError(
            f"无法读取知识目录文件 {path.name}（JSON 位置：$）：文件不存在或无法读取。"
        ) from None
    try:
        json.loads(raw)
    except json.JSONDecodeError as error:
        raise CatalogLoadError(
            f"知识目录文件 {path.name} 无效（JSON 位置：第 {error.lineno} 行，第 {error.colno} 列）：JSON 格式错误。"
        ) from None
    try:
        return model.model_validate_json(raw, strict=True)
    except ValidationError as error:
        detail = error.errors()[0]
        location = _json_location(detail["loc"])
        raise CatalogLoadError(
            f"知识目录文件 {path.name} 无效（JSON 位置：{location}）：{detail['msg']}"
        ) from None


def _json_location(location: tuple[object, ...]) -> str:
    rendered = "$"
    for segment in location:
        rendered += f"[{segment}]" if isinstance(segment, int) else f".{segment}"
    return rendered
