"""Wire contracts for the audit trail (FR-42, T-312).

There is no request schema: the trail is written by the routes that perform the
actions, never by a client posting to it, and there is deliberately no field here
that could carry a record's content. The read shape is the model's columns plus
the sequence the trail assigns.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AuditEntryOut", "AuditPageOut"]


class AuditEntryOut(BaseModel):
    """One recorded action.

    ``detail`` is the thin, non-sensitive context the writing route supplied --
    counts and identifiers -- and it is a ``dict`` here because that is what
    JSONB holds. What must never be in it is asserted where the records are
    built, not here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(description="Trail sequence, 1-based and monotonic.")
    actor: str = Field(description="The principal the access token named.")
    action: str
    target_type: str
    target_id: str
    detail: dict[str, object]
    ip: str | None
    at: datetime


class AuditPageOut(BaseModel):
    """A page of the trail, newest first.

    ``next_before`` is the cursor for the next page -- the sequence to pass back
    -- and ``None`` when this page reached the start of the range. Without it a
    client has to guess whether it saw everything, which is how an audit export
    quietly becomes incomplete.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AuditEntryOut]
    next_before: int | None
