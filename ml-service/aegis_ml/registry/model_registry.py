"""Immutable model registry.

Model versions are content-addressed and never mutated in place (rule R-68).
There is no ``latest``: a caller must ask for a specific model id or for the
active model of a given kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

ModelKind = Literal["flow", "log"]
ModelStatus = Literal["staging", "active", "retired"]


class ModelNotLoaded(RuntimeError):
    """Raised when a requested model is not resident in this process.

    The message names the model id so the caller can report precisely what is
    missing rather than a generic failure (rule R-06).
    """


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Metadata for one loaded model artifact."""

    model_id: str
    kind: ModelKind
    status: ModelStatus
    loaded_at: datetime

    @property
    def is_serving(self) -> bool:
        """Whether this version is allowed to produce published scores."""
        return self.status == "active"


class ModelRegistry:
    """Tracks which model versions this process holds in memory."""

    def __init__(self) -> None:
        """Start with no models resident; nothing is loaded implicitly."""
        self._models: dict[str, ModelInfo] = {}

    def register(self, info: ModelInfo) -> None:
        """Record a loaded model.

        Raises:
            ValueError: if the id is already registered, or if another model of
                the same kind is already ``active``. Two active versions of one
                kind would make scores ambiguous.
        """
        if info.model_id in self._models:
            raise ValueError(f"model {info.model_id!r} is already registered")
        if info.status == "active":
            existing = self.active(info.kind)
            if existing is not None:
                raise ValueError(
                    f"model {existing.model_id!r} is already active for kind "
                    f"{info.kind!r}; retire it before promoting another"
                )
        self._models[info.model_id] = info

    def retire(self, model_id: str) -> ModelInfo:
        """Mark a model retired so another version of its kind can be promoted.

        Raises:
            ModelNotLoaded: if the id is unknown.
        """
        info = self.get(model_id)
        retired = ModelInfo(
            model_id=info.model_id,
            kind=info.kind,
            status="retired",
            loaded_at=info.loaded_at,
        )
        self._models[model_id] = retired
        return retired

    def get(self, model_id: str) -> ModelInfo:
        """Return metadata for a specific model id.

        Raises:
            ModelNotLoaded: naming the id that is not resident.
        """
        try:
            return self._models[model_id]
        except KeyError:
            raise ModelNotLoaded(
                f"model {model_id!r} is not loaded; registered: {sorted(self._models) or 'none'}"
            ) from None

    def active(self, kind: ModelKind) -> ModelInfo | None:
        """Return the active model of a kind, or ``None`` if there isn't one."""
        for info in self._models.values():
            if info.kind == kind and info.status == "active":
                return info
        return None

    def snapshot(self) -> list[ModelInfo]:
        """Return all registered models, ordered by load time."""
        return sorted(self._models.values(), key=lambda info: info.loaded_at)


def now_utc() -> datetime:
    """Return the current UTC time. Isolated so tests can control it."""
    return datetime.now(UTC)
