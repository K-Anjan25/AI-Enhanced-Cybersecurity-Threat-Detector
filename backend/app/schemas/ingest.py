"""Wire models for the ingest API (FR-01, FR-02, FR-04).

These mirror ``aegis_ml.data.records``, which is the schema of record for
``flow@1`` and ``log@1``. They are duplicated rather than imported because the
backend and the ML service are separately deployed containers, and an API
process should not pull the ML package into its import graph.

Duplication that is allowed to drift is worse than coupling, so
``tests/test_ingest_contract.py`` imports the real models and asserts the two
agree field for field, type for type. If ``flow@1`` is ever revised the test
fails until both sides move together.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAX_FLOW_RECORDS",
    "MAX_LOG_LINES",
    "Direction",
    "FlowRecordIn",
    "IngestResponse",
    "LogLevel",
    "LogRecordIn",
    "Protocol",
    "RecordError",
]

#: FR-01: up to 1,000 flow records per request.
MAX_FLOW_RECORDS = 1_000
#: FR-02: up to 5,000 log lines per request.
MAX_LOG_LINES = 5_000


class Protocol(StrEnum):
    """Transport protocols ``flow@1`` recognises."""

    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"


class Direction(StrEnum):
    """Traffic direction relative to the monitored boundary."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class LogLevel(StrEnum):
    """Severity levels ``log@1`` recognises."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FlowRecordIn(BaseModel):
    """One flow record on the wire — the ``flow@1`` contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["flow@1"] = "flow@1"
    timestamp: datetime
    src_ip: IPv4Address
    dst_ip: IPv4Address
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)
    protocol: Protocol
    direction: Direction
    service: str | None = None
    state: str | None = None
    packets: int = Field(ge=0)
    src_packets: int = Field(ge=0)
    dst_packets: int = Field(ge=0)
    src_bytes: int = Field(ge=0)
    dst_bytes: int = Field(ge=0)
    duration: float = Field(ge=0)
    syn: int = Field(default=0, ge=0)
    ack: int = Field(default=0, ge=0)
    rst: int = Field(default=0, ge=0)
    fin: int = Field(default=0, ge=0)
    psh: int = Field(default=0, ge=0)
    urg: int = Field(default=0, ge=0)
    label: str | None = None


class LogRecordIn(BaseModel):
    """One log line on the wire — the ``log@1`` contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["log@1"] = "log@1"
    timestamp: datetime
    host: str = Field(min_length=1)
    service: str = Field(min_length=1)
    level: LogLevel
    message: str = Field(min_length=1)
    template_id: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    label: str | None = None


class RecordError(BaseModel):
    """Why one record in a batch was rejected (FR-04)."""

    model_config = ConfigDict(frozen=True)

    #: Zero-based position in the batch, or the NDJSON line number for a line
    #: that could not be parsed as JSON at all.
    index: int
    #: ``parse`` when the line is not valid JSON, ``validation`` when it is JSON
    #: that does not satisfy the schema.
    stage: Literal["parse", "validation"]
    message: str
    #: Field name for a validation error, absent for a parse error.
    field: str | None = None


class IngestResponse(BaseModel):
    """The outcome of a batch. Nothing accepted or rejected goes unreported."""

    model_config = ConfigDict(frozen=True)

    received: int
    accepted: int
    rejected: int
    errors: list[RecordError] = Field(default_factory=list)
