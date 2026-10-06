"""Correlation: one alert per incident, with both modalities where they exist (T-308).

The correlator is where scored windows become alerts. Four behaviours live here,
and each one is written the hard way for a reason worth stating.

**Banding is a boundary, not a range (FR-13).** ``critical`` is `>= 0.90`, not
`> 0.90`: a score that lands exactly on a published threshold must land in the
band that threshold names, or the numbers move when a model happens to be
accurate. A score outside ``[0, 1]`` is refused rather than clamped, for the
reason the fusion rule refuses one — clamping makes a broken model and a
confident one indistinguishable. The thresholds themselves are data: the values
below are the PRD defaults, and R-69 puts the shipped values in the `thresholds`
table, so a deployment can move them per tenant and family without a code change.

**The cool-down counts occurrences instead of suppressing them (FR-15).** A
repeat for the same `(entity, family)` inside the cool-down does not vanish — it
increments ``occurrence_count`` and moves ``last_seen``. Dropping the repeat
would lose the fact that behaviour is *continuing*, which is the difference
between a scanner that probed once and a scanner that is still probing.

**The case never de-escalates, and its score is the composite (FR-12).** Every
occurrence is re-fused from the best score per modality, and the case keeps the
highest composite it has seen. Two reasons. Fixed feedback matters: an alert
that reads HIGH and later reads MEDIUM while nothing changed for the better
teaches an analyst to distrust the label. And the highest evidence in an
incident is exactly what a triager must see; averaging it down with quieter
repeats is how a real intrusion gets triaged as noise.

**Grouping is not the same rule as deduplication (FR-19).** Dedup keys on
`(entity, family)`; grouping keys on the *entity and the opposite modality*
within ±60 s, because the flow and log models see the same incident from two
sides and neither one alone is the whole picture. A grouped case clears
``partial_evidence``, since the case now genuinely has both sides — which is
also why a grouped case scores higher than either penalised single-modality
score.

**Replay safety.** The worker that produces detections is at-least-once (T-307,
D-036), so the same window can arrive twice. Every detection carries the
identity of the window it came from, and a detection whose evidence is already
recorded is a no-op: the case is returned unchanged. Without this, a worker
restart would double every count it replayed.

**What is not here.** The persistence adapter. :class:`CaseStore` is a protocol
and :class:`InMemoryCaseStore` is the test and single-process implementation; a
SQLAlchemy adapter would need a queryable evidence index (the `alerts` table
holds one `window_ref` pointer per row, which cannot answer "was this window
already counted?") and there is no PostgreSQL in this environment to verify one
against. :func:`alert_row` pins the row encoding so that adapter is a thin
insert rather than a design question.
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from app.db.models import AlertStatus, Severity
from app.observability import metrics
from app.observability.tracing import span, trace_id_from_traceparent

__all__ = [
    "DEFAULT_COOL_DOWN",
    "DEFAULT_GROUP_WINDOW",
    "DEFAULT_EVIDENCE_RETENTION",
    "MAX_REASONS_PER_MODALITY",
    "Action",
    "AlertCase",
    "CaseStore",
    "Correlator",
    "CorrelatorConfig",
    "Detection",
    "Explanation",
    "FusedScoreLike",
    "FusionRule",
    "InMemoryCaseStore",
    "Modality",
    "Outcome",
    "Severity",
    "SeverityBands",
    "alert_row",
    "severity_for",
]

#: FR-15's cool-down. Configurable, and the value here is the documented default.
DEFAULT_COOL_DOWN = timedelta(minutes=15)

#: FR-19's fusion window, symmetric around the entity's latest evidence.
DEFAULT_GROUP_WINDOW = timedelta(seconds=60)

#: How many recent occurrences a case keeps for display. The count itself is
#: exact; this bounds memory, because a sustained flood inside one cool-down is
#: one case that would otherwise grow without limit -- which is a denial of
#: service dressed up as an audit trail.
DEFAULT_EVIDENCE_RETENTION = 20

#: FR-14 asks for the top-3 contributing signals, per modality that contributed.
MAX_REASONS_PER_MODALITY = 3


class Modality(enum.StrEnum):
    """Which model produced a detection."""

    flow = "flow"
    log = "log"


@dataclass(frozen=True, slots=True)
class SeverityBands:
    """Lower bounds for the FR-13 bands, as data rather than as literals.

    Attributes:
        critical: score at or above which the band is ``critical``.
        high: band lower bound for ``high``.
        medium: band lower bound for ``medium``.
        low: band lower bound for ``low``. Below it the band is ``info``.

    The defaults are the PRD's documented initial values (R-69). Validation
    happens on construction so a misplaced band cannot be validated at ingest
    time, hours later, on one unlucky alert.
    """

    critical: float = 0.90
    high: float = 0.75
    medium: float = 0.55
    low: float = 0.35

    def __post_init__(self) -> None:
        """Refuse bounds that are out of range or not strictly descending."""
        ordered = (("critical", self.critical), ("high", self.high), ("medium", self.medium))
        for name, value in (*ordered, ("low", self.low)):
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} band must be in (0, 1), got {value}")
        values = [value for _, value in ordered] + [self.low]
        if any(a <= b for a, b in zip(values[:-1], values[1:], strict=True)):
            raise ValueError(
                f"bands must be strictly descending, got critical={self.critical}, "
                f"high={self.high}, medium={self.medium}, low={self.low}"
            )

    def ordered(self) -> tuple[tuple[float, Severity], ...]:
        """The bounds worst-first, which is the order :func:`severity_for` wants."""
        return (
            (self.critical, Severity.critical),
            (self.high, Severity.high),
            (self.medium, Severity.medium),
            (self.low, Severity.low),
        )


def severity_for(score: float, bands: SeverityBands | None = None) -> Severity:
    """Map a composite score to its band (FR-13).

    Args:
        score: the fused score, which must lie in ``[0, 1]``.
        bands: the bounds to apply; the PRD defaults when omitted.

    Returns:
        The band whose lower bound the score has reached, or ``info``.

    Raises:
        ValueError: if the score is outside ``[0, 1]``. Refused, not clamped: a
            score of 1.7 and a score of 1.0 would otherwise become the same
            alert, and the first one is a defect worth seeing.
    """
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score must be in [0, 1], got {score}")
    active = bands or SeverityBands()
    for lower_bound, band in active.ordered():
        if score >= lower_bound:
            return band
    return Severity.info


@dataclass(frozen=True, slots=True)
class Explanation:
    """Human-readable reasons behind one detection, as the scorer rendered them.

    Attributes:
        reasons: plain-language reasons, most contributory first. The correlator
            takes them in the order given; ranking happened where the model is.
        unavailable: set when explanation generation failed upstream (R-70).
        detail: why it was unavailable, for the log and the alert payload.
    """

    reasons: tuple[str, ...] = ()
    unavailable: bool = False
    detail: str | None = None

    @classmethod
    def unavailable_explanation(cls, detail: str) -> Explanation:
        """Build the R-70 marker, never an empty list of reasons."""
        return cls(reasons=(), unavailable=True, detail=detail)


@dataclass(frozen=True, slots=True)
class Detection:
    """One model's verdict on one closed window.

    A detection is single-modality by construction: the flow model scores a flow
    window and the log model scores a log window, and the composite is the
    correlator's job (FR-12) rather than a number this object may already carry.
    That is what lets a grouped case be re-fused from both sides without any
    party having to reconstruct the other one's input.

    Attributes:
        entity_id: the entity the window belongs to.
        family: the threat family the model attributed the window to.
        modality: which model produced the score.
        score: this model's score in ``[0, 1]``, unpenalised.
        at: when the window closed, timezone-aware UTC.
        evidence_id: the window's stable identity, as emitted by T-307. This is
            the replay key: the same window scored twice carries the same id.
        model_id: the pinned model version that scored it, for the alert row.
        explanation: the rendered reasons, or ``None`` when none were supplied.
        traceparent: the W3C trace context of the ingest request the window came
            from, when the pipeline carried one (T-317). Deliberately not part of
            the evidence identity: identity is what makes a replay idempotent,
            and telemetry must never be able to change it.
    """

    entity_id: int
    family: str
    modality: Modality
    score: float
    at: datetime
    evidence_id: str
    model_id: str | None = None
    explanation: Explanation | None = None
    traceparent: str | None = None

    def __post_init__(self) -> None:
        """Refuse a detection that cannot be correlated unambiguously."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be in [0, 1], got {self.score}")
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError(
                "detection timestamps must be timezone-aware; a naive timestamp is "
                "interpreted in the process timezone, which moves every window boundary"
            )
        if not self.family.strip():
            raise ValueError("a detection must name a threat family")
        if not self.evidence_id.strip():
            raise ValueError(
                "a detection must carry the identity of the window it came from; "
                "without it, a replayed window silently doubles an occurrence count"
            )


