"""The entity retention sweep against a migrated PostgreSQL (NFR-05).

These skip unless ``AEGIS_DATABASE_URL`` names a running PostgreSQL. Each test migrates a
fresh schema with the real Alembic chain, so the real foreign key from ``alerts`` to
``entities`` and the real ``ix_alerts_entity_id`` index are what is under test, not a
stand-in. The schema is dropped afterwards.

To run them locally::

    python -c "import pgserver; print(pgserver.get_server('/tmp/pgdata').get_uri())"
    AEGIS_DATABASE_URL=postgresql+psycopg://... pytest tests/test_entity_retention_live.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_URL = os.environ.get("AEGIS_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not _URL.startswith("postgresql"),
    reason="AEGIS_DATABASE_URL is not set to a PostgreSQL server; these tests need a real one",
)


def _schema_url(schema: str) -> str:
    separator = "&" if "?" in _URL else "?"
    return f"{_URL}{separator}options=-csearch_path={schema}"


@pytest.fixture
def migrated() -> Iterator[object]:
    """An engine on a fresh schema, migrated to head by the real chain."""
    import sqlalchemy as sa

    schema = f"ent_{uuid.uuid4().hex[:12]}"
    admin = sa.create_engine(_URL)
    with admin.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
    env = {**os.environ, "AEGIS_DATABASE_URL": _schema_url(schema)}
    result = subprocess.run(  # noqa: S603 -- sys.executable, fixed arguments
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    engine = sa.create_engine(_schema_url(schema))
    try:
        assert result.returncode == 0, result.stderr
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        admin.dispose()


def _partition_for(engine: object, when: datetime) -> None:
    """Create the alerts partition for ``when``'s month, once."""
    from app.db.partitions import create_partition_sql, partition_name

    name = partition_name("alerts", when.year, when.month)
    with engine.begin() as conn:  # type: ignore[attr-defined]
        exists = conn.exec_driver_sql("SELECT to_regclass(%s) IS NOT NULL", (name,)).scalar_one()
        if not exists:
            conn.exec_driver_sql(create_partition_sql("alerts", when.year, when.month))


def _entity(engine: object, value: str, last_seen: datetime) -> int:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        return int(
            conn.exec_driver_sql(
                "INSERT INTO entities (kind, value, first_seen, last_seen, meta) "
                "VALUES ('ip', %s, %s, %s, '{}') RETURNING id",
                (value, last_seen, last_seen),
            ).scalar_one()
        )


def _alert_on(engine: object, entity_id: int, when: datetime) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.exec_driver_sql(
            "INSERT INTO alerts (created_at, entity_id, family, severity, score, explanation, "
            "status, first_seen, last_seen, occurrence_count) "
            "VALUES (%s, %s, 'scan', 'high', 0.9, '{}', 'open', %s, %s, 1)",
            (when, entity_id, when, when),
        )


def _ids(engine: object) -> set[int]:
    with engine.connect() as conn:  # type: ignore[attr-defined]
        return {int(row[0]) for row in conn.exec_driver_sql("SELECT id FROM entities")}


def _count(engine: object, sql: str) -> int:
    with engine.connect() as conn:  # type: ignore[attr-defined]
        return int(conn.exec_driver_sql(sql).scalar_one())


def test_the_chain_applies_and_creates_the_alert_entity_index(migrated: object) -> None:
    assert (
        _count(
            migrated,
            "SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_alerts_entity_id'",
        )
        >= 1
    )


def test_an_unreferenced_old_entity_is_swept_and_the_referenced_one_is_kept(
    migrated: object,
) -> None:
    from app.services.retention_catalog import sweep_entities

    now = datetime.now(UTC)
    long_ago = now - timedelta(days=500)
    _partition_for(migrated, now)
    orphan = _entity(migrated, "10.0.0.1", long_ago)
    referenced = _entity(migrated, "10.0.0.2", long_ago)
    fresh = _entity(migrated, "10.0.0.3", now)
    _alert_on(migrated, referenced, now)

    deleted = sweep_entities(migrated, cutoff=now - timedelta(days=400))  # type: ignore[arg-type]

    assert deleted == 1
    remaining = _count(migrated, "SELECT count(*) FROM entities")
    assert remaining == 2
    ids = _ids(migrated)
    assert orphan not in ids
    assert referenced in ids
    assert fresh in ids


def test_the_foreign_key_is_what_protects_a_referenced_entity(migrated: object) -> None:
    """Independent of the sweep: the database itself refuses to lose a referenced entity."""
    import sqlalchemy as sa

    now = datetime.now(UTC)
    _partition_for(migrated, now)
    referenced = _entity(migrated, "10.0.0.9", now - timedelta(days=500))
    _alert_on(migrated, referenced, now)
    with pytest.raises(sa.exc.IntegrityError), migrated.begin() as conn:  # type: ignore[attr-defined]
        conn.exec_driver_sql("DELETE FROM entities WHERE id = %s", (referenced,))


def test_a_sweep_across_batches_drains_a_backlog_and_is_idempotent(migrated: object) -> None:
    from app.services.retention_catalog import sweep_entities

    now = datetime.now(UTC)
    for index in range(5):
        _entity(migrated, f"10.1.0.{index}", now - timedelta(days=600 + index))
    cutoff = now - timedelta(days=400)

    assert sweep_entities(migrated, cutoff=cutoff, batch_rows=2) == 5  # type: ignore[arg-type]
    assert sweep_entities(migrated, cutoff=cutoff, batch_rows=2) == 0  # type: ignore[arg-type]


def test_sweep_retained_applies_each_tables_own_cutoff(migrated: object) -> None:
    from app.services.retention_catalog import sweep_retained

    now = datetime.now(UTC)
    _entity(migrated, "10.2.0.1", now - timedelta(days=60))  # outside 30d, inside 400d
    result = sweep_retained(
        migrated,  # type: ignore[arg-type]
        {
            "log_events": now - timedelta(days=30),
            "flow_events": now - timedelta(days=30),
            "entities": now - timedelta(days=400),
        },
    )

    assert result["entities"] == 0  # still inside its alerts window
    assert set(result) == {"log_events", "flow_events", "entities"}


def test_sweep_retained_refuses_a_table_it_does_not_know(migrated: object) -> None:
    from app.services.retention_catalog import sweep_retained

    with pytest.raises(ValueError, match="not a row-swept table"):
        sweep_retained(migrated, {"users": datetime.now(UTC)})  # type: ignore[arg-type]
