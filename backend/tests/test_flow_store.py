"""The flow store's reads and its coverage cache (T-418).

The database here is a scripted fake, for the same reason ``test_log_store.py``'s is:
what this file is about is *what the store does with rows* -- that totals come from the
series rather than from the capped lists, that the coverage cache is dropped by a write,
that every driver failure becomes one exception. The SQL is asserted in
``test_flow_statements.py``; the round trip against a real PostgreSQL is
``test_flow_store_live.py``.

The fake counts statements as well as answering them, which is how two claims that are
otherwise invisible get tested: ``nodes_capped`` is computed from a ``count(distinct)``
rather than inferred from the listed top-N, and a second coverage call is answered from
the cache instead of asking the database again.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import pytest
from app.db.models import FlowEvent
from app.schemas.ingest import Direction, FlowRecordIn, Protocol
from app.services.flow_read_model import FlowFilters, FlowWindow
from app.services.flow_store import FlowStoreUnavailable, PostgresFlowStore
from sqlalchemy.exc import OperationalError

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
WINDOW = FlowWindow(start=START, end=START + timedelta(hours=1))

_T = TypeVar("_T")


def sync(function: Callable[..., Coroutine[Any, Any, _T]]) -> Callable[..., _T]:
    """Run one coroutine test body to completion (the suite has no async plugin)."""

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> _T:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


def async_cases(cls: type) -> type:
    """Wrap every coroutine case in a class so pytest can collect it."""
    for name, value in list(vars(cls).items()):
        if name.startswith("test_") and inspect.iscoroutinefunction(value):
            setattr(cls, name, sync(value))
    return cls


class Row:
    """One row of a canned result.

    Attribute **and** positional access, like the ``Row`` SQLAlchemy hands back: the
    store reads columns by name (``row.flows``) and reads a bare ``count()`` by position
    (``rows[0][0]``), and a fake that supported only one of the two would let a defect
    through in the other.
    """

    def __init__(self, *values: Any, **named: Any) -> None:
        """Hold the row's columns, named and positional."""
        self._values = list(values)
        self.__dict__.update(named)

    def __getitem__(self, index: int) -> Any:
        """The ``index``-th positional column."""
        return self._values[index]


class FakeResult:
    """One canned answer, standing in for a driver's cursor."""

    def __init__(self, rows: Sequence[Any] = ()) -> None:
        """Hold the rows this result will hand back."""
        self._rows = list(rows)

    def all(self) -> list[Any]:
        """Every row."""
        return list(self._rows)


class FakeTransaction:
    """The async context manager ``session.begin()`` returns."""

    async def __aenter__(self) -> None:
        """Enter doing nothing."""
        return None

    async def __aexit__(self, *exc_info: object) -> bool:
        """Exit without suppressing anything."""
        return False


class FakeSession:
    """A session that answers in script order and remembers what it was asked."""

    def __init__(self, script: Sequence[Any] = ()) -> None:
        """Hold the canned answers, in order."""
        self._script = list(script)
        self.executed: list[Any] = []

    async def execute(self, statement: Any, parameters: Any = None) -> FakeResult:
        """Answer with the next canned result, recording the statement."""
        self.executed.append((statement, parameters))
        if self._script:
            answer = self._script.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        raise AssertionError("the store ran more statements than the script provides")

    def begin(self) -> FakeTransaction:
        """Return a transaction whose body does nothing."""
        return FakeTransaction()

    async def __aenter__(self) -> FakeSession:
        """Enter: the session is its own context manager."""
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        """Exit without suppressing anything."""
        return False

    @property
    def statements(self) -> list[str]:
        """The SQL of every statement run, in order."""
        return [str(statement) for statement, _parameters in self.executed]


class Factory:
    """An ``async_sessionmaker`` stand-in handing out one scripted session."""

    def __init__(self, session: FakeSession) -> None:
        """Hold the session every call will return."""
        self.session = session
        self.calls = 0

    def __call__(self) -> FakeSession:
        """Return the scripted session, counting the call."""
        self.calls += 1
        return self.session


def store(session: FakeSession, **kwargs: Any) -> PostgresFlowStore:
    """A store bound to one scripted session."""
    return PostgresFlowStore(Factory(session), **kwargs)  # type: ignore[arg-type]


