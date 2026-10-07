"""Retention: which months may be dropped, and by which right (NFR-05, T-314).

Two things are true at once about deleting old data here, and the design follows
from holding both.

**Retention is a partition drop, not a row delete.** ``alerts`` and
``ingest_stats`` are partitioned monthly (``architecture.md`` §6), so the cheap,
complete way to remove a month is ``DROP TABLE``: it is immediate, it reclaims
the files, and it leaves nothing behind in dead tuples, replicas or WAL. A row
``DELETE`` over the same range leaves the data readable in backups and in any
replica for longer than the window promised, which for a privacy obligation is
the whole point. `app.db.partitions` already builds that DDL; this module decides
*when* it may be run.

**A month is droppable only when all of it is outside the window.** The
distinction that matters is between "this month is old" and "every row in this
month is old". A partition covering a boundary month contains rows that are still
inside the retention window, and dropping it would erase data the policy promises
to keep -- the failure is silent, because the service reports success. So the test
is on the partition's *end* bound: ``end <= cutoff``, never ``start <= cutoff``.
A partition that straddles the cutoff is left alone until it does not, which is
why retention is a periodic job and not a one-shot migration.

**Time comes in, not from the clock.** :func:`plan_retention` takes ``today`` and
the set of existing partitions as arguments, so the plan is a pure function of
its inputs -- assertable without a database, a clock or a task scheduler, which is
the only way the boundary rule above can be proven rather than trusted.

**Two windows cannot invert.** The policy refuses ``alerts_days < raw_days``:
derived summaries may outlive the raw payloads they came from (design.md's
"evidence expired" state is exactly that), but a deployment keeping the more
sensitive artefact -- the raw record -- longer than the derived one would have
inverted the privacy intent of FR-05.

**What this module cannot evict is reported, not hidden.** ``audit_log`` is not
partitioned and R-31 forbids rewriting its rows, so no partition drop reaches it
and no row delete is allowed; ``log_events`` (T-419's store) is not partitioned
either, so an old log line in it survives every plan this module can make. Both appear
in every plan as ``unevictable``, with the reason. The same is true of the raw records themselves
(FR-05's 30 days): they live in Kafka and Elasticsearch, whose retention is
configured in the deployment rather than executed here, so the plan names the
window and the mechanism instead of pretending to have trimmed them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from app.db.models import PARTITIONED_TABLES
from app.db.partitions import drop_partition_sql, month_bounds, partition_name

__all__ = [
    "DEFAULT_ALERT_DAYS",
    "DEFAULT_RAW_RECORD_DAYS",
    "DEFAULT_STATS_DAYS",
    "PARTITION_WINDOWS",
    "DropPlan",
    "DroppedPartition",
    "RetentionPlan",
    "RetentionPolicy",
    "RetentionRun",
    "StatementRunner",
    "Unevictable",
    "apply_retention",
    "existing_partitions",
    "plan_retention",
]

#: FR-05's number: raw ingested records are kept 30 days by default "so alerts
#: remain reproducible". It is a policy value here because the records themselves
#: live in Kafka and Elasticsearch; see the module docstring.
DEFAULT_RAW_RECORD_DAYS = 30

#: Alerts are the analyst-facing record and the thing an investigation cites, so
#: they outlive the evidence. 400 days rather than 365: a year-over-year
#: comparison has to reach back past the same month last year, and a window that
#: ends exactly at 365 cannot see it.
DEFAULT_ALERT_DAYS = 400

#: Ingest counters are metadata -- counts per window, no record content -- and
#: share the alert window so one monthly partition boundary explains both.
DEFAULT_STATS_DAYS = 400

#: Which window applies to which partitioned table. Keys are checked against the
#: model's own list, so a table that gains partitioning without gaining a window
#: fails loudly here rather than silently never being evicted.
PARTITION_WINDOWS: dict[str, str] = {
    "alerts": "alerts_days",
    "ingest_stats": "stats_days",
}

#: Non-partitioned tables that carry retained data, and why they cannot be
#: evicted. Reported in every plan: an operator reading a retention report is
#: entitled to know what it did *not* reach.
UNEVICTABLE_REASONS: dict[str, str] = {
    "audit_log": (
        "append-only (R-31) and not partitioned: no partition drop reaches it and "
        "a row delete is forbidden. Retention for the trail needs its own "
        "partitioning, which is a schema change (recorded, not done here)"
    ),
    "log_events": (
        "the log store (T-419), not partitioned: FR-05's raw-record window reaches "
        "it through a sweep of its own, which is not built, so no plan here removes "
        "an old line. Named rather than omitted because 'retention covers "
        "everything' is exactly the assumption a report like this must not invite"
    ),
    "flow_events": (
        "the traffic read model (T-418), not partitioned and swept by nothing: the "
        "same gap the log store names, and the same reason for naming it here -- a "
        "deployment reading this report must not believe the flows age out"
    ),
}

#: Where FR-05's raw records live, and what enforces their window. Named because
#: the plan is the natural place to look for them.
EXTERNAL_RETENTION: dict[str, str] = {
    "kafka": "AEGIS_KAFKA_RETENTION_HOURS on the flow/log topics",
    "elasticsearch": "index lifecycle management policy for the flow/log indices",
}


class StatementRunner(Protocol):
    """Executes one DDL statement and says whether it changed anything.

    The boolean is not decoration: it is what makes "run the plan twice" a
    measurable no-op rather than a claim. ``DROP TABLE IF EXISTS`` succeeds when
    the table is already gone, so a runner that returned nothing could not
    distinguish "dropped" from "there was nothing to drop".
    """

    def __call__(self, statement: str) -> bool:
        """Run ``statement``; return whether it changed the catalog."""
        ...


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """The windows, in days, that a deployment retains each class of data.

    Attributes:
        raw_records_days: FR-05's window for the raw ingested records. Enforced
            outside this service (Kafka and Elasticsearch); carried here so one
            object answers "what is the policy" and the plan can report it.
        alerts_days: how long an alert row is kept, enforced by partition drop.
        stats_days: how long an ingest counter is kept, likewise.
    """

    raw_records_days: int = DEFAULT_RAW_RECORD_DAYS
    alerts_days: int = DEFAULT_ALERT_DAYS
    stats_days: int = DEFAULT_STATS_DAYS

    def __post_init__(self) -> None:
        """Refuse windows that could not be honoured, or that invert privacy."""
        for name in ("raw_records_days", "alerts_days", "stats_days"):
            value = getattr(self, name)
            if value < 1:
                raise ValueError(f"{name} must be at least 1 day, got {value}")
            if value > 3650:
                raise ValueError(
                    f"{name} is {value} days; a window over ten years is almost "
                    "certainly a units mistake (days, not years)"
                )
        if self.alerts_days < self.raw_records_days:
            raise ValueError(
                f"alerts_days ({self.alerts_days}) must not be shorter than "
                f"raw_records_days ({self.raw_records_days}): raw records are the "
                "more sensitive artefact, and a policy that keeps them longer than "
                "the alerts derived from them inverts FR-05's intent"
            )

    def days_for(self, table: str) -> int:
        """The window for one partitioned table.

        Raises:
            ValueError: if the table has no window. A partitioned table nobody
                set a window for would otherwise be retained forever in silence.
        """
        field_name = PARTITION_WINDOWS.get(table)
        if field_name is None:
            raise ValueError(
                f"no retention window is defined for {table!r}; add one to "
                "PARTITION_WINDOWS rather than letting it accumulate forever"
            )
        value: int = getattr(self, field_name)
        return value

    def cutoff_for(self, table: str, *, today: date) -> date:
        """The first date that is still inside the window for ``table``."""
        return today - timedelta(days=self.days_for(table))


@dataclass(frozen=True, slots=True)
class DroppedPartition:
    """One month a plan will drop.

    Attributes:
        table: the partitioned table the partition belongs to.
        year: the month's year.
        month: 1..12.
        name: the partition's name, a function of table and month.
        statement: the ``DROP TABLE IF EXISTS`` to run.
        covers: half-open ``(start, end)`` dates, so a report can show exactly
            which rows the drop removes.
    """

    table: str
    year: int
    month: int
    name: str
    statement: str
    covers: tuple[date, date]


@dataclass(frozen=True, slots=True)
class Unevictable:
    """A table the plan will not touch, and the reason in one sentence."""

    table: str
    reason: str


@dataclass(frozen=True, slots=True)
class DropPlan:
    """The droppable months for one table.

    Attributes:
        table: which table.
        window_days: the window that produced the decision.
        cutoff: the first date inside the window; a partition ends at or before
            this to be droppable.
        partitions: the months to drop, oldest first.
    """

    table: str
    window_days: int
    cutoff: date
    partitions: tuple[DroppedPartition, ...]


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    """What a retention run would do, now.

    Attributes:
        planned_at: the date the plan was computed for.
        policy: the windows used.
        drops: one :class:`DropPlan` per partitioned table, in a stable order.
        kept: partitions that exist and are inside the window, with their spans.
        missing: ``(table, year, month)`` the plan expects but the catalog does
            not have -- an operator-visible warning, because a missing partition
            means ingests in that month were rejected (there is no default
            partition, deliberately).
        unevictable: tables carrying retained data that no partition drop
            reaches.
        external: the raw-record window and what enforces it, reported because
            FR-05 names the window and this service does not execute it.
    """

    planned_at: date
    policy: RetentionPolicy
    drops: tuple[DropPlan, ...]
    kept: tuple[DroppedPartition, ...]
    missing: tuple[tuple[str, int, int], ...]
    unevictable: tuple[Unevictable, ...]
    external: dict[str, str] = field(default_factory=dict)

    @property
    def statements(self) -> tuple[str, ...]:
        """Every ``DROP`` the plan would run, oldest first, table by table."""
        return tuple(partition.statement for plan in self.drops for partition in plan.partitions)

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing to drop."""
        return not self.statements


