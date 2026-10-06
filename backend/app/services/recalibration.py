"""Weekly threshold recalibration from analyst verdicts (FR-18, T-322).

FR-18 asks for feedback to be *used*: T-309 records verdicts, and a verdict that
changes nothing is a form nobody fills in twice. This module is the job that turns
them into the numbers the detector actually fires on. It is deliberately a small
amount of arithmetic around three decisions.

**The window is when the score happened, not when it was labelled.** Architecture
§7.4 specifies a rolling 14-day window of scores labelled benign/false-positive.
The score's own time is the one that describes the traffic the threshold will next
be applied to; a labelling backlog would otherwise re-shape the sample around
stale alerts, and a fit is supposed to say what benign traffic looks like *now*.
The label must exist as of the run, so a run replayed for a past instant sees the
verdicts that were in force then.

**Only `benign` and `false_positive` labels are evidence.** A `true_positive` is
evidence about an attack, and a threshold is a statement about the benign
distribution; mixing the two moves the bar towards the attack scores, which is
exactly the recall-for-quietness trade this job exists to avoid. A family whose
only labels are `true_positive` gets no fit at all, and is reported as such.

**Too little feedback means no fit.** Below :data:`MIN_FEEDBACK` samples the fit is
refused rather than applied. The number is not arbitrary: the calibrator fits the
``q``-th quantile (0.99 by default, asserting a 1% false-positive budget), and with
fewer than ``1/(1-q)`` samples that quantile *is* the top one or two order
statistics -- the maximum wearing a quantile's name. A threshold fitted from 20
scores is a threshold fitted from its two loudest windows.

**The guardrail, the quantile and the arithmetic come from T-207.** They are not
restated here, because two implementations of "clamp the move to 0.10" would
disagree eventually and neither would be wrong. :class:`Calibrator` is injected and
:class:`~app.services.ml_calibration.MlCalibrator` is the adapter over the ML
package's own ``fit_threshold``/``calibrate``; the backend image does not install
that package, so the dependency is named where it is used instead of assumed.

**Fits are computed before anything is written.** A run that wrote rows as it went
would leave a half-recalibrated tenant behind when one family's sample is corrupt,
so every fit happens first and only then is the store updated. The two phases are
one loop apart, and the failure mode they prevent is invisible without a test.

**What this is not.** The tenant is a property of the deployment here -- ``alerts``
has no tenant column, so the feedback source cannot attribute a score to a tenant
and refuses to pretend (see :class:`AlertVerdictFeedback`). The store, the report
and the audit rows are tenant-keyed so a multi-tenant deployment replaces the
feedback source rather than the job. Scheduling is deployment, too: nothing here
runs weekly on its own, and no manifest schedules it yet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from app.db.models import Verdict
from app.schemas.query import MAX_PAGE_SIZE, AlertQuery
from app.services.alert_store import AlertStore
from app.services.correlator import SeverityBands
from app.services.query_service import paginate
from app.services.verdict_service import VerdictLedger

__all__ = [
    "BAND_DEFAULTS",
    "BENIGN_LABELS",
    "DEFAULT_TENANT_ID",
    "DEFAULT_WINDOW",
    "MIN_FEEDBACK",
    "RECALIBRATED_SOURCE",
    "AlertVerdictFeedback",
    "Calibration",
    "Calibrator",
    "FeedbackSource",
    "InMemoryThresholdStore",
    "OutcomeReason",
    "RecalibrationReport",
    "RecalibrationService",
    "ThresholdKey",
    "ThresholdOutcome",
    "ThresholdRecord",
    "ThresholdStore",
    "UnfittableBand",
]

#: The tenant this deployment's alerts belong to. A name, not a secret: R-53's
#: roles are deployment-wide and ``alerts`` has no tenant column (the gap the
#: module docstring names), so the composition root wires one deployment tenant.
DEFAULT_TENANT_ID = "default"

#: Architecture §7.4's rolling window. A *weekly* job over a *14-day* window is
#: deliberate: consecutive runs overlap, so one quiet week cannot fall out of the
#: sample between two firings and move the threshold on the strength of a gap.
DEFAULT_WINDOW = timedelta(days=14)

#: The smallest sample a fit is allowed to use. ``1 / (1 - 0.99)``: below it the
#: 0.99 quantile is decided by the top one or two observations, so the "fit" would
#: be an extreme value rather than a distribution. See the module docstring.
MIN_FEEDBACK = 100

#: What a recalibrated row's ``source`` column says. The column exists so a
#: threshold's provenance is readable (R-69); a row written by this job says so.
RECALIBRATED_SOURCE = "recalibration"

#: Labels that are evidence about benign traffic. Everything else -- including a
#: missing label -- is not, and is never fitted on.
BENIGN_LABELS = frozenset({Verdict.benign, Verdict.false_positive})

#: FR-13's documented initial band edges, read from the same object the correlator
#: bands by so the two cannot drift (R-69). ``info`` is absent on purpose: FR-13
#: gives it no lower bound -- everything below ``low`` is ``info`` -- so there is no
#: number for a recalibration to move and no row for it to move it in.
_BANDS = SeverityBands()
BAND_DEFAULTS: Mapping[str, float] = MappingProxyType(
    {
        "critical": _BANDS.critical,
        "high": _BANDS.high,
        "medium": _BANDS.medium,
        "low": _BANDS.low,
    }
)


class UnfittableBand(ValueError):
    """The requested band has no documented lower bound to recalibrate."""


class OutcomeReason(StrEnum):
    """Why an outcome looks the way it does. A wire value, so a stable string."""

    fitted = "fitted"
    insufficient_feedback = "insufficient_feedback"


@dataclass(frozen=True, slots=True, order=True)
class ThresholdKey:
    """One threshold's address: the unique key of a ``thresholds`` row.

    Attributes:
        tenant_id: the tenant the threshold governs.
        family: the detection family it governs, as the alert rows name it.
        band: which FR-13 band's lower bound the value is.
    """

    tenant_id: str
    family: str
    band: str

    def __post_init__(self) -> None:
        """Refuse an address that cannot identify a row, or a band it cannot mean."""
        for name, value in (("tenant_id", self.tenant_id), ("family", self.family)):
            if not value.strip():
                raise ValueError(f"a threshold key needs a non-empty {name}")
        if self.band not in BAND_DEFAULTS:
            allowed = ", ".join(sorted(BAND_DEFAULTS))
            raise ValueError(
                f"band {self.band!r} has no documented lower bound to recalibrate; "
                f"FR-13's bands with one are: {allowed}"
            )

    def __str__(self) -> str:
        """The form the audit trail's ``target_id`` carries."""
        return f"{self.tenant_id}/{self.family}/{self.band}"


