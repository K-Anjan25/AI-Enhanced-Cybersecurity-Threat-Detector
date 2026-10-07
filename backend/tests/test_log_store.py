"""The log store's fold, caveats and caching (T-419).

The database here is a scripted fake, for one reason: what this file is about is
*what the store does with rows*, and a real server would only make those assertions
slower. The SQL itself is asserted in ``test_log_statements.py``; the round trip
against a real PostgreSQL -- including the acceptance criterion's restart and
retention clauses -- is ``test_log_store_live.py``.

The fake counts statements as well as answering them, which is how three claims that
are otherwise invisible get tested: the level histogram is scoped to the keys the fold
returned, the present-without-filters count is only asked when the read found nothing
(it is only *needed* then), and the coverage cache really does save the three
aggregates it advertises.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import pytest
from app.db.models import LogEvent
from app.schemas.ingest import LogLevel, LogRecordIn
from app.schemas.logs import LogTailOut
from app.services.log_keys import message_key
from app.services.log_store import MAX_SPAN_SECONDS, Coverage, PostgresLogStore
from app.services.log_tail import LogWindow

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
END = START + timedelta(minutes=5)
WINDOW = LogWindow(start=START, end=END)


_T = TypeVar("_T")


def sync(function: Callable[..., Coroutine[Any, Any, _T]]) -> Callable[..., _T]:
    """Run one coroutine test body to completion.

    The suite deliberately has no async plugin -- every other component is tested
    through a synchronous API, and T-310's hub tests drive their coroutines through
    ``asyncio.run`` too. The log store's reads are coroutines by construction, so
    they are entered the same way.
    """

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> _T:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


def async_cases(cls: type) -> type:
    """Wrap every coroutine case in a class so pytest can collect it.

    Applied per class rather than to the module: which cases are asynchronous is a
    property of what they test, and a reader looking at one should not have to find
    out from a marker on the file.
    """
    for name, value in list(vars(cls).items()):
        if name.startswith("test_") and inspect.iscoroutinefunction(value):
            setattr(cls, name, sync(value))
    return cls


class FakeResult:
    """One canned answer, standing in for a driver's cursor."""

    def __init__(self, rows: Sequence[Sequence[Any]] = ()) -> None:
        """Hold the rows this result will hand back."""
        self._rows = [tuple(row) for row in rows]

    def all(self) -> list[tuple[Any, ...]]:
        """Every row."""
        return list(self._rows)

    def one(self) -> tuple[Any, ...]:
        """The single row, asserting there is exactly one."""
        assert len(self._rows) == 1, f"expected one row, the script holds {len(self._rows)}"
        return self._rows[0]

    def scalar_one(self) -> Any:
        """The single value of the single row."""
        return self.one()[0]


class FakeSession:
    """A session that answers in script order and remembers what it was asked.

    ``executed`` holds every statement in the order the store ran it, which is what
    the query-count assertions read. The script is consumed strictly: a store that
    ran one statement more than a test expects fails loudly rather than being handed
    an answer it did not earn.
    """

    def __init__(self, script: Sequence[FakeResult]) -> None:
        """Hold the canned answers, in order."""
        self._script = list(script)
        self.executed: list[Any] = []

    async def execute(self, statement: Any, parameters: Any = None) -> FakeResult:
        """Answer with the next canned result, recording the statement."""
        self.executed.append((statement, parameters))
        if not self._script:
            raise AssertionError("the store ran more statements than the script provides")
        return self._script.pop(0)

    def begin(self) -> FakeTransaction:
        """Return a transaction whose body does nothing.

        Exists so the store's ``async with self._session_factory() as session,
        session.begin():`` line works against this fake.
        """
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

    def parameters_of(self, index: int) -> Any:
        """The parameters of the ``index``-th statement run."""
        return self.executed[index][1]


class FakeTransaction:
    """The async context manager ``session.begin()`` returns."""

    async def __aenter__(self) -> FakeTransaction:
        """Enter."""
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        """Exit."""
        return False


def store_with(
    script: Sequence[FakeResult], *, ttl: float = 30.0, clock: Any = None
) -> tuple[PostgresLogStore, FakeSession]:
    """A store over one fake session, plus that session for assertions."""
    session = FakeSession(script)
    kwargs = {"coverage_ttl_seconds": ttl}
    if clock is not None:
        kwargs["clock"] = clock
    store = PostgresLogStore(lambda: session, **kwargs)  # type: ignore[arg-type]
    return store, session


