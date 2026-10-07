"""Which log read model a deployment answers from (T-419).

Two sources implement one interface — ``append``, ``clusters``, ``lines``,
``max_span_seconds``, ``name`` — so the read routes never branch on which one the
composition root installed:

* :class:`~app.services.log_store.PostgresLogStore` — the persistent store, which is
  what T-419 asked for: reads that survive a restart, see every worker's lines, and
  span more than a tail's retention.
* :class:`TailLogSource` — the bounded in-process tail (T-407), wrapped here so the
  route can await it and so the *reason* it answered is on the response. A deployment
  with no database is a real deployment, and the honest thing for it to do is say so
  on every read rather than leave a screen to guess whether 15 minutes is all there is.

**The choice is made once, at startup, and never silently revised.** A store that was
configured and is unreachable raises: falling back to the tail mid-request would answer
a 92-day window from a 15-minute buffer and look exactly like "nothing matched", which
is the failure R-70 exists to forbid. :func:`store_requested` is that decision, kept
apart from the wiring so what a deployment gets is assertable without building an
application.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.core.config import LogStoreMode
from app.schemas.ingest import LogRecordIn
from app.schemas.logs import LogLinesOut, LogTailOut
from app.services.log_tail import LogTail, LogWindow

__all__ = [
    "LogSource",
    "TailLogSource",
    "store_requested",
    "tail_reason",
]

#: The sentence a tail-backed deployment's reads carry, by mode. Only two cases reach
#: it: a deployment that turned the store off, and one that never named a database.
_TAIL_REASON = {
    LogStoreMode.OFF: (
        "This deployment answers from the process's own tail because AEGIS_LOG_STORE "
        "is off. The store exists (T-419): set AEGIS_LOG_STORE=on to read stored lines."
    ),
    LogStoreMode.AUTO: (
        "This deployment answers from the process's own tail because no database URL "
        "is named. Set AEGIS_DATABASE_URL to the deployment's PostgreSQL (and run "
        "alembic upgrade head) to read stored lines instead (T-419)."
    ),
}


class LogSource(Protocol):
    """What the log routes need from whichever read model answers.

    ``name`` is on the protocol rather than only on the response because the route
    puts it there *from here*: a source that could not say what it is would be a
    source whose reads are indistinguishable from the other one's.
    """

    #: ``"store"`` or ``"tail"``, and what the response's ``source`` field carries.
    name: str

    @property
    def max_span_seconds(self) -> float:
        """The widest window this source will answer, in seconds."""
        ...

    async def append(self, records: Sequence[LogRecordIn]) -> int:
        """Keep a batch of accepted lines, returning how many were kept."""
        ...

    async def clusters(self, window: LogWindow, *, limit: int) -> LogTailOut:
        """Fold the window's lines into clusters."""
        ...

    async def lines(self, window: LogWindow, *, limit: int) -> LogLinesOut:
        """The newest matching lines, oldest first."""
        ...


class TailLogSource:
    """The in-process tail, behind the same interface as the store.

    The tail's work is a filter and a fold over a bounded deque behind a lock —
    microseconds, no I/O — so this wrapper calls it inline rather than pretending to
    be asynchronous. It is ``async def`` because the interface is, and it says in
    ``reason`` why this deployment is answering from memory.
    """

    __slots__ = ("_reason", "_tail")

    name = "tail"

    def __init__(self, tail: LogTail, *, reason: str) -> None:
        """Wrap one tail, with the sentence its reads carry."""
        self._tail = tail
        self._reason = reason

    @property
    def tail(self) -> LogTail:
        """The wrapped tail, for tests and for the readiness probe."""
        return self._tail

    @property
    def max_span_seconds(self) -> float:
        """A tail's widest window is its own retention."""
        return self._tail.max_age_seconds

    async def append(self, records: Sequence[LogRecordIn]) -> int:
        """Keep the batch in the tail."""
        return self._tail.append(records)

    async def clusters(self, window: LogWindow, *, limit: int) -> LogTailOut:
        """Fold the tail's lines in the window, and say why the tail answered."""
        payload = self._tail.clusters(window, limit=limit)
        payload.caveats.append(self._reason)
        return payload

    async def lines(self, window: LogWindow, *, limit: int) -> LogLinesOut:
        """The newest matching lines the tail holds, and why the tail answered."""
        payload = self._tail.lines(window, limit=limit)
        payload.caveats.append(self._reason)
        return payload


def store_requested(mode: LogStoreMode, *, database_url_named: bool) -> bool:
    """Whether this deployment's reads come from the store.

    ``AUTO`` is a question about configuration, not a probe: the store is used when
    the deployment *named* a database URL, and the tail is used when only the built-in
    default exists. A process that opened a connection at startup to find out would
    make every test that builds an app dial a database it never asked for, and would
    turn "is Postgres up yet" into a reason for a different read model.

    Args:
        mode: the configured mode.
        database_url_named: whether ``AEGIS_DATABASE_URL`` was set by the deployment
            (rather than defaulted), which is what ``auto`` keys on.
    """
    if mode is LogStoreMode.ON:
        return True
    if mode is LogStoreMode.OFF:
        return False
    return database_url_named


def tail_reason(mode: LogStoreMode) -> str:
    """Why a tail is answering under ``mode``, as a sentence a screen can render."""
    return _TAIL_REASON.get(
        mode,
        "This deployment answers from the process's own tail because the log store "
        "is not enabled.",
    )