@dataclass(frozen=True, slots=True)
class RetentionRun:
    """What a retention run did.

    Attributes:
        started_at: timezone-aware start time.
        planned: the partitions the run intended to drop.
        dropped: the partitions whose drop the runner reported as a change.
        already_absent: partitions the plan expected but the catalog no longer
            had -- the second run of the same plan reports every one of these,
            which is what "idempotent" means for a ``DROP TABLE IF EXISTS``.
    """

    started_at: datetime
    planned: tuple[DroppedPartition, ...]
    dropped: tuple[DroppedPartition, ...]
    already_absent: tuple[DroppedPartition, ...]

    @property
    def is_noop(self) -> bool:
        """Whether the run changed nothing."""
        return not self.dropped


def existing_partitions(months: Iterable[tuple[str, int, int]]) -> set[tuple[str, int, int]]:
    """Normalise what a catalog query returned into ``(table, year, month)``.

    Raises:
        ValueError: if a month is out of range. A malformed catalog answer would
            otherwise be silently ignored, and a partition nobody knows about is
            a partition retention never drops.
    """
    found: set[tuple[str, int, int]] = set()
    for table, year, month in months:
        if table not in PARTITIONED_TABLES:
            raise ValueError(f"{table!r} is not a partitioned table")
        if not 1 <= month <= 12:
            raise ValueError(f"month must be 1..12, got {month}")
        found.add((table, year, month))
    return found


