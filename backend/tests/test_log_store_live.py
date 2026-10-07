"""The log store against a real PostgreSQL (T-419, the acceptance criterion).

These tests **skip unless ``AEGIS_DATABASE_URL`` points at a running PostgreSQL**, like
``test_migration_live.py`` and for the same reason: a fake session can prove what the
store does with rows (``test_log_store.py`` does exactly that), but the clause this task
is judged on -- "a read is served from storage rather than from the last 20,000 lines in
memory" -- is a claim about a database, and only a database can settle it.

The criterion's three clauses, and where each is tested:

* *survives a restart* -- :func:`test_a_read_survives_the_process_that_accepted_it`
  ingests through one application and reads through a **second** one, asserting that
  the second process's tail is empty so the lines cannot have come from memory.
* *spans more than the retention window* --
  :func:`test_a_window_older_than_the_tail_would_hold_answers_from_the_store`.
* *answers a filter the tail cannot* -- :func:`test_a_host_that_has_logged_nothing_since`
  asks for a host whose lines aged out of the tail an hour ago.

To run them locally:

    python -c "import pgserver; print(pgserver.get_server('/tmp/pgdata').get_uri())"
    AEGIS_DATABASE_URL=<that uri> pytest tests/test_log_store_live.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.auth.tokens import TokenService
from app.core.config import Environment, Settings
from app.main import create_app
from app.schemas.ingest import LogLevel, LogRecordIn
from app.services.log_keys import message_key
from app.services.log_store import PostgresLogStore
from app.services.log_tail import LogTail, LogWindow
from fastapi.testclient import TestClient
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parent.parent

_URL = os.environ.get("AEGIS_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not _URL.startswith("postgresql"),
    reason="AEGIS_DATABASE_URL is not set to a PostgreSQL server; these tests need a real one",
)

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run Alembic against the live database."""
    return subprocess.run(
        # S607 is a false positive: sys.executable is an absolute path.
        [sys.executable, "-m", "alembic", *args],  # noqa: S607
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "AEGIS_DATABASE_URL": _URL},
        check=False,
    )


@pytest.fixture(scope="module", autouse=True)
def migrated() -> None:
    """The schema under test is the migrated one, applied by Alembic."""
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, result.stderr


@pytest.fixture(autouse=True)
def empty_store() -> Iterator[None]:
    """Each test starts with no stored lines: a read here must not see another's."""
    import psycopg

    sync_url = _URL.replace("postgresql+psycopg", "postgresql") if "+psycopg" in _URL else _URL
    with psycopg.connect(sync_url, autocommit=True) as connection:
        connection.execute("DELETE FROM log_events")
    yield


