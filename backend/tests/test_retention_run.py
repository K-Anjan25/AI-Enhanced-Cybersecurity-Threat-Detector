"""The shared retention run and the scheduler that calls it (NFR-05), without a database.

The live counterpart, against a migrated PostgreSQL, is in ``test_entity_retention_live.py``.
These tests pin the logic that does not need one: each table is swept against its own
window, a missing sweeper is refused rather than reported as a clean run, the scheduler
runs at start and then on its interval, a failing run does not stop the loop, and a
scheduled run is recorded as the system and not as a person.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from app.services.audit_log import AuditAction, InMemoryAuditTrail
from app.services.retention import RetentionPolicy, RetentionRun
from app.services.retention_run import SCHEDULER_ACTOR, execute_retention, record_retention_run
from app.services.retention_scheduler import RetentionScheduler

AT = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def _no_partitions() -> set[tuple[str, int, int]]:
    return set()


def _refuse(statement: str) -> bool:
    raise AssertionError(f"no partition should be dropped in this test: {statement}")


# -- the run ----------------------------------------------------------------------


def test_each_row_swept_table_gets_a_cutoff_from_its_own_window() -> None:
    seen: dict[str, datetime] = {}

    def sweeper(cutoffs: dict[str, datetime]) -> dict[str, int]:
        seen.update(cutoffs)
        return dict.fromkeys(cutoffs, 0)

    execute_retention(
        policy=RetentionPolicy(),
        partitions=_no_partitions,
        runner=_refuse,
        sweeper=sweeper,
        at=AT,
    )
    assert seen["log_events"] == AT - timedelta(days=30)  # raw records window
    assert seen["flow_events"] == AT - timedelta(days=30)
    assert seen["entities"] == AT - timedelta(days=400)  # alerts window, not raw


def test_the_windows_follow_the_policy_not_a_constant() -> None:
    seen: dict[str, datetime] = {}

    def sweeper(cutoffs: dict[str, datetime]) -> dict[str, int]:
        seen.update(cutoffs)
        return {}

    policy = RetentionPolicy(raw_records_days=7, alerts_days=90, stats_days=90)
    execute_retention(
        policy=policy, partitions=_no_partitions, runner=_refuse, sweeper=sweeper, at=AT
    )
    assert seen["log_events"] == AT - timedelta(days=7)
    assert seen["entities"] == AT - timedelta(days=90)


def test_a_run_with_row_swept_tables_and_no_sweeper_is_refused_not_reported_clean() -> None:
    with pytest.raises(RuntimeError, match="retention_sweeper is not configured"):
        execute_retention(
            policy=RetentionPolicy(),
            partitions=_no_partitions,
            runner=_refuse,
            sweeper=None,
            at=AT,
        )


def test_the_sweep_counts_are_reported_on_the_run() -> None:
    run = execute_retention(
        policy=RetentionPolicy(),
        partitions=_no_partitions,
        runner=_refuse,
        sweeper=lambda cutoffs: dict.fromkeys(cutoffs, 5),
        at=AT,
    )
    assert run.swept == {
        "log_events": 5,
        "flow_events": 5,
        "entities": 5,
        "model_versions_history": 5,
    }


def test_days_for_window_refuses_a_name_that_is_not_a_window() -> None:
    with pytest.raises(ValueError, match="not a retention window"):
        RetentionPolicy().days_for_window("rows older than 400 days, in batches")


# -- the audit record -------------------------------------------------------------


def test_a_scheduled_run_is_audited_as_the_system() -> None:
    trail = InMemoryAuditTrail()
    run = RetentionRun(
        started_at=AT, planned=(), dropped=(), already_absent=(), swept={"entities": 2}
    )
    record_retention_run(trail, run, actor=SCHEDULER_ACTOR, ip=None)
    entries = trail.entries(start=AT - timedelta(days=1), end=AT + timedelta(days=1))
    assert len(entries) == 1
    assert entries[0].record.action is AuditAction.retention_apply
    assert entries[0].record.actor == SCHEDULER_ACTOR
    assert entries[0].record.detail["swept"] == {"entities": 2}


# -- the scheduler ----------------------------------------------------------------


def _wait_for(predicate: object, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(0.005)
    return False


def test_the_scheduler_runs_first_after_its_delay_and_then_on_its_interval() -> None:
    calls = []
    scheduler = RetentionScheduler(
        lambda: calls.append(1), interval_seconds=0.01, initial_delay_seconds=0
    )
    scheduler.start()
    try:
        assert _wait_for(lambda: len(calls) >= 3)
    finally:
        scheduler.stop()
    assert scheduler.runs >= 3
    assert scheduler.failures == 0


def test_nothing_runs_before_the_initial_delay() -> None:
    calls = []
    scheduler = RetentionScheduler(
        lambda: calls.append(1), interval_seconds=0.01, initial_delay_seconds=0.3
    )
    scheduler.start()
    time.sleep(0.05)
    try:
        assert calls == []
    finally:
        scheduler.stop()
    assert scheduler.runs == 0


def test_a_failing_run_is_counted_and_the_loop_keeps_going() -> None:
    calls = []

    def flaky() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the database was briefly unavailable")

    scheduler = RetentionScheduler(flaky, interval_seconds=0.01, initial_delay_seconds=0)
    scheduler.start()
    try:
        assert _wait_for(lambda: len(calls) >= 3)
    finally:
        scheduler.stop()
    assert scheduler.failures == 1
    assert scheduler.runs >= 2


def test_stop_wakes_the_loop_instead_of_waiting_out_the_interval() -> None:
    scheduler = RetentionScheduler(lambda: None, interval_seconds=3600, initial_delay_seconds=0)
    scheduler.start()
    assert _wait_for(lambda: scheduler.runs >= 1)
    started = time.monotonic()
    scheduler.stop(timeout=5)
    assert time.monotonic() - started < 1.0


def test_start_is_idempotent_while_running() -> None:
    gate = threading.Event()
    scheduler = RetentionScheduler(
        lambda: gate.wait(0.001), interval_seconds=0.01, initial_delay_seconds=0
    )
    scheduler.start()
    first = scheduler._thread
    scheduler.start()
    assert scheduler._thread is first
    scheduler.stop()


def test_a_non_positive_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        RetentionScheduler(lambda: None, interval_seconds=0)
