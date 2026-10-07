"""The persistent log read model (T-419, FR-02, design.md §4.5).

The log explorer read a process's own bounded tail (T-407): 20,000 lines or 15
minutes, whichever came first, gone on restart and different in every worker. This
module is the store that replaces it — ``log_events``, written the moment a line is
accepted and read back by time window, filter and cluster key.

**What the criterion asks for, and how each half is answered.**

* *Served from storage rather than from memory.* Both reads are SQL over
  ``log_events`` (see :mod:`app.db.log_statements`); the tail is not consulted, and
  the response says ``source: store`` so a screen can say the same.
* *Survives a restart.* Nothing here is process state. The only thing this module
  keeps is a 30-second cache of the store's own coverage — its oldest line, newest
  line and size — which is derived from the table and therefore reproducible.
* *Spans more than the retention window.* The span bound is
  :data:`~app.db.repository.MAX_QUERY_SPAN_DAYS`, the same 92 days every other
  windowed read in this codebase honours, instead of the tail's 15 minutes.
* *Answers a filter the tail cannot.* A time range older than the retention, or a
  host that has logged nothing since it aged out, both read here: the rows are in
  the table, so the window decides what is visible rather than the process's memory.

**Only accepted lines are stored**, because the write happens where T-407's tail
write happened: after the batch was validated, admitted and handed to the broker, so
a stored line is one the pipeline saw, and a rejected record is in neither.

**Two facts this module reports rather than hides (R-70).**

* Its **coverage** — oldest line, newest line, how many it holds — is on every
  response, so an empty window can be read for what it is. It is measured with three
  aggregates that are cached for ``log_store_coverage_ttl_seconds``: a number nobody
  refreshes is a lie with a timestamp, and a number measured per read is three
  queries nobody needed.
* Its **eviction** it cannot report, because nothing evicts yet: FR-05's raw-record
  window reaches these rows through a retention job that is not built, and the plan
  in :mod:`app.services.retention` names that gap instead of implying the data is
  trimmed. ``dropped_lines`` is therefore ``None``, which is what "this source cannot
  say" looks like — not zero, which would mean "nothing was ever lost".
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.log_statements import (
    ClusterRows,
    cluster_levels_statement,
    cluster_rows_statement,
    coverage_statement,
    distinct_cluster_count_statement,
    line_rows_statement,
    untemplated_line_count_statement,
    window_line_count_statement,
)
from app.db.models import LogEvent
from app.db.repository import MAX_QUERY_SPAN_DAYS, TimeRange
from app.schemas.ingest import LogLevel, LogRecordIn
from app.schemas.logs import LogClusterOut, LogLineOut, LogLinesOut, LogTailOut
from app.services.log_keys import MESSAGE_KEY_PREFIX, cluster_key
from app.services.log_tail import LogWindow, level_rank

__all__ = [
    "Coverage",
    "LogStoreUnavailable",
    "PostgresLogStore",
]


class LogStoreUnavailable(RuntimeError):
    """The store was configured but could not be reached or read.

    Raised instead of letting a driver error reach the response, and — more
    importantly — instead of answering from somewhere smaller. A log screen that
    quietly showed the tail's 15 minutes because the database was down would look
    exactly like a quiet system, and an analyst would believe it (R-70).

    The message carries the driver's own words, because "Postgres is down" and "the
    password is wrong" and "the table has not been migrated" are three different
    problems for the operator. It carries no row content, and the driver's error for a
    failed connection has none (R-58).
    """


#: The store's own answer to "how far back can I read", in seconds. Not a retention
#: policy -- the rows stay until a retention job removes them -- but the widest range
#: one query will cover, which is the same bound every other read in this codebase
#: honours (R-34).
MAX_SPAN_SECONDS: float = MAX_QUERY_SPAN_DAYS * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the store holds right now, as three aggregates describe it.

    Attributes:
        oldest: the oldest stored instant, or ``None`` when the table is empty.
        newest: the newest stored instant, or ``None`` when the table is empty.
        held: how many lines the table holds.
    """

    oldest: datetime | None
    newest: datetime | None
    held: int

    @property
    def empty(self) -> bool:
        """Whether the store holds nothing at all."""
        return self.held == 0