def plan_retention(
    policy: RetentionPolicy,
    *,
    today: date,
    partitions: Iterable[tuple[str, int, int]],
) -> RetentionPlan:
    """Decide which months may be dropped, for every partitioned table.

    Args:
        policy: the windows.
        today: the day the plan is computed for. Injected so the plan is a pure
            function of its inputs.
        partitions: ``(table, year, month)`` triples that exist in the catalog.
            Callers with no database pass the months the deployment has created;
            a caller that passes none gets a plan that drops nothing and says so
            in ``missing``.

    Returns:
        The plan. A partition is droppable only when its **entire** month ends
        at or before the table's cutoff, so a boundary month is never dropped
        while any of its rows are still inside the window.

    Raises:
        ValueError: if ``partitions`` names a table with no window, or a month
            out of range.
    """
    present = existing_partitions(partitions)
    drops: list[DropPlan] = []
    kept: list[DroppedPartition] = []
    missing: list[tuple[str, int, int]] = []

    for table in sorted(PARTITIONED_TABLES):
        days = policy.days_for(table)
        cutoff = policy.cutoff_for(table, today=today)
        window = [entry for entry in sorted(present) if entry[0] == table]
        droppable: list[DroppedPartition] = []
        for _, year, month in window:
            start, end = month_bounds(year, month)
            partition = DroppedPartition(
                table=table,
                year=year,
                month=month,
                name=partition_name(table, year, month),
                statement=drop_partition_sql(table, year, month),
                covers=(start, end),
            )
            # end, not start: a month whose end is still inside the window has
            # rows the policy promises to keep.
            if end <= cutoff:
                droppable.append(partition)
            else:
                kept.append(partition)
        drops.append(
            DropPlan(table=table, window_days=days, cutoff=cutoff, partitions=tuple(droppable))
        )
        missing.extend(missing_months(table, window, policy, today=today))

    return RetentionPlan(
        planned_at=today,
        policy=policy,
        drops=tuple(drops),
        kept=tuple(kept),
        missing=tuple(missing),
        unevictable=tuple(
            Unevictable(table=table, reason=reason)
            for table, reason in sorted(UNEVICTABLE_REASONS.items())
        ),
        external=dict(EXTERNAL_RETENTION),
    )


