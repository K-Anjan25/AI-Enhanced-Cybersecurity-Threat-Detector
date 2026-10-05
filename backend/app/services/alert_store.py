"""Where alert rows live between the correlator and the query API (T-319, T-305).

The correlator decides that an incident exists; this module is the seam that keeps
the row the query API reads back, so the golden test can run the whole path --
traffic in, alert out -- without PostgreSQL (R-88). :class:`AlertStore` is the
narrow protocol; :class:`InMemoryAlertStore` is the implementation that runs here.

**One row per case, replaced in place.** An incident does not produce a new row
every time it absorbs a repeat (FR-15): the row's ``occurrence_count`` grows, its
``last_seen`` moves and its severity can only escalate, and an analyst watching the
API must see one alert, not a stream of rows for one incident. So :meth:`save` is
keyed on the correlator's case id -- which is derived from data, so a replayed
window lands on the same row rather than a second one -- and keeps the row's own
``id`` and ``created_at`` stable while the values are refreshed.

That key is the reason this file also records a gap: the ``alerts`` table has no
case-id column and no unique index over the case's identifying data, so a
persistent adapter has nothing to upsert against. The row's ``window_ref`` carries
the window the case opened on, which is derivable from the case id but not
uniquely indexed, and D-053 records the missing column as work for a schema task
rather than papering over it here.

The in-memory implementation re-states the SQL predicates -- the bounded window
(R-34), the filters, the keyset cursor -- in Python, and that duplication is
deliberate and bounded: it is what lets the golden test exercise the API's own
query semantics with no server. ``test_query.py`` still asserts the SQL, so the two
descriptions of "the same page" are both under test.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from app.db.models import Alert, AlertStatus
from app.db.repository import TimeRange
from app.schemas.query import AlertQuery, decode_cursor

__all__ = ["AlertStore", "InMemoryAlertStore"]


class AlertStore(Protocol):
    """Storage for `alerts` rows, in the shape the query layer reads back."""

    def save(self, case_id: str, values: Mapping[str, object], *, created_at: datetime) -> Alert:
        """Store one alert, replacing any earlier row for the same case.

        Args:
            case_id: the correlator's stable case id.
            values: the writable ``alerts`` columns, as :func:`alert_row` produced.
            created_at: the row's creation time, used as its partition key.

        Returns:
            The stored row, with its database-assigned ``id``.
        """
        ...

    def fetch(self, query: AlertQuery) -> list[Alert]:
        """Return up to ``limit + 1`` rows matching the query, in its order.

        The extra row is how the caller knows whether a next page exists without a
        second count, exactly as the SQL does (T-305).

        Raises:
            ValueError: if the time range is not usable (a naive or inverted
                bound, or one wider than the R-34 span limit).
        """
        ...


class InMemoryAlertStore:
    """An :class:`AlertStore` in a list, for tests and single-process runs.

    Rows are the ORM's :class:`~app.db.models.Alert` class, never added to a
    session. That is not a trick: the row the API serialises is the same object
    type the persistent adapter will hand back, so :func:`paginate` does not know
    which store it was given.
    """

    __slots__ = ("_case_ids", "_next_id", "_rows")

    def __init__(self) -> None:
        """Start empty, with database-style ids from 1."""
        self._rows: list[Alert] = []
        self._case_ids: dict[str, int] = {}
        self._next_id = 1

    def save(self, case_id: str, values: Mapping[str, object], *, created_at: datetime) -> Alert:
        """Store or refresh one case's row, keeping its id and creation time."""
        existing = self._case_ids.get(case_id)
        if existing is not None:
            for row in self._rows:
                if row.id == existing:
                    for name, value in values.items():
                        setattr(row, name, _column_value(name, value))
                    return row
        row = Alert(
            id=self._next_id,
            created_at=created_at,
            **{name: _column_value(name, value) for name, value in values.items()},
        )
        self._next_id += 1
        self._case_ids[case_id] = row.id
        self._rows.append(row)
        return row

    def fetch(self, query: AlertQuery) -> list[Alert]:
        """Apply the query's predicates, order and cursor to the stored rows."""
        window = TimeRange(start=query.start, end=query.end)
        cursor = decode_cursor(query.cursor) if query.cursor is not None else None

        matching = [
            row
            for row in self._rows
            if window.start <= row.created_at < window.end
            and _matches(row, query)
            and (cursor is None or _after_cursor(row, cursor, query.order))
        ]
        matching.sort(key=lambda row: (row.created_at, row.id), reverse=query.order == "desc")
        return matching[: query.limit + 1]

    def rows(self) -> tuple[Alert, ...]:
        """Every stored row, for assertions and diagnostics."""
        return tuple(self._rows)

    def __len__(self) -> int:
        """How many rows are stored."""
        return len(self._rows)


def _column_value(name: str, value: object) -> object:
    """Normalise one column value the way the database would on the way back.

    The status column is a native enum, so a string written by the correlator
    reads back as ``AlertStatus``. Doing the same here keeps the in-memory store
    honest about the type a caller gets.
    """
    if name == "status" and isinstance(value, str):
        return AlertStatus(value)
    return value


def _matches(row: Alert, query: AlertQuery) -> bool:
    """Whether one row satisfies every filter in the query."""
    if query.severity and str(row.severity) not in query.severity:
        return False
    if query.status and str(row.status) not in query.status:
        return False
    if query.family and str(row.family) not in query.family:
        return False
    if query.entity_id is not None and row.entity_id != query.entity_id:
        return False
    return not (query.min_score is not None and row.score < query.min_score)


def _after_cursor(row: Alert, cursor: tuple[datetime, int], order: str) -> bool:
    """Whether a row sorts strictly after the cursor, on both key columns."""
    key = (row.created_at, row.id)
    return key < cursor if order == "desc" else key > cursor
