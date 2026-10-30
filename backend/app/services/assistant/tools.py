"""Read-only tools the assistant may call. Each returns plain facts and no secrets.

A tool never receives the request's credentials and never writes. Alert text such as
the explanation is left out on purpose: the assistant summarises fields, not payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from app.schemas.query import AlertQuery
from app.services.query_service import paginate

MAX_HOURS = 168  # one week, comfortably inside the store's span limit
MAX_RECENT = 20
COUNT_CEILING = 1000


class _Store(Protocol):
    def fetch(self, query: AlertQuery) -> list[object]: ...


class _Capture(Protocol):
    def get(self) -> object: ...


@dataclass(frozen=True)
class Context:
    """What the tools may read. Built per request from the app's own services."""

    alert_store: _Store
    capture_control: _Capture
    now: datetime


@dataclass(frozen=True)
class ToolResult:
    """One tool's facts, or the error it hit. Only facts reach the model."""

    name: str
    facts: dict[str, object] = field(default_factory=dict)
    error: str | None = None


def _window(ctx: Context, hours: int) -> tuple[datetime, datetime]:
    hours = max(1, min(hours, MAX_HOURS))
    return ctx.now - timedelta(hours=hours), ctx.now


def count_alerts(ctx: Context, hours: int) -> ToolResult:
    """How many alerts the store holds in the last ``hours`` hours (capped at a week)."""
    start, end = _window(ctx, hours)
    try:
        rows = ctx.alert_store.fetch(AlertQuery(start=start, end=end, limit=COUNT_CEILING))
    except ValueError as exc:
        return ToolResult("count_alerts", error=str(exc))
    page = paginate(rows, AlertQuery(start=start, end=end, limit=COUNT_CEILING))
    more = page.next_cursor is not None
    return ToolResult(
        "count_alerts",
        facts={
            "hours": max(1, min(hours, MAX_HOURS)),
            "count": len(page.items),
            "at_least": more,
        },
    )


def recent_alerts(ctx: Context, hours: int, limit: int = 5) -> ToolResult:
    """The newest alerts in the window, as summary fields only."""
    start, end = _window(ctx, hours)
    limit = max(1, min(limit, MAX_RECENT))
    query = AlertQuery(start=start, end=end, limit=limit, order="desc")
    try:
        rows = ctx.alert_store.fetch(query)
    except ValueError as exc:
        return ToolResult("recent_alerts", error=str(exc))
    page = paginate(rows, query)
    items = [
        {
            "id": item.id,
            "severity": item.severity,
            "family": item.family,
            "score": round(item.score, 3),
            "status": item.status,
            "last_seen": item.last_seen.isoformat(),
        }
        for item in page.items
    ]
    return ToolResult(
        "recent_alerts", facts={"hours": max(1, min(hours, MAX_HOURS)), "alerts": items}
    )


def capture_status(ctx: Context) -> ToolResult:
    """What capture is requested to do. This is the request, not proof the sensor applied it."""
    state = ctx.capture_control.get()
    return ToolResult(
        "capture_status",
        facts={
            "requested": bool(state.running),  # type: ignore[attr-defined]
            "engines": list(state.engines),  # type: ignore[attr-defined]
            "version": state.version,  # type: ignore[attr-defined]
        },
    )
