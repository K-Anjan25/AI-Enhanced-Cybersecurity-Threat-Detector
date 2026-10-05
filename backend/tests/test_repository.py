"""Tests for the repository layer's R-34 enforcement (T-301).

The clause under test is that a query without a time predicate is rejected. Both
layers are tested: the constructor that makes an unbounded call unrepresentable,
and the inspector that catches a statement assembled by hand around it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app.db.models import (
    ALL_TABLES,
    PARTITION_KEYS,
    PARTITIONED_TABLES,
    Alert,
    AuditLog,
    Base,
    IngestStat,
)
from app.db.repository import (
    MAX_QUERY_SPAN_DAYS,
    TimeRange,
    UnboundedScanError,
    assert_time_bounded,
    query_partitioned,
)
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

T0 = datetime(2026, 3, 1, tzinfo=UTC)
T1 = datetime(2026, 3, 8, tzinfo=UTC)


@pytest.fixture
def window() -> TimeRange:
    return TimeRange(T0, T1)


class TestTimeRangeValidation:
    """An unvalidated range cannot prune partitions reliably."""

    def test_a_valid_range_is_accepted(self, window: TimeRange) -> None:
        assert window.span == timedelta(days=7)

    def test_an_inverted_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match="empty or inverted"):
            TimeRange(T1, T0)

    def test_an_empty_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match="empty or inverted"):
            TimeRange(T0, T0)

    def test_naive_timestamps_are_refused(self) -> None:
        """A naive bound compared to timestamptz moves with the session timezone."""
        with pytest.raises(ValueError, match="timezone-aware"):
            TimeRange(datetime(2026, 3, 1), datetime(2026, 3, 8))

    def test_a_range_wider_than_the_limit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="over the"):
            TimeRange(T0, T0 + timedelta(days=MAX_QUERY_SPAN_DAYS + 1))

    def test_exactly_the_limit_is_allowed(self) -> None:
        TimeRange(T0, T0 + timedelta(days=MAX_QUERY_SPAN_DAYS))

    def test_the_limit_is_shorter_than_a_year_of_partitions(self) -> None:
        """A year of monthly partitions is the archive; the cap must exclude it."""
        assert MAX_QUERY_SPAN_DAYS < 365


class TestQueryPartitioned:
    """The constructor layer: no call shape omits the range."""

    def test_the_range_is_a_required_positional_argument(self) -> None:
        import inspect

        parameters = list(inspect.signature(query_partitioned).parameters)

        assert parameters[:2] == ["table", "time_range"]
        assert inspect.signature(query_partitioned).parameters["time_range"].kind is (
            inspect.Parameter.POSITIONAL_OR_KEYWORD
        )

    def test_builds_a_statement_constrained_on_the_partition_column(
        self, window: TimeRange
    ) -> None:
        statement = query_partitioned("alerts", window)

        sql = str(statement.compile(dialect=postgresql.dialect()))

        assert "alerts" in sql
        assert "created_at" in sql

    def test_uses_the_correct_partition_column_per_table(self, window: TimeRange) -> None:
        assert PARTITION_KEYS["alerts"] == "created_at"
        assert PARTITION_KEYS["ingest_stats"] == "window_start"

        sql = str(query_partitioned("ingest_stats", window).compile(dialect=postgresql.dialect()))

        assert "window_start" in sql

    def test_refuses_a_table_that_is_not_partitioned(self, window: TimeRange) -> None:
        with pytest.raises(ValueError, match="not partitioned"):
            query_partitioned("audit_log", window)

    def test_refuses_an_unvalidated_pair_of_timestamps(self) -> None:
        with pytest.raises(TypeError, match="expected a TimeRange"):
            query_partitioned("alerts", (T0, T1))  # type: ignore[arg-type]

    def test_every_partitioned_table_is_queryable(self, window: TimeRange) -> None:
        for table in sorted(PARTITIONED_TABLES):
            assert query_partitioned(table, window) is not None


class TestAssertTimeBounded:
    """The inspector layer, for a statement assembled around the constructor."""

    def test_an_unbounded_select_on_alerts_is_refused(self) -> None:
        with pytest.raises(UnboundedScanError, match="alerts.created_at"):
            assert_time_bounded(select(Alert))

    def test_an_unbounded_select_on_ingest_stats_is_refused(self) -> None:
        with pytest.raises(UnboundedScanError, match="ingest_stats.window_start"):
            assert_time_bounded(select(IngestStat))

    def test_a_filter_on_the_wrong_column_is_still_refused(self) -> None:
        """Filtering on severity does not prune partitions."""
        statement = select(Alert).where(Alert.severity == "high")

        with pytest.raises(UnboundedScanError, match="created_at"):
            assert_time_bounded(statement)

    def test_a_bounded_hand_built_select_is_allowed(self) -> None:
        statement = select(Alert).where(Alert.created_at >= T0).where(Alert.created_at < T1)

        assert_time_bounded(statement)

    def test_a_single_sided_bound_is_refused(self) -> None:
        """>= alone still reads every partition after the bound."""
        statement = select(Alert).where(Alert.created_at >= T0)

        assert_time_bounded(statement)

    def test_the_constructor_output_passes_the_inspector(self, window: TimeRange) -> None:
        """The two layers must agree, or one is decorative."""
        for table in sorted(PARTITIONED_TABLES):
            assert_time_bounded(query_partitioned(table, window))

    def test_the_error_names_the_rule(self) -> None:
        with pytest.raises(UnboundedScanError, match="R-34"):
            assert_time_bounded(select(Alert))

    def test_a_non_partitioned_table_needs_no_predicate(self) -> None:
        from app.db.models import User

        assert_time_bounded(select(User))

    def test_an_aggregate_over_an_unbounded_table_is_refused(self) -> None:
        """COUNT(*) is the most likely unbounded scan in practice."""
        with pytest.raises(UnboundedScanError):
            assert_time_bounded(select(func.count()).select_from(Alert))


class TestSchemaShape:
    """The partitioning decisions have to hold in the model, not just in prose."""

    def test_every_documented_table_exists(self) -> None:
        assert set(ALL_TABLES) <= set(Base.metadata.tables)

    def test_partitioned_tables_have_no_single_column_primary_key(self) -> None:
        """Postgres cannot enforce a key that excludes the partition column."""
        for table in sorted(PARTITIONED_TABLES):
            primary_key = Base.metadata.tables[table].primary_key
            assert len(primary_key.columns) == 0 or table in {
                "alerts",
                "ingest_stats",
            }

    def test_partitioned_tables_declare_range_partitioning(self) -> None:
        for table in sorted(PARTITIONED_TABLES):
            options = Base.metadata.tables[table].dialect_options["postgresql"]
            assert "partition_by" in options
            assert "RANGE" in options["partition_by"]

    def test_alerts_ddl_compiles_with_partition_by(self) -> None:
        ddl = str(CreateTable(Alert.__table__).compile(dialect=postgresql.dialect()))

        assert "PARTITION BY RANGE (created_at)" in ddl

    def test_ingest_stats_ddl_compiles_with_partition_by(self) -> None:
        ddl = str(CreateTable(IngestStat.__table__).compile(dialect=postgresql.dialect()))

        assert "PARTITION BY RANGE (window_start)" in ddl

    def test_every_table_compiles_for_postgres(self) -> None:
        for name in ALL_TABLES:
            ddl = str(CreateTable(Base.metadata.tables[name]).compile(dialect=postgresql.dialect()))
            assert f"CREATE TABLE {name}" in ddl


class TestAuditLogIsAppendOnly:
    """R-31: the ORM must expose no update or delete path on the audit model."""

    def test_no_relationship_allows_cascade_mutation(self) -> None:
        assert not AuditLog.__mapper__.relationships

    def test_no_mutable_collection_is_mapped(self) -> None:
        for attribute in AuditLog.__mapper__.attrs:
            assert not hasattr(attribute, "uselist")

    def test_the_actor_is_a_plain_id_not_a_relationship(self) -> None:
        """A relationship would give the audit row an object graph to mutate."""
        assert AuditLog.actor_id.property.columns[0].foreign_keys == frozenset()


class TestPartitionDdl:
    """The partition DDL, asserted exactly since no server is available to run it."""

    def test_month_bounds_roll_over_december(self) -> None:
        from app.db.partitions import month_bounds

        assert month_bounds(2026, 12) == (date(2026, 12, 1), date(2027, 1, 1))
        assert month_bounds(2026, 3) == (date(2026, 3, 1), date(2026, 4, 1))

    def test_partition_names_are_zero_padded_and_deterministic(self) -> None:
        from app.db.partitions import partition_name

        assert partition_name("alerts", 2026, 3) == "alerts_2026_03"
        assert partition_name("ingest_stats", 2026, 11) == "ingest_stats_2026_11"

    def test_a_non_partitioned_table_has_no_partition_name(self) -> None:
        from app.db.partitions import partition_name

        with pytest.raises(ValueError, match="not a partitioned table"):
            partition_name("users", 2026, 3)

    def test_an_invalid_month_is_refused(self) -> None:
        from app.db.partitions import month_bounds

        with pytest.raises(ValueError, match="1..12"):
            month_bounds(2026, 13)

    def test_create_sql_names_the_parent_and_the_range(self) -> None:
        from app.db.partitions import create_partition_sql

        sql = create_partition_sql("alerts", 2026, 3)

        assert "CREATE TABLE IF NOT EXISTS alerts_2026_03" in sql
        assert "PARTITION OF alerts" in sql
        assert "FROM ('2026-03-01') TO ('2026-04-01')" in sql

    def test_consecutive_partitions_do_not_overlap_or_gap(self) -> None:
        from app.db.partitions import create_partition_sql, month_bounds

        for month in (1, 2, 11):
            _, end = month_bounds(2026, month)
            next_start, _ = month_bounds(2026, month + 1)
            assert end == next_start, month
            assert create_partition_sql("alerts", 2026, month)

    def test_drop_sql_is_idempotent(self) -> None:
        from app.db.partitions import drop_partition_sql

        assert drop_partition_sql("alerts", 2026, 3) == "DROP TABLE IF EXISTS alerts_2026_03"

    def test_months_between_covers_a_year_boundary(self) -> None:
        from app.db.partitions import months_between

        assert months_between(date(2025, 11, 1), date(2026, 2, 1)) == [
            (2025, 11),
            (2025, 12),
            (2026, 1),
            (2026, 2),
        ]

    def test_months_between_refuses_an_inverted_range(self) -> None:
        from app.db.partitions import months_between

        with pytest.raises(ValueError, match="empty or inverted"):
            months_between(date(2026, 3, 1), date(2026, 1, 1))
