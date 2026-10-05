"""Alert query endpoint.

`start` and `end` are required query parameters. They are not optional with a
generous default, because a default is how an unbounded scan of a partitioned
table gets shipped -- R-34.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.auth.rbac import Capability, require
from app.schemas.query import AlertPage, AlertQuery, CursorError
from app.services.query_service import build_alert_select, paginate

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get(
    "/alerts",
    response_model=AlertPage,
    summary="Query alerts within a time window",
    dependencies=[require(Capability.READ)],
)
def list_alerts(
    start: str = Query(description="Inclusive lower bound, ISO-8601 with timezone."),
    end: str = Query(description="Exclusive upper bound, ISO-8601 with timezone."),
    severity: str | None = None,
    status: str | None = None,
    family: str | None = None,
    entity_id: int | None = None,
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=1_000),
    cursor: str | None = None,
) -> AlertPage:
    """Return one page of alerts matching the filters, newest first by default."""
    from datetime import datetime  # noqa: PLC0415

    try:
        query = AlertQuery(
            start=datetime.fromisoformat(start),
            end=datetime.fromisoformat(end),
            severity=severity,
            status=status,
            family=family,
            entity_id=entity_id,
            min_score=min_score,
            order=order,
            limit=limit,
            cursor=cursor,
        )
    except CursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        # A naive or inverted range, or one wider than the R-34 span limit.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Executing needs a session, which T-307 wires up. The select is built here
    # so the query shape -- bounded, filtered, keyset-paged -- is exercised and
    # tested independently of the database connection.
    statement = build_alert_select(query)
    del statement
    return paginate([], query)
