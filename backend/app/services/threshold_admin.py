"""Setting a threshold by hand, and previewing what it would have done (T-410, FR-18).

The admin screen's threshold panel is the first place a *person* writes a threshold.
T-322's job moves one per family from analyst feedback; this module is the deliberate
edit, and it carries three rules that the job did not need:

**A manual set cannot make the bands cross.** The four bands' lower bounds are
strictly descending (``correlator.SeverityBands`` refuses anything else), and the
values in force are per ``(family, band)``. Editing *one* band therefore has to be
checked against the other three, or a person could leave a family with
``medium > high`` — a band set that the correlator would refuse at startup if it ever
read it. The check is not re-implemented here: the proposed value is substituted into
the values in force and the result is handed to ``SeverityBands`` itself, so the rule
that validates a manual edit is the rule that bands a score.

**The preview is exact over recorded cases, and the unit is alerts, not events.**
The correlator creates a case for every window it decides exists and bands it from
its score *afterwards* (T-308), so the alert store holds the cases whatever their
severity — which is what makes "how many alerts would this value have produced" a
count over stored rows rather than an extrapolation. What it cannot do is count raw
events: a row stands for a case, and ``occurrence_count`` says how many occurrences
went into it. The response carries the window and the count, so the number is always
read with what it measures.

**Nothing is invented when there is no row.** A family with no row is governed by
FR-13's documented default, so the listing reports that as the value in force and the
preview differences against it — never against zero, which would make every count look
like an improvement.

**Attribution comes from the trail, not from a column.** ``thresholds`` has no
``updated_by``, and adding one would create a second record of who changed what beside
the append-only one that already exists (FR-42). :func:`last_change` reads the newest
``threshold.set``/``threshold.recalibrate`` record whose instant matches the row's own,
which is what makes the writer of a row and the writer in the trail the same event.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType

from app.schemas.query import MAX_PAGE_SIZE, AlertQuery
from app.services.alert_store import AlertStore
from app.services.audit_log import AuditAction, AuditEntry, AuditTrail
from app.services.correlator import SeverityBands
from app.services.query_service import paginate
from app.services.recalibration import (
    BAND_DEFAULTS,
    RECALIBRATED_SOURCE,
    ThresholdKey,
    ThresholdRecord,
    ThresholdStore,
    UnfittableBand,
)

__all__ = [
    "MANUAL_SOURCE",
    "PREVIEW_WINDOW",
    "SOURCE_DEFAULT",
    "SOURCE_LABELS",
    "BandOrderRefused",
    "InvalidThreshold",
    "ManualWrite",
    "RecordedChange",
    "ThresholdAdminService",
    "ThresholdImpactReader",
    "ThresholdPreview",
    "last_change",
    "source_label",
]

#: What a row written by the admin screen says. The ``source`` column is R-69's
#: provenance, so a hand-set value is distinguishable from a fitted one forever.
MANUAL_SOURCE = "manual"

#: design.md §4.8's third source name: a family governed by FR-13's documented value
#: has no row at all, and "default" is the honest name for that.
SOURCE_DEFAULT = "default"

#: Stored provenance to design.md's vocabulary. A mapping rather than a rename of the
#: stored value: T-322 already persisted ``recalculation`` in deployments and in its
#: tests, and a rename would be a data migration for a label.
SOURCE_LABELS: Mapping[str, str] = MappingProxyType(
    {RECALIBRATED_SOURCE: "calibrated", MANUAL_SOURCE: "manual"}
)

#: The window the impact preview reads, from design.md §4.8. Seven days, because the
#: question the panel answers is "how many alerts would this have produced last week".
PREVIEW_WINDOW = timedelta(days=7)


class InvalidThreshold(ValueError):
    """The proposed value is not a threshold at all."""


class BandOrderRefused(ValueError):
    """The proposed value would leave the family's bands out of order."""


@dataclass(frozen=True, slots=True)
class ManualWrite:
    """What a hand-set threshold did, including when it changed nothing.

    Attributes:
        key: the threshold that was addressed.
        previous: the value in force before the call.
        previous_label: where that value came from, in design.md's vocabulary.
        applied: the value in force after it.
        changed: false when the same hand had already set this value, in which case
            nothing was written and the trail recorded nothing (D-038).
        at: the write instant.
    """

    key: ThresholdKey
    previous: float
    previous_label: str
    applied: float
    changed: bool
    at: datetime


def source_label(source: str) -> str:
    """Design.md's name for a stored provenance, or the stored name if it is new."""
    return SOURCE_LABELS.get(source, source)


@dataclass(frozen=True, slots=True)
class RecordedChange:
    """Who last moved a threshold, and when, as the trail remembers it."""

    actor: str
    at: datetime
    previous: float | None
    applied: float | None