class PostgresLogStore:
    """The ``log_events`` table, read and written through an async session factory.

    Args:
        session_factory: an :func:`~app.db.engine.async_session_factory` over the
            deployment's database. Injected rather than built here so the store can
            be tested against a fake session and a real one without knowing which.
        coverage_ttl_seconds: how long the store's description of itself is reused.
        clock: monotonic seconds, injectable so a test can age the cache instead of
            sleeping.
    """

    __slots__ = ("_clock", "_coverage", "_coverage_at", "_session_factory", "_ttl")

    #: What the response's ``source`` says when this is the reader.
    name = "store"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        coverage_ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Build a store over one session factory.

        Raises:
            ValueError: if the coverage's lifetime is not positive. A zero lifetime
                would mean "measure on every read", which is a decision to make in
                configuration rather than by accident.
        """
        if coverage_ttl_seconds <= 0:
            msg = f"coverage_ttl_seconds must be positive, got {coverage_ttl_seconds}"
            raise ValueError(msg)
        self._session_factory = session_factory
        self._ttl = coverage_ttl_seconds
        self._clock = clock
        self._coverage: Coverage | None = None
        self._coverage_at: float | None = None

    @property
    def max_span_seconds(self) -> float:
        """The widest window this source will answer, in seconds."""
        return MAX_SPAN_SECONDS

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """One session, with every driver error translated into one domain error.

        Every statement this store runs goes through here, so "the store is
        unreachable" reaches the route as :class:`LogStoreUnavailable` and the caller
        gets a 503 naming the dependency, rather than a raw ``OperationalError``
        escaping as a 500 with a connection string in it.
        """
        try:
            async with self._session_factory() as session:
                yield session
        except SQLAlchemyError as exc:
            msg = f"the log store is configured but could not be read: {exc}"
            raise LogStoreUnavailable(msg) from exc

    async def append(self, records: Sequence[LogRecordIn]) -> int:
        """Store a batch of accepted lines in one transaction, returning how many.

        One transaction per batch: a partially stored batch would leave a window
        that is half-present, and every count on the screen would then be a count of
        something the collector did not send in that shape.

        Returns:
            How many records were stored. The caller passes accepted records only,
            like the tail's hook, so this is also the number it handed in.
        """
        if not records:
            return 0
        rows = [
            {
                "timestamp": record.timestamp,
                "host": record.host,
                "service": record.service,
                "level": record.level.value,
                "message": record.message,
                # Normalised the same way the key is: a blank template id is "not
                # mined", not a template named "".
                "template_id": (record.template_id or "").strip() or None,
                "parameters": dict(record.parameters),
                # The key is computed here, by the function the tail folds by, and
                # stored: see app.services.log_keys.
                "key": cluster_key(record),
            }
            for record in records
        ]
        async with self._session() as session, session.begin():
            await session.execute(insert(LogEvent), rows)
        # A write makes the store's description of itself stale; drop it now rather
        # than serving a coverage that predates the batch the caller just stored.
        self._coverage = None
        self._coverage_at = None
        return len(rows)

    async def coverage(self, *, refresh: bool = False) -> Coverage:
        """The instants the store spans and how many lines it holds, cached.

        Args:
            refresh: measure now instead of reusing the cached answer. Used when a
                read is about to report the coverage, and used by tests.
        """
        if not refresh and self._coverage is not None and self._coverage_at is not None:
            age = self._clock() - self._coverage_at
            if age < self._ttl:
                return self._coverage
        async with self._session() as session:
            row = (await session.execute(coverage_statement())).one()
        measured = Coverage(oldest=row[0], newest=row[1], held=int(row[2]))
        self._coverage = measured
        self._coverage_at = self._clock()
        return measured

    async def clusters(self, window: LogWindow, *, limit: int) -> LogTailOut:
        """Fold the window's stored lines into clusters, the busiest first.

        Four queries, and each is one question the response has to answer: the fold
        itself (limited), the level histogram for the rows it returned (bounded by
        that limit), how many clusters exist before the limit, and how many lines
        matched before the limit. The fifth and sixth -- how many lines the window
        holds *without* the filters, and how many matched lines carry no template id
        -- are asked only when they change what the response says, which is when the
        read found nothing to show and when it found something to explain.

        Raises:
            ValueError: if ``limit`` is not positive, or the window is inverted or
                wider than 92 days (the :class:`TimeRange` constructor's own rules).
        """
        time_range = _range_of(window)
        async with self._session() as session:
            rows = [
                _cluster_row(row)
                for row in (
                    await session.execute(
                        cluster_rows_statement(
                            time_range,
                            host=window.host,
                            service=window.service,
                            level=window.level,
                            limit=limit,
                        )
                    )
                ).all()
            ]
            levels: dict[str, dict[str, int]] = {}
            if rows:
                level_rows = (
                    await session.execute(
                        cluster_levels_statement(
                            time_range,
                            keys=[row.key for row in rows],
                            host=window.host,
                            service=window.service,
                            level=window.level,
                        )
                    )
                ).all()
                for key, level, lines in level_rows:
                    levels.setdefault(key, {})[level] = int(lines)
            cluster_count = int(
                (
                    await session.execute(
                        distinct_cluster_count_statement(
                            time_range,
                            host=window.host,
                            service=window.service,
                            level=window.level,
                        )
                    )
                ).scalar_one()
            )
            matched = int(
                (
                    await session.execute(
                        window_line_count_statement(
                            time_range,
                            host=window.host,
                            service=window.service,
                            level=window.level,
                            key=window.key,
                        )
                    )
                ).scalar_one()
            )
            present = matched
            if matched == 0:
                present = int(
                    (await session.execute(window_line_count_statement(time_range))).scalar_one()
                )
            untemplated = 0
            if matched:
                untemplated = int(
                    (
                        await session.execute(
                            untemplated_line_count_statement(
                                time_range,
                                host=window.host,
                                service=window.service,
                                level=window.level,
                                key=window.key,
                            )
                        )
                    ).scalar_one()
                )
        coverage = await self.coverage()
        truncated = cluster_count > len(rows)
        return LogTailOut(
            source="store",
            start=window.start,
            end=window.end,
            clusters=[_cluster_of(row, levels.get(row.key, {})) for row in rows],
            lines_seen=matched,
            clusters_seen=cluster_count,
            clusters_truncated=truncated,
            retained_from=coverage.oldest,
            retained_to=coverage.newest,
            retained_lines=coverage.held,
            dropped_lines=None,
            caveats=_store_caveats(
                window=window,
                matched=matched,
                present=present,
                coverage=coverage,
                truncated=truncated,
                untemplated=untemplated,
            ),
        )

    async def lines(self, window: LogWindow, *, limit: int) -> LogLinesOut:
        """The newest ``limit`` stored lines the window matches, oldest first.

        Same order and same cap as the tail's read -- the newest rows are kept and
        the response says so -- because a cluster expansion read from the store and
        one read from a tail are the same screen.

        Raises:
            ValueError: if ``limit`` is not positive, or the window is unusable.
        """
        time_range = _range_of(window)
        async with self._session() as session:
            matched = int(
                (
                    await session.execute(
                        window_line_count_statement(
                            time_range,
                            host=window.host,
                            service=window.service,
                            level=window.level,
                            key=window.key,
                        )
                    )
                ).scalar_one()
            )
            rows = (
                await session.execute(
                    line_rows_statement(
                        time_range,
                        host=window.host,
                        service=window.service,
                        level=window.level,
                        key=window.key,
                        limit=limit,
                    )
                )
            ).all()
            present = matched
            if matched == 0:
                present = int(
                    (await session.execute(window_line_count_statement(time_range))).scalar_one()
                )
        coverage = await self.coverage()
        truncated = matched > len(rows)
        # Newest first out of SQL, oldest first onto the wire: a stack trace read
        # backwards is a different story (T-407's rule, kept).
        ordered = list(reversed(rows))
        return LogLinesOut(
            source="store",
            start=window.start,
            end=window.end,
            key=window.key,
            lines=[
                LogLineOut(
                    timestamp=row[0],
                    host=row[1],
                    service=row[2],
                    level=LogLevel(row[3]),
                    message=row[4],
                    template_id=row[5],
                    parameters=dict(row[6]),
                    key=row[7],
                )
                for row in ordered
            ],
            lines_seen=matched,
            lines_truncated=truncated,
            retained_from=coverage.oldest,
            retained_to=coverage.newest,
            retained_lines=coverage.held,
            dropped_lines=None,
            caveats=_store_caveats(
                window=window,
                matched=matched,
                present=present,
                coverage=coverage,
                truncated=truncated,
                untemplated=0,
            ),
        )


def _range_of(window: LogWindow) -> TimeRange:
    """Validate a window into a :class:`TimeRange`, or refuse it.

    The route already bounds the span against the source; this is the second layer,
    and the one that a caller reaching the store directly still gets.
    """
    return TimeRange(start=window.start, end=window.end)


def _cluster_row(row: Any) -> ClusterRows:
    """One aggregate row as a :class:`ClusterRows`.

    Unpacked by position and converted by hand rather than trusting the driver's
    types: this is the boundary between SQL and the wire, and a ``Decimal`` or a
    naive datetime that got through here would surface as a schema error three
    layers away.
    """
    key, lines, first_seen, last_seen, message, parameters, hosts, services = row
    return ClusterRows(
        key=str(key),
        lines=int(lines),
        first_seen=first_seen,
        last_seen=last_seen,
        sample_message=str(message),
        sample_parameters=dict(parameters or {}),
        hosts=[str(host) for host in (hosts or [])],
        services=[str(service) for service in (services or [])],
    )


def _cluster_of(row: ClusterRows, levels: dict[str, int]) -> LogClusterOut:
    """One cluster row as the wire model.

    ``template_id`` is derived from the key rather than stored twice: the key *is*
    the template id when the collector mined one, and the prefix says when it is
    not. Levels come back ordered by severity, like the tail's, because a level
    listing sorted alphabetically puts ``critical`` before ``debug``.
    """
    ordered = sorted(levels.items(), key=lambda item: level_rank(LogLevel(item[0])))
    return LogClusterOut(
        key=row.key,
        template_id=None if row.key.startswith(MESSAGE_KEY_PREFIX) else row.key,
        count=row.lines,
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        worst_level=(
            max((LogLevel(level) for level in levels), key=level_rank) if levels else LogLevel.INFO
        ),
        levels=dict(ordered),
        hosts=sorted(row.hosts),
        services=sorted(row.services),
        sample_message=row.sample_message,
        parameters=row.sample_parameters,
    )


def _store_caveats(
    *,
    window: LogWindow,
    matched: int,
    present: int,
    coverage: Coverage,
    truncated: bool,
    untemplated: int,
) -> list[str]:
    """What a reader must know to read a stored answer (R-70, R-74).

    The same four facts the tail reports, asked of a store: nothing was ever
    stored, the window falls outside what is stored, nothing matched the filters, or
    the read hit its row limit. A fifth sentence is specific to this source -- the
    store cannot report evictions, because nothing evicts yet -- and it is a sentence
    rather than a silent ``None`` in the response body, because a screen should not
    have to know which fields a source fills in to read it honestly.
    """
    caveats = [
        (
            "These lines are read from the log store (the log_events table), so they "
            "survive a restart and a second worker sees them. Only accepted lines are "
            "in it."
        )
    ]
    if coverage.empty:
        caveats.append(
            "No log line has been stored yet, so this window is empty because there is "
            "nothing to show rather than because nothing matched."
        )
    elif matched == 0 and present == 0:
        if coverage.oldest is not None and window.end <= coverage.oldest:
            caveats.append(
                f"Nothing is stored at or before {window.end.isoformat()}: the oldest "
                f"stored line is from {coverage.oldest.isoformat()}."
            )
        elif coverage.newest is not None and window.start >= coverage.newest:
            caveats.append(
                f"Nothing has been stored at or after {window.start.isoformat()}: the "
                f"newest stored line is from {coverage.newest.isoformat()}."
            )
        else:
            caveats.append(
                f"No line was stored inside this window. The store holds "
                f"{coverage.held:,} lines; this window falls between them."
            )
    elif matched == 0:
        caveats.append(
            "Nothing matched these filters, though the window does hold lines: the "
            "filter is what removed them, not the store."
        )
    if truncated:
        caveats.append("This read hit its row limit; only the rows shown are listed.")
    if untemplated:
        caveats.append(
            f"{untemplated:,} of {matched:,} matching lines carry no template id, so "
            "they are grouped by a digest of their exact message rather than by a "
            "mined template."
        )
    caveats.append(
        "A cluster's severity is the worst level among its lines, not a model's anomaly "
        "score: no log model is served in this build, so nothing here is called anomalous."
    )
    caveats.append(
        "Nothing evicts rows from the store yet: FR-05's raw-record window reaches this "
        "table through a retention job that is not built, so this read cannot say what "
        "has been removed."
    )
    return caveats