def missing_months(
    table: str,
    window: Sequence[tuple[str, int, int]],
    policy: RetentionPolicy,
    *,
    today: date,
) -> list[tuple[str, int, int]]:
    """Months inside the window that the catalog has no partition for.

    A gap means rows for that month were rejected at insert -- there is no
    default partition, deliberately -- so the report names it rather than letting
    the plan's silence be read as "nothing to do".
    """
    if not window:
        return []
    earliest = min((year, month) for _, year, month in window)
    days = policy.days_for(table)
    start = today - timedelta(days=days)
    expected = _months_covering(start, today)
    present = {(year, month) for _, year, month in window}
    return [
        (table, year, month)
        for year, month in expected
        if (year, month) not in present and (year, month) >= earliest
    ]


def _months_covering(start: date, end: date) -> list[tuple[int, int]]:
    """Every ``(year, month)`` a date range touches, oldest first."""
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def apply_retention(
    plan: RetentionPlan,
    runner: StatementRunner,
    *,
    at: datetime | None = None,
) -> RetentionRun:
    """Run a plan's drops, oldest first, and report what changed.

    Args:
        plan: from :func:`plan_retention`.
        runner: executes one statement and reports whether it changed anything.
        at: start time; defaults to now, UTC.

    Returns:
        The run. Running the same plan twice is safe: the second run finds every
        partition already absent and reports them in ``already_absent``, so the
        only state a repeated run changes is nothing.

    Raises:
        RuntimeError: if a statement fails. The runner's exception propagates
            with the statement that failed attached to it -- a retention job that
            half-ran and reported success is the failure mode to avoid.
    """
    started = at or datetime.now(UTC)
    planned: list[DroppedPartition] = []
    dropped: list[DroppedPartition] = []
    absent: list[DroppedPartition] = []
    for plan_for_table in plan.drops:
        for partition in plan_for_table.partitions:
            planned.append(partition)
            try:
                changed = runner(partition.statement)
            except Exception as exc:  # noqa: BLE001 -- re-raised with context below
                msg = f"retention failed on {partition.name}: {exc}"
                raise RuntimeError(msg) from exc
            (dropped if changed else absent).append(partition)
    return RetentionRun(
        started_at=started,
        planned=tuple(planned),
        dropped=tuple(dropped),
        already_absent=tuple(absent),
    )
