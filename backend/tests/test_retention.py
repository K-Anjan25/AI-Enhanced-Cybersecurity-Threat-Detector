"""T-314: retention -- which months may be dropped, and which may not (NFR-05).

The central property is a boundary, and boundaries are where retention silently
destroys data it promised to keep: a month is droppable only when **every** row
in it is outside the window. So the tests here are written against dates chosen
to sit exactly on the boundary -- a partition whose last day is the cutoff day, a
partition that starts before the cutoff and ends after it -- rather than against
"an old month" and "a recent month", which is what a broken implementation would
also pass.

The second property is that the plan is a pure function of its inputs: time and
the catalog are arguments, not the clock and a connection, so every case below is
asserted without either.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app.db.models import PARTITIONED_TABLES
from app.services.retention import (
    DEFAULT_ALERT_DAYS,
    DEFAULT_RAW_RECORD_DAYS,
    DEFAULT_STATS_DAYS,
    DroppedPartition,
    DropPlan,
    RetentionPolicy,
    apply_retention,
    existing_partitions,
    plan_retention,
)

TODAY = date(2026, 10, 5)


def policy(**overrides: int) -> RetentionPolicy:
    """A policy with any window overridable."""
    fields = {
        "raw_records_days": DEFAULT_RAW_RECORD_DAYS,
        "alerts_days": DEFAULT_ALERT_DAYS,
        "stats_days": DEFAULT_STATS_DAYS,
    }
    return RetentionPolicy(**{**fields, **overrides})


def months(*triples: tuple[str, int, int]) -> set[tuple[str, int, int]]:
    return set(triples)


def _drop_of(plan: object, table: str) -> DropPlan:
    return next(drop for drop in plan.drops if drop.table == table)  # type: ignore[attr-defined]


def _names(plan: object, table: str) -> list[str]:
    return [partition.name for partition in _drop_of(plan, table).partitions]


# --- the policy --------------------------------------------------------------


def test_the_defaults_have_fr05s_raw_window_and_a_longer_alert_window() -> None:
    assert DEFAULT_RAW_RECORD_DAYS == 30
    assert policy().raw_records_days == 30
    assert policy().alerts_days > policy().raw_records_days
    assert policy().stats_days >= policy().raw_records_days


@pytest.mark.parametrize("field", ["raw_records_days", "alerts_days", "stats_days"])
def test_a_window_of_zero_or_negative_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match="at least 1 day"):
        policy(**{field: 0})


def test_an_absurdly_long_window_is_refused_as_a_units_mistake() -> None:
    with pytest.raises(ValueError, match="units mistake"):
        policy(alerts_days=36_500)


def test_alerts_may_not_be_kept_shorter_than_the_raw_records_they_came_from() -> None:
    """The privacy invariant: the sensitive artefact may not outlive the summary."""
    with pytest.raises(ValueError, match="must not be shorter"):
        policy(alerts_days=7, raw_records_days=30)


def test_equal_windows_are_allowed() -> None:
    assert policy(alerts_days=30, raw_records_days=30).alerts_days == 30


def test_every_partitioned_table_has_a_window() -> None:
    """A partitioned table with no window would accumulate forever in silence."""
    for table in PARTITIONED_TABLES:
        assert policy().days_for(table) >= 1


def test_a_table_with_no_window_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="no retention window"):
        policy().days_for("users")


def test_the_cutoff_is_today_minus_the_window() -> None:
    assert policy(alerts_days=400).cutoff_for("alerts", today=TODAY) == date(2025, 8, 31)


# --- the plan: the boundary rule ---------------------------------------------


def test_a_month_ending_on_the_cutoff_day_is_droppable() -> None:
    """``end <= cutoff``: the last day outside the window is still outside it."""
    cutoff = TODAY - timedelta(days=30)  # 2026-09-05
    plan = plan_retention(
        policy(raw_records_days=30, alerts_days=30, stats_days=30),
        today=TODAY,
        partitions=months(("alerts", 2026, 8)),
    )
    assert cutoff == date(2026, 9, 5)
    assert _names(plan, "alerts") == ["alerts_2026_08"]


def test_a_month_whose_end_is_exactly_the_cutoff_drops() -> None:
    """The equality case, stated on its own because both sides are defensible.

    A 399-day window ends on 2025-09-01, which is precisely when the August 2025
    partition ends. The policy promises 399 days, so a month ending on the cutoff
    day is outside it and drops. Written separately from the ``end < cutoff`` case
    above because an implementation that kept this month would pass every other
    boundary test while holding a day more than it says it does.
    """
    assert policy(alerts_days=399).cutoff_for("alerts", today=TODAY) == date(2025, 9, 1)
    plan = plan_retention(
        policy(raw_records_days=30, alerts_days=399, stats_days=399),
        today=TODAY,
        partitions=months(("alerts", 2025, 8), ("alerts", 2025, 9)),
    )
    assert _names(plan, "alerts") == ["alerts_2025_08"]
    assert [partition.name for partition in plan.kept] == ["alerts_2025_09"]


def test_each_partitioned_table_is_retained_by_its_own_window() -> None:
    """The same month, two tables, two windows: one drops and one is kept.

    Alerts are kept for 400 days and ingest stats for 100, so December 2025 is
    inside the alert window (cutoff 2025-08-31) and outside the stats window
    (cutoff 2026-06-27). A policy read off the wrong field would drop a month of
    alerts -- or keep a year of stats -- and this is the case that notices.
    """
    plan = plan_retention(
        policy(raw_records_days=30, alerts_days=400, stats_days=100),
        today=TODAY,
        partitions=months(("alerts", 2025, 12), ("ingest_stats", 2025, 12)),
    )
    assert [drop.table for drop in plan.drops] == ["alerts", "ingest_stats"]
    assert [drop.window_days for drop in plan.drops] == [400, 100]
    assert _names(plan, "alerts") == []
    assert _names(plan, "ingest_stats") == ["ingest_stats_2025_12"]


def test_a_month_that_straddles_the_cutoff_is_kept() -> None:
    """The property that makes this safe: September 2026 ends after the cutoff."""
    plan = plan_retention(
        policy(raw_records_days=30, alerts_days=30, stats_days=30),
        today=TODAY,
        partitions=months(("alerts", 2026, 9)),
    )
    assert _names(plan, "alerts") == []
    assert [partition.name for partition in plan.kept] == ["alerts_2026_09"]


def test_the_current_month_is_never_dropped() -> None:
    plan = plan_retention(
        policy(raw_records_days=1, alerts_days=1, stats_days=1),
        today=TODAY,
        partitions=months(("alerts", 2026, 10), ("ingest_stats", 2026, 10)),
    )
    assert plan.statements == ()
    assert {partition.name for partition in plan.kept} == {"alerts_2026_10", "ingest_stats_2026_10"}


def test_a_boundary_month_is_kept_until_it_does_not_straddle() -> None:
    """The same September partition drops one month later, on 2026-11-01."""
    partitions = months(("alerts", 2026, 9))
    in_october = plan_retention(policy(alerts_days=30), today=TODAY, partitions=partitions)
    in_november = plan_retention(
        policy(alerts_days=30), today=date(2026, 11, 1), partitions=partitions
    )
    assert _names(in_october, "alerts") == []
    assert _names(in_november, "alerts") == ["alerts_2026_09"]


def test_whole_months_in_order_and_only_the_old_ones_drop() -> None:
    plan = plan_retention(
        policy(alerts_days=100, stats_days=100),
        today=TODAY,
        partitions=months(
            ("alerts", 2026, 1),
            ("alerts", 2026, 5),
            ("alerts", 2026, 6),
            ("alerts", 2026, 9),
            ("ingest_stats", 2026, 6),
        ),
    )
    # cutoff = 2026-10-05 - 100 days = 2026-06-27, so June's end (2026-07-01) is
    # still inside the window and it is kept despite starting outside it.
    assert _names(plan, "alerts") == ["alerts_2026_01", "alerts_2026_05"]
    assert _names(plan, "ingest_stats") == []
    assert {partition.name for partition in plan.kept} == {
        "alerts_2026_06",
        "alerts_2026_09",
        "ingest_stats_2026_06",
    }


def test_the_plan_reports_the_span_each_drop_covers() -> None:
    plan = plan_retention(
        policy(alerts_days=100),
        today=TODAY,
        partitions=months(("alerts", 2026, 1)),
    )
    partition = _drop_of(plan, "alerts").partitions[0]
    assert partition.covers == (date(2026, 1, 1), date(2026, 2, 1))
    assert partition.name == "alerts_2026_01"


def test_the_statement_is_a_drop_if_exists_of_the_partition() -> None:
    plan = plan_retention(
        policy(alerts_days=100),
        today=TODAY,
        partitions=months(("alerts", 2026, 1)),
    )
    statement = plan.statements[0]
    assert statement == "DROP TABLE IF EXISTS alerts_2026_01"
    assert "DELETE" not in statement.upper()


def test_a_plan_with_no_partitions_drops_nothing_and_says_so() -> None:
    plan = plan_retention(policy(), today=TODAY, partitions=months())
    assert plan.is_empty
    assert plan.missing == ()
    assert plan.kept == ()


def test_a_december_partition_ends_in_the_next_year() -> None:
    plan = plan_retention(
        policy(alerts_days=100),
        today=date(2027, 6, 1),
        partitions=months(("alerts", 2026, 12)),
    )
    assert _drop_of(plan, "alerts").partitions[0].covers == (date(2026, 12, 1), date(2027, 1, 1))


def test_the_same_inputs_produce_the_same_plan() -> None:
    """Determinism: the caller's set iteration order must not reach the output."""
    partitions = months(("alerts", 2026, 1), ("alerts", 2026, 2), ("ingest_stats", 2026, 2))
    first = plan_retention(policy(alerts_days=30), today=TODAY, partitions=partitions)
    second = plan_retention(policy(alerts_days=30), today=TODAY, partitions=partitions)
    assert first.statements == second.statements
    assert [d.table for d in first.drops] == [d.table for d in second.drops]


