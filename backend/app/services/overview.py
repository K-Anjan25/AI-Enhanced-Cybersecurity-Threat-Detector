"""The overview's arithmetic, on the server (T-416, FR-50).

The overview screen used to count its own rows: it walked ``GET /api/v1/alerts``
pages until a cap and tallied what it had. That made every figure on the screen a
statement about *the pages it happened to read* rather than about the window --
`complete: false` was the honest way to render a 5,000-row cap, and the KPI tiles,
the series and the top-entity list were all built from it. This module is that
arithmetic moved to where the rows are, so a count is a count.

Four rules are kept from the client-side version because each was a defect it was
written to avoid, and each is easier to get right where the whole window is in hand:

* **Every row lands in a bucket.** A timestamp on or after the window's end is
  clamped into the last bucket rather than dropped, so the series total always
  equals the window's row count and a chart cannot quietly lose its tail.
* **An unrecognised severity is counted, not dropped.** The column is a checked
  enum, but this code must not *assume* that: an unknown band is tallied under
  ``unrecognised`` so ``sum(by_severity) + unrecognised == total``.
* **Ordering is total.** Ties break by id, never by input order, so two reads of
  the same window produce byte-identical output and a client cannot show a list
  that reshuffles between refreshes.
* **The entity list is a top-N, and says so.** ``entities_capped`` is set when the
  window held more entities than the limit, because "ten entities" and "ten of
  4,000" are different answers (design.md §8.1).

Nothing here resolves an entity id to a host or user value: that is the entity
registry's job, and the endpoint composes the two. Keeping the arithmetic free of
I/O is also what lets its tests pass rows in directly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db.models import Alert, Severity

__all__ = [
    "BUCKET_MINUTES_DEFAULT",
    "BUCKET_MINUTES_MAX",
    "ENTITY_LIMIT_DEFAULT",
    "ENTITY_LIMIT_MAX",
    "FAMILY_LIMIT_DEFAULT",
    "FAMILY_LIMIT_MAX",
    "Aggregate",
    "EntityTally",
    "FamilyTally",
    "SeriesPoint",
    "aggregate",
    "bucket_starts",
    "verdict_counts",
]

#: One hour: enough resolution for a day-long window, few enough points to draw.
BUCKET_MINUTES_DEFAULT = 60
#: A bucket wider than a day makes the series a single bar for most windows.
BUCKET_MINUTES_MAX = 1_440
#: What design.md §4.1 draws: a short list, worst and biggest first.
ENTITY_LIMIT_DEFAULT = 10
ENTITY_LIMIT_MAX = 50
#: The family mix is a bar chart, not a table: the tail is not readable.
FAMILY_LIMIT_DEFAULT = 8
FAMILY_LIMIT_MAX = 50

#: The verdicts an alert can carry. Absent means not yet triaged.
_VERDICTS = ("true_positive", "false_positive", "benign")


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """One bucket of the severity series.

    Attributes:
        start: the bucket's inclusive lower bound, in the window's own timezone.
        total: how many alerts fell in it.
        by_severity: the same count split by band, with the unrecognised band
            present only when it is non-zero.
    """

    start: datetime
    total: int
    by_severity: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class EntityTally:
    """One entity's share of the window, before its name is resolved.

    Attributes:
        entity_id: the ``entities.id`` the alert rows reference.
        alerts: how many alerts in the window were on this entity.
        occurrences: the sum of those alerts' occurrence counts -- one alert is one
            incident, and an incident that absorbed repeats is not one observation.
        open_alerts: how many of those are still open.
        worst_severity: the most serious band the entity reached.
        max_score: its highest score, as a float (the column is ``Numeric``).
        last_seen: the latest ``last_seen`` among its alerts.
    """

    entity_id: int
    alerts: int
    occurrences: int
    open_alerts: int
    worst_severity: str
    max_score: float
    last_seen: datetime


@dataclass(frozen=True, slots=True)
class FamilyTally:
    """One threat family's share of the window.

    Attributes:
        family: the label the model attributed, or ``(unnamed)`` for a blank one --
            dropped, the counts would not add up, and a blank family is a fact.
        alerts: how many alerts carried it.
        worst_severity: the most serious band it reached.
    """

    family: str
    alerts: int
    worst_severity: str


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Everything the overview's three panels read, over one window.

    Attributes:
        total: alerts created in the window, counted in full.
        by_severity: the window's count per band, worst band first, zero-filled.
        unrecognised: rows whose severity is not one of the five bands.
        open_alerts: how many of the window's alerts are still open.
        verdicts: the window's alerts by their current verdict.
        unrecorded: how many carry no verdict yet.
        verdicts_measured: how many verdict times the mean covers. A mean of one
            verdict is not a trend, so the count travels with it.
        mean_time_to_verdict_seconds: mean of ``verdict_at - created_at`` over the
            alerts a verdict has been recorded on, or ``None`` when none has.
        points: the severity series, oldest bucket first.
        entities: the top entities, biggest first.
        entities_capped: whether the window held more entities than ``entities``
            lists. The client must say "top N of more" rather than "N".
        families: the family mix, largest first.
        families_capped: the same statement for the families.
    """

    total: int
    by_severity: Mapping[str, int]
    unrecognised: int
    open_alerts: int
    verdicts: Mapping[str, int]
    unrecorded: int
    verdicts_measured: int
    mean_time_to_verdict_seconds: float | None
    points: Sequence[SeriesPoint]
    entities: Sequence[EntityTally]
    entities_capped: bool
    families: Sequence[FamilyTally]
    families_capped: bool


