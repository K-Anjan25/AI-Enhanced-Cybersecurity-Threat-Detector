"""Account erasure against a real PostgreSQL, through the real migration chain.

These skip unless ``AEGIS_DATABASE_URL`` names a running PostgreSQL. What they prove is
the part the in-memory model cannot: that deleting a ``users`` row succeeds when the
user triaged alerts and promoted a model, that the alert and promotion survive with the
pointer cleared, that the user's API keys cascade away, and that a second request is a
no-op.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
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

    schema = f"ers_{uuid.uuid4().hex[:12]}"
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


class _RecordingKeys:
    """Stands in for the in-process key store, to see the cascade reach it."""

    def __init__(self) -> None:
        self.erased: list[str] = []

    def erase_owner(self, owner: str, *, replacement: str) -> int:
        self.erased.append(owner)
        return 1


def _seed(engine: object) -> None:
    """Two users, one of whom triaged an alert, promoted a model and owns a key."""
    import sqlalchemy as sa
    from app.db.partitions import create_partition_sql

    now = datetime.now(UTC)
    with engine.begin() as conn:  # type: ignore[attr-defined]
        for user_id, email in ((1, "gone@example.com"), (2, "kept@example.com")):
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, email, argon2_hash, role) "
                    "VALUES (:id, :email, 'x', 'analyst')"
                ),
                {"id": user_id, "email": email},
            )
        conn.execute(
            sa.text(
                "INSERT INTO api_keys (id, owner_id, name, key_hash, scopes) "
                "VALUES (1, 1, 'ci', 'h', ARRAY['alerts:read'])"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO entities (id, kind, value, first_seen, last_seen) "
                "VALUES (1, 'ip', '10.0.0.9', :now, :now)"
            ),
            {"now": now},
        )
        conn.exec_driver_sql(create_partition_sql("alerts", now.year, now.month))
        conn.execute(
            sa.text(
                "INSERT INTO alerts (id, created_at, entity_id, family, severity, score, "
                "first_seen, last_seen, assigned_to, verdict, verdict_at, verdict_by) "
                "VALUES (1, :now, 1, 'beaconing', 'high', 0.9, :now, :now, 1, "
                "'true_positive', :now, 1)"
            ),
            {"now": now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO models (id, name, version, kind, artifact_uri, status) "
                "VALUES (1, 'flow', '1', 'flow', 'file:///m', 'active')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO model_versions_history (id, model_id, promoted_at, promoted_by) "
                "VALUES (1, 1, :now, 1)"
            ),
            {"now": now},
        )


def test_erasing_a_user_who_triaged_and_promoted_succeeds(migrated: object) -> None:
    import sqlalchemy as sa
    from app.services.user_erasure_store import PostgresUserStore

    _seed(migrated)
    store = PostgresUserStore(migrated, keys=None)  # type: ignore[arg-type]

    assert store.erase_owner("gone@example.com", replacement="") == 1

    with migrated.connect() as conn:  # type: ignore[attr-defined]
        emails = conn.execute(sa.text("SELECT email FROM users ORDER BY id")).scalars().all()
        keys = conn.execute(sa.text("SELECT count(*) FROM api_keys")).scalar_one()
        alert = conn.execute(
            sa.text("SELECT assigned_to, verdict_by, verdict FROM alerts WHERE id = 1")
        ).one()
        promoted_by = conn.execute(
            sa.text("SELECT promoted_by FROM model_versions_history WHERE id = 1")
        ).scalar_one()
    assert emails == ["kept@example.com"]  # the other user is untouched
    assert keys == 0  # the key cascaded with its owner
    assert tuple(alert) == (None, None, "true_positive")  # the verdict stays; the person goes
    assert promoted_by is None  # the promotion stays; the person goes


def test_a_second_erasure_removes_nothing_and_does_not_fail(migrated: object) -> None:
    from app.services.user_erasure_store import PostgresUserStore

    _seed(migrated)
    store = PostgresUserStore(migrated, keys=None)  # type: ignore[arg-type]
    assert store.erase_owner("gone@example.com", replacement="") == 1
    assert store.erase_owner("gone@example.com", replacement="") == 0


def test_the_in_process_key_store_is_reached_when_a_user_is_removed(migrated: object) -> None:
    from app.services.user_erasure_store import PostgresUserStore

    _seed(migrated)
    keys = _RecordingKeys()
    store = PostgresUserStore(migrated, keys=keys)  # type: ignore[arg-type]

    store.erase_owner("gone@example.com", replacement="")
    store.erase_owner("gone@example.com", replacement="")

    # Called once: a second request that removed no row must not repeat the cascade.
    assert keys.erased == ["gone@example.com"]
