"""Assemble the alert-detail read model from what the pipeline already stored (T-404).

Pure functions over rows and a policy, so every rule below is testable without an
HTTP server and without a database (R-15). The route stays thin (R-13): it looks
the row up, asks the store for the two bounded windows the context needs, and
hands the result here.

The rules that matter, and why they are here rather than in the renderer:

* **A missing explanation is ``unavailable``, never empty.** R-70 says an alert is
  raised with an explanation or with the explicit marker, and this decodes both.
  A row whose payload is blank or unrecognisable becomes the marker *with a
  reason naming what was found*, because a blank explanation panel and "the model
  service returned no reasons" must not render the same way.
* **Evidence expiry is computed from the policy, not guessed.** Each occurrence
  carries the instant FR-05's raw-record window takes it away, derived from the
  retention policy the deployment actually runs.
* **The family hint counts prior alerts only.** "Marked FP twice in 30 d" is a
  claim about decisions already made; including the alert on screen would let the
  hint quote a verdict that does not exist yet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from app.db.models import Alert
from app.schemas.alert_detail import (
    AlertDetailOut,
    AlertModelsOut,
    AlertVerdictOut,
    EvidenceOccurrenceOut,
    EvidenceOut,
    ExplanationOut,
    FamilyHistoryOut,
    RelatedAlertsOut,
)
from app.schemas.verdict import VerdictRecordOut
from app.services.query_service import alert_row_of
from app.services.retention import RetentionPolicy
from app.services.verdict_service import VerdictLedger, VerdictRecord

__all__ = [
    "FAMILY_HISTORY_DAYS",
    "RELATED_WINDOW_MINUTES",
    "RELATED_LIMIT",
    "decode_evidence",
    "decode_explanation",
    "detail_of",
    "family_history",
    "related_window",
]

#: How far either side of an alert the "related alerts" search reaches.
RELATED_WINDOW_MINUTES = 60

#: How many related alerts the panel is given before it says it is truncated.
RELATED_LIMIT = 20

#: How far back the family hint counts. §4.3's example says "twice in 30 d".
FAMILY_HISTORY_DAYS = 30


def _text(value: object) -> str | None:
    """A non-empty string, or ``None`` for anything else."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _text_list(value: object) -> list[str]:
    """Every non-empty string in a JSON array, in order.

    A string is not an array of characters, and JSON has no tuples: the check is
    on ``Sequence`` minus ``str``/``bytes`` so that a payload carrying a bare
    string where a list belongs decodes as an empty list rather than as a dozen
    single-character reasons.
    """
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [text for text in (_text(item) for item in value) if text is not None]


def decode_explanation(payload: Mapping[str, Any] | None) -> ExplanationOut:
    """Turn the stored explanation JSONB into R-70's contract.

    Handles three shapes, because all three exist in a running system: reasons,
    the explicit unavailable marker, and a row written before this shape existed
    (empty, or carrying only the correlator's descriptive keys). The third becomes
    the marker rather than an empty success — a panel with no reasons and no
    explanation is exactly the state R-70 forbids presenting as an answer.
    """
    if not isinstance(payload, Mapping):
        return ExplanationOut(
            unavailable=True, detail="no explanation was stored for this alert (R-70)"
        )

    reasons = _text_list(payload.get("reasons"))
    families = _text_list(payload.get("families"))
    modalities = _text_list(payload.get("unavailable_modalities"))

    if reasons:
        return ExplanationOut(
            reasons=reasons,
            unavailable=False,
            detail=_text(payload.get("detail")),
            unavailable_modalities=modalities,
            partial_evidence=bool(payload.get("partial_evidence", False)),
            families=families,
        )

    detail = _text(payload.get("detail"))
    return ExplanationOut(
        reasons=[],
        unavailable=True,
        detail=detail or "no occurrence carried an explanation; the alert is raised anyway (R-70)",
        unavailable_modalities=modalities,
        partial_evidence=bool(payload.get("partial_evidence", False)),
        families=families,
    )


def _instant(value: object) -> datetime | None:
    """A timezone-aware instant from an ISO string, or ``None``."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _score(value: object) -> float | None:
    """A score in [0, 1], or ``None`` for anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if 0.0 <= number <= 1.0 else None


def decode_evidence(
    window_ref: Mapping[str, Any] | None,
    *,
    now: datetime,
    policy: RetentionPolicy,
) -> EvidenceOut:
    """Decode the pointer trail, dating each occurrence's expiry from the policy.

    A trail entry missing an identity, a modality, a score or a parseable timestamp
    is counted in ``unreadable`` rather than dropped: an alert whose evidence is
    partly unreadable is a fact an analyst needs, and a silent skip would render
    as a shorter trail that looks complete.
    """
    retention_days = policy.raw_records_days
    if not isinstance(window_ref, Mapping):
        return EvidenceOut(
            retention_days=retention_days,
            note="no evidence trail was recorded for this alert",
        )

    raw_trail = window_ref.get("evidence")
    trail = (
        raw_trail
        if isinstance(raw_trail, Sequence) and not isinstance(raw_trail, (str, bytes))
        else []
    )

    occurrences: list[EvidenceOccurrenceOut] = []
    unreadable = 0
    for entry in trail:
        if not isinstance(entry, Mapping):
            unreadable += 1
            continue
        identity = _text(entry.get("id"))
        modality = _text(entry.get("modality"))
        score = _score(entry.get("score"))
        at = _instant(entry.get("at"))
        if identity is None or modality is None or score is None or at is None:
            unreadable += 1
            continue
        expires_at = at + timedelta(days=retention_days)
        occurrences.append(
            EvidenceOccurrenceOut(
                id=identity,
                modality=modality,
                score=score,
                at=at,
                model=_text(entry.get("model")),
                expires_at=expires_at,
                expired=now >= expires_at,
            )
        )

    expired = bool(occurrences) and all(occurrence.expired for occurrence in occurrences)
    note: str | None = None
    if not trail:
        note = "no evidence trail was recorded for this alert"
    elif not occurrences:
        note = "none of the recorded evidence could be read"
    elif unreadable:
        note = f"{unreadable} evidence record(s) could not be read"

    return EvidenceOut(
        window_id=_text(window_ref.get("id")),
        trace_id=_text(window_ref.get("trace_id")),
        grouped=bool(window_ref.get("grouped", False)),
        occurrences=occurrences,
        retention_days=retention_days,
        expired=expired,
        unreadable=unreadable,
        note=note,
    )