def coverage_rows(
    *,
    oldest: datetime | None = START - timedelta(days=30),
    newest: datetime | None = END,
    held: int = 3,
) -> FakeResult:
    """The three aggregates the coverage statement returns."""
    return FakeResult([(oldest, newest, held)])


def record(
    *,
    offset: float = 0.0,
    message: str = "connection refused to db-1",
    template_id: str | None = "t-1",
    level: str = "error",
    host: str = "web-1",
    service: str = "api",
) -> LogRecordIn:
    """One ``log@1`` line as the ingest service hands it to a source."""
    return LogRecordIn(
        schema_version="log@1",
        timestamp=START + timedelta(seconds=offset),
        host=host,
        service=service,
        level=LogLevel(level),
        message=message,
        template_id=template_id,
        parameters={"db": "db-1"},
    )


class TestTheStoreIsAsynchronouslyReadable:
    """The interface the routes are written against."""

    def test_it_names_itself(self) -> None:
        store, _ = store_with([])

        assert store.name == "store"

    def test_its_span_bound_is_the_query_bound_not_the_tails(self) -> None:
        store, _ = store_with([])

        assert store.max_span_seconds == MAX_SPAN_SECONDS
        assert MAX_SPAN_SECONDS == 92 * 24 * 60 * 60

    def test_a_zero_lifetime_for_the_coverage_is_refused(self) -> None:
        with pytest.raises(ValueError, match="coverage_ttl_seconds must be positive"):
            PostgresLogStore(lambda: None, coverage_ttl_seconds=0)  # type: ignore[arg-type]


@async_cases
class TestAppend:
    """What an accepted batch becomes."""

    async def test_it_writes_every_row_in_one_statement(self) -> None:
        store, session = store_with([FakeResult()])

        stored = await store.append([record(offset=0), record(offset=1)])

        assert stored == 2
        assert len(session.executed) == 1
        rows = session.parameters_of(0)
        assert len(rows) == 2

    async def test_the_key_is_the_tails_own_key(self) -> None:
        """The stored key is the one the tail folds by.

        Two definitions of "what a cluster is" would let a stored read show a row the
        tail would not have.
        """
        store, session = store_with([FakeResult()])

        await store.append([record(template_id="t-1"), record(template_id=None, message="boom")])

        rows = session.parameters_of(0)
        assert rows[0]["key"] == "t-1"
        assert rows[1]["key"] == message_key("boom")

    async def test_a_blank_template_id_is_not_mined_rather_than_empty(self) -> None:
        """A template named "" would collect every line whose collector sent one."""
        store, session = store_with([FakeResult()])

        await store.append([record(template_id="   ")])

        rows = session.parameters_of(0)
        assert rows[0]["template_id"] is None
        assert rows[0]["key"] == message_key("connection refused to db-1")

    async def test_the_level_is_stored_as_its_text(self) -> None:
        store, session = store_with([FakeResult()])

        await store.append([record(level="critical")])

        assert session.parameters_of(0)[0]["level"] == "critical"

    async def test_an_empty_batch_does_not_touch_the_database(self) -> None:
        store, session = store_with([])

        assert await store.append([]) == 0
        assert session.executed == []

    async def test_a_write_drops_the_cached_coverage(self) -> None:
        """A coverage that predates the batch the caller just stored is stale."""
        store, session = store_with([coverage_rows(held=1), FakeResult(), coverage_rows(held=2)])

        assert (await store.coverage()).held == 1
        await store.append([record()])
        assert (await store.coverage()).held == 2

    async def test_the_table_is_the_one_the_migration_creates(self) -> None:
        store, session = store_with([FakeResult()])

        await store.append([record()])

        assert LogEvent.__tablename__ == "log_events"
        assert "INSERT INTO log_events" in session.statements[0]


