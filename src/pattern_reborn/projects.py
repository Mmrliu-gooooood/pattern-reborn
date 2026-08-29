import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
import re
import stat
from typing import Iterable
from uuid import uuid4

from pydantic import ValidationError

from pattern_reborn.domain import (
    ArtifactIndex,
    CategoryId,
    ProjectDomainError,
    ProjectRecord,
    ProvenanceClass,
    SourceRecord,
    StepId,
)


class ProjectRepositoryError(ProjectDomainError):
    """本地项目仓库无法安全完成操作。"""


class ProjectPathError(ProjectRepositoryError):
    """项目路径不在允许的工作区内。"""


class ProjectNotFoundError(ProjectRepositoryError):
    """请求的项目不存在。"""


class ProjectCorruptError(ProjectRepositoryError):
    """项目元数据无法安全读取。"""


class UnsupportedProjectSchemaError(ProjectRepositoryError):
    """项目版本不受当前程序支持。"""


class ProjectRepository:
    _PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
    _STEP_ORDER = (
        StepId.UPLOAD,
        StepId.EXTRACTION,
        StepId.ANALYSIS,
        StepId.RECOMPOSITION,
        StepId.GENERATION,
        StepId.EXPORT,
    )

    def __init__(self, workspace: Path) -> None:
        try:
            resolved_workspace = workspace.resolve()
            resolved_workspace.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ProjectRepositoryError("项目工作区无法创建或访问。") from error
        self.workspace = resolved_workspace

    def project_dir(self, project_id: str) -> Path:
        if not self._PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ProjectPathError("项目标识不合法，无法访问项目目录。")
        return self._contained_path(self.workspace / project_id)

    def create(
        self,
        name: str,
        source: Path,
        category: CategoryId,
        provenance: ProvenanceClass,
    ) -> ProjectRecord:
        project_id = self._new_project_id()
        project_dir = self.project_dir(project_id)
        try:
            project_dir.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise ProjectRepositoryError("项目目录无法创建。") from error
        source_record = self._copy_source(project_dir, source)
        now = datetime.now(UTC)
        project = ProjectRecord(
            id=project_id,
            name=name,
            category=category,
            provenance=provenance,
            source=source_record,
            created_at=now,
            updated_at=now,
        )
        self.save(project)
        return project

    def load(self, project_id: str) -> ProjectRecord:
        project_dir = self.project_dir(project_id)
        project_file = self._contained_path(project_dir / "project.json")
        if not self._path_exists(project_file, "项目文件无法访问。"):
            raise ProjectNotFoundError("项目文件不存在，无法读取项目。")
        project = self._read_project(project_file)
        if project.id != project_id:
            raise ProjectCorruptError("项目文件中的标识与目录不一致。")
        self._validate_project_paths(project, project_dir)
        return project

    def save(self, project: ProjectRecord) -> None:
        project_dir = self.project_dir(project.id)
        if not self._is_directory(project_dir, "项目目录无法访问。"):
            raise ProjectNotFoundError("项目目录不存在，无法保存项目。")
        self._validate_project_paths(project, project_dir)
        project_file = self._contained_path(project_dir / "project.json")
        if self._path_exists(project_file, "项目文件无法访问。"):
            current = self._read_project(project_file)
            if current.id != project.id:
                raise ProjectCorruptError("项目文件中的标识与目录不一致。")
            self._validate_project_paths(current, project_dir)
        temporary_file = self._contained_path(project_dir / "project.json.tmp")
        payload = json.dumps(
            project.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        try:
            with temporary_file.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(f"{payload}\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_file, project_file)
        except OSError as error:
            self._discard_temporary_file(temporary_file)
            raise ProjectRepositoryError("项目保存失败，原项目文件未被替换。") from error

    def list_recent(self, limit: int = 3) -> list[ProjectRecord]:
        if limit < 0:
            raise ProjectRepositoryError("最近项目数量不能为负数。")
        projects: list[ProjectRecord] = []
        try:
            paths = tuple(self.workspace.iterdir())
        except OSError as error:
            raise ProjectRepositoryError("项目工作区无法读取。") from error
        for path in paths:
            if not self._is_directory(path, "项目工作区内容无法读取。"):
                continue
            if not self._PROJECT_ID_PATTERN.fullmatch(path.name):
                continue
            projects.append(self.load(path.name))
        projects.sort(key=lambda project: project.updated_at, reverse=True)
        return projects[:limit]

    def confirm(
        self,
        project_id: str,
        step: StepId,
        artifact_paths: list[str],
    ) -> ProjectRecord:
        project = self.load(project_id)
        project_dir = self.project_dir(project.id)
        for artifact_path in artifact_paths:
            self._validate_relative_path(project_dir, artifact_path)

        step_position = self._STEP_ORDER.index(step)
        for later_step in self._STEP_ORDER[step_position + 1 :]:
            later_paths = getattr(project.artifacts, later_step.value)
            project.stale_artifacts.extend(later_paths)
            setattr(project.artifacts, later_step.value, [])

        setattr(project.artifacts, step.value, list(artifact_paths))
        retained_steps = {
            confirmed_step
            for confirmed_step in project.confirmed_steps
            if self._STEP_ORDER.index(confirmed_step) <= step_position
        }
        retained_steps.add(step)
        project.confirmed_steps = [
            candidate for candidate in self._STEP_ORDER if candidate in retained_steps
        ]
        project.updated_at = datetime.now(UTC)
        self.save(project)
        return project

    def _new_project_id(self) -> str:
        while True:
            project_id = f"project-{uuid4().hex}"
            if not self._path_exists(self.project_dir(project_id), "项目目录无法访问。"):
                return project_id

    def _copy_source(self, project_dir: Path, source: Path) -> SourceRecord:
        try:
            source_path = source.resolve(strict=True)
            source_mode = source_path.stat().st_mode
        except OSError as error:
            raise ProjectRepositoryError("源文件不存在或无法读取。") from error
        if not stat.S_ISREG(source_mode):
            raise ProjectRepositoryError("源文件不是可复制的普通文件。")

        source_dir = self._contained_path(project_dir / "source")
        try:
            source_dir.mkdir(exist_ok=True)
        except OSError as error:
            raise ProjectRepositoryError("项目源文件目录无法创建。") from error
        temporary_file = self._contained_path(source_dir / ".source.tmp")
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with source_path.open("rb") as input_file, temporary_file.open("xb") as output_file:
                while chunk := input_file.read(1024 * 1024):
                    digest.update(chunk)
                    output_file.write(chunk)
                    byte_size += len(chunk)
            destination = self._contained_path(
                source_dir / f"{digest.hexdigest()[:16]}{source_path.suffix.lower()}"
            )
            os.replace(temporary_file, destination)
        except OSError as error:
            self._discard_temporary_file(temporary_file)
            raise ProjectRepositoryError("源文件复制失败，原文件未被修改。") from error
        return SourceRecord(
            original_filename=source_path.name,
            relative_path=destination.relative_to(project_dir).as_posix(),
            sha256=digest.hexdigest(),
            byte_size=byte_size,
        )

    def _read_project(self, project_file: Path) -> ProjectRecord:
        try:
            raw = project_file.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProjectCorruptError("项目文件已损坏，未对原文件作任何修改。") from error
        if not isinstance(payload, dict):
            raise ProjectCorruptError("项目文件格式无效，未对原文件作任何修改。")
        if payload.get("schema_version") != 1:
            raise UnsupportedProjectSchemaError("项目文件版本不支持，未对原文件作任何修改。")
        try:
            return ProjectRecord.model_validate(payload)
        except (ProjectDomainError, ValidationError) as error:
            raise ProjectCorruptError("项目文件内容无效，未对原文件作任何修改。") from error

    def _validate_project_paths(self, project: ProjectRecord, project_dir: Path) -> None:
        self._validate_relative_path(project_dir, project.source.relative_path)
        for artifact_path in self._artifact_paths(project.artifacts):
            self._validate_relative_path(project_dir, artifact_path)
        for artifact_path in project.stale_artifacts:
            self._validate_relative_path(project_dir, artifact_path)
        for generation in project.generations:
            self._validate_relative_path(project_dir, generation.artifact_path)

    @staticmethod
    def _artifact_paths(index: ArtifactIndex) -> Iterable[str]:
        for step in StepId:
            yield from getattr(index, step.value)

    def _validate_relative_path(self, project_dir: Path, relative_path: str) -> Path:
        try:
            candidate = Path(relative_path)
            if not relative_path or candidate.is_absolute():
                raise ProjectPathError("项目中的文件路径不合法。")
            return self._contained_path(project_dir / candidate, project_dir)
        except ProjectRepositoryError:
            raise
        except (OSError, ValueError) as error:
            raise ProjectPathError("项目中的文件路径不合法。") from error

    def _contained_path(self, path: Path, root: Path | None = None) -> Path:
        try:
            container = (root or self.workspace).resolve()
            resolved = path.resolve()
        except OSError as error:
            raise ProjectPathError("项目路径无法解析。") from error
        if not resolved.is_relative_to(container):
            raise ProjectPathError("项目路径超出允许的工作区。")
        return resolved

    @staticmethod
    def _discard_temporary_file(temporary_file: Path) -> None:
        try:
            temporary_file.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _is_directory(path: Path, error_message: str) -> bool:
        try:
            return stat.S_ISDIR(path.stat().st_mode)
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ProjectRepositoryError(error_message) from error

    @staticmethod
    def _path_exists(path: Path, error_message: str) -> bool:
        try:
            path.stat()
            return True
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ProjectRepositoryError(error_message) from error