def related_window(alert: Alert) -> tuple[datetime, datetime]:
    """The bounded window the related-alerts search reads.

    Centred on the alert rather than on *now*: "related" means close in time to
    what happened, and anchoring on now would make the panel's contents change
    while the analyst reads them.
    """
    half = timedelta(minutes=RELATED_WINDOW_MINUTES)
    return alert.created_at - half, alert.created_at + half


def _verdict_out(record: VerdictRecord) -> VerdictRecordOut:
    """Serialise one ledger record, as the verdict routes do (T-309)."""
    return VerdictRecordOut(
        id=record.id,
        alert_id=record.alert_id,
        verdict=record.verdict.value,
        actor=record.actor,
        at=record.at,
        note=record.note,
        supersedes=record.supersedes,
    )


def verdicts_of(alert: Alert, ledger: VerdictLedger) -> AlertVerdictOut:
    """The alert's verdict history, oldest first, and its current verdict."""
    history = list(ledger.history(alert.id, alert.created_at))
    current = history[-1] if history else None
    return AlertVerdictOut(
        current=_verdict_out(current) if current is not None else None,
        history=[_verdict_out(record) for record in history],
    )


def family_history(
    rows: Sequence[Alert],
    *,
    family: str,
    ledger: VerdictLedger,
    window_days: int = FAMILY_HISTORY_DAYS,
) -> FamilyHistoryOut:
    """Tally the verdicts already written on this entity and family.

    ``rows`` are the prior alerts the caller fetched; this function filters to the
    family, asks the ledger for each alert's *current* verdict, and counts. An
    alert with no verdict is counted in ``prior_alerts`` but not in ``labelled``,
    which is what stops "no analyst has looked at this" and "analysts looked and
    agreed" from reading the same way.
    """
    prior = [row for row in rows if row.family == family]
    counts = {"false_positive": 0, "benign": 0, "true_positive": 0}
    labelled = 0
    for row in prior:
        record = ledger.current(row.id, row.created_at)
        if record is None:
            continue
        labelled += 1
        value = record.verdict.value
        if value in counts:
            counts[value] += 1
    return FamilyHistoryOut(
        family=family,
        window_days=window_days,
        prior_alerts=len(prior),
        labelled=labelled,
        false_positive=counts["false_positive"],
        benign=counts["benign"],
        true_positive=counts["true_positive"],
    )


def detail_of(
    alert: Alert,
    *,
    ledger: VerdictLedger,
    related_rows: Sequence[Alert],
    family_rows: Sequence[Alert],
    now: datetime,
    policy: RetentionPolicy,
    related_truncated: bool = False,
    family_window_days: int = FAMILY_HISTORY_DAYS,
) -> AlertDetailOut:
    """Assemble the whole read model for one alert.

    ``related_rows`` and ``family_rows`` are fetched by the caller, because the
    store is what knows how to bound a query (R-34); this function only decides
    what the answer means -- including what counts as *prior*, which is why the
    family rows are filtered here rather than by the caller's window.
    """
    window_ref = alert.window_ref if isinstance(alert.window_ref, Mapping) else None
    related = [
        alert_row_of(row)
        for row in related_rows
        if row.id != alert.id or row.created_at != alert.created_at
    ]
    # "Prior" is decided here rather than by the caller's window bounds. The
    # window the store served is half-open, so a row sharing the alert's own
    # instant is already excluded -- which makes this the rule's only statement
    # (and the only place it can be tested with a row the store would not have
    # served). Strictly less, on the same tuple the list is ordered by: an alert
    # is never its own history, and two alerts at one instant are ordered by id,
    # exactly as the queue orders them.
    prior_rows = [
        row for row in family_rows if (row.created_at, row.id) < (alert.created_at, alert.id)
    ]
    return AlertDetailOut(
        alert=alert_row_of(alert),
        models=AlertModelsOut(flow=alert.model_flow_id, log=alert.model_log_id),
        explanation=decode_explanation(
            alert.explanation if isinstance(alert.explanation, Mapping) else None
        ),
        evidence=decode_evidence(window_ref, now=now, policy=policy),
        verdict=verdicts_of(alert, ledger),
        related=RelatedAlertsOut(
            window_minutes=RELATED_WINDOW_MINUTES,
            items=related,
            truncated=related_truncated,
        ),
        family_history=family_history(
            prior_rows, family=alert.family, ledger=ledger, window_days=family_window_days
        ),
    )