@async_cases
class TestTheClusterRead:
    """The fold, over rows a real server would have produced."""

    def script(self) -> list[FakeResult]:
        """A two-cluster window: three lines, two keys, one untemplated."""
        return [
            FakeResult(
                [
                    # key, lines, first, last, sample, parameters, hosts, services
                    (
                        "t-1",
                        2,
                        START,
                        START + timedelta(seconds=30),
                        "second",
                        {"n": "2"},
                        ["web-2", "web-1"],
                        ["api"],
                    ),
                    (
                        message_key("boom"),
                        1,
                        START + timedelta(seconds=45),
                        START + timedelta(seconds=45),
                        "boom",
                        {},
                        ["web-1"],
                        ["api", "worker"],
                    ),
                ]
            ),
            FakeResult(
                [("t-1", "error", 1), ("t-1", "info", 1), (message_key("boom"), "critical", 1)]
            ),
            FakeResult([(2,)]),
            FakeResult([(3,)]),
            FakeResult([(1,)]),
            coverage_rows(held=3),
        ]

    async def test_it_folds_rows_into_the_wire_model(self) -> None:
        store, _ = store_with(self.script())

        payload = await store.clusters(WINDOW, limit=10)

        assert isinstance(payload, LogTailOut)
        assert payload.source == "store"
        assert [cluster.key for cluster in payload.clusters] == ["t-1", message_key("boom")]
        first = payload.clusters[0]
        assert first.count == 2
        assert first.template_id == "t-1"
        assert first.sample_message == "second"
        assert first.parameters == {"n": "2"}

    async def test_a_digest_key_has_no_template_id(self) -> None:
        """The prefix is what says the collector mined nothing."""
        store, _ = store_with(self.script())

        payload = await store.clusters(WINDOW, limit=10)

        assert payload.clusters[1].template_id is None

    async def test_the_worst_level_is_the_worst_by_rank(self) -> None:
        store, _ = store_with(self.script())

        payload = await store.clusters(WINDOW, limit=10)

        assert payload.clusters[0].worst_level is LogLevel.ERROR
        assert payload.clusters[1].worst_level is LogLevel.CRITICAL

    async def test_the_levels_are_listed_by_rank_not_alphabetically(self) -> None:
        """Sorted keys would publish `critical` before `debug`."""
        store, _ = store_with(
            [
                FakeResult([("t-1", 2, START, END, "m", {}, ["web-1"], ["api"])]),
                FakeResult([("t-1", "critical", 1), ("t-1", "debug", 1)]),
                FakeResult([(1,)]),
                FakeResult([(2,)]),
                FakeResult([(0,)]),
                coverage_rows(),
            ]
        )

        payload = await store.clusters(WINDOW, limit=10)

        assert list(payload.clusters[0].levels) == ["debug", "critical"]

    async def test_the_hosts_and_services_are_sorted(self) -> None:
        """The database's array order is not a promise; the wire's must be."""
        store, _ = store_with(self.script())

        payload = await store.clusters(WINDOW, limit=10)

        assert payload.clusters[0].hosts == ["web-1", "web-2"]
        assert payload.clusters[1].services == ["api", "worker"]
        assert payload.clusters[1].hosts == ["web-1"]

    async def test_the_counts_are_the_windows_counts(self) -> None:
        store, _ = store_with(self.script())

        payload = await store.clusters(WINDOW, limit=10)

        assert payload.lines_seen == 3
        assert payload.clusters_seen == 2

    async def test_exactly_the_limit_is_not_truncated(self) -> None:
        """``> limit``, not ``>= limit``: a read showing all of them cut nothing."""
        script = self.script()
        script[2] = FakeResult([(2,)])
        store, _ = store_with(script)

        payload = await store.clusters(WINDOW, limit=2)

        assert payload.clusters_truncated is False

    async def test_one_more_than_the_limit_is_truncated(self) -> None:
        script = self.script()
        script[2] = FakeResult([(3,)])
        store, _ = store_with(script)

        payload = await store.clusters(WINDOW, limit=2)

        assert payload.clusters_truncated is True

    async def test_the_level_histogram_is_scoped_to_the_keys_the_fold_returned(self) -> None:
        store, session = store_with(self.script())

        await store.clusters(WINDOW, limit=10)

        histogram = session.statements[1]
        assert "GROUP BY log_events.key, log_events.level" in histogram
        assert "log_events.key IN " in histogram

    async def test_the_retention_fields_describe_the_store(self) -> None:
        store, _ = store_with(self.script())

        payload = await store.clusters(WINDOW, limit=10)

        assert payload.retained_from == START - timedelta(days=30)
        assert payload.retained_to == END
        assert payload.retained_lines == 3
        assert payload.dropped_lines is None, "the store cannot report evictions it does not do"

    async def test_the_unfiltered_count_is_not_asked_when_something_matched(self) -> None:
        """It exists to explain an empty screen, so it is only needed then."""
        store, session = store_with(self.script())

        await store.clusters(WINDOW, limit=10)

        # Five statements in the read's own session, plus the coverage that follows
        # it: a store that asked the unfiltered question too would need six in-session
        # answers and the strict script would leave it without one.
        assert len(session.executed) == 6
        assert "IS NULL" in session.statements[4], "the fifth question is the untemplated count"
        assert "log_events.host" not in session.statements[4]

    async def test_a_window_wider_than_the_query_bound_is_refused(self) -> None:
        store, _ = store_with([])
        wide = LogWindow(start=START - timedelta(days=120), end=END)

        with pytest.raises(ValueError, match="92-day"):
            await store.clusters(wide, limit=10)


