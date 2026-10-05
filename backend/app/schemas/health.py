"""Pydantic response schemas for the health endpoints (rule R-14)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness: the process is running. Never reflects dependency state."""

    status: Literal["ok"] = Field(description="Always 'ok' when the process is up.")
    service: str = Field(description="Service name, e.g. aegis-backend.")
    version: str = Field(description="Build version of the running artifact.")
    environment: str = Field(description="Deployment environment.")


class ProbeCheck(BaseModel):
    """Result of one registered readiness probe."""

    name: str
    status: Literal["ok", "degraded", "unavailable"]
    detail: str = ""


class ReadinessResponse(BaseModel):
    """Readiness: can this process serve traffic right now?

    Served with HTTP 503 when ``status`` is ``not_ready``.
    """

    status: Literal["ready", "not_ready"]
    service: str
    version: str
    checks: list[ProbeCheck] = Field(
        default_factory=list,
        description="One entry per registered dependency. Empty in the S0 skeleton.",
    )
