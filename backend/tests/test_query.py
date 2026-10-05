"""T-305: alert queries -- filters that combine, pagination that does not drift.

The acceptance criterion is that pagination is stable under concurrent inserts.
Offset pagination cannot satisfy that, so these tests assert the query shape
that can: a keyset cursor over ``(created_at, id)`` with no OFFSET anywhere, and
a simulation showing what offset pagination would have done to the same data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from app.db.repository import MAX_QUERY_SPAN_DAYS
from app.schemas.query import (
    AlertQuery,
    CursorError,
    decode_cursor,
    encode_cursor,
)
from app.services.query_service import build_alert_select, paginate, time_range_of

START = datetime(2026, 3, 1, tzinfo=UTC)
END = datetime(2026, 3, 31, tzinfo=UTC)


def query(**overrides: object) -> AlertQuery:
    """A valid query, with overrides applied."""
    params: dict[str, object] = {"start": START, "end": END}
    params.update(overrides)
    return AlertQuery(**params)  # type: ignore[arg-type]


def sql_of(q: AlertQuery) -> str:
    """The compiled SQL, so the query shape can be asserted on."""
    return str(build_alert_select(q).compile(dialect=sa.dialects.postgresql.dialect()))


# --- R-34: the window is mandatory -----------------------------------------


def test_start_and_end_are_required() -> None:
    with pytest.raises(Exception, match="start"):  # noqa: B017, PT011
        AlertQuery(end=END)  # type: ignore[call-arg]
    with pytest.raises(Exception, match="end"):  # noqa: B017, PT011
        AlertQuery(start=START)  # type: ignore[call-arg]


def test_a_naive_timestamp_is_refused() -> None:
    """A naive bound compared against timestamptz moves the partition boundary."""
    with pytest.raises(ValueError, match="timezone-aware"):
        sql_of(query(start=datetime(2026, 3, 1)))


def test_an_inverted_range_is_refused() -> None:
    with pytest.raises(ValueError, match="empty or inverted"):
        sql_of(query(start=END, end=START))


def test_a_range_wider_than_the_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="limit"):
        sql_of(query(start=START, end=START + timedelta(days=MAX_QUERY_SPAN_DAYS + 1)))


def test_every_query_carries_a_time_predicate() -> None:
    assert "created_at >=" in sql_of(query())
    assert "created_at <" in sql_of(query())


def test_no_query_uses_offset() -> None:
    """Offset pagination is unstable under concurrent inserts, so it is absent."""
    for q in (query(), query(limit=5, cursor=encode_cursor(START, 1))):
        assert "OFFSET" not in sql_of(q).upper()


# --- filters combine --------------------------------------------------------


def test_each_filter_appears_in_the_sql() -> None:
    sql = sql_of(
        query(severity="high,critical", status="open", family="DoS", entity_id=7, min_score=0.5)
    )
    assert "severity IN" in sql
    assert "status IN" in sql
    assert "family IN" in sql
    assert "entity_id =" in sql
    assert "score >=" in sql


def test_filters_combine_with_and_not_or() -> None:
    sql = sql_of(query(severity="high", family="DoS"))
    assert sql.count(" AND ") >= 3


def test_an_omitted_filter_narrows_nothing() -> None:
    """An absent filter must not become a filter for empty."""
    bare = sql_of(query())
    for fragment in ("severity IN", "family IN", "entity_id =", "score >="):
        assert fragment not in bare


def test_a_comma_separated_filter_is_split() -> None:
    q = query(severity="high, critical ,low")
    assert q.severity == frozenset({"high", "critical", "low"})


def test_an_empty_filter_string_narrows_nothing() -> None:
    assert query(severity=",, ").severity == frozenset()
    assert "severity IN" not in sql_of(query(severity=",, "))


# --- ordering and the cursor ------------------------------------------------


def test_ordering_uses_both_key_columns() -> None:
    """Id alone is not unique across partitions (D-030), so it cannot order."""
    sql = sql_of(query())
    order_clause = sql.split("ORDER BY")[1].split("LIMIT")[0]
    assert "created_at" in order_clause
    assert "id" in order_clause


def test_descending_is_the_default() -> None:
    assert "DESC" in sql_of(query()).split("ORDER BY")[1]


def test_ascending_is_available() -> None:
    assert "ASC" in sql_of(query(order="asc")).split("ORDER BY")[1]


def test_a_cursor_is_a_row_value_comparison() -> None:
    """(created_at, id) < (a, b), not two separate predicates.

    Written as `created_at < a AND id < b` it silently drops rows sharing the
    cursor's timestamp, which is a quiet data loss bug rather than an error.
    """
    sql = sql_of(query(cursor=encode_cursor(START, 5)))
    assert "(alerts.created_at, alerts.id) <" in sql


def test_an_ascending_cursor_compares_the_other_way() -> None:
    sql = sql_of(query(order="asc", cursor=encode_cursor(START, 5)))
    assert "(alerts.created_at, alerts.id) >" in sql


def test_one_extra_row_is_fetched_to_detect_a_next_page() -> None:
    """limit+1, so a next page is known without a second COUNT over partitions."""
    assert int(build_alert_select(query(limit=25))._limit_clause.value) == 26  # noqa: SLF001


def test_the_cursor_round_trips() -> None:
    moment = datetime(2026, 3, 15, 10, 30, tzinfo=UTC)
    assert decode_cursor(encode_cursor(moment, 4242)) == (moment, 4242)


def test_a_malformed_cursor_is_refused_not_ignored() -> None:
    """Restarting from page one would repeat rows and look like a client bug."""
    for bad in ("", "not-base64!!", "aGVsbG8", encode_cursor(START, 1)[:-2] + "zz"):
        with pytest.raises(CursorError):
            decode_cursor(bad)


# --- pagination stability ---------------------------------------------------


def test_keyset_pagination_is_stable_under_concurrent_inserts() -> None:
    """The criterion, demonstrated on the same data both ways.

    A row arrives between pages. Offset pagination then loses a row, because
    the list shifted underneath it; keyset pagination anchors on the last row
    the reader actually saw, so it covers exactly the rows that follow.
    """
    rows = sorted([(START + timedelta(minutes=i), i) for i in range(6)], reverse=True)

    page_one = rows[:2]
    cursor = page_one[-1]

    # A new alert arrives, newer than anything already read.
    newer = (cursor[0] + timedelta(seconds=30), 999)
    after_insert = sorted([newer, *rows], reverse=True)

    # Offset page two: skip two, take two -- but the list has shifted by one.
    offset_page_two = after_insert[2:4]
    # Keyset page two: everything strictly after the cursor, in sort order.
    keyset_page_two = [r for r in after_insert if r < cursor][:2]

    # Offset pagination lost a row: it should have continued at rows[2:4].
    assert offset_page_two != rows[2:4]
    assert len(set(page_one) | set(offset_page_two)) < 4

    # Keyset pagination covered exactly the next two, with no gap and no repeat.
    assert keyset_page_two == rows[2:4]
    assert len(set(page_one) | set(keyset_page_two)) == 4


def test_paginate_returns_no_cursor_on_the_last_page() -> None:
    class Row:
        def __init__(self, i: int) -> None:
            self.id = i
            self.created_at = START + timedelta(minutes=i)
            self.entity_id = 1
            self.family = "DoS"
            self.severity = "high"
            self.score = 0.9
            self.status = "open"
            self.first_seen = self.created_at
            self.last_seen = self.created_at
            self.occurrence_count = 1

    q = query(limit=3)
    page = paginate([Row(i) for i in range(2)], q)  # type: ignore[arg-type]
    assert page.next_cursor is None
    assert len(page.items) == 2


def test_paginate_returns_a_cursor_when_more_rows_exist() -> None:
    class Row:
        def __init__(self, i: int) -> None:
            self.id = i
            self.created_at = START + timedelta(minutes=i)
            self.entity_id = 1
            self.family = "DoS"
            self.severity = "high"
            self.score = 0.9
            self.status = "open"
            self.first_seen = self.created_at
            self.last_seen = self.created_at
            self.occurrence_count = 1

    q = query(limit=2)
    rows = [Row(i) for i in range(3)]  # the extra row means "more available"
    page = paginate(rows, q)  # type: ignore[arg-type]
    assert len(page.items) == 2
    assert page.next_cursor is not None
    # The cursor points at the last row actually returned, not the extra one.
    assert decode_cursor(page.next_cursor) == (rows[1].created_at, rows[1].id)


def test_the_time_range_is_the_validated_one() -> None:
    tr = time_range_of(query())
    assert (tr.start, tr.end) == (START, END)