@async_cases
class TestTheLineRead:
    """The raw lines behind a cluster."""

    def script(self, *, matched: int = 2, page: int = 2) -> list[FakeResult]:
        """``matched`` lines, of which ``page`` are on the page."""
        # Newest first, as ``ORDER BY timestamp DESC`` would hand them over: the fake
        # emulates the server's order rather than the wire's, or the test would pass
        # against a store that never reversed anything.
        rows = [
            (
                START + timedelta(seconds=index),
                f"web-{index + 1}",
                "api",
                "error",
                f"line {index}",
                "t-1",
                {"n": str(index)},
                "t-1",
            )
            for index in reversed(range(page))
        ]
        return [FakeResult([(matched,)]), FakeResult(rows), coverage_rows(held=matched)]

    async def test_it_returns_the_lines_oldest_first(self) -> None:
        """Newest first out of SQL, oldest first on the wire.

        A stack trace read backwards is a different story.
        """
        store, _ = store_with(self.script())

        payload = await store.lines(WINDOW, limit=10)

        assert [line.message for line in payload.lines] == ["line 0", "line 1"]
        assert payload.lines[0].timestamp < payload.lines[1].timestamp

    async def test_it_carries_the_cluster_key_on_every_line(self) -> None:
        store, _ = store_with(self.script())

        payload = await store.lines(WINDOW, limit=10)

        assert {line.key for line in payload.lines} == {"t-1"}

    async def test_it_reports_how_many_matched_before_the_cap(self) -> None:
        store, _ = store_with(self.script(matched=9, page=2))

        payload = await store.lines(WINDOW, limit=2)

        assert payload.lines_seen == 9
        assert payload.lines_truncated is True
        assert len(payload.lines) == 2

    async def test_exactly_the_limit_is_not_truncated(self) -> None:
        store, _ = store_with(self.script(matched=2, page=2))

        payload = await store.lines(WINDOW, limit=2)

        assert payload.lines_truncated is False

    async def test_the_key_it_was_narrowed_to_comes_back(self) -> None:
        store, _ = store_with(self.script())
        window = LogWindow(start=START, end=END, key="t-1")

        payload = await store.lines(window, limit=10)

        assert payload.key == "t-1"
        assert payload.source == "store"