def settings_for(**overrides: object) -> Settings:
    """Settings for a deployment that has named its database."""
    base: dict[str, object] = {
        "env": Environment.TEST,
        "service_name": "aegis-backend-live-test",
        "secret_key": SECRET,
        "log_level": "WARNING",
        "database_url": _URL,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def application() -> TestClient:
    """A client over an application wired to the live store."""
    built = create_app(settings_for())
    built.state.token_service = TokenService(SECRET)
    return TestClient(built)


def headers(client: TestClient, role: str = "analyst") -> dict[str, str]:
    """An Authorization header for one role."""
    pair = client.app.state.token_service.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def ingest(client: TestClient, lines: list[dict[str, object]]) -> object:
    """Post ``log@1`` lines through the real ingest route."""
    body = "\n".join(json.dumps(line) for line in lines).encode()
    return client.post(
        "/api/v1/ingest/logs",
        content=body,
        headers={**headers(client), "content-type": "application/x-ndjson"},
    )


def line(
    *,
    at: datetime,
    message: str = "connection refused to db-1",
    template_id: str | None = "t-1",
    host: str = "web-1",
    service: str = "api",
    level: str = "error",
) -> dict[str, object]:
    """One ``log@1`` line."""
    payload: dict[str, object] = {
        "schema_version": "log@1",
        "timestamp": at.isoformat(),
        "host": host,
        "service": service,
        "level": level,
        "message": message,
        "parameters": {"db": "db-1"},
    }
    if template_id is not None:
        payload["template_id"] = template_id
    return payload


def read(client: TestClient, *, start: datetime, end: datetime, **params: object) -> object:
    """Read the cluster view over a window."""
    return client.get(
        "/api/v1/logs",
        params={"start": start.isoformat(), "end": end.isoformat(), **params},
        headers=headers(client, "viewer"),
    )


def stored_rows() -> int:
    """How many rows the table holds, straight from the database."""
    import psycopg

    sync_url = _URL.replace("postgresql+psycopg", "postgresql") if "+psycopg" in _URL else _URL
    with psycopg.connect(sync_url, autocommit=True) as connection:
        return int(connection.execute("SELECT count(*) FROM log_events").fetchone()[0])


class TestTheAcceptanceCriterion:
    """The three clauses, each against the database rather than an in-memory double."""

    def test_a_window_that_the_store_answers_and_the_tail_refuses(self) -> None:
        """The same request, two sources: 200 with the lines, or 400 naming the bound."""
        now = datetime.now(UTC).replace(microsecond=0)
        older = now - timedelta(hours=2)
        with application() as client:
            assert ingest(client, [line(at=older)]).json()["accepted"] == 1

            served = client.get(
                "/api/v1/logs",
                params={
                    "start": (now - timedelta(hours=3)).isoformat(),
                    "end": (now - timedelta(hours=1)).isoformat(),
                },
                headers=headers(client, "viewer"),
            )
            assert served.status_code == 200
            body = served.json()
            assert body["source"] == "store"
            assert body["clusters"][0]["key"] == "t-1"
            assert body["clusters"][0]["count"] == 1

            # The tail deployment cannot even ask: its retention is the bound.
            with application_with_tail() as tail_client:
                refused = tail_client.get(
                    "/api/v1/logs",
                    params={
                        "start": (now - timedelta(hours=3)).isoformat(),
                        "end": (now - timedelta(hours=1)).isoformat(),
                    },
                    headers=headers(tail_client, "viewer"),
                )
            assert refused.status_code == 400
            assert "the tail can read" in refused.json()["detail"]

    def test_a_read_survives_the_process_that_accepted_it(self) -> None:
        """Ingest through one application, read through a second, empty one."""
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as writer:
            assert ingest(writer, [line(at=now), line(at=now)]).json()["accepted"] == 2

        assert stored_rows() == 2

        with application() as reader:
            # The reader has never seen the lines: its tail is a different process's
            # memory, and it is empty -- so anything the read returns came from storage.
            assert len(reader.app.state.log_tail) == 0
            response = read(
                reader, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1)
            )

            assert response.status_code == 200
            body = response.json()
            assert body["source"] == "store"
            assert body["lines_seen"] == 2
            assert body["retained_lines"] == 2

    def test_a_host_that_has_logged_nothing_since(self) -> None:
        """The tail holds 15 minutes; this host stopped logging two hours ago."""
        now = datetime.now(UTC).replace(microsecond=0)
        quiet = now - timedelta(hours=2)
        with application() as client:
            accepted = ingest(
                client,
                [
                    line(at=quiet, host="old-1", template_id="t-quiet"),
                    line(at=now, host="busy-1", template_id="t-busy"),
                ],
            )
            assert accepted.json()["accepted"] == 2

            # Into the tail directly: only the recent line is in it, which is exactly
            # the situation the criterion describes.
            tail = client.app.state.log_tail
            assert len(tail) == 0, "the store deployment does not fill the tail"

            response = read(
                client,
                start=now - timedelta(hours=3),
                end=now - timedelta(hours=1),
                host="old-1",
            )

            assert response.status_code == 200
            body = response.json()
            assert body["clusters"][0]["key"] == "t-quiet"
            assert body["clusters"][0]["hosts"] == ["old-1"]

    def test_the_filter_is_what_narrows_the_window_not_the_cap(self) -> None:
        """Counts are the window's, not a page's: 300 lines, 2 clusters."""
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            batch = [line(at=now, template_id="t-1") for _ in range(150)]
            batch += [line(at=now, template_id="t-2", message="other") for _ in range(150)]
            assert ingest(client, batch).json()["accepted"] == 300

            response = read(
                client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1), limit=1
            )

            body = response.json()
            assert body["lines_seen"] == 300
            assert body["clusters_seen"] == 2
            assert body["clusters_truncated"] is True
            assert len(body["clusters"]) == 1
            assert body["clusters"][0]["count"] == 150

    def test_a_line_without_a_template_is_findable_by_its_digest(self) -> None:
        """The key written at ingest is the key the fold and the lookup use."""
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            assert (
                ingest(client, [line(at=now, template_id=None, message="bare message")]).json()[
                    "accepted"
                ]
                == 1
            )

            digest = message_key("bare message")
            response = read(
                client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1), key=digest
            )

            body = response.json()
            assert body["lines_seen"] == 1
            assert body["clusters"][0]["key"] == digest
            assert body["clusters"][0]["template_id"] is None
            assert any("carry no template id" in caveat for caveat in body["caveats"])


