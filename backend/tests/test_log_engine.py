"""The request path's engine: what it refuses, and what it refuses to do while refusing.

`app/db/engine.py` is the one module T-419 added that has no I/O of its own, so its
contract is easy to state and easy to leave untested -- and it was: the refusals lived
in a mutation battery that no test could kill, because nothing imported the module. The
contract the store depends on is threefold.

* **A URL this build cannot open asynchronously is refused, and the refusal names the
  driver that works.** R-06 says an error names the fix; a deployment that read
  "sqlite is not async" without being told what is would be left guessing.
* **The refusal happens at build time, not at first read.** The engine is built before
  it is judged -- `create_async_engine` resolves a dialect and a DBAPI and opens
  nothing -- so a process whose database is down still starts, which is what lets the
  log routes answer 503 instead of the process refusing to boot.
* **Nothing is opened or disposed on the way out.** An `AsyncEngine.dispose()` is a
  coroutine, so a synchronous builder that called it would leave a coroutine un-awaited
  (mypy's `unused-coroutine`) for a pool it never created.

The reason this is a module of its own rather than a few cases in `test_log_store.py`
is that the refusal is a *startup* behaviour: nothing in the store's tests can reach it,
because every one of them hands the store a session that is already built.
"""

from __future__ import annotations

import asyncio

import pytest
from app.db.engine import async_session_factory, create_async_database_engine, require_async_dialect
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession

#: A DSN shape the driver this codebase declares can serve asynchronously.
PSYCOPG_URL = "postgresql+psycopg://aegis@127.0.0.1:59999/aegis"

#: A DSN that is fine to *build* and useless to dial: nothing here connects, which is
#: the property under test rather than an inconvenience to work around.
UNROUTABLE_HOST = "db.invalid"


def test_every_asynchronous_postgres_url_this_build_supports_is_accepted() -> None:
    engine = create_async_database_engine(PSYCOPG_URL, echo=False)

    assert engine.dialect.is_async is True
    assert engine.dialect.driver == "psycopg"


def test_a_missing_database_is_not_a_startup_failure() -> None:
    # The host does not resolve and nothing listens on the port; building the engine
    # must not care, because the alternative is a process that cannot boot before its
    # dependency does (R-18: readiness reports the dependency, a read reports the error).
    engine = create_async_database_engine(
        f"postgresql+psycopg://aegis@{UNROUTABLE_HOST}:5432/aegis"
    )

    assert engine.dialect.is_async is True


@pytest.mark.parametrize(
    "url", ["sqlite:///./aegis.db", "postgresql+psycopg2://aegis@localhost:5432/aegis"]
)
def test_a_url_this_build_cannot_open_asynchronously_is_refused_by_the_builder(url: str) -> None:
    # Neither URL reaches the dialect rule below: SQLAlchemy refuses a synchronous DBAPI
    # *while the engine is being built* -- "the loaded 'pysqlite' is not async" -- and the
    # builder turns that into a sentence naming the driver that works (R-06). The rule
    # keeps its own case precisely because this path cannot reach it.
    if url.startswith("postgresql+psycopg2"):
        pytest.importorskip("psycopg2")

    with pytest.raises(ValueError) as caught:
        create_async_database_engine(url)

    message = str(caught.value)
    assert "cannot be opened by the asynchronous engine" in message
    assert "postgresql+psycopg://" in message


def test_the_rule_is_the_built_dialect_and_not_a_url_allowlist() -> None:
    # SQLite over an async driver is not a URL this build ships, and it is still
    # accepted: the check is "did the engine resolve an asynchronous dialect", not "is
    # the string the one we expected". An allowlist would pass the test above and fail
    # this one.
    pytest.importorskip("aiosqlite")

    engine = create_async_database_engine("sqlite+aiosqlite:///./aegis.db")

    assert engine.dialect.is_async is True


def test_the_rule_itself_refuses_a_synchronously_built_engine() -> None:
    # The builder cannot reach this branch -- `create_async_engine` refuses a
    # synchronous DBAPI while it builds, and the builder's own handler turns that into
    # the same sentence -- so the rule takes an engine and is handed one built the
    # synchronous way. Without this case the mutation battery kills the branch only by
    # removing the rule from the module, which is not the same as testing it.
    sync_engine = create_engine("sqlite:///./aegis.db")

    with pytest.raises(ValueError) as caught:
        require_async_dialect(sync_engine)  # type: ignore[arg-type]

    message = str(caught.value)
    assert "SQLiteDialect" in message
    assert "synchronous dialect" in message
    assert "postgresql+psycopg://" in message


def test_the_rule_accepts_the_engine_this_build_serves_with() -> None:
    require_async_dialect(create_async_database_engine(PSYCOPG_URL))  # does not raise


def test_a_string_that_is_not_a_url_at_all_is_refused_with_the_url_in_it() -> None:
    with pytest.raises(ValueError) as caught:
        create_async_database_engine("not-a-url")

    assert "not-a-url" in str(caught.value)
    assert "not a usable database URL" in str(caught.value)


def test_a_driver_that_is_not_installed_names_the_fix() -> None:
    # A dialect SQLAlchemy knows but this install cannot load: the refusal is the same
    # sentence, naming the driver that is installed rather than a traceback from the
    # first await of a live request.
    with pytest.raises(ValueError) as caught:
        create_async_database_engine("postgresql+asyncpg://aegis@localhost:5432/aegis")

    message = str(caught.value)
    assert "cannot be opened by the asynchronous engine" in message
    assert "postgresql+psycopg://" in message


def test_the_refusal_leaves_no_coroutine_behind() -> None:
    # `AsyncEngine.dispose()` is a coroutine, so a refusal path that called it would
    # raise `RuntimeWarning: coroutine ... was never awaited` (and mypy's
    # `unused-coroutine`). Running the refusal with warnings as errors is what proves
    # the engine was dropped rather than disposed.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(ValueError):
            create_async_database_engine("sqlite:///./aegis.db")
        # Give a leaked coroutine's GC a chance to warn, which is when CPython reports it.
        import gc

        gc.collect()


def test_the_session_factory_builds_sessions_bound_to_the_engine() -> None:
    engine = create_async_database_engine(PSYCOPG_URL)
    factory = async_session_factory(engine)

    async def build() -> AsyncSession:
        return factory()

    session = asyncio.run(build())
    try:
        assert session.bind is engine
    finally:
        # Closing a session opens no connection either -- there is nothing to close --
        # so this stays a unit test of the factory.
        asyncio.run(session.close())


def test_the_session_factory_does_not_expire_on_commit() -> None:
    engine = create_async_database_engine(PSYCOPG_URL)
    factory = async_session_factory(engine)

    assert factory.kw["expire_on_commit"] is False
