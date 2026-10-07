"""The asynchronous database engine the request path uses (R-18, D-030).

T-323 declared psycopg 3 as the driver precisely because one driver serves both
halves of this application: the synchronous engine ``alembic`` dials at deploy time,
and the asynchronous one a request-path session needs. This module is the second
half, and it is deliberately tiny -- it builds an engine and a session factory, and it
refuses a URL it cannot open asynchronously *before* anything tries to use it.

**The dialect is checked by building the engine, not by reading the URL.** psycopg 3
is unusual in that ``postgresql+psycopg`` is a *sync-mapped* dialect name whose async
variant SQLAlchemy selects for ``create_async_engine``; a URL-string allowlist here
would either reject the driver this codebase declares or accept one it cannot open.
So the engine is built first -- which opens no connection, only resolves the dialect
and the DBAPI -- and its dialect's ``is_async`` is what decides. A driver that is not
installed fails the same way, with the same sentence naming the fix (R-06), instead of
an ``InvalidRequestError`` raised deep inside the first await of a live request.

**No connection is opened here.** Engines are lazy, so a process whose database is not
up yet still starts: readiness reports the dependency, and a read that cannot reach the
store fails as an error rather than silently answering from somewhere smaller (R-70).
"""

from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

__all__ = [
    "async_session_factory",
    "create_async_database_engine",
    "require_async_dialect",
]

#: The driver the request path expects, as a URL for the error message. Named once so
#: a deployment is told the same thing wherever the refusal surfaces.
_ASYNC_DRIVER_HINT = "postgresql+psycopg://"


def create_async_database_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Build the request path's engine, refusing a URL it cannot open asynchronously.

    ``pool_pre_ping`` is on because a pooled connection that a database restart or a
    network hop killed is otherwise handed to a request and fails there; the ping
    costs one round trip on a *reused* connection and turns that into a reconnect.

    Raises:
        ValueError: if the URL is unusable, names a dialect with no async variant, or
            names a driver that is not installed. Raised at startup, because a URL is
            configuration and a configuration error belongs at the beginning of a
            process -- not in the middle of the first log read of the day.
    """
    try:
        parsed = make_url(url)
    except Exception as exc:  # noqa: BLE001 - sqlalchemy raises ArgumentError here
        msg = f"{url!r} is not a usable database URL: {exc}"
        raise ValueError(msg) from exc

    try:
        engine = create_async_engine(url, echo=echo, pool_pre_ping=True, future=True)
    except Exception as exc:  # noqa: BLE001 - the DBAPI or the dialect is missing
        msg = (
            f"{parsed.drivername!r} cannot be opened by the asynchronous engine: {exc}. "
            f"Use {_ASYNC_DRIVER_HINT!r}, which psycopg 3 serves asynchronously; alembic "
            "opens the same URL the synchronous way."
        )
        raise ValueError(msg) from exc

    require_async_dialect(engine)
    return engine


def require_async_dialect(engine: AsyncEngine) -> None:
    """Refuse an engine whose dialect has no asynchronous half (R-18).

    Split out from the builder because the mutation battery proved the branch was
    **unreachable through it**: `create_async_engine` already refuses a synchronous
    DBAPI while it builds -- with `InvalidRequestError`, which the builder's first
    handler turns into the same sentence -- so no URL reaches this check. An
    unreachable guard is either removed or made reachable; this one is worth keeping,
    because it is the statement of the rule the builder is enforcing, so it takes an
    engine and can be handed a synchronously built one in a test.

    Raises:
        ValueError: if the engine's dialect is synchronous, naming the driver and the
            hint that works.
    """
    if engine.dialect.is_async:
        return
    # The engine is dropped without being disposed: it resolved a dialect and a DBAPI
    # and opened nothing, so there is no pool to close, and ``dispose()`` on an async
    # engine is itself a coroutine this synchronous module must not leave un-awaited.
    dialect = engine.dialect.__class__.__name__
    msg = (
        f"{engine.url.drivername!r} resolved to {dialect}, which is a synchronous "
        "dialect, and the request path may not use one (R-18). Use "
        f"{_ASYNC_DRIVER_HINT!r} instead."
    )
    raise ValueError(msg)


def async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """A factory of sessions bound to ``engine``, with no autocommit and no flush magic.

    ``expire_on_commit=False`` so an object read back after a commit is still usable
    without a second round trip; every read here serialises inside the same block it
    queried in, so nothing depends on it, but a session that quietly re-queries on
    attribute access is the kind of surprise this codebase avoids elsewhere.
    """
    return async_sessionmaker(engine, expire_on_commit=False)