class FusedScoreLike(Protocol):
    """The part of a fusion result the correlator uses.

    A protocol, so the real rule in ``aegis_ml.scoring.fusion`` satisfies it
    structurally without the backend importing the ML package: the composition
    root injects the rule and the backend image stays free of it.
    """

    score: float
    partial_evidence: bool


class FusionRule(Protocol):
    """Late fusion of the two modality scores (FR-12)."""

    def __call__(self, flow_score: float | None, log_score: float | None, /) -> FusedScoreLike:
        """Combine the best score per modality, penalising a missing one."""
        ...


@dataclass(frozen=True, slots=True)
class CorrelatorConfig:
    """The correlator's policy knobs.

    Attributes:
        cool_down: how long a repeat for the same `(entity, family)` is counted
            as an occurrence of the existing alert rather than a new one.
        group_window: how far apart a flow detection and a log detection for one
            entity may be and still be grouped (FR-19, ±60 s).
        bands: severity bounds (FR-13).
        evidence_retention: how many recent occurrences a case keeps.
    """

    cool_down: timedelta = DEFAULT_COOL_DOWN
    group_window: timedelta = DEFAULT_GROUP_WINDOW
    bands: SeverityBands = SeverityBands()
    evidence_retention: int = DEFAULT_EVIDENCE_RETENTION

    def __post_init__(self) -> None:
        """Refuse policy that cannot describe a window."""
        if self.cool_down <= timedelta(0):
            raise ValueError(f"cool_down must be positive, got {self.cool_down}")
        if self.group_window <= timedelta(0):
            raise ValueError(f"group_window must be positive, got {self.group_window}")
        if self.evidence_retention < 1:
            raise ValueError(
                f"evidence_retention must be at least 1, got {self.evidence_retention}"
            )


