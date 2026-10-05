r"""Monthly partition DDL as pure functions (T-301).

Kept as string builders rather than inline SQL in the migration for one reason:
a migration cannot be executed in this repository's CI, because declarative
partitioning is PostgreSQL-only and the test suite runs without a server. Pure
functions can be asserted against exactly, so the DDL is checked even though it
cannot be applied here.

Partition names are derived from the month they cover — ``alerts_2026_03`` — so
the name is a function of the range and the same month always produces the same
name. A name carrying a timestamp of when it was created would make two runs of
the same migration disagree.

There is no default partition, deliberately. A row outside every partition is
rejected, which is loud; a default partition accepts it silently and accumulates
until it is the largest table in the database, defeating the retention model that
dropping partitions provides (NFR-05, GDPR erasure).
"""

from __future__ import annotations

from datetime import date

from app.db.models import PARTITIONED_TABLES


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """The first day of a month and the first day of the next.

    Raises:
        ValueError: if the month is out of range.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def partition_name(table: str, year: int, month: int) -> str:
    """The name of one monthly partition.

    Raises:
        ValueError: if ``table`` is not partitioned.
    """
    if table not in PARTITIONED_TABLES:
        raise ValueError(f"{table!r} is not a partitioned table")
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    return f"{table}_{year}_{month:02d}"


def create_partition_sql(table: str, year: int, month: int) -> str:
    """``CREATE TABLE ... PARTITION OF ... FOR VALUES FROM ... TO ...``."""
    start, end = month_bounds(year, month)
    return (
        f"CREATE TABLE IF NOT EXISTS {partition_name(table, year, month)} "
        f"PARTITION OF {table} FOR VALUES FROM ('{start.isoformat()}') "
        f"TO ('{end.isoformat()}')"
    )


def drop_partition_sql(table: str, year: int, month: int) -> str:
    """``DROP TABLE IF EXISTS`` for one partition.

    This is the retention mechanism, and why erasure under GDPR is a ``DROP``
    rather than a ``DELETE``: dropping a partition is immediate and leaves
    nothing behind, whereas deleting rows leaves them in dead tuples and in any
    replica or backup until vacuum.
    """
    return f"DROP TABLE IF EXISTS {partition_name(table, year, month)}"


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    """Every ``(year, month)`` a half-open date range covers.

    Raises:
        ValueError: if the range is empty or inverted.
    """
    if end <= start:
        raise ValueError(f"empty or inverted range: {start} to {end}")
    covered: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        covered.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return covered


__all__ = [
    "create_partition_sql",
    "drop_partition_sql",
    "month_bounds",
    "months_between",
    "partition_name",
]
