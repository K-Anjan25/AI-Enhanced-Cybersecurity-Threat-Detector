"""Model ops endpoints: list, metrics, promote, rollback (T-315, FR-30…FR-33).

Four routes:

* ``GET /api/v1/models`` -- the version table: id, kind, status, who promoted it.
* ``GET /api/v1/models/{model_id}/metrics`` -- FR-31's held-out metrics, each with
  the run it was read from.
* ``POST /api/v1/models/{model_id}/promote`` -- make a version active, retiring
  the incumbent, in one call (FR-33).
* ``POST /api/v1/models/{kind}/rollback`` -- reverse the most recent promotion of
  a kind, in one call (FR-33).

**Reading is open to every authenticated role; changing what serves is admin's.**
R-53 already lists a ``models`` capability and gives it to ``admin`` alone, so
promotion and rollback use it rather than a new one. A viewer can see which model
is serving and what it scored -- that is operational information an analyst needs
to interpret an alert -- but cannot change it.

**Rollback names the kind, not a version.** An operator cannot roll back to a
version that never served traffic, and the previous version comes from the
service's own history rather than from the caller's memory of it. See
``app/services/model_ops.py`` for why this is not modelled as a promotion.

**A no-op is not recorded.** Promoting the version that is already active returns
``changed=false`` and appends nothing to the audit trail: the trail records
changes, not requests (D-041), and a client that retries must not be able to fill
it with copies of one decision.

**The notes stay out of the trail.** The justification for a promotion and the
reason for a rollback are required by the request and carried on the version
record and the response -- but the audit detail holds only the ids, the kind and
the status, because the trail is readable by every role (R-58, and T-309's
precedent for analyst notes).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import audit_trail, client_ip, model_ops
from app.auth.rbac import Capability, Principal, require
from app.schemas.model import (
    ConfusionMatrixOut,
    EvaluationDetailsOut,
    MetricPointOut,
    ModelListOut,
    ModelMetricsOut,
    ModelOut,
    ModelTransitionOut,
    PromotionRequest,
    RollbackRequest,
    ScoreHistogramBinOut,
    ScoreHistogramOut,
)
from app.services.audit_log import AuditAction, record_action
from app.services.model_ops import (
    KINDS,
    FloatingModelId,
    MissingManifest,
    ModelKindName,
    ModelMetrics,
    ModelStatusName,
    ModelVersion,
    NothingToRollBack,
    RefusedTransition,
    TransitionOutcome,
    UnknownModel,
)

router = APIRouter(prefix="/api/v1/models", tags=["models"])


def _metrics_out(metrics: ModelMetrics) -> ModelMetricsOut:
    """Serialise a metric set, every value beside its provenance."""
    return ModelMetricsOut(
        split=metrics.split,
        evaluated_at=metrics.evaluated_at,
        metrics={
            name: MetricPointOut(value=point.value, artifact=point.artifact, field=point.field)
            for name, point in metrics.points.items()
        },
        evaluation=(
            None
            if metrics.evaluation is None
            else EvaluationDetailsOut(
                confusion=ConfusionMatrixOut(
                    threshold=metrics.evaluation.confusion.threshold,
                    tp=metrics.evaluation.confusion.tp,
                    fp=metrics.evaluation.confusion.fp,
                    tn=metrics.evaluation.confusion.tn,
                    fn=metrics.evaluation.confusion.fn,
                    artifact=metrics.evaluation.confusion.artifact,
                    field=metrics.evaluation.confusion.field,
                ),
                score_histogram=ScoreHistogramOut(
                    bins=[
                        ScoreHistogramBinOut(
                            lower=item.lower,
                            upper=item.upper,
                            benign=item.benign,
                            threat=item.threat,
                        )
                        for item in metrics.evaluation.score_histogram.bins
                    ],
                    artifact=metrics.evaluation.score_histogram.artifact,
                    field=metrics.evaluation.score_histogram.field,
                ),
            )
        ),
    )


def _out(version: ModelVersion) -> ModelOut:
    """Serialise one version. A version with no recorded evaluation says so."""
    return ModelOut(
        model_id=version.model_id,
        kind=version.kind,
        status=version.status,
        artifact_uri=version.artifact_uri,
        sha256=version.sha256,
        manifest_present=version.manifest_present,
        promoted_at=version.promoted_at,
        promoted_by=version.promoted_by,
        justification=version.justification,
    )


def _transition_out(outcome: TransitionOutcome, *, kind: str, actor: str) -> ModelTransitionOut:
    """Serialise a transition: what is serving, what stepped down, and when."""
    return ModelTransitionOut(
        model_id=outcome.model_id,
        kind=kind,
        status="active",
        retired=outcome.retired,
        changed=outcome.changed,
        at=outcome.at,
        actor=actor,
    )


@router.get(
    "",
    response_model=ModelListOut,
    summary="List registered model versions (FR-30)",
    dependencies=[require(Capability.READ)],
)
def list_models(
    request: Request,
    kind: Annotated[ModelKindName | None, Query()] = None,
    status: Annotated[ModelStatusName | None, Query()] = None,
) -> ModelListOut:
    """The version table, filtered by kind and status when asked.

    Raises:
        HTTPException: 422 from the query validation when a filter names a kind or
            status that does not exist -- worth naming rather than ignoring, since
            a filter that matches nothing silently shows an empty table.
    """
    versions = model_ops(request).list(kind=kind, status=status)
    return ModelListOut(items=[_out(version) for version in versions], count=len(versions))


@router.get(
    "/{model_id}/metrics",
    response_model=ModelMetricsOut,
    summary="Held-out metrics and recorded evaluation artifacts for one version (FR-31, T-420)",
    dependencies=[require(Capability.READ)],
)
def get_metrics(model_id: str, request: Request) -> ModelMetricsOut:
    """FR-31's metrics, each with the recorded run it came from (R-74).

    Raises:
        HTTPException: 400 for a floating id (R-68 refuses ``latest`` with a
            different remedy than a typo), 404 when the version is unknown or has
            no recorded evaluation -- the second is a fact about the model, and
            the message says which one it is.
    """
    try:
        version = model_ops(request).get(model_id)
    except FloatingModelId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnknownModel as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if version.metrics is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"model {model_id!r} is registered but has no recorded evaluation; "
                "FR-31's metrics are read from a run, and no run is attached to this version"
            ),
        )
    return _metrics_out(version.metrics)


@router.post(
    "/{model_id}/promote",
    response_model=ModelTransitionOut,
    summary="Make a version active and retire the incumbent (FR-33)",
)
def promote_model(
    model_id: str,
    body: PromotionRequest,
    request: Request,
    caller: Annotated[Principal, require(Capability.MODELS)],
) -> ModelTransitionOut:
    """Promote a version, in one call (admin only).

    Raises:
        HTTPException: 400 for a floating id or a blank justification; 404 when the
            version is unknown; 409 when the lifecycle refuses the move -- a retired
            version (terminal under R-68) or one with no training manifest (R-63).
            A conflict with the version's own state is 409, not 400: the request is
            well formed and the answer is "not from here".
    """
    ops = model_ops(request)
    try:
        outcome = ops.promote(
            model_id,
            actor=caller.subject,
            justification=body.justification.strip(),
            at=datetime.now(UTC),
        )
    except FloatingModelId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RefusedTransition, MissingManifest) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnknownModel as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    kind = ops.get(outcome.model_id).kind
    if outcome.changed:
        record_action(
            audit_trail(request),
            action=AuditAction.model_promote,
            actor=caller.subject,
            target_type="model",
            target_id=outcome.model_id,
            at=outcome.at,
            # Ids, kind and status. The justification is deliberately absent: the
            # trail is readable by every role and notes do not belong in it.
            detail={"kind": kind, "retired": outcome.retired, "status": "active"},
            ip=client_ip(request),
        )
    return _transition_out(outcome, kind=kind, actor=caller.subject)


@router.post(
    "/{kind}/rollback",
    response_model=ModelTransitionOut,
    summary="Reverse the most recent promotion of a kind (FR-33)",
)
def rollback_model(
    kind: str,
    body: RollbackRequest,
    request: Request,
    caller: Annotated[Principal, require(Capability.MODELS)],
) -> ModelTransitionOut:
    """Roll a kind back to the version its active model displaced (admin only).

    Raises:
        HTTPException: 400 for a blank reason or a kind that is not ``flow`` or
            ``log``, naming what is allowed; 409 when there is nothing to roll back
            to -- no active version, or an active version that displaced nothing.
    """
    ops = model_ops(request)
    if kind not in KINDS:
        allowed = ", ".join(KINDS)
        raise HTTPException(
            status_code=400, detail=f"unknown model kind; allowed kinds are: {allowed}"
        )
    try:
        outcome = ops.rollback(
            kind,
            actor=caller.subject,
            reason=body.reason.strip(),
            at=datetime.now(UTC),
        )
    except NothingToRollBack as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_action(
        audit_trail(request),
        action=AuditAction.model_rollback,
        actor=caller.subject,
        target_type="model",
        target_id=outcome.model_id,
        at=outcome.at,
        detail={"kind": kind, "retired": outcome.retired, "status": "active"},
        ip=client_ip(request),
    )
    return _transition_out(outcome, kind=kind, actor=caller.subject)
