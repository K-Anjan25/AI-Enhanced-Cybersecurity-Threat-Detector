"""The audit trail's read endpoint (FR-42, T-312).

Read-only, and that is the whole design: R-31 makes the trail append-only, so
there is no route that edits a record, no route that deletes one, and no bulk
export here -- export is ``responder`` and above with its own audit entry
(FR-43), and it is E4's screen plus a later task rather than a query parameter
added quietly in this one.

``start`` and ``end`` are required. The trail is not partitioned -- it must keep
every row -- but it grows without bound, so a read with a generous default range
is the unbounded scan R-34's principle forbids, written differently. The window
is capped at :data:`MAX_QUERY_SPAN_DAYS`, the same bound the repository layer
puts on partitioned scans, so there is one number to reason about rather than
two that can disagree.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import audit_trail, parse_instant
from app.auth.rbac import Capability, require
from app.db.repository import MAX_QUERY_SPAN_DAYS
from app.schemas.audit import AuditEntryOut, AuditPageOut
from app.services.audit_log import DEFAULT_LIMIT, MAX_LIMIT, AuditAction, AuditEntry

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _out(entry: AuditEntry) -> AuditEntryOut:
    """Serialise one stored record."""
    record = entry.record
    return AuditEntryOut(
        id=entry.sequence,
        actor=record.actor,
        action=record.action.value,
        target_type=record.target_type,
        target_id=record.target_id,
        detail=dict(record.detail),
        ip=record.ip,
        at=record.at,
    )


@router.get(
    "",
    response_model=AuditPageOut,
    summary="Read the audit trail, newest first (FR-42)",
    dependencies=[require(Capability.READ)],
)
def list_audit_entries(
    request: Request,
    start: Annotated[str, Query(description="ISO-8601 inclusive lower bound.")],
    end: Annotated[str, Query(description="ISO-8601 exclusive upper bound.")],
    action: Annotated[AuditAction | None, Query(description="Filter to one action.")] = None,
    actor: Annotated[str | None, Query(max_length=200)] = None,
    target_type: Annotated[str | None, Query(max_length=80)] = None,
    target_id: Annotated[str | None, Query(max_length=120)] = None,
    before: Annotated[int | None, Query(ge=1, description="Exclusive id cursor.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> AuditPageOut:
    """Page through the trail within a bounded window.

    Raises:
        HTTPException: 400 when a timestamp is unparseable or naive, when the
            range is empty or inverted, or when it is wider than
            :data:`~app.db.repository.MAX_QUERY_SPAN_DAYS`.
    """
    try:
        window_start = parse_instant(start, name="start")
        window_end = parse_instant(end, name="end")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if window_end <= window_start:
        raise HTTPException(
            status_code=400,
            detail="end must be later than start; an inverted range reads nothing",
        )
    span_days = (window_end - window_start).days
    if span_days > MAX_QUERY_SPAN_DAYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"the range spans {span_days} days, over the {MAX_QUERY_SPAN_DAYS}-day "
                "limit. Page it rather than reading the whole trail in one request."
            ),
        )

    entries = audit_trail(request).entries(
        start=window_start,
        end=window_end,
        action=action,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        before=before,
        limit=limit,
    )
    # ``limit + 1`` would be needed to know whether more exist without a second
    # read; instead the cursor is always the last row handed out, and a client
    # stops when a page comes back empty. That is exact and costs nothing.
    next_before = entries[-1].sequence if entries else None
    return AuditPageOut(items=[_out(entry) for entry in entries], next_before=next_before)