@dataclass(slots=True)
class AlertCase:
    """A correlated incident: one row in `alerts`, several detections behind it.

    Instances are treated as immutable: the correlator builds a new one with
    :func:`dataclasses.replace` on every change, so a snapshot handed to a caller
    never changes underneath them. The store keeps the latest instance per id.

    Attributes:
        id: stable, derived from the entity, the family and the first evidence --
            data, not process state (D-036), so a replay recomputes the same id.
        entity_id: the entity every occurrence belongs to.
        family: the family the case is labelled with -- the first one seen, kept
            stable for the case's life, because the label is what the cool-down
            key and the analyst's filter both refer to.
        families: every family grouped into the case, since a 60 s correlation
            can join a scan and a brute-force run into one incident.
        severity: the highest band any composite for this case has reached.
        score: the highest composite, matching ``severity``.
        first_severity: the band of the first occurrence, so escalation is visible.
        first_score: the composite of the first occurrence.
        status: alert lifecycle; a closed case absorbs nothing further.
        first_seen: the earliest occurrence.
        last_seen: the latest occurrence.
        occurrence_count: exact, including occurrences no longer retained.
        partial_evidence: True while only one modality has contributed.
        grouped: True once a second modality joined the case (FR-19).
        first_evidence_id: the window the case was opened by, kept even after the
            occurrence is evicted from the retained list.
        occurrences: the most recent detections, oldest first, bounded.
        traceparent: the trace context of the first occurrence that carried one,
            kept for the case's life: the question a trace answers is "which
            ingest request opened this alert", and later occurrences of a
            long-running incident are the same incident, not a new question.
    """

    id: str
    entity_id: int
    family: str
    families: tuple[str, ...]
    severity: Severity
    score: float
    first_severity: Severity
    first_score: float
    status: AlertStatus
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int
    partial_evidence: bool
    grouped: bool
    first_evidence_id: str
    occurrences: tuple[Detection, ...]
    traceparent: str | None = None

    @property
    def trace_id(self) -> str | None:
        """The trace id of this case, in the 32-hex form the alert record holds."""
        return trace_id_from_traceparent(self.traceparent)

    def evidence_ids(self) -> tuple[str, ...]:
        """Window identities currently retained, for replay checks in tests."""
        return tuple(occurrence.evidence_id for occurrence in self.occurrences)

    def best_by_modality(self) -> dict[Modality, Detection]:
        """The highest-scoring retained occurrence of each modality."""
        best: dict[Modality, Detection] = {}
        for occurrence in self.occurrences:
            current = best.get(occurrence.modality)
            if current is None or occurrence.score > current.score:
                best[occurrence.modality] = occurrence
        return best

    def _reasons_for(self, modality: Modality) -> tuple[str, ...]:
        """The top reasons from the best occurrence of one modality."""
        candidates = [
            occurrence
            for occurrence in self.occurrences
            if occurrence.modality is modality and _reasons(occurrence.explanation)
        ]
        if not candidates:
            return ()
        best = max(candidates, key=lambda occurrence: occurrence.score)
        return _reasons(best.explanation)[:MAX_REASONS_PER_MODALITY]

    def explanation_payload(self) -> dict[str, object]:
        """R-70's payload: reasons, or the explicit unavailable marker.

        Never both, and never an empty reason list presented as an explanation.
        An occurrence whose scorer produced no reasons is recorded under
        ``unavailable_modalities`` rather than silently dropped, because a
        missing log explanation and a log window with nothing unusual in it must
        not render the same way.
        """
        reasons: list[str] = []
        unavailable_modalities: list[str] = []
        details: list[str] = []
        for modality in (Modality.flow, Modality.log):
            modality_reasons = self._reasons_for(modality)
            if modality_reasons:
                reasons.extend(modality_reasons)
                continue
            contributed = [
                occurrence for occurrence in self.occurrences if occurrence.modality is modality
            ]
            if not contributed:
                continue
            unavailable_modalities.append(modality.value)
            details.extend(
                occurrence.explanation.detail
                for occurrence in contributed
                if occurrence.explanation is not None and occurrence.explanation.detail
            )
        common: dict[str, object] = {
            "families": list(self.families),
            "partial_evidence": self.partial_evidence,
            "occurrence_count": self.occurrence_count,
        }
        if not reasons:
            return {
                **common,
                "explanation_unavailable": True,
                "detail": (
                    details[0]
                    if details
                    else "no occurrence carried an explanation; the alert is raised anyway (R-70)"
                ),
            }
        payload: dict[str, object] = {**common, "reasons": reasons}
        if unavailable_modalities:
            payload["unavailable_modalities"] = unavailable_modalities
        return payload