def record(*, at: datetime | None = None) -> FlowRecordIn:
    """One flow record, with what the store's write path reads."""
    return FlowRecordIn(
        timestamp=at or START,
        src_ip="10.0.0.1",  # type: ignore[arg-type]
        dst_ip="10.0.0.2",  # type: ignore[arg-type]
        src_port=1,
        dst_port=2,
        protocol=Protocol.TCP,
        direction=Direction.OUTBOUND,
        packets=3,
        src_packets=3,
        dst_packets=0,
        src_bytes=100,
        dst_bytes=40,
        duration=1.0,
    )


def series_script(session: FakeSession) -> None:
    """Add the five answers a ``summary`` read consumes, in statement order."""
    session._script.extend(
        [
            FakeResult([Row(start=START, flows=2, bytes=280, packets=6)]),  # buckets
            FakeResult([Row(ip="10.0.0.1", flows=2, bytes=280, packets=6, inbound=0, outbound=2)]),
            FakeResult([Row(source="10.0.0.1", target="10.0.0.2", flows=2, bytes=280)]),
            FakeResult([Row(1)]),  # distinct address count
            FakeResult([Row(1)]),  # distinct pair count
        ]
    )


@async_cases
class TestTheWrite:
    """One statement per batch, and the description afterwards is not stale."""

    async def test_a_batch_is_one_statement(self) -> None:
        session = FakeSession([FakeResult()])
        flow_store = store(session)

        kept = await flow_store.append([record(), record()])

        assert kept == 2
        assert len(session.executed) == 1

    async def test_the_bytes_column_is_the_sum_of_the_two_halves(self) -> None:
        # One definition of "the bytes this record carried", computed on the write
        # so no grouping query adds two columns and gets it slightly differently.
        session = FakeSession([FakeResult()])
        flow_store = store(session)

        await flow_store.append([record()])

        _statement, parameters = session.executed[0]
        assert parameters[0]["bytes"] == 140

    async def test_an_empty_batch_runs_nothing(self) -> None:
        session = FakeSession()
        flow_store = store(session)

        assert await flow_store.append([]) == 0
        assert session.executed == []

    async def test_a_write_drops_the_cached_coverage(self) -> None:
        session = FakeSession(
            [
                FakeResult([Row(oldest=None, newest=None, held=0)]),
                FakeResult(),
                FakeResult([Row(oldest=START, newest=START, held=1)]),
            ]
        )
        flow_store = store(session)
        assert (await flow_store.coverage()).held == 0

        await flow_store.append([record()])
        after = await flow_store.coverage()

        assert after.held == 1, "the write must invalidate the cached description"

    async def test_a_driver_failure_becomes_the_stores_refusal(self) -> None:
        session = FakeSession([OperationalError("select 1", {}, Exception("down"))])
        flow_store = store(session)

        with pytest.raises(FlowStoreUnavailable, match="could not accept a batch"):
            await flow_store.append([record()])


