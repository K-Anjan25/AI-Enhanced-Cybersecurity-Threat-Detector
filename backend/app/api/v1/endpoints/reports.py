"""``GET /api/v1/reports/daily`` -- a deterministic daily report from stored alerts.

Read-only, one UTC day, one aggregate. The report is generated on request, so the
scheduled-report output and an on-screen report are the same function over the same
rows, and a re-run for a past day gives the same answer.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import alert_store
from app.auth.rbac import Capability, require
from app.services.daily_report import day_window, render_daily_report

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get(
    "/reports/daily",
    summary="A deterministic report of one UTC day's stored alerts (Phase 3)",
    dependencies=[require(Capability.READ)],
)
def read_daily_report(
    request: Request,
    day: str = Query(description="The UTC day, YYYY-MM-DD."),
    family_limit: int = Query(default=5, ge=1, le=50),
    entity_limit: int = Query(default=5, ge=1, le=50),
) -> dict[str, object]:
    """Return the day's totals, the families and entities that lead, and plain sentences."""
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD") from exc
    try:
        agg = alert_store(request).aggregate(
            day_window(parsed), entity_limit=entity_limit, family_limit=family_limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return render_daily_report(parsed, agg)