def last_change(trail: AuditTrail, key: ThresholdKey, *, at: datetime) -> RecordedChange | None:
    """The newest role change... the newest threshold change recorded for ``key``.

    The row's own ``updated_at`` is the anchor: the trail is asked for a window
    around that instant rather than for all history, so the read is bounded by
    construction and cannot miss a fresher record than the row it is attributed to.

    Returns:
        The record's actor, instant and the numbers it carried, or ``None`` when the
        trail holds no record at that instant -- which is a fact worth rendering
        rather than a reason to guess an actor.
    """
    window = timedelta(seconds=1)
    newest: AuditEntry | None = None
    for action in (AuditAction.threshold_set, AuditAction.threshold_recalibrate):
        found = trail.entries(
            start=at - window,
            end=at + window,
            action=action,
            target_id=str(key),
            limit=1,
        )
        for entry in found:
            if newest is None or entry.sequence > newest.sequence:
                newest = entry
    if newest is None:
        return None
    detail = newest.record.detail
    applied = detail.get("applied")
    previous = detail.get("previous")
    return RecordedChange(
        actor=newest.record.actor,
        at=newest.record.at,
        previous=float(previous) if isinstance(previous, (int, float)) else None,
        applied=float(applied) if isinstance(applied, (int, float)) else None,
    )


