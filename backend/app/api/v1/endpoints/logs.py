"""The log tail read API (T-407, design.md §4.5).

Two reads, both bounded by construction (R-34) rather than by a default that happens
to be small:

* ``GET /api/v1/logs`` folds the lines in a window into clusters — identical lines
  become one row with a count.
* ``GET /api/v1/logs/lines`` returns the raw lines behind one cluster, or behind a
  window when no cluster is named.

``start`` and ``end`` are required and the span between them may not exceed the tail's
own retention: the retention *is* the bound, so a wider request is refused (400, like
the other over-wide window in this codebase) rather than answered with a subset the
caller may not realise is partial. Reading is R-53's ``viewer`` capability, like
reading alerts.

The router stays thin (R-13): parse, validate the window, call the service, serialise.
Everything worth testing about the fold — counts, ordering, digest keys, eviction —
lives in :mod:`app.services.log_tail` and is tested without an HTTP server.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import log_tail, parse_instant
from app.auth.rbac import Capability, require
from app.schemas.ingest import LogLevel
from app.schemas.logs import LogLinesOut, LogTailOut
from app.services.log_tail import (
    DEFAULT_CLUSTER_LIMIT,
    DEFAULT_LINE_LIMIT,
    MAX_CLUSTER_LIMIT,
    MAX_LINE_LIMIT,
    LogTail,
    LogWindow,
)

__all__ = ["router"]

router = APIRouter(prefix="/api/v1", tags=["logs"])

_Start = Annotated[str, Query(description="Inclusive lower bound, ISO-8601 with timezone.")]
_End = Annotated[str, Query(description="Exclusive upper bound, ISO-8601 with timezone.")]

#: The filters both routes share. Named once so the two cannot drift apart: a
#: cluster read and the expansion of that cluster must select the same lines, or
#: opening a row would show lines the row did not count.
_Filter = Annotated[
    str | None,
    Query(description="Cluster key: a template id, or a digest for lines without one."),
]
_Host = Annotated[str | None, Query(description="Only lines from this host.")]
_Service = Annotated[str | None, Query(description="Only lines from this service.")]
_Level = Annotated[LogLevel | None, Query(description="Only lines at this level.")]


def _window(
    tail: LogTail,
    *,
    start: str,
    end: str,
    key: str | None,
    host: str | None,
    service: str | None,
    level: LogLevel | None,
) -> LogWindow:
    """Validate the query parameters into a window, or refuse the request.

    ``start`` and ``end`` are declared required on the routes themselves, so a
    missing one is FastAPI's own 422 before this is reached — which is also why the
    annotation is ``str`` rather than ``str | None``: a required parameter has no
    ``None`` to check for.

    Raises:
        HTTPException: 400 for an unparseable, naive, inverted or over-wide window.
            Each of those makes the answer ambiguous, and an ambiguous answer about
            what the logs said is worse than an error naming the bound.
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
    span = window_end - window_start
    allowed = timedelta(seconds=tail.max_age_seconds)
    if span > allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"the range spans {span.total_seconds():.0f}s, over the "
                f"{allowed.total_seconds():.0f}s this tail retains. Narrow the window; "
                "a wider one has nothing more to read."
            ),
        )
    return LogWindow(
        start=window_start,
        end=window_end,
        key=key,
        host=host,
        service=service,
        level=level,
    )


@router.get(
    "/logs",
    response_model=LogTailOut,
    summary="Clustered log tail (log@1)",
    dependencies=[require(Capability.READ)],
)
def read_log_tail(
    request: Request,
    start: _Start,
    end: _End,
    key: _Filter = None,
    host: _Host = None,
    service: _Service = None,
    level: _Level = None,
    limit: Annotated[int, Query(ge=1, le=MAX_CLUSTER_LIMIT)] = DEFAULT_CLUSTER_LIMIT,
) -> LogTailOut:
    """Fold the window's lines into clusters, the busiest first."""
    tail = log_tail(request)
    window = _window(
        tail,
        start=start,
        end=end,
        key=key,
        host=host,
        service=service,
        level=level,
    )
    return tail.clusters(window, limit=limit)


@router.get(
    "/logs/lines",
    response_model=LogLinesOut,
    summary="Raw log lines behind a cluster (log@1)",
    dependencies=[require(Capability.READ)],
)
def read_log_lines(
    request: Request,
    start: _Start,
    end: _End,
    key: _Filter = None,
    host: _Host = None,
    service: _Service = None,
    level: _Level = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LINE_LIMIT)] = DEFAULT_LINE_LIMIT,
) -> LogLinesOut:
    """Return the newest ``limit`` matching raw lines, oldest first."""
    tail = log_tail(request)
    window = _window(
        tail,
        start=start,
        end=end,
        key=key,
        host=host,
        service=service,
        level=level,
    )
    return tail.lines(window, limit=limit)
