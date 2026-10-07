"""The log store's table: the model, the migration and the statements (T-419).

A schema change is checked two ways that need no server, for the same reason T-321
checked its own that way:

* the ORM metadata and the DDL it compiles to, so the model cannot quietly lose a
  column the store writes or the read groups by; and
* the migration's own SQL, emitted by Alembic in ``--sql`` mode, so what will be
  applied is what was reviewed.

The one property that matters most here is agreement: the model's column list and the
migration's must be the same, in the same order, with the same nullability -- because
``tests/test_log_store_live.py`` is what would otherwise find the difference, and only
where a PostgreSQL happens to be running.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.db.models import ALL_TABLES, PARTITION_KEYS, PARTITIONED_TABLES, LogEvent
from sqlalchemy import String
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "0003_log_events_store.py"

#: Offline mode never connects, so any PostgreSQL-shaped URL works.
_URL = "postgresql://aegis:aegis@localhost:5432/aegis"  # pragma: allowlist secret

#: The model's columns, in the order the model declares them. Written out here so that
#: adding one to a single side is a failing test rather than a runtime surprise.
_COLUMNS = (
    "id",
    "timestamp",
    "host",
    "service",
    "level",
    "message",
    "template_id",
    "parameters",
    "key",
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
    """``log_events`` in the ORM, where the store's statements read it."""

    def test_the_table_is_declared(self) -> None:
        assert LogEvent.__tablename__ == "log_events"
        assert "log_events" in ALL_TABLES

    def test_its_columns_are_the_store_s_own(self) -> None:
        assert tuple(LogEvent.__table__.columns.keys()) == _COLUMNS

    def test_the_key_and_the_message_are_required(self) -> None:
        """A stored line without either cannot be folded or shown."""
        for name in ("key", "message", "timestamp", "host", "service", "level"):
            assert LogEvent.__table__.columns[name].nullable is False, name

    def test_the_template_id_may_be_absent(self) -> None:
        """A collector that mined nothing sends none, and the fold digests instead."""
        assert LogEvent.__table__.columns["template_id"].nullable is True

    def test_the_level_is_a_short_text_column(self) -> None:
        """``log@1``'s five levels, as text -- the enum lives in the schema module."""
        assert isinstance(LogEvent.__table__.columns["level"].type, String)
        assert LogEvent.__table__.columns["level"].type.length == 16

    def test_the_instant_is_timezone_aware(self) -> None:
        assert LogEvent.__table__.columns["timestamp"].type.timezone is True

    def test_the_parameters_are_jsonb(self) -> None:
        assert LogEvent.__table__.columns["parameters"].type.__class__.__name__ == "JSONB"

    def test_it_is_not_partitioned(self) -> None:
        """The store is swept by a retention job of its own, which is not built.

        Recorded rather than implied: a table that *looked* partitioned here would
        make R-34's inspector demand a predicate for a table no plan drops.
        """
        assert "log_events" not in PARTITIONED_TABLES
        assert "log_events" not in PARTITION_KEYS

    def test_it_compiles_for_postgres(self) -> None:
        ddl = str(CreateTable(LogEvent.__table__).compile(dialect=postgresql.dialect()))

        assert "CREATE TABLE log_events" in ddl
        assert "BIGINT" in ddl.upper()
        assert "JSONB" in ddl.upper()

    def test_the_indexes_serve_the_reads_that_exist(self) -> None:
        """Every read is "these keys, inside this window" or a host-filtered one."""
        names = {
            index.name: tuple(column.name for column in index.columns)
            for index in LogEvent.__table__.indexes
        }

        assert names["ix_log_events_timestamp"] == ("timestamp",)
        assert names["ix_log_events_key_timestamp"] == ("key", "timestamp")
        assert names["ix_log_events_host_timestamp"] == ("host", "timestamp")

    def test_nothing_indexes_the_message(self) -> None:
        """Text search is deliberately absent; an index would be a promise it is not."""
        for index in LogEvent.__table__.indexes:
            assert "message" not in {column.name for column in index.columns}


class TestTheMigration:
    """What Alembic will actually apply."""

    def test_it_revises_the_typed_score_migration(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")

        assert 'revision = "0003_log_events"' in source
        assert 'down_revision = "0002_typed_scores"' in source
        assert "def upgrade() -> None:" in source
        assert "def downgrade() -> None:" in source

    def test_the_offline_upgrade_creates_the_table_and_its_indexes(self) -> None:
        emitted = _alembic("upgrade", "0002_typed_scores:head", "--sql")

        assert "CREATE TABLE log_events" in emitted
        assert "ix_log_events_timestamp" in emitted
        assert "ix_log_events_key_timestamp" in emitted
        assert "ix_log_events_host_timestamp" in emitted

    def test_the_offline_downgrade_reverses_it(self) -> None:
        emitted = _alembic("downgrade", "head:0002_typed_scores", "--sql")

        assert "DROP TABLE log_events" in emitted or "DROP TABLE IF EXISTS log_events" in emitted
        assert "DROP INDEX" in emitted

    def test_the_migration_declares_the_model_s_columns(self) -> None:
        """Both sides in one place: a column added to one and not the other fails here."""
        emitted = _alembic("upgrade", "0002_typed_scores:head", "--sql")
        table = emitted[emitted.index("CREATE TABLE log_events") :]
        # The first line that closes the statement, not the first ``)`` -- which is
        # inside ``VARCHAR(512)``.
        table = table[: table.index("\n)")]
        assert "timestamp TIMESTAMP WITH TIME ZONE NOT NULL" in table

        for column in _COLUMNS:
            assert f"\n\t{column} " in table or f"\n    {column} " in table, column

    def test_the_key_has_no_server_default(self) -> None:
        """A key computed by the database would be a second definition of the fold."""
        emitted = _alembic("upgrade", "0002_typed_scores:head", "--sql")

        assert "key VARCHAR(300) NOT NULL" in emitted
