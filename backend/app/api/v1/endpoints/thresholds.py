"""Threshold endpoints: what is in force, and the weekly recalibration (T-322).

Two routes:

* ``GET /api/v1/thresholds`` -- the rows in force for this deployment, plus the
  FR-13 defaults that govern every family without one (R-69).
* ``POST /api/v1/thresholds/recalibrate`` -- run the job: fit each family's benign
  sample through T-207's guardrailed calibrator, move what may be moved, and
  record every change.

**Reading is open to every role; moving a threshold is admin's.** R-53 lists a
``models`` capability and gives it to ``admin`` alone. A recalibration changes what
the system alerts on -- the same class of change as promoting a version -- so it
uses that capability rather than a new one, while the values themselves are read
by anyone who has to interpret a score against the bar it was compared to.

**One audit row per changed threshold, and none for the rest.** FR-42's trail
records changes (D-041); the response reports the thresholds the run left alone,
so an operator can tell "nothing moved" from "nothing ran". A clamped movement is
still a movement, and its row carries both the requested and the applied value --
the entry that matters most is the one where the data and the deployed bar
disagree (T-207).

**The duration and the size of the run are bounded by construction.** The window
is the job's own 14 days and every read goes through the subscription's paged,
time-bounded alert query (R-34). The job's other inputs are policy -- the quantile,
the guardrail, the minimum sample -- and deliberately not request parameters: a
caller who could pass them could remove the guardrail an acceptance criterion is
about.

**A missing seam fails loudly.** No wired service means a RuntimeError naming it,
rather than an empty listing that reads like "this deployment has no thresholds".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import (
    audit_trail,
    client_ip,
    recalibration_service,
    threshold_admin,
    threshold_impact,
)
from app.auth.rbac import Capability, Principal, require
from app.schemas.thresholds import (
    RecalibrationOut,
    RecalibrationRequest,
    ThresholdImpactOut,
    ThresholdListOut,
    ThresholdOut,
    ThresholdOutcomeOut,
    ThresholdSetOut,
    ThresholdSetRequest,
)
from app.services.audit_log import AuditAction, record_action
from app.services.recalibration import (
    BAND_DEFAULTS,
    RecalibrationReport,
    ThresholdOutcome,
    ThresholdRecord,
    UnfittableBand,
)
from app.services.threshold_admin import (
    MANUAL_SOURCE,
    BandOrderRefused,
    InvalidThreshold,
    ThresholdPreview,
    last_change,
    source_label,
)

router = APIRouter(prefix="/api/v1", tags=["thresholds"])


def _row_out(record: ThresholdRecord, *, changed_by: str | None = None) -> ThresholdOut:
    """Serialise one stored threshold row, with its provenance and its last writer."""
    return ThresholdOut(
        tenant_id=record.key.tenant_id,
        family=record.key.family,
        band=record.key.band,
        value=record.value,
        source=record.source,
        source_label=source_label(record.source),
        updated_at=record.updated_at,
        changed_by=changed_by,
    )


def _preview_out(preview: ThresholdPreview, *, tenant_id: str) -> ThresholdImpactOut:
    """Serialise one impact preview, with the window that produced it."""
    return ThresholdImpactOut(
        tenant_id=tenant_id,
        family=preview.family,
        band=preview.band,
        proposed=preview.proposed,
        current=preview.current,
        current_source=preview.current_label,
        window_start=preview.window_start,
        window_end=preview.window_end,
        alerts_read=preview.alerts_read,
        would_fire=preview.would_fire,
        would_stop_firing=preview.would_stop_firing,
        would_start_firing=preview.would_start_firing,
        complete=preview.complete,
    )


def _outcome_out(outcome: ThresholdOutcome) -> ThresholdOutcomeOut:
    """Serialise one decision, refusal included."""
    return ThresholdOutcomeOut(
        family=outcome.key.family,
        band=outcome.key.band,
        previous=outcome.previous,
        previous_was_default=outcome.previous_was_default,
        requested=outcome.requested,
        applied=outcome.applied,
        changed=outcome.changed,
        clamped=outcome.clamped,
        sample_size=outcome.sample_size,
        reason=outcome.reason.value,
    )


def _report_out(report: RecalibrationReport) -> RecalibrationOut:
    """Serialise a run: the window it read and every threshold it considered."""
    return RecalibrationOut(
        tenant_id=report.tenant_id,
        band=report.band,
        at=report.at,
        since=report.since,
        until=report.until,
        quantile=report.quantile,
        minimum_sample=report.minimum_sample,
        considered=len(report.outcomes),
        changed=len(report.changed),
        outcomes=[_outcome_out(outcome) for outcome in report.outcomes],
    )


@router.get(
    "/thresholds",
    response_model=ThresholdListOut,
    summary="Thresholds in force, and the FR-13 defaults behind them (R-69)",
)
def list_thresholds(
    request: Request,
    _caller: Annotated[Principal, require(Capability.READ)],
) -> ThresholdListOut:
    """The stored values for this tenant, beside the documented initial ones.

    Each row carries who last moved it, read from the audit trail at the row's own
    write instant: ``thresholds`` has no ``updated_by`` column, and adding one would
    be a second record of the same event beside the append-only one (FR-42).
    """
    service = recalibration_service(request)
    trail = audit_trail(request)
    return ThresholdListOut(
        tenant_id=service.tenant_id,
        defaults=dict(BAND_DEFAULTS),
        items=[
            _row_out(
                row,
                changed_by=(
                    change.actor
                    if (change := last_change(trail, row.key, at=row.updated_at))
                    else None
                ),
            )
            for row in service.rows()
        ],
    )


@router.get(
    "/thresholds/preview",
    response_model=ThresholdImpactOut,
    summary="What a proposed threshold would have produced over the last 7 days (design.md §4.8)",
    dependencies=[require(Capability.READ)],
)
def preview_threshold(
    request: Request,
    family: Annotated[str, Query(min_length=1, max_length=80, description="Detection family.")],
    band: Annotated[str, Query(min_length=1, max_length=40, description="FR-13 band whose bound.")],
    value: Annotated[float, Query(gt=0.0, lt=1.0, description="The proposed bound.")],
) -> ThresholdImpactOut:
    """Count a proposed value against the alerts already recorded.

    A read, and open to every role for the same reason the values are: an analyst
    who has to interpret a score against a bar should be able to ask what a
    different bar would have done. Nothing is written and nothing is audited.

    Raises:
        HTTPException: 400 for a band with no documented lower bound (``info``) or a
            value that is not a threshold. There is no 404: a family with no row is
            governed by FR-13's default, which the response reports as ``current``.
    """
    try:
        preview = threshold_impact(request).preview(
            family=family, band=band, proposed=value, at=datetime.now(UTC)
        )
    except UnfittableBand as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InvalidThreshold as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _preview_out(preview, tenant_id=recalibration_service(request).tenant_id)


@router.put(
    "/thresholds/{family}/{band}",
    response_model=ThresholdSetOut,
    summary="Set one threshold by hand, or refuse a band set it would invert (T-410)",
)
def set_threshold(
    family: str,
    band: str,
    body: ThresholdSetRequest,
    request: Request,
    caller: Annotated[Principal, require(Capability.MODELS)],
) -> ThresholdSetOut:
    """Write a manual threshold, recording the move in the trail.

    ``models`` rather than a new capability, for the reason the recalibration route
    gives: moving a threshold changes what the system alerts on.

    Raises:
        HTTPException: 400 for a band with no bound to move; 409 when the value would
            leave the family's four bounds out of order -- a conflict with the values
            in force rather than a malformed request.
    """
    admin = threshold_admin(request)
    try:
        write = admin.set_manual(
            family=family, band=band, value=body.value, actor=caller.subject, at=datetime.now(UTC)
        )
    except UnfittableBand as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InvalidThreshold as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BandOrderRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if write.changed:
        record_action(
            audit_trail(request),
            action=AuditAction.threshold_set,
            actor=caller.subject,
            target_type="threshold",
            target_id=str(write.key),
            at=write.at,
            # What moved, from where to where. No free-text note: the trail is the
            # widest-read table in the system (R-58).
            detail={"previous": write.previous, "applied": write.applied},
            ip=client_ip(request),
        )

    return ThresholdSetOut(
        tenant_id=write.key.tenant_id,
        family=write.key.family,
        band=write.key.band,
        previous=write.previous,
        previous_label=write.previous_label,
        applied=write.applied,
        source=MANUAL_SOURCE,
        changed=write.changed,
        at=write.at,
    )


@router.post(
    "/thresholds/recalibrate",
    response_model=RecalibrationOut,
    summary="Recalibrate a band from analyst verdicts, under T-207's guardrail (FR-18)",
)
def recalibrate_thresholds(
    body: RecalibrationRequest,
    request: Request,
    caller: Annotated[Principal, require(Capability.MODELS)],
) -> RecalibrationOut:
    """Run the weekly job now, and record every threshold it moved.

    Raises:
        HTTPException: 400 when the band has no documented lower bound, naming the
            ones that have. Refused rather than defaulted: `info` has no number to
            move, and silently recalibrating `high` instead would be a different
            decision than the one that was asked for.
    """
    try:
        report = recalibration_service(request).recalibrate(
            band=body.band.strip().lower(), at=datetime.now(UTC)
        )
    except UnfittableBand as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    trail = audit_trail(request)
    for outcome in report.changed:
        record_action(
            trail,
            action=AuditAction.threshold_recalibrate,
            actor=caller.subject,
            target_type="threshold",
            target_id=str(outcome.key),
            at=report.at,
            # The numbers and the evidence, no sample content. A threshold is
            # configuration, and the requested value is the interesting one: it is
            # the record of the data disagreeing with the deployed bar (T-207).
            detail={
                "previous": outcome.previous,
                "previous_was_default": outcome.previous_was_default,
                "requested": outcome.requested,
                "applied": outcome.applied,
                "clamped": outcome.clamped,
                "sample_size": outcome.sample_size,
            },
            ip=client_ip(request),
        )
    return _report_out(report)
