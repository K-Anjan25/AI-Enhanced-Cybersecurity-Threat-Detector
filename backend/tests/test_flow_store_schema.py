"""The flow store's table: the model, the migration and the DDL (T-418).

Checked the way the log store's table is (T-419's ``test_log_store_schema.py``), and for
the same reason: the ORM metadata and the emitted DDL are both assertable without a
server, and the property that matters most is that the model and the migration agree --
column for column, in order, with the same nullability. The live round trip in
``test_flow_store_live.py`` would find a difference too, but only where a PostgreSQL
happens to be running.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.db.models import ALL_TABLES, PARTITION_KEYS, PARTITIONED_TABLES, FlowEvent
from sqlalchemy import String
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "0004_flow_events_store.py"

#: Offline mode never connects, so any PostgreSQL-shaped URL works.
_URL = "postgresql://aegis:aegis@localhost:5432/aegis"  # pragma: allowlist secret

#: The model's columns, in the order the model declares them.
_COLUMNS = (
    "id",
    "timestamp",
    "src_ip",
    "dst_ip",
    "protocol",
    "direction",
    "bytes",
    "packets",
)


def _alembic(*args: str) -> str:
    """Run Alembic and return stdout, or fail with its stderr."""
    result = subprocess.run(
        # S607 is a false positive: sys.executable is an absolute path.
        [sys.executable, "-m", "alembic", *args],  # noqa: S607
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "AEGIS_DATABASE_URL": _URL},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


class TestTheModel:
    """``flow_events`` in the ORM, where the store's statements read it."""

    def test_the_table_is_declared(self) -> None:
        assert FlowEvent.__tablename__ == "flow_events"
        assert "flow_events" in ALL_TABLES

    def test_its_columns_are_the_stores_own(self) -> None:
        assert tuple(FlowEvent.__table__.columns.keys()) == _COLUMNS

    def test_the_record_fields_are_required(self) -> None:
        """A stored flow without either address or its bounds cannot be grouped."""
        for name in _COLUMNS:
            assert FlowEvent.__table__.columns[name].nullable is False, name

    def test_the_addresses_are_wide_enough_for_v6(self) -> None:
        """``flow@1`` carries IPv4 today; the column does not promise it always will."""
        for name in ("src_ip", "dst_ip"):
            column = FlowEvent.__table__.columns[name]
            assert isinstance(column.type, String)
            assert column.type.length == 45

    def test_the_labels_are_short_text_columns(self) -> None:
        """The protocol and direction enums live in the schema module, as text here."""
        assert FlowEvent.__table__.columns["protocol"].type.length == 16
        assert FlowEvent.__table__.columns["direction"].type.length == 16

    def test_the_counters_are_integers(self) -> None:
        for name in ("bytes", "packets"):
            assert "BIGINT" in str(FlowEvent.__table__.columns[name].type).upper()

    def test_the_instant_is_timezone_aware(self) -> None:
        assert FlowEvent.__table__.columns["timestamp"].type.timezone is True

    def test_it_is_not_partitioned(self) -> None:
        """Swept by a retention job of its own, which is not built (T-418's caveat).

        Recorded rather than implied: a table that *looked* partitioned would make
        R-34's inspector demand a predicate for a table no plan drops, and the privacy
        report would stop naming it as unevictable.
        """
        assert "flow_events" not in PARTITIONED_TABLES
        assert "flow_events" not in PARTITION_KEYS

    def test_it_compiles_for_postgres(self) -> None:
        ddl = str(CreateTable(FlowEvent.__table__).compile(dialect=postgresql.dialect()))

        assert "CREATE TABLE flow_events" in ddl
        assert "BIGINT" in ddl.upper()

    def test_the_indexes_serve_the_reads_that_exist(self) -> None:
        """Every read is "this window" or "this address inside this window"."""
        names = {
            index.name: tuple(column.name for column in index.columns)
            for index in FlowEvent.__table__.indexes
        }

        assert names["ix_flow_events_timestamp"] == ("timestamp",)
        assert names["ix_flow_events_src_ip_timestamp"] == ("src_ip", "timestamp")
        assert names["ix_flow_events_dst_ip_timestamp"] == ("dst_ip", "timestamp")

    def test_the_bytes_column_is_not_derived_at_read_time(self) -> None:
        """One definition of what a record carried: summed on the write (T-418).

        A read that added ``src_bytes + dst_bytes`` would need both columns stored and
        would give the grouping a second place to get the addition wrong.
        """
        assert "src_bytes" not in FlowEvent.__table__.columns
        assert "dst_bytes" not in FlowEvent.__table__.columns


class TestTheMigration:
    """What Alembic will actually apply."""

    def test_it_revises_the_log_store_migration(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")

        assert 'revision = "0004_flow_events"' in source
        assert 'down_revision = "0003_log_events"' in source
        assert "def upgrade() -> None:" in source
        assert "def downgrade() -> None:" in source

    def test_it_is_the_head_of_the_chain(self) -> None:
        heads = _alembic("heads")

        assert "0004_flow_events" in heads

    def test_the_offline_upgrade_creates_the_table_and_its_indexes(self) -> None:
        emitted = _alembic("upgrade", "0003_log_events:head", "--sql")

        assert "CREATE TABLE flow_events" in emitted
        assert "ix_flow_events_timestamp" in emitted
        assert "ix_flow_events_src_ip_timestamp" in emitted
        assert "ix_flow_events_dst_ip_timestamp" in emitted

    def test_the_offline_downgrade_reverses_it(self) -> None:
        emitted = _alembic("downgrade", "head:0003_log_events", "--sql")

        assert "DROP TABLE flow_events" in emitted or "DROP TABLE IF EXISTS flow_events" in emitted

    def test_the_migration_and_the_model_declare_the_same_columns(self) -> None:
        emitted = _alembic("upgrade", "0003_log_events:head", "--sql")

        for name in _COLUMNS:
            assert name in emitted, name