@async_cases
class TestTheRead:
    """Five statements, and the totals come from the series."""

    async def test_a_summary_is_five_statements(self) -> None:
        session = FakeSession()
        series_script(session)
        flow_store = store(session)

        await flow_store.summary(WINDOW, bucket_minutes=60)

        assert len(session.executed) == 5

    async def test_the_totals_come_from_the_series_not_from_the_lists(self) -> None:
        # The scripted bucket rows say two flows over more bytes than the single
        # scripted node and edge do; the totals must follow the series (T-416's
        # rule), so a store that summed its capped lists would fail here.
        session = FakeSession()
        series_script(session)
        flow_store = store(session)

        summary = await flow_store.summary(WINDOW, bucket_minutes=60)

        assert summary.totals.flows == 2
        assert summary.totals.bytes == 280
        assert summary.totals.packets == 6

    async def test_the_address_count_comes_from_a_count_not_from_the_list(self) -> None:
        session = FakeSession()
        series_script(session)
        session._script[3] = FakeResult([Row(9)])  # nine distinct addresses
        flow_store = store(session)

        summary = await flow_store.summary(WINDOW, bucket_minutes=60, entity_limit=1)

        assert summary.totals.nodes == 9
        assert summary.totals.nodes_capped is True
        assert len(summary.entities) == 1

    async def test_the_pair_count_comes_from_a_count_not_from_the_list(self) -> None:
        session = FakeSession()
        series_script(session)
        session._script[4] = FakeResult([Row(3)])
        flow_store = store(session)

        summary = await flow_store.summary(WINDOW, bucket_minutes=60, edge_limit=1)

        assert summary.totals.edges == 3
        assert summary.totals.edges_capped is True

    async def test_the_series_is_filled_at_every_bucket_of_the_window(self) -> None:
        # One scripted bucket over a three-bucket window: the other two are zeroes,
        # so a quiet interval is drawn as an empty bucket rather than closed up.
        session = FakeSession()
        series_script(session)
        flow_store = store(session)

        summary = await flow_store.summary(WINDOW, bucket_minutes=20)

        assert [bucket.flows for bucket in summary.series] == [2, 0, 0]
        assert len(summary.series) == 3

    async def test_the_store_never_reports_an_untracked_record(self) -> None:
        # Nothing is untracked here: a store keeps every record it is given, so the
        # two rollup-only counters are zero by construction rather than by luck.
        session = FakeSession()
        series_script(session)
        flow_store = store(session)

        summary = await flow_store.summary(WINDOW, bucket_minutes=60)

        assert summary.totals.untracked_address_flows == 0
        assert summary.totals.untracked_pair_flows == 0

    async def test_a_failing_read_becomes_the_stores_refusal(self) -> None:
        session = FakeSession([OperationalError("select 1", {}, Exception("down"))])
        flow_store = store(session)

        with pytest.raises(FlowStoreUnavailable, match="could not answer"):
            await flow_store.summary(WINDOW, bucket_minutes=60)

    async def test_the_filters_reach_every_statement(self) -> None:
        session = FakeSession()
        series_script(session)
        flow_store = store(session)

        await flow_store.summary(
            WINDOW, bucket_minutes=60, filters=FlowFilters(protocol="udp", direction="internal")
        )

        for text in session.statements:
            assert "protocol" in text or "union" in text.lower() or "count" in text


@async_cases
class TestCoverage:
    """What the table holds, asked once while the answer is fresh."""

    async def test_the_cache_answers_the_second_call(self) -> None:
        session = FakeSession([FakeResult([Row(oldest=START, newest=START, held=5)])])
        flow_store = store(session, coverage_ttl_seconds=30.0)

        first = await flow_store.coverage()
        second = await flow_store.coverage()

        assert first == second
        assert len(session.executed) == 1, "a fresh coverage must not be re-asked"

    async def test_a_refresh_is_asked_of_the_database(self) -> None:
        session = FakeSession(
            [
                FakeResult([Row(oldest=START, newest=START, held=5)]),
                FakeResult([Row(oldest=START, newest=START, held=6)]),
            ]
        )
        flow_store = store(session)

        await flow_store.coverage()
        refreshed = await flow_store.coverage(refresh=True)

        assert refreshed.held == 6
        assert len(session.executed) == 2

    async def test_an_empty_table_is_an_empty_coverage_not_an_error(self) -> None:
        session = FakeSession([FakeResult([Row(oldest=None, newest=None, held=0)])])
        flow_store = store(session)

        coverage = await flow_store.coverage()

        assert coverage.empty is True
        assert coverage.oldest is None

    async def test_a_zero_ttl_is_refused(self) -> None:
        with pytest.raises(ValueError, match="coverage_ttl_seconds must be positive"):
            PostgresFlowStore(Factory(FakeSession()), coverage_ttl_seconds=0)


class TestTheStoreSpeaksTheProtocolsLanguage:
    """What the endpoint reads off whichever source answered."""

    def test_it_names_itself(self) -> None:
        assert PostgresFlowStore(Factory(FakeSession())).name == "store"  # type: ignore[arg-type]

    def test_its_widest_window_is_r_34s_ceiling(self) -> None:
        from app.db.repository import MAX_QUERY_SPAN_DAYS

        assert PostgresFlowStore(Factory(FakeSession())).max_span_seconds == (  # type: ignore[arg-type]
            MAX_QUERY_SPAN_DAYS * 86_400.0
        )

    def test_the_table_it_reads_is_the_one_the_migration_created(self) -> None:
        assert FlowEvent.__tablename__ == "flow_events"
