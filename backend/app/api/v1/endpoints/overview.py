"""``GET /api/v1/overview`` -- one window, one read, three panels (T-416, FR-50).

The screen this serves is the one an operator opens first, and it used to open by
walking alert pages until a cap. Three consequences, all of which this route
removes:

* **The tiles, the series and the entity list could disagree.** They were three
  tallies over three page walks, and a page boundary falling between two of them
  was enough to make the chart's total differ from the tile above it. One window,
  one aggregate, one answer.
* **A count was a count of what had been read.** ``complete: false`` was the honest
  rendering of a 5,000-row cap, which meant the screen's most authoritative-looking
  number came with an asterisk. The aggregate is computed where the rows are, so
  the count is the window's count.
* **An entity had no name.** Alert rows carry ``entity_id`` and nothing else, so the
  list was keyed by id and said so on screen. The registry (T-419's opposite number,
  injected here) resolves ``(kind, value)`` for every id this process has seen, and
  an id it has not seen comes back *unnamed* rather than as a missing field.

The pipeline health strip is deliberately not part of this: it reads ``/metrics``,
because a scrape is not a window (D-060). One request fills the KPI tiles, the
severity series and the entity list, and that is what the dashboard test asserts by
counting requests.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import alert_store, entity_registry
from app.auth.rbac import Capability, require
from app.db.repository import TimeRange
from app.schemas.overview import (
    OverviewBucket,
    OverviewEntity,
    OverviewFamily,
    OverviewOut,
    OverviewTotals,
    OverviewWindow,
)
from app.services.overview import (
    BUCKET_MINUTES_DEFAULT,
    BUCKET_MINUTES_MAX,
    ENTITY_LIMIT_DEFAULT,
    ENTITY_LIMIT_MAX,
    FAMILY_LIMIT_DEFAULT,
    FAMILY_LIMIT_MAX,
    Aggregate,
)

router = APIRouter(prefix="/api/v1", tags=["overview"])


@router.get(
    "/overview",
    response_model=OverviewOut,
    summary="One window's counts, severity series and named entities (FR-50)",
    dependencies=[require(Capability.READ)],
)
def read_overview(
    request: Request,
    start: str = Query(description="Inclusive lower bound, ISO-8601 with an offset."),
    end: str = Query(description="Exclusive upper bound, ISO-8601 with an offset."),
    bucket_minutes: int = Query(
        default=BUCKET_MINUTES_DEFAULT,
        ge=1,
        le=BUCKET_MINUTES_MAX,
        description="The severity series' resolution.",
    ),
    entity_limit: int = Query(
        default=ENTITY_LIMIT_DEFAULT,
        ge=1,
        le=ENTITY_LIMIT_MAX,
        description="How many entities the top-N lists. The counts are unaffected.",
    ),
    family_limit: int = Query(
        default=FAMILY_LIMIT_DEFAULT,
        ge=1,
        le=FAMILY_LIMIT_MAX,
        description="How many families the mix lists. The counts are unaffected.",
    ),
) -> OverviewOut:
    """Aggregate one bounded window into everything the overview's panels read.

    ``start`` and ``end`` are required for the same reason the alert list's are
    (R-34): an aggregate over a partitioned table with no time predicate is the
    unbounded scan the rule names, and a generous default is how one ships.

    ``entity_limit`` and ``family_limit`` cap a *list*, never a count. ``totals``
    and ``series`` cover every row in the window; when the window held more
    entities than the limit, ``entities_capped`` says so and the screen says "top N
    of more" rather than printing a number that reads like the whole population.
    """
    try:
        window = TimeRange(start=datetime.fromisoformat(start), end=datetime.fromisoformat(end))
    except ValueError as exc:
        # A naive or inverted range, or one wider than the R-34 span limit.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        summary = alert_store(request).aggregate(
            window,
            bucket_minutes=bucket_minutes,
            entity_limit=entity_limit,
            family_limit=family_limit,
        )
    except ValueError as exc:
        # Validated where it is used, like the list route: a client error is a 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _response(summary, window, bucket_minutes, _names(request, summary))


def _names(request: Request, summary: Aggregate) -> dict[int, tuple[str, str]]:
    """Resolve every entity in the aggregate through the registry.

    One lookup per listed entity rather than one per alert: the aggregate has
    already reduced a window to at most ``entity_limit`` ids.
    """
    registry = entity_registry(request)
    resolved: dict[int, tuple[str, str]] = {}
    for tally in summary.entities:
        ref = registry.ref(tally.entity_id)
        if ref is not None:
            resolved[tally.entity_id] = ref
    return resolved


def _response(
    summary: Aggregate,
    window: TimeRange,
    bucket_minutes: int,
    names: dict[int, tuple[str, str]],
) -> OverviewOut:
    """Serialise an aggregate, naming the entities it could resolve."""
    return OverviewOut(
        window=OverviewWindow(
            start=window.start,
            end=window.end,
            hours=window.span.total_seconds() / 3_600,
        ),
        bucket_minutes=bucket_minutes,
        totals=OverviewTotals(
            alerts=summary.total,
            open=summary.open_alerts,
            by_severity=dict(summary.by_severity),
            unrecognised_severity=summary.unrecognised,
            verdicts=dict(summary.verdicts),
            unrecorded=summary.unrecorded,
            verdicts_measured=summary.verdicts_measured,
            mean_time_to_verdict_seconds=summary.mean_time_to_verdict_seconds,
        ),
        series=[
            OverviewBucket(
                start=point.start, total=point.total, by_severity=dict(point.by_severity)
            )
            for point in summary.points
        ],
        entities=[
            OverviewEntity(
                entity_id=tally.entity_id,
                kind=names[tally.entity_id][0] if tally.entity_id in names else None,
                value=names[tally.entity_id][1] if tally.entity_id in names else None,
                named=tally.entity_id in names,
                alerts=tally.alerts,
                occurrences=tally.occurrences,
                open=tally.open_alerts,
                worst_severity=tally.worst_severity,
                max_score=tally.max_score,
                last_seen=tally.last_seen,
            )
            for tally in summary.entities
        ],
        entities_capped=summary.entities_capped,
        families=[
            OverviewFamily(
                family=tally.family,
                alerts=tally.alerts,
                worst_severity=tally.worst_severity,
            )
            for tally in summary.families
        ],
        families_capped=summary.families_capped,
    )


__all__ = ["router"]
