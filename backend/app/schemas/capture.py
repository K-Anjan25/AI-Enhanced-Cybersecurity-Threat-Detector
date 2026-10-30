"""Packet-capture control wire shapes (step 4). Checked against the dashboard's types."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: The engines a request may name by default, matching the sensor's default allowlist.
DEFAULT_CAPTURE_ENGINES: list[str] = ["zeek", "suricata"]


class CaptureStateIn(BaseModel):
    """A request to start or stop capture, and which engines to use."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    running: bool
    engines: list[str] = Field(default_factory=lambda: list(DEFAULT_CAPTURE_ENGINES), max_length=3)


class CaptureStateOut(BaseModel):
    """The desired capture state and when it was last changed."""

    running: bool
    engines: list[str]
    version: int
    changed_by: str | None
    changed_at: datetime | None