def application_with_tail() -> TestClient:
    """An application wired to the tail, over the same database URL.

    Built by turning the store *off* rather than by omitting the URL, so the two
    clients in a test differ in exactly one setting.
    """
    built = create_app(settings_for(log_store="off"))
    built.state.token_service = TokenService(SECRET)
    return TestClient(built)


class TestTheStoreItself:
    """The fold, through the real SQL, over real rows."""

    def test_the_store_and_the_tail_fold_the_same_lines_the_same_way(self) -> None:
        """One definition of a cluster: the same window read two ways must agree."""
        records = [
            LogRecordIn(
                schema_version="log@1",
                timestamp=datetime.now(UTC).replace(microsecond=0),
                host="web-1",
                service="api",
                level=LogLevel.ERROR,
                message="first",
                template_id="t-1",
                parameters={"n": "1"},
            ),
            LogRecordIn(
                schema_version="log@1",
                timestamp=datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=5),
                host="web-2",
                service="worker",
                level=LogLevel.CRITICAL,
                message="second",
                template_id="t-1",
                parameters={"n": "2"},
            ),
            LogRecordIn(
                schema_version="log@1",
                timestamp=datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=9),
                host="web-1",
                service="api",
                level=LogLevel.INFO,
                message="a bare line",
                template_id=None,
            ),
        ]
        # The tail's clock is the records' own, so nothing ages out while we compare.
        tail = LogTail(max_lines=100, max_age_seconds=3600.0, clock=lambda: datetime.now(UTC))

        with application() as client:
            app = client.app
            store = app.state.log_source
            assert isinstance(store, PostgresLogStore)
            run(store.append(records))
            tail.append(records)

            window = LogWindow(
                start=min(record.timestamp for record in records) - timedelta(minutes=1),
                end=max(record.timestamp for record in records) + timedelta(minutes=1),
            )
            from_store = run(store.clusters(window, limit=10))
            from_tail = tail.clusters(window, limit=10)

        def comparable(payload: object) -> list[dict[str, object]]:
            import json as _json

            rows = _json.loads(payload.model_dump_json())["clusters"]  # type: ignore[attr-defined]
            for row in rows:
                row.pop("key")
            return rows

        assert comparable(from_store) == comparable(from_tail)
        assert from_store.lines_seen == from_tail.lines_seen == 3

    def test_an_empty_store_reports_its_coverage_as_empty(self) -> None:
        with application() as client:
            store = client.app.state.log_source
            assert isinstance(store, PostgresLogStore)

            coverage = run(store.coverage(refresh=True))

            assert coverage.empty
            assert coverage.oldest is None
            assert coverage.newest is None

    def test_the_coverage_follows_what_is_stored(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            store = client.app.state.log_source
            assert isinstance(store, PostgresLogStore)
            run(store.append([_record_at(now - timedelta(hours=1)), _record_at(now)]))

            coverage = run(store.coverage(refresh=True))

            assert coverage.held == 2
            assert coverage.newest is not None and coverage.newest >= now - timedelta(seconds=1)

    def test_a_read_of_a_missing_table_names_the_migration(self) -> None:
        """The likeliest deployment mistake gets the fix in the message, not a 500."""
        import sqlalchemy as sa

        with application() as client:
            store = client.app.state.log_source
            assert isinstance(store, PostgresLogStore)
            run(store.append([_record_at(datetime.now(UTC))]))

        # Rename the table out from under a fresh store, then read.
        sync_url = _URL.replace("postgresql+psycopg", "postgresql")
        engine = sa.create_engine(sync_url, poolclass=sa.pool.NullPool)
        try:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE log_events RENAME TO log_events_hidden"))
            with application() as client:
                store = client.app.state.log_source
                assert isinstance(store, PostgresLogStore)
                from app.services.log_store import LogStoreUnavailable

                with pytest.raises(LogStoreUnavailable, match="log store"):
                    run(store.coverage(refresh=True))
        finally:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE log_events_hidden RENAME TO log_events"))
            engine.dispose()


def _record_at(at: datetime) -> LogRecordIn:
    """One record at a given instant."""
    return LogRecordIn(
        schema_version="log@1",
        timestamp=at,
        host="web-1",
        service="api",
        level=LogLevel.ERROR,
        message="stored",
        template_id="t-1",
    )


def run(coro: object) -> object:
    """Drive one store coroutine from a sync test, as the suite does elsewhere."""
    import asyncio

    return asyncio.run(coro)  # type: ignore[arg-type]