# --- what the plan will not reach --------------------------------------------


def test_the_audit_trail_is_reported_as_unevictable_with_its_reason() -> None:
    """An operator reading a retention report must see what it did not reach."""
    plan = plan_retention(policy(), today=TODAY, partitions=months(("alerts", 2026, 1)))
    audit = next(item for item in plan.unevictable if item.table == "audit_log")
    assert "R-31" in audit.reason
    assert "not partitioned" in audit.reason


def test_the_raw_record_window_is_reported_with_its_external_mechanism() -> None:
    """FR-05's 30 days live in Kafka and ES, so the plan names them."""
    plan = plan_retention(policy(), today=TODAY, partitions=months())
    assert set(plan.external) == {"kafka", "elasticsearch"}
    assert all(value for value in plan.external.values())
    assert plan.policy.raw_records_days == 30


def test_the_plan_exposes_the_policy_it_was_computed_from() -> None:
    plan = plan_retention(policy(alerts_days=123), today=TODAY, partitions=months())
    assert plan.policy.alerts_days == 123
    assert plan.planned_at == TODAY


def test_a_month_inside_the_window_with_no_partition_is_reported_as_missing() -> None:
    """There is no default partition, so a gap means rows were rejected."""
    plan = plan_retention(
        policy(alerts_days=100, raw_records_days=30),
        today=TODAY,
        partitions=months(("alerts", 2026, 1), ("alerts", 2026, 9)),
    )
    assert ("alerts", 2026, 8) in plan.missing
    assert all(table == "alerts" for table, _, _ in plan.missing)


