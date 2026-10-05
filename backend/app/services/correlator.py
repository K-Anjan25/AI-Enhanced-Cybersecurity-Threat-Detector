"""Correlator: severity banding, cool-down dedup, and flow/log grouping (T-308).

FR-13, FR-14, FR-15 and FR-19 in one place, because they are one decision
pipeline: a score becomes a band, a band plus an entity becomes an alert, and an
alert that already exists becomes an increment.

The acceptance criterion is the dedup. A duplicate `(entity, family)` inside the
cool-down increments `occurrence_count` rather than creating a row, so the
question that decides the implementation is *what the cool-down is measured
from*. Two readings are defensible and they behave very differently:

- **Sliding, from `last_seen`** (chosen): a recurrence within 15 minutes of the
  previous occurrence is suppressed. An attack that runs for hours stays one
  alert with a growing count, which is what an operator wants -- one incident,
  not 12.
- **Fixed, from `first_seen`**: a new alert appears every 15 minutes for as long
  as the attack lasts. That produces a fresh row for what is plainly the same
  ongoing event.

Sliding is the default and `anchor` makes the other available, because the
choice is operational policy rather than a fact about the data and should not be
buried.

Note the consequence of sliding, stated rather than hidden: a slow attack that
recurs every 14 minutes forever produces exactly one alert. That is intended,
but it means `occurrence_count` and `last_seen - first_seen` are the only record
of how long it ran, so both are maintained on every increment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol

__all__ = [
    "BAND_FLOOR",
    "DEFAULT_COOL_DOWN",
    "GROUPING_WINDOW",
    "AlertStore",
    "CorrelatedAlert",
    "Correlator",
    "InMemoryAlertStore",
    "ScoreEvent",
    "Severity",
    "severity_band",
]

#: FR-15: default cool-down of 15 minutes.
DEFAULT_COOL_DOWN = timedelta(minutes=15)

#: FR-19: a flow alert and a log alert on the same entity within +/-60s are one
#: case.
GROUPING_WINDOW = timedelta(seconds=60)

#: FR-13, in descending order. The floor is what `info` catches.
BAND_FLOOR = 0.35


class Severity(StrEnum):
    """The five bands FR-13 defines."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


#: FR-13's thresholds, written out. Ordered highest first so the first band
#: whose floor is met wins.
_THRESHOLDS: tuple[tuple[Severity, float], ...] = (
    (Severity.CRITICAL, 0.90),
    (Severity.HIGH, 0.75),
    (Severity.MEDIUM, 0.55),
    (Severity.LOW, BAND_FLOOR),
)


def severity_band(score: float) -> Severity:
    """Map a composite score in [0, 1] to a severity band (FR-13).

    The thresholds are inclusive lower bounds, so 0.90 is `critical` and not
    `high`. A score outside [0, 1] is refused rather than clamped: a score of
    1.4 means something upstream is broken, and banding it as `critical` would
    hide that.
    """
    if not 0.0 <= score <= 1.0:
        msg = f"score {score} is outside [0, 1]; a composite score must be bounded"
        raise ValueError(msg)
    for severity, floor in _THRESHOLDS:
        if score >= floor:
            return severity
    return Severity.INFO


@dataclass(frozen=True, slots=True)
class ScoreEvent:
    """A scored window arriving at the correlator."""

    entity_id: int
    entity_value: str
    family: str
    score: float
    #: "flow" or "log"; FR-19 groups across the two.
    modality: Literal["flow", "log"]
    seen_at: datetime
    #: FR-14: top contributing features or log templates, most significant first.
    reasons: tuple[str, ...] = ()


@dataclass(slots=True)
class CorrelatedAlert:
    """The alert row an event produced, and whether it was new."""

    alert_id: int
    entity_id: int
    family: str
    severity: str
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime
    is_new: bool
    #: "flow" or "log". FR-19 groups across the two, so it has to be stored.
    modality: str = "flow"
    explanation: list[str] = field(default_factory=list)
    group_id: str | None = None


class AlertStore(Protocol):
    """Where alerts live. Narrow enough to fake without a database."""

    def find_open(self, entity_id: int, family: str) -> CorrelatedAlert | None:
        """The current alert for this entity and family, if one is open."""
        ...

    def insert(self, alert: CorrelatedAlert) -> int:
        """Create a row and return its id."""
        ...

    def increment(self, alert_id: int, seen_at: datetime) -> CorrelatedAlert:
        """Bump `occurrence_count` and `last_seen` on an existing row."""
        ...

    def all(self) -> list[CorrelatedAlert]:
        """Every stored alert."""
        ...


