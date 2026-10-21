"""The database side of retention: the real partition catalog and the partition runner.

:mod:`app.services.retention` decides *what* may be dropped and is a pure function of
its inputs. This module supplies the two things it cannot have on its own, and does
them against PostgreSQL:

* :func:`list_partitions` reads the monthly partitions that actually exist, from
  ``pg_inherits``. The retention plan is only as honest as this list: a plan built on
  a guessed catalog reports drops that were never there.
* :class:`CatalogRunner` executes the drop statements the plan names. It accepts one
  shape of statement -- ``DROP TABLE IF EXISTS <table>_<YYYY>_<MM>`` for a partitioned
  table -- and refuses everything else, so the runner cannot be pointed at a table
  that is not a retention partition.

Both refuse a name they cannot account for, loudly. A partition that matches no rule
is one retention would never drop, and a silent skip there is the failure this
module exists to prevent.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from app.db.models import PARTITIONED_TABLES
from app.db.partitions import partition_name

__all__ = [
    "SWEEPABLE_TABLES",
    "CatalogRunner",
    "list_partitions",
    "sweep_expired_rows",
]

#: ``<table>_<YYYY>_<MM>``, the name :func:`partition_name` produces.
_PARTITION_NAME = re.compile(r"([a-z_]+)_(\d{4})_(\d{2})")
_DROP_STATEMENT = re.compile(r"DROP TABLE IF EXISTS ([a-z_]+_\d{4}_\d{2})")

_CATALOG = text("""
    SELECT parent.relname AS parent_name, child.relname AS child_name
    FROM pg_inherits AS link
    JOIN pg_class AS child ON child.oid = link.inhrelid
    JOIN pg_class AS parent ON parent.oid = link.inhparent
    JOIN pg_namespace AS ns ON ns.oid = child.relnamespace
    WHERE ns.nspname = current_schema()
      AND parent.relname = ANY(:tables)
    """)

#: Non-partitioned tables that age out by row, and the column that dates them. Both
#: are indexed on that column (``ix_*_timestamp``), so the sweep is a range read. The
#: table names are a fixed allowlist: they are interpolated into SQL below, and nothing
#: outside this mapping ever reaches that interpolation.
SWEEPABLE_TABLES: dict[str, str] = {
    "log_events": "timestamp",
    "flow_events": "timestamp",
}

#: One fixed statement per sweepable table. Written out rather than built from the table
#: name, so no SQL is assembled at runtime; the table list above is the same set.
_SWEEP_STATEMENTS: dict[str, Any] = {
    "log_events": text(
        "DELETE FROM log_events WHERE id IN (SELECT id FROM log_events "
        "WHERE timestamp < :cutoff ORDER BY timestamp LIMIT :batch)"
    ),
    "flow_events": text(
        "DELETE FROM flow_events WHERE id IN (SELECT id FROM flow_events "
        "WHERE timestamp < :cutoff ORDER BY timestamp LIMIT :batch)"
    ),
}

#: Rows removed per transaction. A bounded batch keeps each statement short and each
#: lock brief on a table that is still being written.
SWEEP_BATCH_ROWS = 5_000

#: Upper bound on batches in one run. A run that hits it reports how far it got, and
#: the next run continues: retention is periodic, so a backlog drains over runs.
SWEEP_MAX_BATCHES = 200


def list_partitions(engine: Engine) -> set[tuple[str, int, int]]:
    """Every ``(table, year, month)`` monthly partition that exists right now.

    Raises:
        ValueError: if a child of a partitioned table is not named the way
            :func:`partition_name` names it. Such a partition cannot be planned, so
            it would survive every run; the answer is to say so, not to skip it.
    """
    with engine.connect() as conn:
        rows: Sequence[tuple[str, str]] = conn.execute(
            _CATALOG, {"tables": sorted(PARTITIONED_TABLES)}
        ).all()
    found: set[tuple[str, int, int]] = set()
    for parent, child in rows:
        match = _PARTITION_NAME.fullmatch(child)
        if match is None or match.group(1) != parent:
            msg = (
                f"partition {child!r} of {parent!r} does not follow the "
                "<table>_<YYYY>_<MM> naming retention depends on"
            )
            raise ValueError(msg)
        year, month = int(match.group(2)), int(match.group(3))
        if not 1 <= month <= 12 or partition_name(parent, year, month) != child:
            msg = f"partition {child!r} names a month that does not exist"
            raise ValueError(msg)
        found.add((parent, year, month))
    return found


class CatalogRunner:
    """Executes the retention plan's drop statements against the database.

    Satisfies :class:`app.services.retention.StatementRunner`: each call runs one
    statement and returns whether it changed the catalog, which is what makes a second
    run of the same plan a measurable no-op.
    """

    def __init__(self, engine: Engine) -> None:
        """Bind the runner to an engine. No connection is opened here."""
        self._engine = engine

    def __call__(self, statement: str) -> bool:
        """Drop one named partition, returning whether it existed beforehand.

        Raises:
            ValueError: if the statement is not a drop of a retention partition.
        """
        match = _DROP_STATEMENT.fullmatch(statement)
        if match is None:
            msg = f"refusing to run {statement!r}: retention only drops monthly partitions"
            raise ValueError(msg)
        name = match.group(1)
        parsed = _PARTITION_NAME.fullmatch(name)
        if parsed is None or parsed.group(1) not in PARTITIONED_TABLES:
            msg = f"refusing to drop {name!r}: it is not a partition of a retained table"
            raise ValueError(msg)
        with self._engine.begin() as conn:
            existed = bool(
                conn.execute(
                    text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}
                ).scalar_one()
            )
            conn.exec_driver_sql(statement)
        return existed


def sweep_expired_rows(
    engine: Engine,
    *,
    cutoff: datetime,
    tables: dict[str, str] | None = None,
    batch_rows: int = SWEEP_BATCH_ROWS,
    max_batches: int = SWEEP_MAX_BATCHES,
) -> dict[str, int]:
    """Delete rows older than ``cutoff`` from the row-swept tables, in bounded batches.

    A row delete is the only way to age out a table that is not partitioned. It leaves
    dead tuples until vacuum, so it is weaker than a partition drop for erasure; the
    retention report says so. It is still the right mechanism here: the alternative is
    rows that never expire.

    Returns:
        Rows deleted per table in this run. A table that hit ``max_batches`` has more
        expired rows waiting, and the next run continues from there.

    Raises:
        ValueError: if a table is not on the allowlist or the batch sizes are not
            positive.
    """
    if batch_rows < 1 or max_batches < 1:
        msg = "batch_rows and max_batches must both be at least 1"
        raise ValueError(msg)
    chosen = SWEEPABLE_TABLES if tables is None else tables
    deleted: dict[str, int] = {}
    for table, column in chosen.items():
        if SWEEPABLE_TABLES.get(table) != column or table not in _SWEEP_STATEMENTS:
            msg = f"{table!r}.{column!r} is not a row-swept table"
            raise ValueError(msg)
        statement = _SWEEP_STATEMENTS[table]
        total = 0
        for _ in range(max_batches):
            with engine.begin() as conn:
                removed = conn.execute(statement, {"cutoff": cutoff, "batch": batch_rows}).rowcount
            total += removed
            if removed < batch_rows:
                break
        deleted[table] = total
    return deleted
