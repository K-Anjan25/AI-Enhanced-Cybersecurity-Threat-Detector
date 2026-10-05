"""Retention and erasure endpoints (NFR-05, R-37, T-314).

Four routes, all ``admin``: R-53 gives retention to admin alone, and erasure is
the same authority as deleting data.

* ``GET /api/v1/retention`` -- the policy and what a run would drop, now.
* ``POST /api/v1/retention/run`` -- drop the months that plan names.
* ``POST /api/v1/privacy/erasure`` -- erase one subject across every store.
* ``GET /api/v1/privacy/erasures`` -- the ledger of erasures, tombstones only.

**The preview and the run build the plan the same way.** Both call
:func:`_plan_for`, so what an operator approved is what executes; a preview
computed by a second implementation would be a promise nobody kept.

**A run is audited; a preview is not.** Reading a plan changes nothing, and the
trail records changes (D-041). The run records what it dropped *and* what was
already gone: "ran retention, dropped nothing" and "ran retention, dropped March
and April" are different facts, and the second is what makes the job idempotent in
a way an operator can see.

**An erasure is audited once, and only when something changed.** A repeat request
is answered with ``already_erased`` and appends nothing -- the ledger and the trail
both already say it happened. The audit detail carries per-target counts and the
tombstone, never the identifier: R-58 applies to the widest-read table in the
system more than anywhere else.

**The identifier is in the process for the length of one call.** No store keeps it
(the ledger keeps a tombstone), no audit row holds it, and the response carries the
tombstone instead. The test module asserts that by scanning everything the call
touched, because "we erased them" is a claim about where the data is not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import (
    audit_trail,
    client_ip,
    erasure_service,
    known_partitions,
    partition_runner,
    retention_policy,
)
from app.auth.rbac import Capability, Principal, require
from app.schemas.privacy import (
    DroppedPartitionOut,
    ErasureLedgerEntryOut,
    ErasureLedgerPageOut,
    ErasureReportOut,
    ErasureRequest,
    ErasureTargetOut,
    PreservedLedgerOut,
    RetentionPlanOut,
    RetentionPolicyOut,
    RetentionRunOut,
    UnevictableOut,
)
from app.services.audit_log import AuditAction, record_action
from app.services.erasure import (
    DEFAULT_LEDGER_LIMIT,
    MAX_LEDGER_LIMIT,
    ErasureKind,
    ErasureReport,
    ErasureSubject,
    LedgerEntry,
)
from app.services.retention import (
    DroppedPartition,
    RetentionPlan,
    RetentionPolicy,
    RetentionRun,
    apply_retention,
    existing_partitions,
    plan_retention,
)

router = APIRouter(tags=["privacy"])


def _partition_out(partition: DroppedPartition) -> DroppedPartitionOut:
    """Serialise one monthly partition."""
    return DroppedPartitionOut(
        table=partition.table,
        name=partition.name,
        year=partition.year,
        month=partition.month,
        covers_start=partition.covers[0],
        covers_end=partition.covers[1],
        statement=partition.statement,
    )


def _plan_out(plan: RetentionPlan) -> RetentionPlanOut:
    """Serialise a plan, flattening the per-table drops into one list."""
    return RetentionPlanOut(
        planned_at=plan.planned_at,
        policy=RetentionPolicyOut(
            raw_records_days=plan.policy.raw_records_days,
            alerts_days=plan.policy.alerts_days,
            stats_days=plan.policy.stats_days,
        ),
        drop=[_partition_out(partition) for drop in plan.drops for partition in drop.partitions],
        kept=[_partition_out(partition) for partition in plan.kept],
        missing=[f"{table}_{year}_{month:02d}" for table, year, month in plan.missing],
        unevictable=[
            UnevictableOut(table=item.table, reason=item.reason) for item in plan.unevictable
        ],
        external=plan.external,
        statements=list(plan.statements),
    )


def _run_out(run: RetentionRun) -> RetentionRunOut:
    """Serialise a run: what it planned, what it changed, what was already gone."""
    return RetentionRunOut(
        started_at=run.started_at,
        planned=[partition.name for partition in run.planned],
        dropped=[partition.name for partition in run.dropped],
        already_absent=[partition.name for partition in run.already_absent],
        changed_anything=not run.is_noop,
    )


def _report_out(report: ErasureReport, *, reason: str = "") -> ErasureReportOut:
    """Serialise an erasure report: tombstone, counts, preserved stores, no value."""
    return ErasureReportOut(
        kind=report.kind.value,
        tombstone=report.tombstone,
        at=report.at,
        targets=[
            ErasureTargetOut(name=outcome.name, affected=outcome.affected)
            for outcome in report.outcomes
        ],
        preserved=[
            PreservedLedgerOut(name=item.name, reason=item.reason) for item in report.preserved
        ],
        already_erased=report.already_erased,
        ledger_sequence=report.ledger_sequence,
        affected=report.affected,
        reason=reason,
    )


def _ledger_out(entry: LedgerEntry) -> ErasureLedgerEntryOut:
    """Serialise one ledger entry."""
    return ErasureLedgerEntryOut(
        sequence=entry.sequence,
        tombstone=entry.tombstone,
        kind=entry.kind.value,
        at=entry.at,
        requested_by=entry.requested_by,
        targets=[ErasureTargetOut(name=name, affected=count) for name, count in entry.targets],
    )


def _plan_for(request: Request, policy: RetentionPolicy) -> RetentionPlan:
    """Plan retention for today, over the partitions this deployment can see.

    The catalog is a dependency (:func:`known_partitions`) rather than a query
    here, because there is no session in the request path yet (D-030) and because
    a test that wants to prove a boundary case should not need a database.
    """
    today = datetime.now(UTC).date()
    return plan_retention(
        policy,
        today=today,
        partitions=existing_partitions(known_partitions(request)),
    )


@router.get(
    "/api/v1/retention",
    response_model=RetentionPlanOut,
    summary="Retention policy and the plan a run would execute (NFR-05)",
)
def get_retention(
    request: Request,
    _caller: Annotated[Principal, require(Capability.RETENTION)],
) -> RetentionPlanOut:
    """What retention would drop right now, and what it will never reach."""
    return _plan_out(_plan_for(request, retention_policy(request)))


@router.post(
    "/api/v1/retention/run",
    response_model=RetentionRunOut,
    summary="Apply the retention plan (NFR-05)",
)
def run_retention(
    request: Request,
    caller: Annotated[Principal, require(Capability.RETENTION)],
) -> RetentionRunOut:
    """Drop the months the plan names, then record what changed.

    Raises:
        RuntimeError: if no partition runner is wired. Loudly: a retention run that
            silently did nothing is the worst answer this route could give, and the
            deployment's own misconfiguration must not look like a clean run.
        HTTPException: 500 when a drop fails, with the partition named -- the
            run's exception carries which statement failed.
    """
    plan = _plan_for(request, retention_policy(request))
    run = apply_retention(plan, partition_runner(request), at=datetime.now(UTC))
    record_action(
        audit_trail(request),
        action=AuditAction.retention_apply,
        actor=caller.subject,
        target_type="retention",
        target_id=str(run.started_at.date()),
        at=run.started_at,
        # Partition names and nothing else. A partition name is a table and a
        # month, so the trail answers "was March dropped" without a row of content.
        detail={
            "dropped": [partition.name for partition in run.dropped],
            "already_absent": [partition.name for partition in run.already_absent],
        },
        ip=client_ip(request),
    )
    return _run_out(run)


@router.post(
    "/api/v1/privacy/erasure",
    response_model=ErasureReportOut,
    summary="Erase one data subject across every store (NFR-05, R-37)",
)
def erase_subject(
    body: ErasureRequest,
    request: Request,
    caller: Annotated[Principal, require(Capability.RETENTION)],
) -> ErasureReportOut:
    """Erase a subject, cascading across the registered stores.

    Raises:
        HTTPException: 400 when the kind is not one of the two defined, naming
            them. The value never appears in the message.
    """
    try:
        kind = ErasureKind(body.kind.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(member.value for member in ErasureKind)
        raise HTTPException(status_code=400, detail=f"kind must be one of: {allowed}") from exc

    report = erasure_service(request).erase(
        ErasureSubject(kind=kind, value=body.value),
        requested_by=caller.subject,
        at=datetime.now(UTC),
    )
    if not report.already_erased:
        record_action(
            audit_trail(request),
            action=AuditAction.privacy_erasure,
            actor=caller.subject,
            target_type="erasure",
            target_id=report.tombstone,
            at=report.at,
            detail={
                "kind": report.kind.value,
                "targets": {outcome.name: outcome.affected for outcome in report.outcomes},
                "preserved": [item.name for item in report.preserved],
            },
            ip=client_ip(request),
        )
    return _report_out(report, reason=body.reason.strip())


@router.get(
    "/api/v1/privacy/erasures",
    response_model=ErasureLedgerPageOut,
    summary="The erasure ledger, newest first (NFR-05)",
)
def list_erasures(
    request: Request,
    _caller: Annotated[Principal, require(Capability.RETENTION)],
    limit: Annotated[int, Query(ge=1, le=MAX_LEDGER_LIMIT)] = DEFAULT_LEDGER_LIMIT,
    before: Annotated[int | None, Query(ge=1)] = None,
) -> ErasureLedgerPageOut:
    """Recorded erasures: tombstones, counts and who asked. Never identifiers.

    One row over ``limit`` is fetched to answer "is there another page", which is
    cheaper than counting the ledger and cannot go stale between two queries.
    """
    entries = erasure_service(request).histogram(limit=limit + 1, before=before)
    page = entries[:limit]
    return ErasureLedgerPageOut(
        items=[_ledger_out(entry) for entry in page],
        # The cursor has to be the last item handed out, not the first one left
        # out: ``before`` is exclusive, so answering with the latter would skip the
        # next page entirely.
        next_before=page[-1].sequence if len(entries) > limit and page else None,
    )