@dataclass(frozen=True, slots=True)
class ThresholdRecord:
    """One ``thresholds`` row: the value in force for one key.

    Attributes:
        key: the row's unique address.
        value: the threshold, in ``[0, 1]``.
        source: where the value came from -- :data:`RECALIBRATED_SOURCE` for a row
            this job wrote, so the provenance R-69 asks for is readable.
        updated_at: when it was last written, timezone-aware.
    """

    key: ThresholdKey
    value: float
    source: str
    updated_at: datetime

    def __post_init__(self) -> None:
        """Refuse a value that is not a threshold or a time that is not an instant."""
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {self.value}")
        if not self.source.strip():
            raise ValueError("a threshold row must name where its value came from")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class LabelledScore:
    """One alert's score, with the verdict an analyst has given it.

    Only labelled scores exist as instances of this type, which is the point: the
    job cannot fit on unlabelled traffic because unlabelled traffic has no
    representation here.

    Attributes:
        alert_id: the alert's ``id`` column.
        family: the detection family the alert was written under.
        score: the fused score, in ``[0, 1]``.
        verdict: the decision in force.
        alerted_at: when the alert fired -- the time the window is over.
        labelled_at: when the verdict was recorded.
    """

    alert_id: int
    family: str
    score: float
    verdict: Verdict
    alerted_at: datetime
    labelled_at: datetime


@dataclass(frozen=True, slots=True)
class Calibration:
    """One clamped fit, in the shape the backend needs (T-207's result).

    Attributes:
        previous: the value in force before the run.
        requested: what the fit asked for, before the guardrail.
        applied: what the guardrail allowed.
        clamped: whether the guardrail limited the movement.
        quantile: the quantile the fit used.
        sample_size: how many labelled scores the fit saw.
    """

    previous: float
    requested: float
    applied: float
    clamped: bool
    quantile: float
    sample_size: int


@dataclass(frozen=True, slots=True)
class ThresholdOutcome:
    """What one run decided about one threshold.

    Attributes:
        key: the threshold's address.
        previous: the value in force before the run.
        previous_was_default: ``True`` when no row existed, so ``previous`` is
            FR-13's documented initial value rather than a stored one.
        requested: what the fit asked for, or ``None`` when no fit was attempted.
        applied: the value now in force -- ``previous`` when nothing changed.
        changed: whether the run wrote a value different from ``previous``.
        clamped: whether the guardrail limited the movement.
        sample_size: the benign labelled scores the fit saw (or would have).
        reason: :class:`OutcomeReason`, so a refusal is distinguishable from a fit
            that happened to request the value already in force.
    """

    key: ThresholdKey
    previous: float
    previous_was_default: bool
    requested: float | None
    applied: float
    changed: bool
    clamped: bool
    sample_size: int
    reason: OutcomeReason