@dataclass(frozen=True, slots=True)
class ThresholdAdminService:
    """The values in force, and the one write a person makes to them.

    Attributes:
        store: where the rows live.
        tenant_id: the tenant a write belongs to.
    """

    store: ThresholdStore
    tenant_id: str

    def __post_init__(self) -> None:
        """Refuse a service that cannot name the tenant it writes for."""
        if not self.tenant_id.strip():
            raise ValueError("a threshold administrator must name its tenant")

    def row(self, family: str, band: str) -> ThresholdRecord | None:
        """The row in force for one key, or ``None`` when the default governs."""
        return self.store.get(self.key(family, band))

    def key(self, family: str, band: str) -> ThresholdKey:
        """The address of one threshold, refusing a band with no bound to move.

        Raises:
            UnfittableBand: for ``info``, which FR-13 gives no lower bound: there is
                no number in force and none to set. ``ThresholdKey`` refuses it as a
                plain ``ValueError``; the type is named here because this is the
                layer that knows a *request* asked for it, and the route maps that
                to a 400 naming the bands that do have bounds.
            ValueError: for an empty family.
        """
        try:
            return ThresholdKey(tenant_id=self.tenant_id, family=family, band=band)
        except ValueError as exc:
            if band in BAND_DEFAULTS:
                raise
            raise UnfittableBand(str(exc)) from exc

    def value_in_force(self, family: str, band: str) -> tuple[float, str]:
        """The value governing ``(family, band)`` and where it comes from.

        Returns:
            ``(value, label)`` with the label in design.md's vocabulary --
            ``default`` when no row exists, else ``calibrated``/``manual``.
        """
        found = self.row(family, band)
        if found is None:
            return BAND_DEFAULTS[band], SOURCE_DEFAULT
        return found.value, source_label(found.source)

    def values_in_force(self, family: str) -> dict[str, float]:
        """Every band's value for a family, from rows where they exist."""
        return {band: self.value_in_force(family, band)[0] for band in BAND_DEFAULTS}

    def set_manual(
        self, *, family: str, band: str, value: float, actor: str, at: datetime
    ) -> ManualWrite:
        """Write a hand-set threshold, or refuse without touching the store.

        Args:
            family: the detection family the value governs.
            band: which band's lower bound to move.
            value: the new bound, strictly inside ``(0, 1)``.
            actor: who asked. Recorded by the caller in the trail; the model itself
                does not write an audit row, so a refused set records nothing.
            at: the write instant, timezone-aware.

        Returns:
            The write: the value in force before and after, and ``changed`` false when
            the same hand had already set this value.

        Raises:
            UnfittableBand: for a band FR-13 gives no lower bound.
            InvalidThreshold: for a value outside ``(0, 1)`` or a naive instant.
            BandOrderRefused: when the value would leave the bands out of order.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("a threshold write needs a timezone-aware instant")
        if not actor.strip():
            raise ValueError("a threshold write must name the actor that asked for it")
        if not 0.0 < value < 1.0:
            raise InvalidThreshold(
                f"a threshold is strictly between 0 and 1, got {value}: 0 would band "
                "everything at this level and 1 would band nothing"
            )
        key = self.key(family, band)  # raises for a band with no bound

        in_force = self.values_in_force(family)
        proposed = {**in_force, band: value}
        try:
            SeverityBands(**proposed)
        except ValueError as exc:
            raise BandOrderRefused(
                f"{exc}; a manual edit to {family}/{band} is checked against the other "
                "three bands, because a score is banded by all four together"
            ) from exc

        previous, previous_label = self.value_in_force(family, band)
        found = self.store.get(key)
        if found is not None and found.value == value and found.source == MANUAL_SOURCE:
            # Already this value, from the same hand: nothing to write, nothing to
            # audit. A calibrated row that happens to hold this value is still a
            # change -- the provenance is part of what is being set.
            return ManualWrite(
                key=key,
                previous=previous,
                previous_label=previous_label,
                applied=value,
                changed=False,
                at=at,
            )

        record = ThresholdRecord(key=key, value=value, source=MANUAL_SOURCE, updated_at=at)
        self.store.put(record)
        return ManualWrite(
            key=key,
            previous=previous,
            previous_label=previous_label,
            applied=value,
            changed=True,
            at=at,
        )


@dataclass(frozen=True, slots=True)
class ThresholdPreview:
    """What a proposed threshold would have done over the preview window.

    Attributes:
        family: the family the value governs.
        band: the band whose lower bound was proposed.
        proposed: the value the operator typed.
        current: the value in force, so the preview can say what changes.
        current_label: where ``current`` comes from (``default``/``calibrated``/``manual``).
        window_start: inclusive lower bound of the window actually read.
        window_end: exclusive upper bound.
        alerts_read: how many recorded alerts the count was taken over.
        would_fire: alerts at or above the proposed bound -- what the value would
            have produced at this band or worse.
        would_stop_firing: alerts that reached this band under the current value and
            would not under the proposed one. Only meaningful when raising.
        would_start_firing: alerts below the current bound that the proposed value
            would have pulled in. Only meaningful when lowering.
        complete: false when the page cap stopped the walk, in which case the counts
            are a floor rather than a total.
    """

    family: str
    band: str
    proposed: float
    current: float
    current_label: str
    window_start: datetime
    window_end: datetime
    alerts_read: int
    would_fire: int
    would_stop_firing: int
    would_start_firing: int
    complete: bool


@dataclass(frozen=True, slots=True)
class ThresholdImpactReader:
    """Counts a proposed threshold against the alerts already recorded.

    Attributes:
        alerts: where recorded alerts live -- the same store the query API reads, so
            the preview counts what the list would show rather than a copy.
        admin: the service that knows the value in force.
        window: how far back to look. Defaults to design.md §4.8's seven days.
        page_size: rows per page through the alert query.
        max_pages: a bound on the walk, so a cursor that never advances cannot hang
            a request. Hitting it is reported as ``complete=False``.
    """

    alerts: AlertStore
    admin: ThresholdAdminService
    window: timedelta = PREVIEW_WINDOW
    page_size: int = MAX_PAGE_SIZE
    max_pages: int = 100

    def __post_init__(self) -> None:
        """Refuse a configuration that cannot produce an honest count."""
        if self.window <= timedelta(0):
            raise ValueError(f"the preview window must be positive, got {self.window}")
        if not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be in [1, {MAX_PAGE_SIZE}], got {self.page_size}")
        if self.max_pages < 1:
            raise ValueError(f"max_pages must be at least 1, got {self.max_pages}")

    def preview(self, *, family: str, band: str, proposed: float, at: datetime) -> ThresholdPreview:
        """Count what ``proposed`` would have produced over the window ending at ``at``.

        Args:
            family: the family to count within. A threshold is keyed by family, so a
                count across families would answer a different question.
            band: whose lower bound is being proposed.
            proposed: the value the operator typed.
            at: the instant the window ends. Time comes in rather than from the
                clock so a boundary is testable.

        Raises:
            InvalidThreshold: for a value outside ``(0, 1)``, or a naive instant.
            UnfittableBand: for a band FR-13 gives no lower bound.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("a preview needs a timezone-aware instant")
        if not 0.0 < proposed < 1.0:
            raise InvalidThreshold(f"a threshold is strictly between 0 and 1, got {proposed}")
        self.admin.key(family, band)  # refuses a band with no bound to move
        current, current_label = self.admin.value_in_force(family, band)
        start = at - self.window

        alerts_read = 0
        would_fire = 0
        would_stop = 0
        would_start = 0
        cursor: str | None = None
        complete = False
        for _ in range(self.max_pages):
            query = AlertQuery(
                start=start,
                end=at,
                family=frozenset({family}),
                order="asc",
                limit=self.page_size,
                cursor=cursor,
            )
            page = paginate(self.alerts.fetch(query), query)
            for row in page.items:
                alerts_read += 1
                if row.score >= proposed:
                    would_fire += 1
                if current <= row.score < proposed:
                    would_stop += 1
                if proposed <= row.score < current:
                    would_start += 1
            if page.next_cursor is None:
                complete = True
                break
            cursor = page.next_cursor

        return ThresholdPreview(
            family=family,
            band=band,
            proposed=proposed,
            current=current,
            current_label=current_label,
            window_start=start,
            window_end=at,
            alerts_read=alerts_read,
            would_fire=would_fire,
            would_stop_firing=would_stop,
            would_start_firing=would_start,
            complete=complete,
        )


def bands_in_force(admin: ThresholdAdminService, family: str) -> SeverityBands:
    """The four bounds a score in this family is banded against, rows included.

    Public because two callers need the same answer: a manual set validates against
    it, and the screen shows the operator what the family looks like after the edit.
    """
    return SeverityBands(**admin.values_in_force(family))
