"""Wire contracts for retention and erasure (NFR-05, T-314).

The split that matters is on the erasure side: a request carries the identifier,
a report does not. :class:`ErasureRequest` is the only model in this module with a
field for a subject's value, and :class:`ErasureReportOut` carries the tombstone
instead -- so a response, a dashboard tile and a support ticket built from these
models cannot become a copy of the data the request asked to remove.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAX_ERASURE_REASON_LENGTH",
    "DroppedPartitionOut",
    "ErasureLedgerEntryOut",
    "ErasureLedgerPageOut",
    "ErasureRequest",
    "ErasureReportOut",
    "ErasureTargetOut",
    "PreservedLedgerOut",
    "RetentionPlanOut",
    "RetentionPolicyOut",
    "RetentionRunOut",
    "UnevictableOut",
]

#: A note for the erasure record, not a document store.
MAX_ERASURE_REASON_LENGTH = 500


class RetentionPolicyOut(BaseModel):
    """The windows a deployment retains each class of data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_records_days: int
    alerts_days: int
    stats_days: int


class DroppedPartitionOut(BaseModel):
    """One monthly partition, with the span it covers.

    ``statement`` is the DDL a run would execute. It is shown because a retention
    screen that only says "a month was dropped" makes the operator guess which
    rows went; the statement is a partition name and carries no data.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    table: str
    name: str
    year: int
    month: int
    covers_start: date
    covers_end: date
    statement: str


class UnevictableOut(BaseModel):
    """A table retention will not touch, and the reason in one sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    table: str
    reason: str


class RetentionPlanOut(BaseModel):
    """What a retention run would do, now.

    ``missing`` lists months inside the window that have no partition: there is no
    default partition, so a gap means rows for that month were rejected at insert.
    Reporting it here is what stops a plan's silence being read as "nothing to do".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    planned_at: date
    policy: RetentionPolicyOut
    drop: list[DroppedPartitionOut]
    kept: list[DroppedPartitionOut]
    missing: list[str]
    unevictable: list[UnevictableOut]
    external: dict[str, str]
    statements: list[str]


class RetentionRunOut(BaseModel):
    """What a retention run did, including how much of it was already done."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    started_at: datetime
    planned: list[str]
    dropped: list[str]
    already_absent: list[str]
    changed_anything: bool


class ErasureRequest(BaseModel):
    """An erasure request. The only model here that carries the subject's value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(
        description="'user' (an account) or 'entity' (an observed host, service or address)."
    )
    value: str = Field(min_length=1, max_length=512, description="The identifier to erase.")
    reason: str = Field(
        default="",
        max_length=MAX_ERASURE_REASON_LENGTH,
        description="Why the request was made. Recorded; never an identifier.",
    )


class ErasureTargetOut(BaseModel):
    """What one store did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    affected: int


class PreservedLedgerOut(BaseModel):
    """An append-only store the erasure did not rewrite, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    reason: str


class ErasureReportOut(BaseModel):
    """The result of an erasure -- with the tombstone, never the identifier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    tombstone: str
    at: datetime
    targets: list[ErasureTargetOut]
    preserved: list[PreservedLedgerOut]
    already_erased: bool
    ledger_sequence: int | None
    affected: int
    reason: str = ""


class ErasureLedgerEntryOut(BaseModel):
    """One recorded erasure.

    ``requested_by`` is the authenticated principal that asked. The ledger holds
    it because R-37 requires the action to be attributable, and it is the one
    identifier on the row; the subject is only ever a tombstone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    tombstone: str
    kind: str
    at: datetime
    requested_by: str
    targets: list[ErasureTargetOut]


class ErasureLedgerPageOut(BaseModel):
    """A page of the erasure ledger, newest first, with a cursor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[ErasureLedgerEntryOut]
    next_before: int | None
