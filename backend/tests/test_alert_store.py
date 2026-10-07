"""What an in-memory row is, and what a mean is a mean of (T-418, R-39).

T-418's own tests found this: the flow route's series score is the mean of the
alerts in a bucket, and it is computed from rows the store hands back. The store
handed back the float it was given, where the table hands back a ``Decimal`` at
``numeric(5, 4)`` -- so every bucket's mean was skipped and the screen drew a floor
of zero. The defect lived between two files that were each tested, which is exactly
the seam this file covers.

Three claims, each with the SQL it stands in for:

* A score written as a float reads back as the ``Decimal`` the column returns.
* ``min_score`` keeps a row that sits exactly on the threshold, because the SQL
  compares a ``numeric`` column against a ``float8`` bound.
* The overview's bucket mean is over the rows that carried a readable score, so a
  malformed row neither lowers the mean nor invents a zero for an empty bucket.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.db.models import Alert
from app.db.repository import TimeRange
from app.schemas.query import AlertQuery
from app.services.alert_store import InMemoryAlertStore
from app.services.overview import aggregate

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


def values(*, score: object = 0.9, status: str = "open") -> dict[str, object]:
    """The writable columns of one alert, as the correlator's writer sends them."""
    return {
        "entity_id": 1,
        "family": "Reconnaissance",
        "severity": "high",
        "score": score,
        "model_flow_id": None,
        "model_log_id": None,
        "window_ref": {"store": "stream", "id": "win-1", "trace_id": None, "grouped": False},
        "explanation": {"families": [], "partial_evidence": False, "reasons": []},
        "status": status,
        "first_seen": START,
        "last_seen": START,
        "occurrence_count": 1,
        "verdict": None,
        "verdict_at": None,
    }


def store_with(*scores: object) -> InMemoryAlertStore:
    """A store holding one alert per score, a minute apart."""
    store = InMemoryAlertStore()
    for index, score in enumerate(scores):
        store.save(
            f"case-{index}",
            values(score=score),
            created_at=START + timedelta(minutes=index + 1),
        )
    return store


def scores_of(store: InMemoryAlertStore, **filters: Any) -> list[Any]:
    """The scores the store returns for one read, in the order it returns them."""
    query = AlertQuery(start=START, end=END, **filters)
    return [row.score for row in store.fetch(query)]


# --- the row is the column ---------------------------------------------------


def test_a_float_score_reads_back_as_the_decimal_the_column_holds() -> None:
    """`numeric(5, 4)` returns a Decimal at that scale, so the store does too."""
    row = store_with(0.9).rows()[0]

    assert isinstance(row.score, Decimal)
    assert row.score == Decimal("0.9000")
    assert not isinstance(row.score, float)


def test_a_score_with_more_decimals_rounds_half_away_from_zero() -> None:
    """The rounding PostgreSQL's numeric does, and migration 0002 documents.

    Half-even -- Python's default -- would round this tie down to 0.8122.
    """
    row = store_with(0.81225).rows()[0]

    assert row.score == Decimal("0.8123")


def test_a_refreshed_case_is_re_typed_as_well() -> None:
    """The update path re-applies the column's type, not just the insert path."""
    store = store_with(0.4)
    store.save("case-0", values(score=0.75), created_at=START + timedelta(minutes=1))

    assert store.rows()[0].score == Decimal("0.7500")


# --- the filter compares as the SQL does -------------------------------------


def test_a_row_exactly_on_the_score_threshold_is_kept() -> None:
    """``score >= 0.9`` against a float8 bound keeps a stored 0.9.

    The column's Decimal is compared as the SQL compares it: ``Decimal("0.9000")
    < 0.9`` is true -- the exact 0.9 is below the float, which rounds up -- while
    the query keeps the row. A threshold of 0.5 would not show this: that float is
    the exact half, so the two comparisons agree.
    """
    assert scores_of(store_with(0.9), min_score=0.9) == [Decimal("0.9000")]


def test_a_row_below_the_threshold_is_dropped() -> None:
    """The other half of the boundary, so the test above is not passing vacuously."""
    assert scores_of(store_with(0.4999), min_score=0.5) == []


# --- the mean, over the rows that carried one --------------------------------


def alert(score: object) -> Alert:
    """An :class:`Alert` for the arithmetic's tests, never added to a session."""
    return Alert(
        id=1,
        created_at=START + timedelta(minutes=1),
        entity_id=1,
        family="Reconnaissance",
        severity="high",
        score=score,
        status="open",
        first_seen=START,
        last_seen=START,
        occurrence_count=1,
        verdict=None,
        verdict_at=None,
    )


def windowed(rows: list[Alert]) -> Any:
    """The overview's aggregate for the window these tests describe."""
    return aggregate(rows, start=START, end=END, bucket_minutes=15)


def test_a_bucket_s_mean_is_over_the_rows_that_carried_a_score() -> None:
    """A row with no readable score is skipped, not averaged in as a zero.

    The rows here are constructed rather than stored -- the store types them, as
    the column does -- so this pins the arithmetic against a caller that hands
    ``aggregate`` something the column would not have returned.
    """
    summary = windowed([alert(Decimal("0.8")), alert(0.4)])

    assert summary.points[0].total == 2
    assert summary.points[0].score == pytest.approx(0.8)


def test_a_bucket_with_no_readable_score_has_none() -> None:
    """Not a fabricated zero: a bucket with an alert is not a quiet bucket."""
    summary = windowed([alert(0.4)])

    assert summary.points[0].total == 1
    assert summary.points[0].score is None


def test_a_stored_alert_s_mean_is_its_score() -> None:
    """End to end through the store, which is the path the screen reads."""
    summary = store_with(0.7, 0.3).aggregate(
        TimeRange(start=START, end=END), bucket_minutes=60, entity_limit=5, family_limit=5
    )

    assert summary.points[0].total == 2
    assert summary.points[0].score == pytest.approx(0.5)
