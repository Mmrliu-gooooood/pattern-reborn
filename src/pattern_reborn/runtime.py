from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    cache: Path
    models: Path
    workspace: Path
    outputs: Path

    @classmethod
    def from_root(cls, root: Path) -> "RuntimePaths":
        resolved = root.resolve()
        return cls(
            resolved,
            resolved / ".cache",
            resolved / "models",
            resolved / "workspace",
            resolved / "outputs",
        )

    def mutable_directories(self) -> tuple[Path, ...]:
        return (
            self.cache / "pip",
            self.cache / "huggingface",
            self.cache / "torch",
            self.cache / "xdg",
            self.cache / "tmp",
            self.models,
            self.workspace,
            self.outputs,
        )

    def environment(self) -> dict[str, str]:
        return {
            "PIP_CACHE_DIR": str(self.cache / "pip"),
            "HF_HOME": str(self.cache / "huggingface"),
            "TORCH_HOME": str(self.cache / "torch"),
            "XDG_CACHE_HOME": str(self.cache / "xdg"),
            "TEMP": str(self.cache / "tmp"),
            "TMP": str(self.cache / "tmp"),
        }
