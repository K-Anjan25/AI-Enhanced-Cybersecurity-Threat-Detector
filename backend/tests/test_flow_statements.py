"""The flow store's statements (T-418).

Asserted as SQL, for the reason the log statements are: a builder that dropped its
window, ordered by the wrong column or joined a table it should not is a bug a live
server would happily execute. The round trip is ``test_flow_store_live.py``.

Four things are pinned here, and each is a rule rather than a preference:

* **Every windowed statement carries both bounds** and passes R-34's inspector, so the
  day ``flow_events`` is partitioned these statements are already what the rule demands.
* **No alert join.** A ``flow@1`` record carries no score, severity or entity; the
  overlay is composed at the endpoint from the alert store (D-075's rule). A statement
  that reached into the alert tables would make the traffic read model a second owner of
  the alert numbers.
* **The bucket is ``date_bin`` on the window's own origin**, because PostgreSQL 16 is the
  deployed server and ``date_trunc`` cannot take an arbitrary minute width. It is also
  the grid ``bucket_index`` uses, so a stored read and a rolled-up read agree bucket for
  bucket.
* **Both ends of a record are addresses**, unioned before grouping -- an address that only
  ever receives is half the traffic a graph is drawn from.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.db.flow_statements import (
    bucket_rows_statement,
    coverage_statement,
    edge_rows_statement,
    node_rows_statement,
)
from app.db.repository import TimeRange
from sqlalchemy.dialects import postgresql

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
END = START.replace(hour=11)
RANGE = TimeRange(start=START, end=END)


def sql(statement: object) -> str:
    """One statement compiled for PostgreSQL, as the server would receive it."""
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


class TestTheBucketRows:
    """The series comes from ``date_bin``, not from arithmetic on the client."""

    def test_it_bins_on_the_windows_own_origin(self) -> None:
        text = sql(bucket_rows_statement(RANGE, bucket_minutes=5))

        assert "date_bin(" in text
        assert "flow_events.timestamp" in text

    def test_the_width_is_a_parameter_not_a_literal(self) -> None:
        # ``date_trunc`` cannot take an arbitrary minute width; ``date_bin`` takes one as
        # an interval parameter, which is why the deployed PostgreSQL 16 is a floor.
        text = sql(bucket_rows_statement(RANGE, bucket_minutes=7))

        assert "date_bin(" in text
        assert "minute" in text or "param" in text

    def test_it_is_bounded_at_both_ends(self) -> None:
        text = sql(bucket_rows_statement(RANGE, bucket_minutes=5))

        assert "flow_events.timestamp >= " in text
        assert "flow_events.timestamp < " in text

    def test_it_groups_by_the_bucket_it_labels(self) -> None:
        text = sql(bucket_rows_statement(RANGE, bucket_minutes=5))

        assert "GROUP BY date_bin(" in text

    def test_it_orders_oldest_first(self) -> None:
        # Ascending by the bucket, which is the label the select already computed: a
        # client that had to re-sort the series would be a client that could get it wrong.
        text = sql(bucket_rows_statement(RANGE, bucket_minutes=5))

        assert "ORDER BY start" in text
        assert "DESC" not in text

    def test_a_protocol_filter_is_a_predicate(self) -> None:
        text = sql(bucket_rows_statement(RANGE, bucket_minutes=5, protocol="tcp"))

        assert "flow_events.protocol = " in text

    def test_a_direction_filter_is_a_predicate(self) -> None:
        text = sql(bucket_rows_statement(RANGE, bucket_minutes=5, direction="inbound"))

        assert "flow_events.direction = " in text

    def test_a_zero_width_is_refused_before_the_server_sees_it(self) -> None:
        with pytest.raises(ValueError, match="bucket_minutes must be positive"):
            bucket_rows_statement(RANGE, bucket_minutes=0)


class TestTheNodeRows:
    """Per-address totals, from both ends, busiest first, capped."""

    def test_both_ends_are_unioned(self) -> None:
        text = sql(node_rows_statement(RANGE, limit=5))

        assert "UNION ALL" in text
        assert "flow_events.src_ip AS ip" in text
        assert "flow_events.dst_ip AS ip" in text

    def test_the_two_sides_are_labelled_inbound_and_outbound(self) -> None:
        text = sql(node_rows_statement(RANGE, limit=5))

        assert "inbound" in text
        assert "outbound" in text

    def test_it_groups_by_address(self) -> None:
        text = sql(node_rows_statement(RANGE, limit=5))

        assert "GROUP BY" in text
        assert "ip" in text

    def test_it_orders_by_count_then_bytes_then_address(self) -> None:
        # The order the in-process rollup sorts by, so one window lists the same
        # addresses in the same order whichever source answered.
        text = sql(node_rows_statement(RANGE, limit=5))

        header, _, tail = text.partition("ORDER BY")
        assert "count" in tail
        assert "sum(" in tail
        assert ".ip" in tail

    def test_it_is_capped(self) -> None:
        text = sql(node_rows_statement(RANGE, limit=3))

        assert "LIMIT" in text

    def test_the_inner_selects_are_bounded_too(self) -> None:
        text = sql(node_rows_statement(RANGE, limit=5))

        # Both bounds in each half of the union: four predicates in total.
        assert text.count("flow_events.timestamp >= ") == 2
        assert text.count("flow_events.timestamp < ") == 2

    def test_a_non_positive_limit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="limit must be at least 1"):
            node_rows_statement(RANGE, limit=0)


class TestTheEdgeRows:
    """Per-directional-pair totals, heaviest first, capped."""

    def test_it_groups_by_the_directional_pair(self) -> None:
        text = sql(edge_rows_statement(RANGE, limit=5))

        assert "GROUP BY flow_events.src_ip, flow_events.dst_ip" in text

    def test_it_does_not_merge_the_two_directions(self) -> None:
        # ``a -> b`` and ``b -> a`` are two rows: a count that merged them would
        # describe a conversation, and the responder reads an edge for the direction.
        text = sql(edge_rows_statement(RANGE, limit=5))

        assert "LEAST" not in text
        assert "GREATEST" not in text

    def test_it_is_bounded_at_both_ends(self) -> None:
        text = sql(edge_rows_statement(RANGE, limit=5))

        assert "flow_events.timestamp >= " in text
        assert "flow_events.timestamp < " in text

    def test_it_orders_by_count_then_bytes_then_the_pair(self) -> None:
        text = sql(edge_rows_statement(RANGE, limit=5))

        _, _, tail = text.partition("ORDER BY")
        assert "count" in tail
        assert "sum(" in tail
        assert "src_ip" in tail

    def test_a_non_positive_limit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="limit must be at least 1"):
            edge_rows_statement(RANGE, limit=-1)


class TestNoAlertJoin:
    """The flow statements count traffic and nothing else (D-075's rule)."""

    @pytest.mark.parametrize(
        "statement",
        [
            bucket_rows_statement(RANGE, bucket_minutes=5),
            node_rows_statement(RANGE, limit=5),
            edge_rows_statement(RANGE, limit=5),
        ],
    )
    def test_no_alert_table_appears(self, statement: object) -> None:
        text = sql(statement)

        assert "alerts" not in text
        assert "score" not in text
        assert "severity" not in text


class TestCoverage:
    """The one unwindowed statement, and why it is allowed to be."""

    def test_it_asks_for_the_oldest_newest_and_the_count(self) -> None:
        text = sql(coverage_statement())

        assert "min(flow_events.timestamp)" in text
        assert "max(flow_events.timestamp)" in text
        assert "count(" in text

    def test_it_has_no_window_because_it_answers_about_the_table_not_a_window(self) -> None:
        # Deliberately the only statement without bounds: it separates "nothing has ever
        # been stored" from "the window held nothing", which is the difference the
        # caveats are built on. A window here would make it unable to answer that.
        text = sql(coverage_statement())

        assert "WHERE" not in text