def _reasons(explanation: Explanation | None) -> tuple[str, ...]:
    """Reasons from an explanation, treating a blank one as no explanation."""
    if explanation is None or explanation.unavailable:
        return ()
    return tuple(reason for reason in explanation.reasons if reason.strip())


class CaseStore(Protocol):
    """Where cases live between detections.

    Deliberately small. The correlator decides policy; the store answers
    questions and persists results, so swapping in a database does not mean
    re-deriving the policy from SQL.
    """

    def case_with_evidence(self, entity_id: int, evidence_id: str) -> AlertCase | None:
        """The case that already accounted for a window, if any.

        This is the replay check, and it must outlive the occurrence list: a
        window evicted from display retention was still counted, and counting it
        again on replay is the defect this method exists to prevent.
        """
        ...

    def latest_for_entity(self, entity_id: int, *, not_before: datetime) -> AlertCase | None:
        """The most recently active case for an entity, for FR-19 grouping."""
        ...

    def latest_for(
        self, entity_id: int, families: Collection[str], *, not_before: datetime
    ) -> AlertCase | None:
        """The most recently active case for an entity carrying any of the families."""
        ...

    def save(self, case: AlertCase) -> None:
        """Store the current state of a case, replacing any earlier state of it."""
        ...


class InMemoryCaseStore:
    """A :class:`CaseStore` in dictionaries, for tests and single-process runs.

    The evidence index is deliberately **never pruned**: it is the record that a
    window has been counted, and a persistent store must keep an equivalent for
    at least as long as evidence can be replayed. What *is* bounded is the
    occurrence list a case retains for display, which is a memory guard rather
    than a policy (see :data:`DEFAULT_EVIDENCE_RETENTION`).
    """

    __slots__ = ("_by_entity", "_cases", "_evidence")

    def __init__(self) -> None:
        """Start empty."""
        self._cases: dict[str, AlertCase] = {}
        self._evidence: dict[tuple[int, str], str] = {}
        self._by_entity: dict[int, list[str]] = {}

    def case_with_evidence(self, entity_id: int, evidence_id: str) -> AlertCase | None:
        """The case that already counted this window, if one did."""
        case_id = self._evidence.get((entity_id, evidence_id))
        return self._cases.get(case_id) if case_id is not None else None

    def latest_for_entity(self, entity_id: int, *, not_before: datetime) -> AlertCase | None:
        """The most recently active case for an entity, or ``None``."""
        return self._latest(self._by_entity.get(entity_id, ()), not_before, None)

    def latest_for(
        self, entity_id: int, families: Collection[str], *, not_before: datetime
    ) -> AlertCase | None:
        """The most recently active case carrying any of the families, or ``None``."""
        return self._latest(self._by_entity.get(entity_id, ()), not_before, set(families))

    def _latest(
        self, case_ids: Sequence[str], not_before: datetime, families: set[str] | None
    ) -> AlertCase | None:
        """Newest case whose last activity is inside the window and family filter."""
        candidates = [
            self._cases[case_id]
            for case_id in case_ids
            if self._cases[case_id].last_seen >= not_before
            and (families is None or families.intersection(self._cases[case_id].families))
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda case: case.last_seen)

    def save(self, case: AlertCase) -> None:
        """Store the case and index every window identity it has ever carried."""
        if case.id not in self._cases:
            self._by_entity.setdefault(case.entity_id, []).append(case.id)
        self._cases[case.id] = case
        for occurrence in case.occurrences:
            self._evidence[(case.entity_id, occurrence.evidence_id)] = case.id

    def cases(self) -> tuple[AlertCase, ...]:
        """Every stored case, oldest first -- for assertions and diagnostics."""
        return tuple(self._cases.values())

    def __len__(self) -> int:
        """How many cases are stored."""
        return len(self._cases)


