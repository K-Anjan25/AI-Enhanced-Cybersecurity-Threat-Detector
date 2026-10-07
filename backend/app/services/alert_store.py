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

**A stored row is the row the column would return.** Two of the ``alerts`` columns
have a type the database imposes and Python does not: ``status`` is a native enum,
and ``score`` is ``numeric(5, 4)`` (R-39), so a score written here as a float would
come back from the table as a ``Decimal`` at that scale. :func:`_column_value`
imposes both, because the difference is not cosmetic: the overview's series score
is the mean of a bucket's scores and counts only the rows whose score is a
``Decimal``, so a float in this store reads on screen as a floor of zero (D-077).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.db.models import SCORE_SCALE, Alert, AlertStatus
from app.db.repository import TimeRange
from app.schemas.query import AlertQuery, decode_cursor
from app.services.overview import (
    BUCKET_MINUTES_DEFAULT,
    ENTITY_LIMIT_DEFAULT,
    FAMILY_LIMIT_DEFAULT,
    Aggregate,
    aggregate,
)

__all__ = ["AlertStore", "InMemoryAlertStore"]

#: The unit a score rounds to: the last digit of ``numeric(5, 4)`` (R-39).
_SCORE_QUANTUM = Decimal(1).scaleb(-SCORE_SCALE)


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

    def aggregate(
        self,
        window: TimeRange,
        *,
        bucket_minutes: int = BUCKET_MINUTES_DEFAULT,
        entity_limit: int = ENTITY_LIMIT_DEFAULT,
        family_limit: int = FAMILY_LIMIT_DEFAULT,
    ) -> Aggregate:
        """Aggregate **every** row in the window into the overview's panels (T-416).

        The distinction from :meth:`fetch` is the task: ``fetch`` answers one page
        and is capped by ``limit``, which is why the screen that counted its own
        rows could report a partial window. This counts the window. An adapter is
        free to implement it as a ``GROUP BY`` (see
        :func:`app.db.repository.alert_aggregate_statements`), and it must not
        apply a row cap to the totals -- ``entities_capped`` is the only cap in
        the response, and it caps a list, not a count.

        Args:
            window: the bounded range to aggregate.
            bucket_minutes: the series' resolution.
            entity_limit: how many entities the response lists.
            family_limit: how many families the mix lists.

        Returns:
            The window's aggregate, complete for the totals and the series.

        Raises:
            ValueError: if the range is not usable (naive, inverted or over-wide).
        """
        ...

    def get(self, alert_id: int, created_at: datetime) -> Alert | None:
        """Return one alert addressed by its partition key, or ``None``.

        Both halves of the key are required, per D-030: ``id`` alone is not unique
        across partitions, so an id-only lookup can address a different row in a
        different month. A point lookup on the partition key is not an R-34
        concern -- the key constrains ``created_at`` exactly -- which is why this
        is a method rather than a window query the caller has to guess at.
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

    def get(self, alert_id: int, created_at: datetime) -> Alert | None:
        """Return the stored row with this ``(id, created_at)``, or ``None``."""
        for row in self._rows:
            if row.id == alert_id and row.created_at == created_at:
                return row
        return None

    def aggregate(
        self,
        window: TimeRange,
        *,
        bucket_minutes: int = BUCKET_MINUTES_DEFAULT,
        entity_limit: int = ENTITY_LIMIT_DEFAULT,
        family_limit: int = FAMILY_LIMIT_DEFAULT,
    ) -> Aggregate:
        """Aggregate every stored row in the window, with no cap on the counts.

        The in-memory reach of this is the whole store rather than a page: the
        point of T-416 is that a count is the window's count, so filtering here is
        the same predicate the SQL uses and the tally is complete either way.
        """
        rows = [row for row in self._rows if window.start <= row.created_at < window.end]
        return aggregate(
            rows,
            start=window.start,
            end=window.end,
            bucket_minutes=bucket_minutes,
            entity_limit=entity_limit,
            family_limit=family_limit,
        )

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
    reads back as ``AlertStatus``. The score column is ``numeric(5, 4)``, so a
    float written by a caller reads back as a ``Decimal`` rounded to four places
    -- half away from zero, which is what PostgreSQL's ``numeric`` does and what
    migration ``0002`` documents. Doing both here keeps the in-memory store honest
    about the types a caller gets, which is the only reason the overview's mean
    score and the ``min_score`` filter agree with the SQL they stand in for.
    """
    if name == "status" and isinstance(value, str):
        return AlertStatus(value)
    if name == "score" and isinstance(value, int | float | str | Decimal):
        return Decimal(str(value)).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
    return value


def _matches(row: Alert, query: AlertQuery) -> bool:
    """Whether one row satisfies every filter in the query.

    The score filter compares as the SQL does rather than in ``Decimal``: the
    parameter is a float, and ``Alert.score >= query.min_score`` reaches PostgreSQL
    as a ``numeric`` column against a ``float8`` bound, so a row *at* the threshold
    is kept. Comparing the column's ``Decimal`` against the float directly would
    drop ``0.9000`` from a ``min_score=0.9`` read, because the exact ``0.9`` is
    below the float -- which is not the exact tenth either (D-077).
    """
    if query.severity and str(row.severity) not in query.severity:
        return False
    if query.status and str(row.status) not in query.status:
        return False
    if query.family and str(row.family) not in query.family:
        return False
    if query.entity_id is not None and row.entity_id != query.entity_id:
        return False
    return not (query.min_score is not None and float(row.score) < query.min_score)


def _after_cursor(row: Alert, cursor: tuple[datetime, int], order: str) -> bool:
    """Whether a row sorts strictly after the cursor, on both key columns."""
    key = (row.created_at, row.id)
    return key < cursor if order == "desc" else key > cursor
