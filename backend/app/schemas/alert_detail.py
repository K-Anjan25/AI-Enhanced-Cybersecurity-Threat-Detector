"""Response schemas for the alert-detail read model (T-404, FR-51).

One request fills the four zones design.md §4.3 draws, because the triage screen
is the place where a second round trip is most expensive: an analyst opens an
alert, and every panel on it must already have something true to say.

Three payloads here are *interpretations* of stored JSONB rather than a direct
projection of a column, and each one has a rule attached:

* ``ExplanationOut`` is R-70's contract — either reasons, or the explicit
  ``unavailable`` marker with the reason it is missing. Never an empty list
  presented as an explanation, and never a reason synthesised from something else.
* ``EvidenceOut`` is the pointer trail from ``window_ref``, each occurrence
  carrying the instant its raw record expires past FR-05's retention window, so
  §4.3's "evidence expired at <date>" is a fact about the data rather than a guess
  the client makes from a policy it cannot read.
* ``FamilyHistoryOut`` is the trust hint: "analyst marked this FP twice in 30 d".
  It counts *prior* alerts on the same entity and family, which is the only form
  of the claim that can be true — a window that included the alert being viewed
  would claim the analyst had judged a verdict that does not exist yet.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.query import AlertRow
from app.schemas.verdict import VerdictRecordOut

__all__ = [
    "AlertDetailOut",
    "AlertModelsOut",
    "AlertVerdictOut",
    "EvidenceOccurrenceOut",
    "EvidenceOut",
    "ExplanationOut",
    "FamilyHistoryOut",
    "RelatedAlertsOut",
]


class AlertModelsOut(BaseModel):
    """The model versions that scored this alert, when the row recorded them.

    Both are optional because a single-modality case records one and a case whose
    scoring predates model pinning records neither; ``None`` is an honest gap and
    the screen says so rather than inventing a version.
    """

    flow: str | None = Field(
        default=None, description="Pinned flow-model version, e.g. flownet@1.4.2."
    )
    log: str | None = Field(default=None, description="Pinned log-model version.")


class ExplanationOut(BaseModel):
    """R-70's explanation contract, as the alert row stored it.

    Exactly one of ``reasons`` and ``unavailable`` carries the answer: when
    ``unavailable`` is true the alert was raised anyway and ``detail`` says why the
    explanation is missing. ``partial_evidence`` and ``unavailable_modalities``
    describe a case that has *some* reasons and is missing a modality — §8.1's
    "partial evidence — log model unavailable", which must be labelled rather than
    presented as complete.
    """

    reasons: list[str] = Field(
        default_factory=list, description="Rendered reasons, most contributory first."
    )
    unavailable: bool = Field(
        default=False, description="True when no explanation could be produced (R-70)."
    )
    detail: str | None = Field(
        default=None, description="Why it is unavailable. Never a stack trace (R-58)."
    )
    unavailable_modalities: list[str] = Field(
        default_factory=list, description="Modalities that contributed without reasons."
    )
    partial_evidence: bool = Field(
        default=False, description="True while only one modality has contributed."
    )
    families: list[str] = Field(
        default_factory=list, description="Every family the case's occurrences named."
    )


class EvidenceOccurrenceOut(BaseModel):
    """One window in the evidence trail behind an alert."""

    id: str = Field(description="The window's stable identity, as T-307 emitted it.")
    modality: str = Field(description="Which model scored the window: flow or log.")
    score: float = Field(description="That model's score for the window, in [0, 1].")
    at: datetime = Field(description="When the window closed, timezone-aware UTC.")
    model: str | None = Field(default=None, description="The version that scored it.")
    expires_at: datetime = Field(
        description="When FR-05's raw-record window takes this evidence away."
    )
    expired: bool = Field(description="True once the raw records behind it are gone.")


class EvidenceOut(BaseModel):
    """design.md §4.3's zone 3: the raw records behind the alert.

    The trail is pointers, not rows: raw flows and log lines live in the stream
    store, and what an alert keeps is the bounded list of windows that produced it.
    ``expired`` is true only when *every* occurrence is past retention — a case
    with some evidence left is partial, not expired, and says which it is.
    """

    window_id: str | None = Field(
        default=None, description="The window the case opened on, when recorded."
    )
    trace_id: str | None = Field(
        default=None, description="Trace of the ingest request that opened the case (T-317)."
    )
    grouped: bool = Field(
        default=False,
        description="True when the correlator fused several detections into one case.",
    )
    occurrences: list[EvidenceOccurrenceOut] = Field(default_factory=list)
    retention_days: int = Field(
        description="FR-05's raw-record window the expiry dates above are computed from."
    )
    expired: bool = Field(
        default=False, description="True when every occurrence is past retention."
    )
    unreadable: int = Field(
        default=0,
        description="Trail entries that could not be decoded, reported rather than dropped.",
    )
    note: str | None = Field(
        default=None, description="Why the trail is incomplete, in the operator's words."
    )


class RelatedAlertsOut(BaseModel):
    """Other alerts on the same entity around this one, for §4.3's "Related alerts"."""

    window_minutes: int = Field(description="Half-width of the window searched, in minutes.")
    items: list[AlertRow] = Field(default_factory=list)
    truncated: bool = Field(
        default=False, description="True when more related alerts exist than were returned."
    )


class FamilyHistoryOut(BaseModel):
    """The trust hint: what analysts decided about this entity and family before.

    ``prior_alerts`` counts alerts *before* the one being viewed, so the numbers
    are stable on re-read and cannot include the verdict the analyst is about to
    write. ``labelled`` is what makes the counts readable: two false positives out
    of three reviewed alerts is a different claim from two out of two hundred.
    """

    family: str
    window_days: int = Field(description="How far back the counts reach.")
    prior_alerts: int = Field(
        default=0, description="Alerts on this entity and family before this one."
    )
    labelled: int = Field(default=0, description="How many of them carry a verdict at all.")
    false_positive: int = 0
    benign: int = 0
    true_positive: int = 0


class AlertVerdictOut(BaseModel):
    """The alert's verdict history, oldest first, and the current one."""

    current: VerdictRecordOut | None = None
    history: list[VerdictRecordOut] = Field(default_factory=list)


class AlertDetailOut(BaseModel):
    """Everything design.md §4.3's four zones render, in one response."""

    alert: AlertRow
    models: AlertModelsOut = Field(default_factory=AlertModelsOut)
    explanation: ExplanationOut
    evidence: EvidenceOut
    verdict: AlertVerdictOut = Field(default_factory=AlertVerdictOut)
    related: RelatedAlertsOut
    family_history: FamilyHistoryOut
