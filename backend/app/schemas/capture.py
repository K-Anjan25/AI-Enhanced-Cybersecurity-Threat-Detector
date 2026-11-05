"""Wire contracts for Docker-managed network-capture health."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CaptureEngine = Literal["zeek", "suricata", "tshark"]
CaptureSensorState = Literal["healthy", "stale"]
CaptureFleetState = Literal["unknown", "healthy", "stale"]


class CaptureHeartbeatIn(BaseModel):
    """One heartbeat emitted by the supervised Docker capture service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sensor_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    engines: list[CaptureEngine] = Field(min_length=1, max_length=3)

    @field_validator("engines")
    @classmethod
    def engines_are_unique(cls, engines: list[CaptureEngine]) -> list[CaptureEngine]:
        """Reject a report that claims the same supervised engine twice."""
        if len(set(engines)) != len(engines):
            raise ValueError("capture engines must be unique")
        return engines


class CaptureSensorHealth(BaseModel):
    """The latest server-received heartbeat for one configured sensor."""

    model_config = ConfigDict(frozen=True)

    sensor_id: str
    engines: list[CaptureEngine]
    status: CaptureSensorState
    last_seen_at: datetime
    age_seconds: float = Field(ge=0)


class CaptureHealthOut(BaseModel):
    """Capture reporting state; an empty sensor list means unknown, not healthy."""

    model_config = ConfigDict(frozen=True)

    status: CaptureFleetState
    heartbeat_timeout_seconds: int = Field(ge=1)
    sensors: list[CaptureSensorHealth]