class InMemoryAlertStore:
    """An AlertStore for tests and single-process use."""

    __slots__ = ("_alerts", "_next_id")

    def __init__(self) -> None:
        """Start empty."""
        self._alerts: dict[int, CorrelatedAlert] = {}
        self._next_id = 1

    def find_open(self, entity_id: int, family: str) -> CorrelatedAlert | None:
        """The most recent alert for this entity and family."""
        matches = [
            a for a in self._alerts.values() if a.entity_id == entity_id and a.family == family
        ]
        return max(matches, key=lambda a: a.last_seen) if matches else None

    def insert(self, alert: CorrelatedAlert) -> int:
        """Store a new alert under the next id."""
        alert.alert_id = self._next_id
        self._alerts[self._next_id] = alert
        self._next_id += 1
        return alert.alert_id

    def increment(self, alert_id: int, seen_at: datetime) -> CorrelatedAlert:
        """Bump the count and move `last_seen` forward.

        `last_seen` never moves backwards, because a late-arriving record must
        not make an alert look less recent than it already did.
        """
        alert = self._alerts[alert_id]
        alert.occurrence_count += 1
        if seen_at > alert.last_seen:
            alert.last_seen = seen_at
        return alert

    def all(self) -> list[CorrelatedAlert]:
        """Every alert, ordered by id."""
        return [self._alerts[key] for key in sorted(self._alerts)]


class Correlator:
    """Turns scored events into alerts, suppressing duplicates."""

    __slots__ = ("_anchor", "_cool_down", "_store")

    def __init__(
        self,
        store: AlertStore,
        *,
        cool_down: timedelta = DEFAULT_COOL_DOWN,
        anchor: Literal["last_seen", "first_seen"] = "last_seen",
    ) -> None:
        """Bind to a store and a cool-down policy."""
        if cool_down <= timedelta(0):
            msg = "cool_down must be positive; zero would suppress nothing"
            raise ValueError(msg)
        self._store = store
        self._cool_down = cool_down
        self._anchor = anchor

    @property
    def cool_down(self) -> timedelta:
        """The configured suppression window."""
        return self._cool_down

    def correlate(self, event: ScoreEvent) -> CorrelatedAlert:
        """Correlate one event, creating or incrementing an alert.

        A duplicate `(entity, family)` inside the cool-down increments
        `occurrence_count` and creates no row. That is the acceptance criterion,
        and it is why this returns the alert rather than a boolean: the caller
        needs to know the count went up.
        """
        severity = severity_band(event.score)
        existing = self._store.find_open(event.entity_id, event.family)

        if existing is not None and self._within_cool_down(existing, event.seen_at):
            updated = self._store.increment(existing.alert_id, event.seen_at)
            # A snapshot, not the live row. Two things go wrong otherwise:
            # `is_new` would describe the row's history rather than this call,
            # and because the store hands back the same object, mutating it
            # would silently rewrite results the caller already holds.
            return replace(updated, is_new=False)

        alert = CorrelatedAlert(
            alert_id=0,
            entity_id=event.entity_id,
            family=event.family,
            severity=severity.value,
            occurrence_count=1,
            first_seen=event.seen_at,
            last_seen=event.seen_at,
            is_new=True,
            modality=event.modality,
            # FR-14: top three, never fewer when three exist.
            explanation=list(event.reasons[:3]),
            group_id=str(event.entity_id),
        )
        self._store.insert(alert)
        return replace(alert)

    def correlate_batch(self, events: Iterable[ScoreEvent]) -> list[CorrelatedAlert]:
        """Correlate a batch in order.

        Order matters: which event is "first" decides which becomes the row and
        which become increments.
        """
        return [self.correlate(event) for event in events]

    def _within_cool_down(self, alert: CorrelatedAlert, seen_at: datetime) -> bool:
        """Whether this event is a duplicate of an existing alert."""
        reference = alert.last_seen if self._anchor == "last_seen" else alert.first_seen
        return abs(seen_at - reference) <= self._cool_down

    def grouped_cases(self) -> dict[str, list[CorrelatedAlert]]:
        """Flow and log alerts on one entity within +/-60s, as one case (FR-19).

        A group qualifies only if it contains **both** modalities and they fall
        inside the window. A flow alert with no log alert nearby is not a case,
        and calling it one would make the grouping look more useful than it is.

        Grouping is resolved here rather than at insert time because a flow
        alert usually arrives before the log alert it belongs with, and neither
        knows the other exists yet.
        """
        by_entity: dict[str, list[CorrelatedAlert]] = {}
        for alert in self._store.all():
            if alert.group_id is not None:
                by_entity.setdefault(alert.group_id, []).append(alert)

        grouped: dict[str, list[CorrelatedAlert]] = {}
        for key, members in by_entity.items():
            modalities = {a.modality for a in members}
            if not {"flow", "log"} <= modalities:
                continue
            times = sorted(a.last_seen for a in members)
            if times[-1] - times[0] <= GROUPING_WINDOW:
                grouped[key] = members
        return grouped
