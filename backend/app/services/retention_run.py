"""One retention run, shared by the operator's route and the scheduler (NFR-05).

Both paths must do exactly the same thing, so the logic lives here once: plan the
partitions the policy names, drop them, then sweep the row-swept tables, each against its
own window. The route records the run in the audit trail as the operator's action; the
scheduler records it as the system's. Neither path has its own copy of the steps, which
is how a scheduled run quietly stops matching the manual one.

A run is idempotent. Partition drops are ``DROP TABLE IF EXISTS``, and a sweep deletes
only rows that are still expired, so a second run after a crash changes nothing that the
first did not.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from app.services.audit_log import AuditAction, AuditTrail, record_action
from app.services.retention import (
    ROW_SWEPT_WINDOWS,
    RetentionPolicy,
    RetentionRun,
    StatementRunner,
    apply_retention,
    existing_partitions,
    plan_retention,
)

__all__ = ["SCHEDULER_ACTOR", "execute_retention", "record_retention_run"]

#: The audit actor for runs the scheduler starts. Not a user, and not spoofable as one.
SCHEDULER_ACTOR = "system:retention-scheduler"

#: ``sweeper(cutoffs)`` deletes expired rows per table; see ``retention_catalog.sweep_retained``.
Sweeper = Callable[[dict[str, datetime]], dict[str, int]]


def execute_retention(
    *,
    policy: RetentionPolicy,
    partitions: Callable[[], set[tuple[str, int, int]]],
    runner: StatementRunner,
    sweeper: Sweeper | None,
    at: datetime,
) -> RetentionRun:
    """Plan, drop, then sweep, returning what changed.

    Raises:
        RuntimeError: if the plan names row-swept tables and no sweeper is wired. A run
            that cannot sweep must not report a clean run in which those tables kept
            everything.
    """
    plan = plan_retention(
        policy,
        today=at.date(),
        partitions=existing_partitions(partitions()),
    )
    run = apply_retention(plan, runner, at=at)
    if not plan.row_swept:
        return run
    if sweeper is None:
        msg = (
            "retention_sweeper is not configured on app.state: the row-swept tables "
            f"{sorted(plan.row_swept)} would never age out"
        )
        raise RuntimeError(msg)
    # The plan's row_swept values are display text for the preview; the window name that
    # governs each table is looked up here, from the one mapping that defines it.
    cutoffs = {
        table: at - timedelta(days=policy.days_for_window(ROW_SWEPT_WINDOWS[table]))
        for table in plan.row_swept
    }
    return replace(run, swept=sweeper(cutoffs))


def record_retention_run(
    trail: AuditTrail, run: RetentionRun, *, actor: str, ip: str | None
) -> None:
    """Append the run to the audit trail, with names and counts and no content."""
    record_action(
        trail,
        action=AuditAction.retention_apply,
        actor=actor,
        target_type="retention",
        target_id=str(run.started_at.date()),
        at=run.started_at,
        # Partition names and sweep counts only: a partition name is a table and a month,
        # so the trail answers "was March dropped" without a row of content.
        detail={
            "dropped": [partition.name for partition in run.dropped],
            "already_absent": [partition.name for partition in run.already_absent],
            "swept": run.swept,
        },
        ip=ip,
    )