def _rank(severity: str) -> int:
    """Sort key for a severity: **higher is worse**, ``Severity.rank``'s own order.

    ``Severity.rank`` is the one definition of the band order (R-38); a value that
    is not a member sorts after every member rather than raising, because the
    aggregate must be able to count a row the enum does not know.
    """
    try:
        return Severity(severity).rank
    except ValueError:
        return len(Severity) + 1


def _known(severity: str) -> bool:
    """Whether the band is one of the five the column defines."""
    return severity in {member.value for member in Severity}


def bucket_starts(start: datetime, end: datetime, bucket_minutes: int) -> list[datetime]:
    """The inclusive lower bound of every bucket covering ``[start, end)``.

    The last bucket may extend past ``end``: a window of 90 minutes at an hourly
    bucket is two buckets, and clipping the second would make the series total
    disagree with the window's row count.
    """
    width = timedelta(minutes=bucket_minutes)
    if width <= timedelta(0):
        msg = "bucket_minutes must be positive"
        raise ValueError(msg)
    count = max(1, -(-(end - start) // width))
    return [start + width * index for index in range(count)]


def _bucket_index(at: datetime, start: datetime, bucket_minutes: int, count: int) -> int:
    """Which bucket a timestamp belongs to, clamped into the series."""
    offset = at - start
    width = timedelta(minutes=bucket_minutes)
    index = int(offset.total_seconds() // width.total_seconds())
    return min(max(index, 0), count - 1)


def verdict_counts(rows: Sequence[Alert]) -> tuple[dict[str, int], int]:
    """Count the window's alerts by current verdict, and how many have none."""
    counts = dict.fromkeys(_VERDICTS, 0)
    unrecorded = 0
    for row in rows:
        verdict = str(row.verdict) if row.verdict is not None else None
        if verdict in counts:
            counts[verdict] += 1
        else:
            unrecorded += 1
    return counts, unrecorded


def _mean_time_to_verdict(rows: Sequence[Alert]) -> tuple[float | None, int]:
    """Mean seconds from an alert's creation to its verdict.

    Only alerts that *have* a verdict and a verdict time count, and a verdict
    stamped before its own alert is left out rather than dragging the mean
    negative: a clock that disagrees with itself is not a triage speed.
    """
    durations: list[float] = []
    for row in rows:
        if row.verdict is None or row.verdict_at is None:
            continue
        seconds = (row.verdict_at - row.created_at).total_seconds()
        if seconds >= 0:
            durations.append(seconds)
    if not durations:
        return None, 0
    return sum(durations) / len(durations), len(durations)


def _entity_tallies(rows: Sequence[Alert], limit: int) -> tuple[list[EntityTally], bool]:
    """Per-entity totals for the window, biggest first, capped at ``limit``."""
    grouped: dict[int, EntityTally] = {}
    for row in rows:
        severity = str(row.severity)
        current = grouped.get(row.entity_id)
        if current is None:
            grouped[row.entity_id] = EntityTally(
                entity_id=row.entity_id,
                alerts=1,
                occurrences=row.occurrence_count,
                open_alerts=1 if str(row.status) == "open" else 0,
                worst_severity=severity,
                max_score=float(row.score),
                last_seen=row.last_seen,
            )
            continue
        grouped[row.entity_id] = EntityTally(
            entity_id=row.entity_id,
            alerts=current.alerts + 1,
            occurrences=current.occurrences + row.occurrence_count,
            open_alerts=current.open_alerts + (1 if str(row.status) == "open" else 0),
            worst_severity=max((current.worst_severity, severity), key=_rank),
            max_score=max(current.max_score, float(row.score)),
            last_seen=max(current.last_seen, row.last_seen),
        )
    ordered = sorted(grouped.values(), key=lambda tally: (-tally.alerts, tally.entity_id))
    return ordered[:limit], len(ordered) > limit


def _family_tallies(rows: Sequence[Alert], limit: int) -> tuple[list[FamilyTally], bool]:
    """Per-family counts for the window, largest first, capped at ``limit``."""
    grouped: dict[str, FamilyTally] = {}
    for row in rows:
        family = row.family.strip() or "(unnamed)"
        severity = str(row.severity)
        current = grouped.get(family)
        grouped[family] = FamilyTally(
            family=family,
            alerts=(current.alerts if current is not None else 0) + 1,
            worst_severity=(
                severity if current is None else max((current.worst_severity, severity), key=_rank)
            ),
        )
    ordered = sorted(grouped.values(), key=lambda tally: (-tally.alerts, tally.family))
    return ordered[:limit], len(ordered) > limit


def aggregate(
    rows: Sequence[Alert],
    *,
    start: datetime,
    end: datetime,
    bucket_minutes: int = BUCKET_MINUTES_DEFAULT,
    entity_limit: int = ENTITY_LIMIT_DEFAULT,
    family_limit: int = FAMILY_LIMIT_DEFAULT,
) -> Aggregate:
    """Aggregate every row of one window into the overview's three panels.

    Args:
        rows: **the window's rows, not a page of them.** Completeness is the
            caller's promise and this function's whole point (T-416): a caller
            that hands over a capped page gets a capped screen, which is what the
            endpoint must not do.
        start: the window's inclusive lower bound.
        end: its exclusive upper bound.
        bucket_minutes: the series' resolution, clamped to the documented range.
        entity_limit: how many entities to list, clamped to the documented range.
        family_limit: how many families the mix lists, clamped the same way.

    Returns:
        The aggregate. ``entities_capped`` says whether the list is a top-N.
    """
    if bucket_minutes < 1:
        msg = "bucket_minutes must be positive"
        raise ValueError(msg)
    bucket_minutes = min(bucket_minutes, BUCKET_MINUTES_MAX)
    entity_limit = min(max(entity_limit, 1), ENTITY_LIMIT_MAX)
    family_limit = min(max(family_limit, 1), FAMILY_LIMIT_MAX)

    starts = bucket_starts(start, end, bucket_minutes)
    totals = dict.fromkeys((member.value for member in Severity), 0)
    buckets = [dict.fromkeys((member.value for member in Severity), 0) for _ in starts]
    unrecognised = 0
    open_alerts = 0
    for row in rows:
        severity = str(row.severity)
        if severity in totals:
            totals[severity] += 1
        else:
            unrecognised += 1
        if str(row.status) == "open":
            open_alerts += 1
        index = _bucket_index(row.created_at, start, bucket_minutes, len(starts))
        buckets[index][severity] = buckets[index].get(severity, 0) + 1

    points = []
    for index, bucket_start in enumerate(starts):
        counts = buckets[index]
        points.append(
            SeriesPoint(
                start=bucket_start,
                # The bucket's total counts the unrecognised band too: a bucket
                # whose rows are all unknown is not an empty bucket.
                total=sum(counts.values()),
                by_severity={band: count for band, count in counts.items() if count > 0},
            )
        )

    verdicts, unrecorded = verdict_counts(rows)
    mean_seconds, measured = _mean_time_to_verdict(rows)
    entities, capped = _entity_tallies(rows, entity_limit)
    families, families_capped = _family_tallies(rows, family_limit)
    return Aggregate(
        total=len(rows),
        by_severity=totals,
        unrecognised=unrecognised,
        open_alerts=open_alerts,
        verdicts=verdicts,
        unrecorded=unrecorded,
        verdicts_measured=measured,
        mean_time_to_verdict_seconds=(None if mean_seconds is None else round(mean_seconds, 3)),
        points=points,
        entities=entities,
        entities_capped=capped,
        families=families,
        families_capped=families_capped,
    )
