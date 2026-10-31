"""Deterministic daily report built only from stored alert rows (Phase 3).

Every sentence is rendered from a number in the aggregate, so each statement can be
traced back to a stored fact. Nothing here calls a model, and nothing is inferred
that the aggregate does not count. Plain-language explanations of a single alert
belong to the assistant, which must cite these same fields.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.db.repository import TimeRange
from app.services.overview import Aggregate

_BANDS = ("critical", "high", "medium", "low", "info")


def day_window(day: date) -> TimeRange:
    """The UTC day ``day``, as a half-open range (inclusive start, exclusive end)."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return TimeRange(start=start, end=start + timedelta(days=1))


def render_daily_report(day: date, agg: Aggregate) -> dict[str, Any]:
    """Turn one day's aggregate into the report's structured body and its sentences.

    The ``facts`` list is the plain-language form; ``totals`` is the same numbers in
    machine-readable form, so a consumer can check the sentences against it.
    """
    by_severity = {band: int(agg.by_severity.get(band, 0)) for band in _BANDS}
    facts: list[str] = []
    if agg.total == 0:
        facts.append(f"No alerts were recorded on {day.isoformat()} (UTC).")
    else:
        parts = [f"{by_severity[b]} {b}" for b in _BANDS if by_severity[b]]
        facts.append(
            f"{agg.total} alerts were recorded on {day.isoformat()} (UTC): "
            + ", ".join(parts)
            + "."
        )
        facts.append(f"{agg.open_alerts} of them are still open.")
    if agg.unrecognised:
        facts.append(
            f"{agg.unrecognised} alerts carry a severity outside the five bands and are "
            "counted in the total only."
        )
    for family in agg.families[:3]:
        facts.append(
            f"The family '{family.family}' accounts for {family.alerts} alerts "
            f"(worst band: {family.worst_severity})."
        )
    if agg.families_capped:
        facts.append("More families exist than are listed here.")
    for entity in agg.entities[:3]:
        facts.append(
            f"Entity {entity.entity_id} raised {entity.alerts} alerts "
            f"({entity.occurrences} occurrences, max score {entity.max_score:.2f})."
        )
    if agg.entities_capped:
        facts.append("More entities exist than are listed here.")
    if agg.unrecorded:
        facts.append(f"{agg.unrecorded} alerts have no verdict yet.")

    return {
        "date": day.isoformat(),
        "timezone": "UTC",
        "source": "stored alerts only",
        "totals": {
            "alerts": agg.total,
            "by_severity": by_severity,
            "unrecognised": agg.unrecognised,
            "open": agg.open_alerts,
            "unrecorded_verdicts": agg.unrecorded,
        },
        "families": [
            {"family": f.family, "alerts": f.alerts, "worst_severity": f.worst_severity}
            for f in agg.families
        ],
        "families_capped": agg.families_capped,
        "entities": [
            {
                "entity_id": e.entity_id,
                "alerts": e.alerts,
                "occurrences": e.occurrences,
                "max_score": e.max_score,
            }
            for e in agg.entities
        ],
        "entities_capped": agg.entities_capped,
        "facts": facts,
    }