@dataclass(frozen=True, slots=True)
class RecalibrationReport:
    """One run: what it considered, what it changed, and on what evidence.

    Attributes:
        tenant_id: the tenant the run covered.
        band: the band whose lower bound was recalibrated.
        at: when the run happened, timezone-aware.
        since: the start of the window, inclusive.
        until: the end of the window, exclusive -- the run's instant.
        quantile: the quantile the fit used, as the calibrator reports it.
        minimum_sample: the floor a fit had to clear.
        outcomes: one entry per threshold considered, sorted by family.
    """

    tenant_id: str
    band: str
    at: datetime
    since: datetime
    until: datetime
    quantile: float
    minimum_sample: int
    outcomes: tuple[ThresholdOutcome, ...]

    @property
    def changed(self) -> tuple[ThresholdOutcome, ...]:
        """The thresholds this run moved. One audit row each, and no others."""
        return tuple(outcome for outcome in self.outcomes if outcome.changed)

    @property
    def refused(self) -> tuple[ThresholdOutcome, ...]:
        """The thresholds the run declined to fit, with their sample sizes."""
        return tuple(
            outcome
            for outcome in self.outcomes
            if outcome.reason is OutcomeReason.insufficient_feedback
        )


class ThresholdStore(Protocol):
    """Where the values in force live.

    Mirrors the ``thresholds`` table's unique key: one row per
    ``(tenant, family, band)``, replaced in place. The persistent adapter is a
    session over that table -- unwired here because no session exists (D-030) --
    and the in-memory implementation is what runs.
    """

    def rows(self) -> Sequence[ThresholdRecord]:
        """Every row in force."""
        ...

    def get(self, key: ThresholdKey) -> ThresholdRecord | None:
        """The row for one key, or ``None`` when FR-13's default is in force."""
        ...

    def put(self, record: ThresholdRecord) -> None:
        """Insert or replace one row."""
        ...


class FeedbackSource(Protocol):
    """Where labelled scores come from.

    A source answers for one tenant at a time, and answers ``()`` for a tenant it
    cannot attribute scores to rather than mixing tenants -- see
    :class:`AlertVerdictFeedback`, which is that refusal made concrete.
    """

    def labelled_scores(
        self, *, tenant_id: str, since: datetime, until: datetime
    ) -> Sequence[LabelledScore]:
        """Labelled scores alerted in ``[since, until)``, oldest first."""
        ...


class Calibrator(Protocol):
    """T-207's calibrator, injected because the backend does not install it.

    The protocol is deliberately narrow. It carries no guardrail, quantile or
    sample-size argument: those are the ML implementation's own documented values,
    and a caller that could pass them could quietly remove the guardrail the
    acceptance criterion is about.
    """

    @property
    def quantile(self) -> float:
        """The quantile a fit is taken at -- the false-positive budget, inverted."""
        ...

    def fit(self, scores: Sequence[float]) -> float:
        """The threshold these benign scores imply, before any clamping."""
        ...

    def clamp(
        self, key: str, requested: float, *, previous: float, sample_size: int
    ) -> Calibration:
        """``requested``, limited to what one run is allowed to move."""
        ...


class InMemoryThresholdStore:
    """A :class:`ThresholdStore` in a dictionary, for tests and single-process runs.

    Not durable, and therefore not the store a deployment runs: a restart would
    forget every recalibrated bound and every tenant would silently fall back to
    FR-13's defaults. The adapter over the ``thresholds`` table -- which already
    has the unique index this key needs -- is unwired for the reason D-030 names,
    recorded rather than hidden.
    """

    __slots__ = ("_rows",)

    def __init__(self) -> None:
        """Start empty: no family is invented before feedback exists for it."""
        self._rows: dict[ThresholdKey, ThresholdRecord] = {}

    def rows(self) -> tuple[ThresholdRecord, ...]:
        """Every row in force, in insertion order."""
        return tuple(self._rows.values())

    def get(self, key: ThresholdKey) -> ThresholdRecord | None:
        """The row for one key, or ``None``."""
        return self._rows.get(key)

    def put(self, record: ThresholdRecord) -> None:
        """Insert or replace one row."""
        self._rows[record.key] = record

    def __len__(self) -> int:
        """How many rows are stored."""
        return len(self._rows)


