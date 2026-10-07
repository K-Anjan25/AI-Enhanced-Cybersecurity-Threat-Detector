"""The log store's statements (T-419).

These assert the SQL rather than the round trip: the fold is PostgreSQL's job, and a
statement that has no ``ORDER BY`` or reads outside its window is a bug no amount of
server would make visible. The live round trip is in ``test_log_store_live.py``.

What is pinned here, and why each is worth a test:

* **the window, on every statement that has one.** R-34 is enforced at the route, but
  a builder that forgot a bound would be reachable from anywhere the store is used.
* **the filters, as values rather than member reprs.** ``LogLevel`` is a ``StrEnum``,
  so ``LogLevel.ERROR`` compares equal to ``"error"``; the SQL must carry the text or
  the parameter would be a member object the driver refuses.
* **the ordering.** ``count DESC, key ASC`` is the tail's order too, and a store that
  listed clusters differently would make the same window read two ways depending on a
  deployment's configuration.
* **``template_id IS NULL``** for "no template mined". A prefix test on the key would
  be cheaper and wrong: a template id may legally begin with ``message:``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.db.log_statements import (
    cluster_levels_statement,
    cluster_rows_statement,
    coverage_statement,
    distinct_cluster_count_statement,
    line_rows_statement,
    untemplated_line_count_statement,
    window_line_count_statement,
)
from app.db.repository import MAX_QUERY_SPAN_DAYS, TimeRange
from app.schemas.ingest import LogLevel
from sqlalchemy.dialects import postgresql

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
END = START.replace(hour=11)
RANGE = TimeRange(start=START, end=END)


def sql(statement: object) -> str:
    """One statement compiled for PostgreSQL, as the server would receive it."""
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


class TestTheFold:
    """One row per cluster, busiest first, capped."""

    def test_it_groups_by_the_stored_key(self) -> None:
        text = sql(cluster_rows_statement(RANGE, limit=5))

        assert "GROUP BY log_events.key" in text

    def test_it_is_bounded_at_both_ends(self) -> None:
        text = sql(cluster_rows_statement(RANGE, limit=5))

        assert "log_events.timestamp >= " in text
        assert "log_events.timestamp < " in text

    def test_it_orders_by_count_then_key(self) -> None:
        """The tail's own order, so the same window reads the same way twice."""
        text = sql(cluster_rows_statement(RANGE, limit=5))

        assert "ORDER BY count(*) DESC, key ASC" in text

    def test_the_limit_is_rendered(self) -> None:
        text = sql(cluster_rows_statement(RANGE, limit=7))

        assert "LIMIT " in text
        assert "param_1" in text or "7" in text

    def test_it_carries_the_count_the_span_and_the_sample(self) -> None:
        text = sql(cluster_rows_statement(RANGE, limit=5))

        assert "count(*) AS lines" in text
        assert "min(log_events.timestamp) AS first_seen" in text
        assert "max(log_events.timestamp) AS last_seen" in text
        assert "array_agg(log_events.message ORDER BY" in text
        assert "log_events.id DESC" in text, "a tie must break on arrival order"

    def test_it_collects_the_distinct_hosts_and_services(self) -> None:
        text = sql(cluster_rows_statement(RANGE, limit=5))

        assert "array_agg(distinct(log_events.host))" in text
        assert "array_agg(distinct(log_events.service))" in text

    def test_a_host_filter_is_a_predicate(self) -> None:
        text = sql(cluster_rows_statement(RANGE, host="web-1", limit=5))

        assert "log_events.host = " in text

    def test_an_absent_filter_is_no_predicate_at_all(self) -> None:
        """``None`` means "no filter", not "match the empty string"."""
        text = sql(cluster_rows_statement(RANGE, limit=5))

        assert "log_events.host = " not in text
        assert "log_events.service = " not in text
        assert "log_events.level = " not in text

    def test_a_level_filter_carries_the_text_not_the_member(self) -> None:
        text = sql(cluster_rows_statement(RANGE, level=LogLevel.ERROR, limit=5))

        assert "log_events.level = " in text

    def test_the_level_parameter_is_a_string(self) -> None:
        statement = cluster_rows_statement(RANGE, level=LogLevel.ERROR, limit=5)
        compiled = statement.compile(dialect=postgresql.dialect())

        assert "error" in compiled.params.values()

    @pytest.mark.parametrize("limit", [0, -1])
    def test_a_limit_below_one_is_refused(self, limit: int) -> None:
        with pytest.raises(ValueError, match="limit must be at least 1"):
            cluster_rows_statement(RANGE, limit=limit)


