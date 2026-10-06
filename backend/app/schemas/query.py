"""Query and pagination contracts for the alert API.

Pagination is **keyset**, not offset, and the reason is the acceptance
criterion: "pagination is stable under concurrent inserts". Offset pagination
is not stable -- insert a row earlier in the ordering and every subsequent
page shifts by one, so a client paging through a live system sees one record
twice and another not at all. Keyset pagination anchors on the last row the
client actually saw, so inserts elsewhere cannot move it.

The cursor is the sort key ``(created_at, id)``. That pairing is not optional:
per D-030 ``id`` alone is **not** unique across the partitioned ``alerts``
table, because uniqueness cannot span partitions. Ordering by ``id`` alone
would produce ties, and a keyset cursor with ties either skips rows or repeats
them. ``(created_at, id)`` is the usable key.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "AlertRow",
    "AlertQuery",
    "CursorError",
    "decode_cursor",
    "encode_cursor",
]

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1_000

SortOrder = Literal["desc", "asc"]


class CursorError(ValueError):
    """The cursor is not one this API issued."""


def encode_cursor(created_at: datetime, row_id: int) -> str:
    """Encode the sort key of the last row on a page."""
    payload = json.dumps([created_at.isoformat(), row_id]).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode a cursor, refusing anything this API did not produce.

    A malformed cursor is a client error, not a reason to silently restart from
    the first page -- that would return the same rows again and look like a
    pagination bug in the client.
    """
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at_raw, row_id = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(created_at_raw), int(row_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        msg = "cursor is malformed or was not issued by this API"
        raise CursorError(msg) from exc


class AlertQuery(BaseModel):
    """Filter and pagination parameters for ``GET /api/v1/alerts``."""

    model_config = ConfigDict(frozen=True)

    #: Mandatory. R-34 forbids querying a partitioned table without a time
    #: predicate, so these are required fields rather than optional ones with
    #: generous defaults -- a default is how an unbounded scan gets shipped.
    start: datetime
    end: datetime

    severity: frozenset[str] | None = None
    status: frozenset[str] | None = None
    family: frozenset[str] | None = None
    entity_id: int | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)

    order: SortOrder = "desc"
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    cursor: str | None = None

    @field_validator("severity", "status", "family", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept a repeated query parameter or a comma-separated list."""
        if isinstance(value, str):
            return frozenset(part.strip() for part in value.split(",") if part.strip())
        if isinstance(value, (list, tuple, set, frozenset)):
            return frozenset(str(v) for v in value)
        return value


class AlertRow(BaseModel):
    """One alert as returned by the API."""

    model_config = ConfigDict(frozen=True)

    id: int
    created_at: datetime
    entity_id: int
    family: str
    severity: str
    score: float
    status: str
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int
    #: The trace id of the ingest request that opened the alert, when one was
    #: recorded (T-317). ``None`` for an alert whose detection arrived without a
    #: trace context -- an honest gap, not a placeholder id.
    trace_id: str | None = None


class AlertPage(BaseModel):
    """A page of alerts plus the cursor for the next one."""

    model_config = ConfigDict(frozen=True)

    items: list[AlertRow]
    next_cursor: str | None
    #: Echoed so a client can tell which filters produced a page.
    limit: int
    order: SortOrder
