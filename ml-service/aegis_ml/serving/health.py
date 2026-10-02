"""Model-service health endpoint (T-003).

Distinguishes three states an operator needs to tell apart:
``up and serving``, ``up but no model loaded``, and ``not ready``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from aegis_ml.registry.model_registry import ModelRegistry


class LoadedModel(BaseModel):
    """One resident model version."""

    model_id: str
    kind: Literal["flow", "log"]
    status: Literal["staging", "active", "retired"]
    loaded_at: str


class ServiceHealth(BaseModel):
    """Health payload for the inference process."""

    status: Literal["ok"] = "ok"
    service: str = Field(description="Always aegis-ml-service.")
    version: str
    model_state: Literal["serving", "no_model_loaded"] = Field(
        description="'serving' once at least one model is active, otherwise "
        "'no_model_loaded'. The process is up in both cases."
    )
    models: list[LoadedModel] = Field(default_factory=list)


def build_health(
    version: str, registry: ModelRegistry, service: str = "aegis-ml-service"
) -> ServiceHealth:
    """Build the health payload from the registry contents.

    A process with no active model is still healthy — it is up and able to load
    — so the distinction is reported in ``model_state`` rather than as a failure.
    """
    snapshot = registry.snapshot()
    serving = any(info.is_serving for info in snapshot)
    return ServiceHealth(
        version=version,
        model_state="serving" if serving else "no_model_loaded",
        models=[
            LoadedModel(
                model_id=info.model_id,
                kind=info.kind,
                status=info.status,
                loaded_at=info.loaded_at.isoformat(),
            )
            for info in snapshot
        ],
        service=service,
    )