class TestTheLevelHistogram:
    """``(key, level, count)`` for the rows the fold returned."""

    def test_it_groups_by_key_and_level(self) -> None:
        text = sql(cluster_levels_statement(RANGE, keys=["t-1"]))

        assert "GROUP BY log_events.key, log_events.level" in text

    def test_it_is_scoped_to_the_given_keys(self) -> None:
        """Otherwise the histogram's cost is the window's cardinality, not the read's."""
        text = sql(cluster_levels_statement(RANGE, keys=["t-1", "t-2"]))

        assert "log_events.key IN " in text

    def test_it_is_still_bounded_and_filtered(self) -> None:
        text = sql(cluster_levels_statement(RANGE, keys=["t-1"], host="web-1", service="api"))

        assert "log_events.timestamp >= " in text
        assert "log_events.timestamp < " in text
        assert "log_events.host = " in text
        assert "log_events.service = " in text

    def test_no_keys_is_refused(self) -> None:
        with pytest.raises(ValueError, match="keys must not be empty"):
            cluster_levels_statement(RANGE, keys=[])


class TestTheCounts:
    """The statements that let a read say how much it is not showing."""

    def test_distinct_clusters_counts_keys_not_rows(self) -> None:
        text = sql(distinct_cluster_count_statement(RANGE))

        assert "count(distinct(log_events.key))" in text

    def test_the_line_count_is_bounded(self) -> None:
        text = sql(window_line_count_statement(RANGE))

        assert "count(*) AS lines" in text
        assert "log_events.timestamp >= " in text
        assert "log_events.timestamp < " in text

    def test_the_line_count_takes_a_key(self) -> None:
        """Expanding a cluster asks the same question the row answered."""
        text = sql(window_line_count_statement(RANGE, key="t-1"))

        assert "log_events.key = " in text

    def test_untemplated_counts_a_null_template_not_a_key_prefix(self) -> None:
        text = sql(untemplated_line_count_statement(RANGE))

        assert "log_events.template_id IS NULL" in text
        assert "LIKE" not in text.upper(), "a prefix test would misread a template id"

    def test_untemplated_carries_the_reads_filters(self) -> None:
        text = sql(untemplated_line_count_statement(RANGE, host="web-1", key="t-1"))

        assert "log_events.host = " in text
        assert "log_events.key = " in text


class TestTheLines:
    """The raw rows behind a cluster, newest first in SQL."""

    def test_it_orders_newest_first(self) -> None:
        text = sql(line_rows_statement(RANGE, limit=10))

        assert "ORDER BY log_events.timestamp DESC, log_events.id DESC" in text

    def test_it_selects_the_columns_the_wire_model_needs(self) -> None:
        text = sql(line_rows_statement(RANGE, limit=10))

        for column in ("timestamp", "host", "service", "level", "message", "template_id"):
            assert f"log_events.{column}" in text

    def test_it_is_bounded_and_capped(self) -> None:
        text = sql(line_rows_statement(RANGE, limit=10))

        assert "log_events.timestamp >= " in text
        assert "log_events.timestamp < " in text
        assert "LIMIT " in text

    def test_a_limit_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="limit must be at least 1"):
            line_rows_statement(RANGE, limit=0)


class TestCoverage:
    """What the store holds, which is not a windowed question."""

    def test_it_measures_the_whole_table(self) -> None:
        text = sql(coverage_statement())

        assert "min(log_events.timestamp) AS oldest" in text
        assert "max(log_events.timestamp) AS newest" in text
        assert "count(*) AS lines" in text

    def test_it_has_no_time_predicate_on_purpose(self) -> None:
        """A coverage that was itself windowed would answer a different question."""
        text = sql(coverage_statement())

        assert "WHERE" not in text.upper()


class TestTheBoundsAreTheRulesOwn:
    """R-34, at the layer that builds the SQL."""

    def test_a_range_over_the_query_limit_cannot_be_built(self) -> None:
        """The bound is the type's, so a builder cannot be handed a wider one."""
        with pytest.raises(ValueError, match=str(MAX_QUERY_SPAN_DAYS)):
            TimeRange(start=START, end=START.replace(year=START.year + 1))

    def test_an_inverted_range_cannot_be_built(self) -> None:
        with pytest.raises(ValueError, match="empty or inverted"):
            window_line_count_statement(TimeRange(start=END, end=START))

    def test_a_naive_bound_cannot_be_built(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            window_line_count_statement(TimeRange(start=datetime(2026, 10, 6), end=END))

    def test_every_windowed_statement_carries_both_bounds(self) -> None:
        statements = [
            cluster_rows_statement(RANGE, limit=5),
            cluster_levels_statement(RANGE, keys=["t-1"]),
            distinct_cluster_count_statement(RANGE),
            window_line_count_statement(RANGE),
            untemplated_line_count_statement(RANGE),
            line_rows_statement(RANGE, limit=5),
        ]

        for statement in statements:
            text = sql(statement)
            assert "log_events.timestamp >= " in text
            assert "log_events.timestamp < " in text