class AlertVerdictFeedback:
    """Labelled scores read from the alert store and the verdict ledger (T-309, T-319).

    The join is the point: a score alone is traffic, a verdict alone has no score,
    and only together are they evidence a threshold can be fitted to. Both halves
    are the real seams -- the query API's own paging, including its stable cursor,
    and the ledger's current verdict per alert -- so the job sees what the API
    would return rather than a store kept in step by hand.

    **The tenant cannot be attributed, and this class says so.** ``alerts`` has no
    tenant column, so a score that came from this deployment's alert store cannot
    be shown to belong to another tenant. Rather than return it and let a
    multi-tenant deployment fit one tenant's threshold on another's traffic, this
    source answers ``()`` for any tenant but the one it was wired with. A real
    multi-tenant deployment needs the column (or a store per tenant); until then
    the failure is a refusal to fit, which is visible, rather than a wrong number,
    which is not.

    Args:
        alerts: where alert rows live.
        ledger: the append-only verdict history.
        tenant_id: the tenant this deployment's alerts belong to.
        page_size: rows per page. Sized for the paging test as much as for the
            query: a page loop that is never exercised is a page loop that does
            not work.
    """

    __slots__ = ("_alerts", "_ledger", "_page_size", "_tenant_id")

    #: A cursor that never advances would otherwise page forever. Named, and
    #: refused, rather than left as a hang in a weekly job.
    MAX_PAGES = 10_000

    def __init__(
        self,
        alerts: AlertStore,
        ledger: VerdictLedger,
        *,
        tenant_id: str = DEFAULT_TENANT_ID,
        page_size: int = MAX_PAGE_SIZE,
    ) -> None:
        """Bind the two stores and the tenant this deployment serves."""
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be in [1, {MAX_PAGE_SIZE}], got {page_size}")
        self._alerts = alerts
        self._ledger = ledger
        self._tenant_id = tenant_id
        self._page_size = page_size

    @property
    def tenant_id(self) -> str:
        """The tenant every score this source returns belongs to."""
        return self._tenant_id

    def labelled_scores(
        self, *, tenant_id: str, since: datetime, until: datetime
    ) -> tuple[LabelledScore, ...]:
        """Labelled scores alerted in ``[since, until)``, oldest first.

        Raises:
            ValueError: if the window is naive or not increasing -- the same rule
                ``app.db.repository.TimeRange`` applies to the SQL path.
            RuntimeError: if the alert store keeps handing back a cursor that does
                not advance, which no honest store does.
        """
        if tenant_id != self._tenant_id:
            return ()
        if since.tzinfo is None or until.tzinfo is None:
            raise ValueError("the window must be timezone-aware on both ends")
        if since >= until:
            raise ValueError(f"the window must increase, got since={since} until={until}")

        found: list[LabelledScore] = []
        cursor: str | None = None
        for _ in range(self.MAX_PAGES):
            query = AlertQuery(
                start=since, end=until, order="asc", limit=self._page_size, cursor=cursor
            )
            page = paginate(self._alerts.fetch(query), query)
            for row in page.items:
                record = self._ledger.current(row.id, row.created_at)
                if record is None or record.at > until:
                    # Unlabelled, or labelled after this run's instant: the first
                    # is not evidence, and the second did not exist yet.
                    continue
                found.append(
                    LabelledScore(
                        alert_id=row.id,
                        family=row.family,
                        score=row.score,
                        verdict=record.verdict,
                        alerted_at=row.created_at,
                        labelled_at=record.at,
                    )
                )
            if page.next_cursor is None:
                return tuple(found)
            cursor = page.next_cursor
        msg = (
            f"the alert store returned {self.MAX_PAGES} pages without reaching the end; "
            "its cursor is not advancing"
        )
        raise RuntimeError(msg)


