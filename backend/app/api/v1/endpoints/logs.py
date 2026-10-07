"""The log read API (T-407, T-419, design.md §4.5).

Two reads, both bounded by construction (R-34) rather than by a default that happens
to be small:

* ``GET /api/v1/logs`` folds the lines in a window into clusters — identical lines
  become one row with a count.
* ``GET /api/v1/logs/lines`` returns the raw lines behind one cluster, or behind a
  window when no cluster is named.

**The window's bound is the source's own reach.** ``start`` and ``end`` are required,
and the span between them may not exceed what the answering source can see: a tail's
retention (15 minutes by default), or the store's 92-day query bound. A wider request
is refused (400, like the other over-wide window in this codebase) rather than answered
with a subset the caller may not realise is partial, and the message names which source
answered and what its bound is.

**Which source answers is a deployment's configuration, not this router's choice**
(T-419). Both implement :class:`~app.services.log_source.LogSource`; the response's
``source`` field says which one replied, and its caveats say what that source cannot
do. Reading is R-53's ``viewer`` capability, like reading alerts.

The router stays thin (R-13): parse, validate the window, call the source, serialise.
Everything worth testing about the fold — counts, ordering, digest keys, eviction —
lives in :mod:`app.services.log_tail` and :mod:`app.services.log_store`, and is tested
without an HTTP server.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import log_source, parse_instant
from app.auth.rbac import Capability, require
from app.schemas.ingest import LogLevel
from app.schemas.logs import LogLinesOut, LogTailOut
from app.services.log_source import LogSource
from app.services.log_store import LogStoreUnavailable
from app.services.log_tail import (
    DEFAULT_CLUSTER_LIMIT,
    DEFAULT_LINE_LIMIT,
    MAX_CLUSTER_LIMIT,
    MAX_LINE_LIMIT,
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
    source: LogSource,
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

    The span bound comes from the source, and the refusal names it: a tail's bound is
    its retention, the store's is the query bound, and a caller told "narrow the
    window" without being told which of the two applies would keep guessing.

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
    allowed = timedelta(seconds=source.max_span_seconds)
    if span > allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"the range spans {span.total_seconds():.0f}s, over the "
                f"{allowed.total_seconds():.0f}s the {source.name} can read. Narrow "
                "the window; a wider one has nothing more to read."
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
    summary="Clustered log read (log@1)",
    dependencies=[require(Capability.READ)],
)
async def read_log_clusters(
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
    source = log_source(request)
    window = _window(
        source,
        start=start,
        end=end,
        key=key,
        host=host,
        service=service,
        level=level,
    )
    try:
        return await source.clusters(window, limit=limit)
    except LogStoreUnavailable as exc:
        # 503 rather than an empty screen: a configured store that cannot be read is
        # a dependency outage, and "no logs matched" would be a different claim.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/logs/lines",
    response_model=LogLinesOut,
    summary="Raw log lines behind a cluster (log@1)",
    dependencies=[require(Capability.READ)],
)
async def read_log_lines(
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
    source = log_source(request)
    window = _window(
        source,
        start=start,
        end=end,
        key=key,
        host=host,
        service=service,
        level=level,
    )
    try:
        return await source.lines(window, limit=limit)
    except LogStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
