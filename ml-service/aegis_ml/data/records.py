"""Canonical telemetry record schemas.

These define the ``flow@1`` and ``log@1`` wire contracts from architecture.md §7
and prd.md FR-04. They are the single definition of what a flow record and a log
line are; parsers, the synthetic generator, and the ingest API all speak these.

Versioning (R-44): a field change that alters meaning requires a version bump to
``flow@2``. Never edit ``flow@1`` in place — recorded data must stay readable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Annotated as Literals, not str: they are the defaults for Literal-typed
# fields, and a plain str default is a mypy assignment error.
SCHEMA_VERSION_FLOW: Literal["flow@1"] = "flow@1"
SCHEMA_VERSION_LOG: Literal["log@1"] = "log@1"


class Protocol(StrEnum):
    """Transport protocols the pipeline understands."""

    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"


class Direction(StrEnum):
    """Flow direction relative to the monitored boundary."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class FlowRecord(BaseModel):
    """One summarised network conversation — the ``flow@1`` contract.

    Fields are raw observations only. Derived quantities (byte ratio, port
    entropy, destination counts) are computed during feature extraction so the
    stored record stays a faithful capture.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["flow@1"] = SCHEMA_VERSION_FLOW

    timestamp: datetime = Field(description="Flow start, timezone-aware UTC.")

    src_ip: IPv4Address
    dst_ip: IPv4Address
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)

    protocol: Protocol
    direction: Direction
    service: str | None = Field(
        default=None,
        description="Inferred service name, e.g. 'http'. Null when unknown.",
    )
    state: str | None = Field(default=None, description="Connection state, e.g. 'SF', 'S0', 'REJ'.")

    # Volume
    packets: int = Field(ge=0)
    src_packets: int = Field(ge=0)
    dst_packets: int = Field(ge=0)
    src_bytes: int = Field(ge=0)
    dst_bytes: int = Field(ge=0)

    # Timing
    duration: float = Field(ge=0.0, description="Flow duration in seconds.")

    # TCP flag counts
    syn: int = Field(default=0, ge=0)
    ack: int = Field(default=0, ge=0)
    rst: int = Field(default=0, ge=0)
    fin: int = Field(default=0, ge=0)
    psh: int = Field(default=0, ge=0)
    urg: int = Field(default=0, ge=0)

    # Supervision. Required for generated and benchmark data; absent for live
    # traffic, which is by definition unlabelled.
    label: str | None = Field(
        default=None, description="Attack family, or 'normal'. Null for live traffic."
    )

    @field_validator("timestamp")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        """Normalise to UTC and reject naive timestamps (R-30).

        A naive timestamp is ambiguous across timezones and would silently
        corrupt every window boundary computed from it.
        """
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware; naive datetimes are rejected")
        return value.astimezone(UTC)


class LogLevel(StrEnum):
    """Standard syslog severities."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogRecord(BaseModel):
    """One log line — the ``log@1`` contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["log@1"] = SCHEMA_VERSION_LOG

    timestamp: datetime = Field(description="Event time, timezone-aware UTC.")
    host: str = Field(min_length=1)
    service: str = Field(min_length=1)
    level: LogLevel
    message: str = Field(min_length=1)

    # Populated by Drain3 template mining (T-204); null before mining runs.
    template_id: str | None = None
    parameters: Annotated[dict[str, str], Field(default_factory=dict)] = Field(
        default_factory=dict, description="Values extracted from the message template."
    )

    label: str | None = None

    @field_validator("timestamp")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        """Normalise to UTC and reject naive timestamps (R-30)."""
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware; naive datetimes are rejected")
        return value.astimezone(UTC)