@dataclass(frozen=True, slots=True)
class RecalibrationService:
    """The job: fit, clamp, persist, and report what it did.

    Frozen and injected end to end -- store, feedback and calibrator -- so the
    route holds no arithmetic and the tests can run the real calibrator against a
    stub store (or the real store against the real one, as the API tests do).

    Attributes:
        store: the values in force.
        feedback: where labelled scores come from.
        calibrator: T-207's fit and guardrail.
        tenant_id: the tenant this deployment serves.
        window: the rolling window, over when each score was alerted.
        minimum_sample: the floor a fit must clear.
    """

    store: ThresholdStore
    feedback: FeedbackSource
    calibrator: Calibrator
    tenant_id: str = DEFAULT_TENANT_ID
    window: timedelta = DEFAULT_WINDOW
    minimum_sample: int = MIN_FEEDBACK

    def __post_init__(self) -> None:
        """Refuse a configuration that cannot run."""
        if not self.tenant_id.strip():
            raise ValueError("a recalibration run must name the tenant it covers")
        if self.window <= timedelta(0):
            raise ValueError(f"window must be positive, got {self.window}")
        if self.minimum_sample < 1:
            raise ValueError(f"minimum_sample must be at least 1, got {self.minimum_sample}")

    def rows(self) -> tuple[ThresholdRecord, ...]:
        """This tenant's rows in force, by family then band. What the GET returns."""
        mine = [row for row in self.store.rows() if row.key.tenant_id == self.tenant_id]
        return tuple(sorted(mine, key=lambda row: (row.key.family, row.key.band)))

    def recalibrate(self, *, band: str, at: datetime) -> RecalibrationReport:
        """Recalibrate one band for every family this tenant has evidence or a row for.

        Args:
            band: which FR-13 band's lower bound to move. ``high`` is the usual
                one: the PRD measures precision and recall at the deployed ``high``
                threshold, so that is the bar a false-positive budget applies to.
            at: the run's instant. Time comes in rather than from the clock so a
                run is reproducible and a boundary case is testable.

        Returns:
            The report: every threshold considered, including the ones left alone
            and why.

        Raises:
            UnfittableBand: if the band has no documented lower bound.
            ValueError: if ``at`` is naive, or the calibrator refuses a sample.
        """
        if band not in BAND_DEFAULTS:
            allowed = ", ".join(sorted(BAND_DEFAULTS))
            raise UnfittableBand(f"band must be one of: {allowed}")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError(f"at must be timezone-aware, got {at}")

        since = at - self.window
        benign: dict[str, list[float]] = {}
        labelled: set[str] = set()
        for score in self.feedback.labelled_scores(tenant_id=self.tenant_id, since=since, until=at):
            labelled.add(score.family)
            if score.verdict in BENIGN_LABELS:
                benign.setdefault(score.family, []).append(score.score)

        stored = {
            row.key: row
            for row in self.store.rows()
            if row.key.tenant_id == self.tenant_id and row.key.band == band
        }
        # The union, not the intersection. A family with a row but no feedback is
        # reported as refused rather than dropped; one with enough feedback but no
        # row starts from FR-13's default; and one whose labels were all
        # `true_positive` still appears, refused, so a run says "I saw this family
        # and could not use it" instead of silently leaving it out of the report.
        families = sorted({key.family for key in stored} | labelled)

        outcomes: list[ThresholdOutcome] = []
        pending: list[ThresholdRecord] = []
        for family in families:
            key = ThresholdKey(self.tenant_id, family, band)
            existing = stored.get(key)
            previous = existing.value if existing is not None else BAND_DEFAULTS[band]
            sample = benign.get(family, [])
            if len(sample) < self.minimum_sample:
                outcomes.append(
                    ThresholdOutcome(
                        key=key,
                        previous=previous,
                        previous_was_default=existing is None,
                        requested=None,
                        applied=previous,
                        changed=False,
                        clamped=False,
                        sample_size=len(sample),
                        reason=OutcomeReason.insufficient_feedback,
                    )
                )
                continue
            change = self.calibrator.clamp(
                str(key),
                self.calibrator.fit(sample),
                previous=previous,
                sample_size=len(sample),
            )
            changed = abs(change.applied - previous) > 1e-12
            if changed:
                pending.append(
                    ThresholdRecord(
                        key=key,
                        value=change.applied,
                        source=RECALIBRATED_SOURCE,
                        updated_at=at,
                    )
                )
            outcomes.append(
                ThresholdOutcome(
                    key=key,
                    previous=previous,
                    previous_was_default=existing is None,
                    requested=change.requested,
                    applied=change.applied,
                    changed=changed,
                    clamped=change.clamped,
                    sample_size=change.sample_size,
                    reason=OutcomeReason.fitted,
                )
            )

        # Every fit has succeeded by now, so a sample the calibrator refuses
        # leaves the store exactly as it was instead of half-updated.
        for record in pending:
            self.store.put(record)

        return RecalibrationReport(
            tenant_id=self.tenant_id,
            band=band,
            at=at,
            since=since,
            until=at,
            quantile=self.calibrator.quantile,
            minimum_sample=self.minimum_sample,
            outcomes=tuple(outcomes),
        )