@async_cases
class TestTheCaveats:
    """R-70: five different empty screens, five different sentences."""

    async def test_every_read_says_where_the_lines_came_from(self) -> None:
        store, _ = store_with(self.script_for_empty_window(held=0, present=0))

        payload = await store.clusters(WINDOW, limit=10)

        assert "log store" in payload.caveats[0]
        assert "survive a restart" in payload.caveats[0]

    async def test_an_empty_store_says_it_has_never_stored_anything(self) -> None:
        store, _ = store_with(self.script_for_empty_window(held=0, present=0))

        payload = await store.clusters(WINDOW, limit=10)

        assert any("has been stored yet" in caveat for caveat in payload.caveats)

    async def test_a_window_before_everything_says_which_line_is_the_oldest(self) -> None:
        store, _ = store_with(
            [
                FakeResult([]),
                FakeResult([(0,)]),
                FakeResult([(0,)]),
                FakeResult([(0,)]),
                coverage_rows(
                    oldest=END + timedelta(hours=1), newest=END + timedelta(hours=2), held=5
                ),
            ]
        )
        window = LogWindow(start=START, end=END)

        payload = await store.clusters(window, limit=10)

        assert any("Nothing is stored at or before" in caveat for caveat in payload.caveats)

    async def test_a_window_after_everything_says_which_line_is_the_newest(self) -> None:
        store, _ = store_with(
            [
                FakeResult([]),
                FakeResult([(0,)]),
                FakeResult([(0,)]),
                FakeResult([(0,)]),
                coverage_rows(
                    oldest=START - timedelta(days=2), newest=START - timedelta(days=1), held=5
                ),
            ]
        )

        payload = await store.clusters(WINDOW, limit=10)

        assert any("Nothing has been stored at or after" in caveat for caveat in payload.caveats)

    async def test_a_window_between_stored_lines_says_so(self) -> None:
        store, _ = store_with(
            [
                FakeResult([]),
                FakeResult([(0,)]),
                FakeResult([(0,)]),
                FakeResult([(0,)]),
                coverage_rows(
                    oldest=START - timedelta(days=2), newest=END + timedelta(days=2), held=5
                ),
            ]
        )

        payload = await store.clusters(WINDOW, limit=10)

        assert any("falls between them" in caveat for caveat in payload.caveats)

    async def test_a_filter_that_removed_everything_says_the_filter_did_it(self) -> None:
        """The distinction the unfiltered count exists for."""
        store, _ = store_with(
            [
                FakeResult([]),
                FakeResult([(0,)]),
                FakeResult([(0,)]),
                FakeResult([(12,)]),
                coverage_rows(held=12),
            ]
        )
        window = LogWindow(start=START, end=END, host="web-9")

        payload = await store.clusters(window, limit=10)

        assert any("filter is what removed them" in caveat for caveat in payload.caveats)
        assert not any("falls between them" in caveat for caveat in payload.caveats)

    async def test_an_untemplated_line_is_explained(self) -> None:
        store, _ = store_with(
            [
                FakeResult(
                    [(message_key("boom"), 1, START, START, "boom", {}, ["web-1"], ["api"])]
                ),
                FakeResult([(message_key("boom"), "error", 1)]),
                FakeResult([(1,)]),
                FakeResult([(1,)]),
                FakeResult([(1,)]),
                coverage_rows(held=1),
            ]
        )

        payload = await store.clusters(WINDOW, limit=10)

        assert any("carry no template id" in caveat for caveat in payload.caveats)

    async def test_a_hit_row_limit_says_so(self) -> None:
        store, _ = store_with(
            [
                FakeResult([("t-1", 5, START, END, "m", {}, ["web-1"], ["api"])]),
                FakeResult([("t-1", "error", 5)]),
                FakeResult([(9,)]),
                FakeResult([(40,)]),
                FakeResult([(0,)]),
                coverage_rows(held=40),
            ]
        )

        payload = await store.clusters(WINDOW, limit=1)

        assert any("hit its row limit" in caveat for caveat in payload.caveats)

    async def test_every_read_says_a_level_is_not_an_anomaly_score(self) -> None:
        store, _ = store_with(self.script_for_empty_window(held=0, present=0))

        payload = await store.clusters(WINDOW, limit=10)

        assert any("no log model is served" in caveat for caveat in payload.caveats)

    async def test_every_read_says_nothing_evicts_yet(self) -> None:
        """FR-05's window does not reach this table, and the read says so."""
        store, _ = store_with(self.script_for_empty_window(held=0, present=0))

        payload = await store.clusters(WINDOW, limit=10)

        assert any("Nothing evicts rows" in caveat for caveat in payload.caveats)

    def script_for_empty_window(self, *, held: int, present: int) -> list[FakeResult]:
        """An empty fold, the three counts it then needs, and a coverage.

        The third count is the one without the read's filters -- the whole point of
        the empty-window sentences -- so a helper that omitted it would run out of
        answers in the fake rather than pass silently.
        """
        return [
            FakeResult([]),
            FakeResult([(0,)]),
            FakeResult([(0,)]),
            FakeResult([(present,)]),
            coverage_rows(held=held),
        ]


@async_cases
class TestTheCoverageCache:
    """Three aggregates that are reused for a short while, and no longer."""

    async def test_a_second_read_inside_the_window_reuses_it(self) -> None:
        store, session = store_with([coverage_rows(held=1)], ttl=30.0, clock=lambda: 100.0)

        first = await store.coverage()
        second = await store.coverage()

        assert first == second
        assert len(session.executed) == 1

    async def test_it_is_remeasured_once_the_lifetime_expires(self) -> None:
        now = [100.0]
        store, session = store_with(
            [coverage_rows(held=1), coverage_rows(held=2)],
            ttl=30.0,
            clock=lambda: now[0],
        )

        assert (await store.coverage()).held == 1
        now[0] += 31.0
        assert (await store.coverage()).held == 2
        assert len(session.executed) == 2

    async def test_a_refresh_ignores_the_cache(self) -> None:
        store, session = store_with(
            [coverage_rows(held=1), coverage_rows(held=2)], ttl=300.0, clock=lambda: 100.0
        )

        await store.coverage()
        await store.coverage(refresh=True)

        assert len(session.executed) == 2

    async def test_an_empty_store_reports_itself_empty(self) -> None:
        store, _ = store_with([coverage_rows(oldest=None, newest=None, held=0)])

        measured = await store.coverage()

        assert isinstance(measured, Coverage)
        assert measured.empty
        assert measured.oldest is None
