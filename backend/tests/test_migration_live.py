"""Migration up and down against a real PostgreSQL (T-301, clause 1).

These tests **skip unless ``AEGIS_DATABASE_URL`` points at a running PostgreSQL**.
CI has no server, so they skip there; that is deliberate rather than an excuse --
declarative partitioning is PostgreSQL-only, so an in-memory substitute would
prove nothing about the thing being tested.

They exist because compiling DDL is not the same as applying it. The composite
primary keys on the partitioned tables silently lost their autoincrement when
SQLAlchemy stopped emitting a sequence, and every insert failed with a not-null
violation. Nothing that runs without a server can catch that.

To run them locally:

    python -c "import pgserver; print(pgserver.get_server('/tmp/pgdata').get_uri())"
    AEGIS_DATABASE_URL=<that uri> pytest tests/test_migration_live.py
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent

_URL = os.environ.get("AEGIS_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not _URL.startswith("postgresql"),
    reason="AEGIS_DATABASE_URL is not set to a PostgreSQL server; these tests need a real one",
)


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    # sys.executable -m rather than a bare "alembic": the console script is only
    # on PATH in some environments, and a test that fails because of PATH is
    # testing nothing.
    import sys

    return subprocess.run(
        # S607 is a false positive: sys.executable is an absolute path.
        [sys.executable, "-m", "alembic", *args],  # noqa: S607
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "AEGIS_DATABASE_URL": _URL},
        check=False,
    )


@pytest.fixture
def engine() -> object:
    import sqlalchemy as sa

    return sa.create_engine(_URL)


def _tables(engine: object) -> list[str]:
    import sqlalchemy as sa

    with engine.connect() as connection:  # type: ignore[attr-defined]
        return [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
        ]


def test_upgrade_applies_cleanly(engine: object) -> None:
    assert _alembic("downgrade", "base").returncode == 0

    result = _alembic("upgrade", "head")

    assert result.returncode == 0, result.stderr
    assert len(_tables(engine)) == 15


def test_downgrade_removes_everything(engine: object) -> None:
    """A downgrade that leaves tables behind is not a downgrade."""
    assert _alembic("upgrade", "head").returncode == 0

    result = _alembic("downgrade", "base")

    assert result.returncode == 0, result.stderr
    assert _tables(engine) == []


def test_the_cycle_repeats(engine: object) -> None:
    """Up, down, up must land in the same place -- retention drops partitions."""
    assert _alembic("upgrade", "head").returncode == 0
    first = sorted(_tables(engine))
    assert _alembic("downgrade", "base").returncode == 0

    assert _alembic("upgrade", "head").returncode == 0

    assert sorted(_tables(engine)) == first


def test_both_partitioned_tables_are_actually_partitioned(engine: object) -> None:
    import sqlalchemy as sa

    assert _alembic("upgrade", "head").returncode == 0
    with engine.connect() as connection:  # type: ignore[attr-defined]
        partitioned = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'p'"
                )
            )
        }

    assert partitioned == {"alerts", "ingest_stats"}


def test_the_partition_key_is_in_the_primary_key(engine: object) -> None:
    """PostgreSQL cannot enforce a key that excludes the partition column."""
    import sqlalchemy as sa

    assert _alembic("upgrade", "head").returncode == 0
    expected = {"alerts": {"id", "created_at"}, "ingest_stats": {"id", "window_start"}}
    with engine.connect() as connection:  # type: ignore[attr-defined]
        for table, want in expected.items():
            got = {
                row[0]
                for row in connection.execute(
                    sa.text(
                        # S608: `table` comes from the fixed dict two lines above,
                        # never from input. regclass cannot be bound as a parameter.
                        "SELECT a.attname FROM pg_index i "  # noqa: S608
                        "JOIN pg_attribute a ON a.attrelid = i.indrelid "
                        "AND a.attnum = ANY(i.indkey) "
                        f"WHERE i.indrelid = '{table}'::regclass AND i.indisprimary"
                    )
                )
            }
            assert got == want, table


def test_there_is_no_default_partition(engine: object) -> None:
    """A default partition accumulates silently and defeats retention."""
    import sqlalchemy as sa

    assert _alembic("upgrade", "head").returncode == 0
    with engine.connect() as connection:  # type: ignore[attr-defined]
        defaults = list(
            connection.execute(
                sa.text(
                    "SELECT c.relname FROM pg_class c WHERE c.relkind = 'r' "
                    "AND pg_get_expr(c.relpartbound, c.oid) = 'DEFAULT'"
                )
            )
        )

    assert defaults == []


def test_a_row_is_routed_to_its_month(engine: object) -> None:
    import sqlalchemy as sa

    assert _alembic("upgrade", "head").returncode == 0
    with engine.begin() as connection:  # type: ignore[attr-defined]
        connection.execute(
            sa.text(
                "INSERT INTO entities (kind, value, first_seen, last_seen, meta) "
                "VALUES ('ip', '10.9.9.9', now(), now(), '{}'::jsonb)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO alerts (entity_id, family, severity, score, status, "
                "first_seen, last_seen, created_at) "
                "SELECT id, 'DoS', 'high', 0.9, 'open', now(), now(), "
                "'2026-03-15'::timestamptz FROM entities WHERE value = '10.9.9.9'"
            )
        )
    with engine.connect() as connection:  # type: ignore[attr-defined]
        routed = list(connection.execute(sa.text("SELECT tableoid::regclass FROM alerts")))

    assert routed and str(routed[0][0]) == "alerts_2026_03"


def test_a_row_outside_every_partition_is_rejected(engine: object) -> None:
    """The loud failure that the absence of a default partition buys."""
    import sqlalchemy as sa

    assert _alembic("upgrade", "head").returncode == 0
    with engine.begin() as connection:  # type: ignore[attr-defined]
        connection.execute(
            sa.text(
                "INSERT INTO entities (kind, value, first_seen, last_seen, meta) "
                "VALUES ('ip', '10.8.8.8', now(), now(), '{}'::jsonb) "
                "ON CONFLICT DO NOTHING"
            )
        )
    with (
        pytest.raises(Exception, match="no partition of relation"),  # noqa: B017, PT011
        engine.begin() as connection,  # type: ignore[attr-defined]
    ):
        connection.execute(
            sa.text(
                "INSERT INTO alerts (entity_id, family, severity, score, status, "
                "first_seen, last_seen, created_at) "
                "SELECT id, 'DoS', 'high', 0.9, 'open', now(), now(), "
                "'2031-01-01'::timestamptz FROM entities WHERE value = '10.8.8.8'"
            )
        )


def test_a_bounded_query_prunes_to_one_partition(engine: object) -> None:
    """R-34's premise: the predicate is what keeps the scan small."""
    import sqlalchemy as sa

    assert _alembic("upgrade", "head").returncode == 0
    with engine.connect() as connection:  # type: ignore[attr-defined]
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                sa.text(
                    "EXPLAIN SELECT * FROM alerts "
                    "WHERE created_at >= '2026-03-01' AND created_at < '2026-04-01'"
                )
            )
        )

    assert "alerts_2026_03" in plan
    assert "alerts_2026_04" not in plan


def test_audit_log_has_no_foreign_key(engine: object) -> None:
    """R-31: a cascade from users would give an append-only table a delete path."""
    import sqlalchemy as sa

    assert _alembic("upgrade", "head").returncode == 0
    with engine.connect() as connection:  # type: ignore[attr-defined]
        fks = list(
            connection.execute(
                sa.text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'audit_log'::regclass AND contype = 'f'"
                )
            )
        )

    assert fks == []
