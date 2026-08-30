"""Time-to-detect and time-to-contain, measured from real rows.

Buyers of an AI SOC do not purchase alert counts; they purchase outcomes, and
the outcome they benchmark is elapsed time. That makes these numbers the most
tempting thing in the product to invent — and they had been. `exec_risk_service`
reported `mttd = 2.5  # hours` as a literal, alongside a board pack claiming
"$50,000 cost avoidance" and "120 analyst hours saved" that were typed in by
hand. A fabricated MTTD is worse than no MTTD: it is the figure a buyer
benchmarks against, and it appeared in an export addressed to a board.

Everything here is computed from timestamps the system actually records:

    alert.created_at  →  case.created_at  →  case.decided_at
    (ingested)           (triaged)           (decided)

Two honesty constraints are load-bearing.

**MTTD is measured only where the source supplied a time.** True
mean-time-to-detect runs from when the event happened to when it was detected.
That needs `SecurityAlert.event_time`, which connectors now populate from the
originating system — but only when the provider sends something parseable.
Alerts without one are excluded from `time_to_detect` rather than falling back
to `created_at`, which would report zero latency and drag the median toward
zero precisely for the sources with the worst visibility. The metric therefore
carries `coverage`: how many alerts in the window could be measured at all.
`time_to_triage` remains, measuring ingest→triage, because the two answer
different questions and conflating them hides ingestion lag.

**A percentile needs a sample.** With three cases, a median is an anecdote. Each
metric carries its `sample_size`, and anything below `_MIN_SAMPLE` is returned
with `reliable: false` and a reason rather than a confident-looking figure.
Metrics with no qualifying data return `None` — never `0`, which reads as
"instant" on a dashboard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import SecurityAlert
from app.models.case import Case

# Below this many samples a percentile is an anecdote, not a measurement.
_MIN_SAMPLE = 5

_DECIDED = ("approved", "declined")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; compare everything in UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _elapsed_minutes(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    start, end = _aware(start), _aware(end)
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds() / 60.0
    # A negative interval means the clocks disagree or rows were backdated.
    # Discard it rather than letting it drag an average downward.
    return delta if delta >= 0 else None


def _summarize(
    samples: List[float],
    *,
    name: str,
    measures: str,
    caveat: Optional[str] = None,
) -> Dict[str, Any]:
    """Turn raw durations into a metric that states its own trustworthiness."""
    count = len(samples)
    if count == 0:
        return {
            "metric": name,
            "measures": measures,
            "sample_size": 0,
            "median_minutes": None,
            "p90_minutes": None,
            "reliable": False,
            "reason": "no cases in this window have both timestamps recorded",
            "caveat": caveat,
        }

    ordered = sorted(samples)
    # Nearest-rank p90, which is well defined for small samples.
    p90_index = max(0, min(count - 1, int(round(0.9 * count)) - 1))

    reliable = count >= _MIN_SAMPLE
    return {
        "metric": name,
        "measures": measures,
        "sample_size": count,
        "median_minutes": round(median(ordered), 1),
        "p90_minutes": round(ordered[p90_index], 1),
        "fastest_minutes": round(ordered[0], 1),
        "slowest_minutes": round(ordered[-1], 1),
        "reliable": reliable,
        "reason": None
        if reliable
        else f"only {count} case(s) measured; {_MIN_SAMPLE} needed before this is meaningful",
        "caveat": caveat,
    }


def _cases_in_window(db: Session, org_id: Optional[int], since: datetime) -> List[Case]:
    query = db.query(Case).filter(Case.created_at >= since)
    if org_id is not None:
        query = query.filter(Case.org_id == org_id)
    return query.all()


def compute(db: Session, org_id: Optional[int], window_days: int = 30) -> Dict[str, Any]:
    """Response-time metrics over the trailing ``window_days``.

    Returns a dict safe to render directly. Never raises and never invents a
    figure: when a window has nothing to measure, the metric is None and the
    reason is stated.
    """
    since = _now() - timedelta(days=window_days)
    cases = _cases_in_window(db, org_id, since)

    # Source alerts, fetched once, for the ingest→triage leg.
    alert_ids = [c.source_alert_id for c in cases if c.source_alert_id]
    alerts_by_id: Dict[int, SecurityAlert] = {}
    if alert_ids:
        rows = db.query(SecurityAlert).filter(SecurityAlert.id.in_(alert_ids)).all()
        alerts_by_id = {a.id: a for a in rows}

    detect_samples: List[float] = []
    detect_eligible = 0
    triage_samples: List[float] = []
    decision_samples: List[float] = []
    end_to_end_samples: List[float] = []

    for case in cases:
        alert = alerts_by_id.get(case.source_alert_id) if case.source_alert_id else None

        # True detection latency: the event happened, then we saw it.
        if alert is not None:
            detect_eligible += 1
            event_to_ingest = _elapsed_minutes(
                getattr(alert, "event_time", None), alert.created_at
            )
            if event_to_ingest is not None:
                detect_samples.append(event_to_ingest)

        ingest_to_triage = (
            _elapsed_minutes(alert.created_at, case.created_at) if alert else None
        )
        if ingest_to_triage is not None:
            triage_samples.append(ingest_to_triage)

        if case.decision in _DECIDED and case.decided_at is not None:
            triage_to_decision = _elapsed_minutes(case.created_at, case.decided_at)
            if triage_to_decision is not None:
                decision_samples.append(triage_to_decision)

            if alert is not None:
                end_to_end = _elapsed_minutes(alert.created_at, case.decided_at)
                if end_to_end is not None:
                    end_to_end_samples.append(end_to_end)

    undecided = [c for c in cases if c.decision not in _DECIDED]

    return {
        "window_days": window_days,
        "cases_in_window": len(cases),
        "metrics": [
            _summarize(
                detect_samples,
                name="time_to_detect",
                measures="event occurred at source → alert ingested",
                caveat=(
                    (
                        f"Measured on {len(detect_samples)} of {detect_eligible} "
                        "alert(s) whose source supplied an event time. Sources that "
                        "send none are excluded rather than counted as zero latency."
                    )
                    if detect_samples
                    else (
                        "No alerts in this window carried a source event time, so "
                        f"none of the {detect_eligible} alert(s) could be measured. "
                        "This is missing instrumentation, not instant detection."
                    )
                    if detect_eligible
                    else "No alerts in this window."
                ),
            ),
            _summarize(
                triage_samples,
                name="time_to_triage",
                measures="alert ingested → case raised",
                caveat=(
                    "Starts at ingest, not at the moment of attack. No source event "
                    "time is recorded, so dwell time before ingest is not included "
                    "and this is not a true MTTD."
                ),
            ),
            _summarize(
                decision_samples,
                name="time_to_decision",
                measures="case raised → human decision",
            ),
            _summarize(
                end_to_end_samples,
                name="time_to_contain",
                measures="alert ingested → decision executed",
                caveat=(
                    "Starts at ingest, not at the event, so that every decided case "
                    "is comparable — only some sources supply an event time. Add "
                    "time_to_detect for elapsed time since the event. Measures the "
                    "decision being recorded, not confirmation that the containment "
                    "action took effect on the endpoint."
                ),
            ),
        ],
        "open_backlog": {
            "undecided_cases": len(undecided),
            "oldest_undecided_minutes": (
                round(
                    max(
                        (
                            m
                            for m in (
                                _elapsed_minutes(c.created_at, _now()) for c in undecided
                            )
                            if m is not None
                        ),
                        default=0.0,
                    ),
                    1,
                )
                if undecided
                else None
            ),
        },
        "not_measured": _not_measured(),
    }


def _not_measured() -> List[Dict[str, str]]:
    """Metrics a buyer will ask for that this system genuinely cannot produce.

    Naming them is the point. Silence here would let a reader assume the
    absent numbers were merely zero or unremarkable.
    """
    return [
        {
            "metric": "dwell_time_before_logging",
            "reason": (
                "time_to_detect starts when the source system logged the event. "
                "If an attacker acted before anything was logged, that interval "
                "is invisible to every system downstream of the log."
            ),
        },
        {
            "metric": "cost_avoidance",
            "reason": (
                "depends on breach-cost assumptions this system has no basis to "
                "make. Previously reported as a flat $50,000, which was invented."
            ),
        },
        {
            "metric": "analyst_hours_saved",
            "reason": (
                "requires a baseline of how long these cases took before "
                "automation. No such baseline has been captured."
            ),
        },
    ]
