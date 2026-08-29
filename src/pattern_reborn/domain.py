from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectDomainError(ValueError):
    """项目领域数据不符合持久化约束。"""


class CategoryId(str, Enum):
    PAPER_CUTTING = "paper_cutting"
    EMBROIDERY_BROCADE = "embroidery_brocade"
    DYEING_TEXTILE = "dyeing_textile"
    CERAMIC_ORNAMENT = "ceramic_ornament"
    LACQUER_ORNAMENT = "lacquer_ornament"
    FOLK_PAINTING = "folk_painting"
    ARCHITECTURAL_ORNAMENT = "architectural_ornament"
    METAL_JEWELRY = "metal_jewelry"
    FOLK_CRAFTS = "folk_crafts"


class ProfileId(str, Enum):
    SILHOUETTE = "silhouette"
    FLAT_COLOR = "flat_color"
    TEXTILE = "textile"
    ARTIFACT_PHOTO = "artifact_photo"


class ProvenanceClass(str, Enum):
    VERIFIED_ICH_SOURCE = "verified_ich_source"
    TRADITIONAL_REFERENCE = "traditional_reference"
    USER_SUPPLIED_UNVERIFIED = "user_supplied_unverified"


class StepId(str, Enum):
    UPLOAD = "upload"
    EXTRACTION = "extraction"
    ANALYSIS = "analysis"
    RECOMPOSITION = "recomposition"
    GENERATION = "generation"
    EXPORT = "export"


class ArtifactKind(str, Enum):
    SOURCE = "source"
    MASK = "mask"
    EXTRACTED = "extracted"
    ANALYSIS = "analysis"
    PATTERN = "pattern"
    GENERATION = "generation"
    MOCKUP = "mockup"
    EXPORT = "export"


class SourceRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    original_filename: str
    relative_path: str
    sha256: str
    byte_size: int


class ArtifactIndex(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    upload: list[str] = Field(default_factory=list)
    extraction: list[str] = Field(default_factory=list)
    analysis: list[str] = Field(default_factory=list)
    recomposition: list[str] = Field(default_factory=list)
    generation: list[str] = Field(default_factory=list)
    export: list[str] = Field(default_factory=list)


class GenerationRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    provider: str
    model: str
    prompt: str
    artifact_path: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProjectDomainError("项目时间必须包含 UTC 时区。")
        return value.astimezone(UTC)


class ProjectRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    schema_version: Literal[1] = 1
    id: str
    name: str
    category: CategoryId
    provenance: ProvenanceClass
    source: SourceRecord
    created_at: datetime
    updated_at: datetime
    subject: str | None = None
    profile: ProfileId | None = None
    processing_parameters: dict[str, object] = Field(default_factory=dict)
    artifacts: ArtifactIndex = Field(default_factory=ArtifactIndex)
    generations: list[GenerationRecord] = Field(default_factory=list)
    confirmed_steps: list[StepId] = Field(default_factory=list)
    stale_artifacts: list[str] = Field(default_factory=list)

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProjectDomainError("项目时间必须包含 UTC 时区。")
        return value.astimezone(UTC)