def test_no_partitions_means_no_missing_months_are_invented() -> None:
    plan = plan_retention(policy(), today=TODAY, partitions=months())
    assert plan.missing == ()


# --- the catalog input -------------------------------------------------------


def test_the_catalog_input_is_validated() -> None:
    assert existing_partitions([("alerts", 2026, 1)]) == {("alerts", 2026, 1)}
    with pytest.raises(ValueError, match="not a partitioned table"):
        existing_partitions([("users", 2026, 1)])
    with pytest.raises(ValueError, match="month must be 1..12"):
        existing_partitions([("alerts", 2026, 13)])


# --- applying -----------------------------------------------------------------


def test_applying_reports_which_partitions_it_dropped() -> None:
    plan = plan_retention(
        policy(alerts_days=30, stats_days=30),
        today=TODAY,
        partitions=months(("alerts", 2026, 1), ("ingest_stats", 2026, 2)),
    )
    seen: list[str] = []

    def runner(statement: str) -> bool:
        seen.append(statement)
        return True

    run = apply_retention(plan, runner, at=datetime(2026, 10, 5, 3, 0, tzinfo=UTC))
    assert seen == list(plan.statements)
    assert [partition.name for partition in run.dropped] == [
        "alerts_2026_01",
        "ingest_stats_2026_02",
    ]
    assert run.already_absent == ()
    assert run.is_noop is False
    assert run.started_at == datetime(2026, 10, 5, 3, 0, tzinfo=UTC)


