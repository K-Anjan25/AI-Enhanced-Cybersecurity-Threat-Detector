"""Live alert stream — SSE with single-use ticket auth.

EventSource cannot set Authorization headers, so a JWT in the URL would be
logged by proxies and kept in browser history. Instead POST /stream/ticket
mints a 30-second single-use ticket; GET /stream/alerts?ticket= consumes it.
Reconnecting mints a new ticket — retrying a spent URL would 401.

Process-scoped: the bus lives in one API process. Run several workers and a
tab sees one worker's events. /stream/status reports this honestly.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.core.events import bus, tickets
from app.models import User

router = APIRouter(prefix="/stream", tags=["Live stream"])

HEARTBEAT_SECONDS = 15


def _frame(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def alert_frames(subscriber, heartbeat_seconds: int = HEARTBEAT_SECONDS) -> AsyncGenerator[str, None]:
    try:
        yield _frame("ready", {"live": True, "heartbeat_seconds": heartbeat_seconds})
        while True:
            try:
                event = await asyncio.wait_for(subscriber.queue.get(), timeout=heartbeat_seconds)
            except (asyncio.TimeoutError, TimeoutError):
                yield ": keep-alive\n\n"
                continue
            yield _frame(event.get("type", "alert"), event)
            if subscriber.dropped:
                dropped = subscriber.dropped
                subscriber.dropped = 0
                yield _frame("gap", {"dropped": dropped, "message": "Some events were dropped — refetch recommended"})
    finally:
        bus.unsubscribe(subscriber)


@router.post("/ticket")
def issue_ticket(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    ticket = tickets.issue(org_id=current_user.org_id)
    return {"ticket": ticket, "expires_in": tickets.ttl_seconds}


@router.get("/status")
def stream_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {
        "process_scoped": True,
        "subscriber_count": bus.subscriber_count(),
        "queue_size": bus.queue_size,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
        "note": "This bus lives in one API process. Run several workers and a tab sees one worker's events. The dashboard reconnects and refetches on gap.",
    }


@router.get("/alerts")
async def stream_alerts(
    ticket: str = Query(..., description="Single-use ticket from POST /stream/ticket"),
):
    org_id = tickets.redeem(ticket)
    if org_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired stream ticket — request a new one")

    subscriber = bus.subscribe(org_id=org_id)

    return StreamingResponse(
        alert_frames(subscriber),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