class Action(enum.StrEnum):
    """What ingesting one detection did."""

    created = "created"
    absorbed = "absorbed"
    grouped = "grouped"
    duplicate = "duplicate"


@dataclass(frozen=True, slots=True)
class Outcome:
    """The result of ingesting one detection."""

    action: Action
    case: AlertCase


class Correlator:
    """Turns detections into cases, one incident at a time."""

    __slots__ = ("_config", "_fuse", "_store")

    def __init__(
        self,
        store: CaseStore,
        fuse: FusionRule,
        *,
        config: CorrelatorConfig | None = None,
    ) -> None:
        """Wire the store and the fusion rule.

        ``fuse`` is injected rather than imported: the real rule lives in
        ``aegis_ml.scoring.fusion``, and the backend image does not install the
        ML package. Passing the rule keeps one implementation of the arithmetic
        (the alternative -- a second copy here -- would drift, which is the
        defect T-307 already avoided for windowing).
        """
        self._store = store
        self._fuse = fuse
        self._config = config or CorrelatorConfig()

    @property
    def config(self) -> CorrelatorConfig:
        """The active policy, so callers do not re-declare the defaults."""
        return self._config

    def ingest(self, detection: Detection) -> Outcome:
        """Fold one detection into the case landscape, on the detector's trace.

        The span is a child of the ingest request the window came from, so the
        correlation stage appears on the same trace as the request that fed it
        (NFR-07, T-317).

        Returns:
            The action taken and the case afterwards: ``duplicate`` when the
            window was already counted, ``grouped`` when it joined an
            opposite-modality case (FR-19), ``absorbed`` when it was a repeat
            inside the cool-down (FR-15), ``created`` otherwise.
        """
        with span(
            "correlate detection",
            parent_traceparent=detection.traceparent,
            attributes={
                "aegis.entity.id": detection.entity_id,
                "aegis.family": detection.family,
                "aegis.modality": detection.modality.value,
            },
        ) as active:
            outcome = self._correlate(detection)
            active.set_attribute("aegis.correlator.action", outcome.action.value)
        if outcome.action is Action.created:
            # Created, not absorbed: FR-15's repeat increments a count, and
            # "alerts created" must not be read as "detections seen".
            metrics.observe_alert_created(outcome.case.severity.value)
        return outcome

    def _correlate(self, detection: Detection) -> Outcome:
        """The four-way decision, uninstrumented so the span wraps all of it."""
        replayed = self._store.case_with_evidence(detection.entity_id, detection.evidence_id)
        if replayed is not None:
            return Outcome(action=Action.duplicate, case=replayed)

        groupable = self._grouping_candidate(detection)
        if groupable is not None:
            merged = self._merge(groupable, detection, grouped=True)
            self._store.save(merged)
            return Outcome(action=Action.grouped, case=merged)

        repeat = self._repeat_candidate(detection)
        if repeat is not None:
            merged = self._merge(repeat, detection, grouped=False)
            self._store.save(merged)
            return Outcome(action=Action.absorbed, case=merged)

        created = self._create(detection)
        self._store.save(created)
        return Outcome(action=Action.created, case=created)

    def _grouping_candidate(self, detection: Detection) -> AlertCase | None:
        """A case for this entity that wants this detection's modality (FR-19).

        The window is symmetric -- ``abs`` of the gap -- because a detection can
        arrive after the case it belongs to or before it, depending on which
        model finished first, and both orders describe one incident.
        """
        candidate = self._store.latest_for_entity(
            detection.entity_id, not_before=detection.at - self._config.group_window
        )
        if candidate is None or candidate.status is AlertStatus.closed:
            return None
        gap = abs(detection.at - candidate.last_seen)
        if gap > self._config.group_window:
            return None
        seen = {occurrence.modality for occurrence in candidate.occurrences}
        if detection.modality in seen:
            return None
        return candidate

    def _repeat_candidate(self, detection: Detection) -> AlertCase | None:
        """The case this detection is a repeat of, if it is inside the cool-down (FR-15).

        A closed case is never a repeat target. The analyst decided that
        incident was over, and swallowing a fresh occurrence into a closed row
        leaves nobody looking at it -- the recurrence is a new alert on purpose.
        """
        candidate = self._store.latest_for(
            detection.entity_id,
            (detection.family,),
            not_before=detection.at - self._config.cool_down,
        )
        if candidate is None or candidate.status is AlertStatus.closed:
            return None
        return candidate

    def _fuse_best(self, occurrences: Sequence[Detection]) -> FusedScoreLike:
        """Fuse the best score per modality across a set of detections."""
        best: dict[Modality, float] = {}
        for occurrence in occurrences:
            current = best.get(occurrence.modality)
            if current is None or occurrence.score > current:
                best[occurrence.modality] = occurrence.score
        return self._fuse(best.get(Modality.flow), best.get(Modality.log))

    def _create(self, detection: Detection) -> AlertCase:
        """Open a case from the first detection of an incident."""
        fused = self._fuse_best((detection,))
        severity = severity_for(fused.score, self._config.bands)
        return AlertCase(
            id=f"{detection.entity_id}:{detection.family}:{detection.evidence_id}",
            entity_id=detection.entity_id,
            family=detection.family,
            families=(detection.family,),
            severity=severity,
            score=fused.score,
            first_severity=severity,
            first_score=fused.score,
            status=AlertStatus.open,
            first_seen=detection.at,
            last_seen=detection.at,
            occurrence_count=1,
            partial_evidence=fused.partial_evidence,
            grouped=False,
            first_evidence_id=detection.evidence_id,
            occurrences=(detection,),
            traceparent=detection.traceparent,
        )

    def _merge(self, case: AlertCase, detection: Detection, *, grouped: bool) -> AlertCase:
        """Add one detection to a case: count it, re-fuse it, never de-escalate.

        The family label stays as the case was opened, because the cool-down key
        and the analyst's filters both refer to it, while ``families`` grows.
        Retaining the newest occurrences and counting all of them keeps the
        count exact without letting a flood grow memory without bound.
        """
        families = (
            case.families
            if detection.family in case.families
            else (*case.families, detection.family)
        )
        occurrences = (*case.occurrences, detection)[-self._config.evidence_retention :]
        fused = self._fuse_best(occurrences)
        score = max(case.score, fused.score)
        return replace(
            case,
            families=families,
            severity=severity_for(score, self._config.bands),
            score=score,
            first_seen=min(case.first_seen, detection.at),
            last_seen=max(case.last_seen, detection.at),
            occurrence_count=case.occurrence_count + 1,
            partial_evidence=fused.partial_evidence,
            grouped=case.grouped or grouped,
            occurrences=occurrences,
            # Adopted if the case was opened by an untraced detection: a trace id
            # that arrives late is still the id of this incident.
            traceparent=case.traceparent or detection.traceparent,
        )