def test_applying_twice_is_a_noop_the_second_time() -> None:
    """``DROP TABLE IF EXISTS`` succeeds when the table is gone: the run says so."""
    plan = plan_retention(
        policy(alerts_days=30),
        today=TODAY,
        partitions=months(("alerts", 2026, 1)),
    )
    dropped: set[str] = set()

    def runner(statement: str) -> bool:
        name = statement.rsplit(" ", 1)[-1]
        if name in dropped:
            return False  # already gone, as PostgreSQL would report
        dropped.add(name)
        return True

    first = apply_retention(plan, runner)
    second = apply_retention(plan, runner)
    assert [partition.name for partition in first.dropped] == ["alerts_2026_01"]
    assert second.dropped == ()
    assert second.is_noop is True
    assert [partition.name for partition in second.already_absent] == ["alerts_2026_01"]


def test_an_empty_plan_runs_nothing() -> None:
    plan = plan_retention(policy(), today=TODAY, partitions=months())
    calls: list[str] = []
    run = apply_retention(plan, lambda statement: calls.append(statement) or True)
    assert calls == []
    assert run.planned == ()
    assert run.is_noop


def test_a_failing_drop_names_the_partition_and_propagates() -> None:
    """A retention job that half-ran must not report success."""
    plan = plan_retention(
        policy(alerts_days=30),
        today=TODAY,
        partitions=months(("alerts", 2026, 1)),
    )

    def runner(statement: str) -> bool:
        msg = "permission denied"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="retention failed on alerts_2026_01"):
        apply_retention(plan, runner)


def test_a_plan_lists_every_partitioned_table_even_when_one_has_nothing() -> None:
    plan = plan_retention(policy(), today=TODAY, partitions=months(("alerts", 2026, 1)))
    assert {drop.table for drop in plan.drops} == set(PARTITIONED_TABLES)


def test_the_dropped_partition_records_the_table_and_month_it_belongs_to() -> None:
    partition = DroppedPartition(
        table="alerts",
        year=2026,
        month=1,
        name="alerts_2026_01",
        statement="DROP TABLE IF EXISTS alerts_2026_01",
        covers=(date(2026, 1, 1), date(2026, 2, 1)),
    )
    assert (partition.table, partition.year, partition.month) == ("alerts", 2026, 1)