def alert_row(case: AlertCase) -> dict[str, object]:
    """The `alerts` column values for a case, ready for one INSERT.

    Kept free of SQLAlchemy so the encoding is testable here and the adapter is
    mechanical later. ``window_ref`` keeps its documented ``store``/``id``
    pointer to the window the case opened on and adds the bounded evidence trail
    under ``evidence``; the field is specified as opaque, and the trail is what
    the alert-detail screen renders under "related raw records".

    Returns:
        A mapping of column name to value for every writable column of
        ``alerts`` except the database-assigned ones.
    """
    best = case.best_by_modality()
    window_ref: dict[str, object] = {
        "store": "stream",
        "id": case.first_evidence_id,
        # The trace of the ingest request that opened the case, under the key the
        # query API reads back. Optional by construction: a detection that never
        # had a trace context yields None, never an invented id.
        "trace_id": case.trace_id,
        "grouped": case.grouped,
        "evidence": [
            {
                "id": occurrence.evidence_id,
                "modality": occurrence.modality.value,
                "score": occurrence.score,
                "at": occurrence.at.isoformat(),
                "model": occurrence.model_id,
            }
            for occurrence in case.occurrences
        ],
    }
    return {
        "entity_id": case.entity_id,
        "family": case.family,
        "severity": case.severity.value,
        "score": case.score,
        "model_flow_id": best[Modality.flow].model_id if Modality.flow in best else None,
        "model_log_id": best[Modality.log].model_id if Modality.log in best else None,
        "window_ref": window_ref,
        "explanation": case.explanation_payload(),
        "status": case.status.value,
        "first_seen": case.first_seen,
        "last_seen": case.last_seen,
        "occurrence_count": case.occurrence_count,
    }
