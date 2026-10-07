"""The flow store against a real PostgreSQL (T-418).

These tests **skip unless ``AEGIS_DATABASE_URL`` points at a running PostgreSQL**, like
``test_log_store_live.py`` and for the same reason: a scripted session can prove what the
store does with rows (``test_flow_store.py``), but this task's claim is about a database.

What only a server can settle, and where each is tested:

* **The grouping is SQL, and ``date_bin`` is a real function.** The statements are
  asserted as text in ``test_flow_statements.py``; whether the server accepts
  ``date_bin(width, timestamp, origin)`` at all is a fact about PostgreSQL 16.
* **A read survives the process that wrote it.** One application ingests, a *second* one
  reads, and the second one's rollup is empty -- so the numbers cannot have come from
  memory.
* **Counts are complete for the window.** More addresses than the entity limit and more
  pairs than the edge limit, with the totals asserted against what was ingested.
* **The coverage sentence distinguishes an empty store from an empty window.** A window
  heavier than what was ingested and a window before anything was stored are two
  different answers.

To run them locally:

    python -c "import pgserver; print(pgserver.get_server('/tmp/pgdata').get_uri())"
    AEGIS_DATABASE_URL=<that uri> pytest tests/test_flow_store_live.py
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
from fastapi.testclient import TestClient

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
    """Each test starts with no stored flows: a read here must not see another's."""
    import psycopg

    sync_url = _URL.replace("postgresql+psycopg", "postgresql") if "+psycopg" in _URL else _URL
    with psycopg.connect(sync_url, autocommit=True) as connection:
        connection.execute("DELETE FROM flow_events")
    yield


def settings_for(**overrides: object) -> Settings:
    """Settings for a deployment that has named its database."""
    base: dict[str, object] = {
        "env": Environment.TEST,
        "service_name": "aegis-backend-flow-live-test",
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


def ingest(client: TestClient, records: list[dict[str, object]]) -> object:
    """Post ``flow@1`` records through the real ingest route."""
    body = "\n".join(json.dumps(record) for record in records).encode()
    return client.post(
        "/api/v1/ingest/flows",
        content=body,
        headers={**headers(client, "responder"), "content-type": "application/x-ndjson"},
    )


def record(
    *,
    at: datetime,
    src: str = "10.0.0.1",
    dst: str = "10.0.0.2",
    protocol: str = "tcp",
    direction: str = "outbound",
    src_bytes: int = 100,
    dst_bytes: int = 40,
    packets: int = 3,
) -> dict[str, object]:
    """One ``flow@1`` record."""
    return {
        "schema_version": "flow@1",
        "timestamp": at.isoformat(),
        "src_ip": src,
        "dst_ip": dst,
        "src_port": 51000,
        "dst_port": 443,
        "protocol": protocol,
        "direction": direction,
        "packets": packets,
        "src_packets": packets,
        "dst_packets": 0,
        "src_bytes": src_bytes,
        "dst_bytes": dst_bytes,
        "duration": 1.0,
    }


def read(client: TestClient, *, start: datetime, end: datetime, **params: object) -> object:
    """Read the traffic aggregate over a window."""
    return client.get(
        "/api/v1/flows",
        params={"start": start.isoformat(), "end": end.isoformat(), **params},
        headers=headers(client, "viewer"),
    )


def stored_rows() -> int:
    """How many rows the table holds, straight from the database."""
    import psycopg

    sync_url = _URL.replace("postgresql+psycopg", "postgresql") if "+psycopg" in _URL else _URL
    with psycopg.connect(sync_url, autocommit=True) as connection:
        return int(connection.execute("SELECT count(*) FROM flow_events").fetchone()[0])


class TestTheAcceptanceCriterion:
    """A read is served from storage, and the numbers are the traffic's."""

    def test_a_read_survives_the_process_that_accepted_it(self) -> None:
        """The second application's rollup is empty, so the numbers came from storage."""
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as writer:
            response = ingest(writer, [record(at=now), record(at=now)])
            assert response.json()["accepted"] == 2
        assert stored_rows() == 2

        with application() as reader:
            assert reader.app.state.flow_source.name == "store"  # type: ignore[attr-defined]
            body = read(
                reader, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1)
            ).json()

        assert body["source"] == "store"
        assert body["totals"]["flows"] == 2
        assert any("survive a restart" in caveat for caveat in body["caveats"])

    def test_a_window_the_rollup_would_refuse_is_answered(self) -> None:
        """The store's bound is R-34's, not the rollup's hour: a two-day window reads."""
        now = datetime.now(UTC).replace(microsecond=0)
        old = now - timedelta(days=2)
        with application() as client:
            ingest(client, [record(at=old)])
            body = read(client, start=now - timedelta(days=3), end=now, bucket_minutes=1_440).json()

        assert body["totals"]["flows"] == 1

    def test_the_traffic_is_counted_even_where_no_alert_exists(self) -> None:
        """The window holds traffic and no alerts at all, and the traffic is counted."""
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            ingest(client, [record(at=now) for _ in range(5)])
            body = read(
                client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1)
            ).json()

        assert body["totals"]["flows"] == 5
        assert body["series"][0]["alerts"] == 0
        assert body["series"][0]["score"] is None


class TestTheSqlGrouping:
    """The panels are grouped by the database, not by a client."""

    def test_the_buckets_land_on_the_windows_grid(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0, second=0)
        with application() as client:
            ingest(
                client,
                [
                    record(at=now),
                    record(at=now + timedelta(minutes=5)),
                    record(at=now + timedelta(minutes=15)),
                ],
            )
            body = read(
                client,
                start=now,
                end=now + timedelta(minutes=20),
                bucket_minutes=5,
            ).json()

        assert [bucket["flows"] for bucket in body["series"]] == [1, 1, 0, 1]

    def test_an_address_that_only_receives_is_counted(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            ingest(client, [record(at=now, src="10.0.0.1", dst="10.0.0.2")])
            body = read(
                client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1)
            ).json()

        seen = {entity["ip"]: entity for entity in body["entities"]}
        assert seen["10.0.0.2"]["inbound"] == 1
        assert seen["10.0.0.2"]["bytes"] == 140

    def test_the_two_directions_are_two_edges(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            ingest(
                client,
                [
                    record(at=now, src="10.0.0.1", dst="10.0.0.2"),
                    record(at=now, src="10.0.0.2", dst="10.0.0.1"),
                ],
            )
            body = read(
                client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1)
            ).json()

        assert body["totals"]["edges"] == 2

    def test_the_filters_are_where_predicates(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            ingest(
                client,
                [
                    record(at=now, protocol="tcp"),
                    record(at=now, protocol="udp"),
                    record(at=now, protocol="udp"),
                ],
            )
            body = read(
                client,
                start=now - timedelta(minutes=1),
                end=now + timedelta(minutes=1),
                protocol="udp",
            ).json()

        assert body["totals"]["flows"] == 2


class TestCountsAreComplete:
    """The totals are the window's, whatever the caps did to the lists."""

    def test_more_addresses_than_the_limit_still_counts_them_all(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        records = [
            record(at=now, src=f"10.0.0.{index}", dst="10.0.0.254") for index in range(1, 40)
        ]
        with application() as client:
            ingest(client, records)
            body = read(
                client,
                start=now - timedelta(minutes=1),
                end=now + timedelta(minutes=1),
                entity_limit=5,
            ).json()

        assert len(body["entities"]) == 5
        assert body["totals"]["nodes"] == 40
        assert body["totals"]["nodes_capped"] is True
        assert body["totals"]["flows"] == 39

    def test_more_pairs_than_the_limit_still_counts_them_all(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        records = [
            record(at=now, src=f"10.0.1.{index}", dst=f"10.0.2.{index}") for index in range(1, 30)
        ]
        with application() as client:
            ingest(client, records)
            body = read(
                client,
                start=now - timedelta(minutes=1),
                end=now + timedelta(minutes=1),
                edge_limit=4,
            ).json()

        assert len(body["edges"]) == 4
        assert body["totals"]["edges"] == 29
        assert body["totals"]["edges_capped"] is True

    def test_the_bytes_are_the_records_bytes_not_a_rows_bytes(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            ingest(client, [record(at=now, src_bytes=300, dst_bytes=200) for _ in range(3)])
            body = read(
                client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1)
            ).json()

        assert body["totals"]["bytes"] == 1_500


class TestCoverageSentences:
    """An empty store and an empty window are different answers."""

    def test_a_window_before_anything_was_stored_says_nothing_matched(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            ingest(client, [record(at=now)])
            body = read(
                client,
                start=now - timedelta(hours=2),
                end=now - timedelta(hours=1),
                bucket_minutes=10,
            ).json()

        assert body["totals"]["flows"] == 0
        assert any("No accepted flow record falls inside this window" in c for c in body["caveats"])

    def test_an_empty_table_says_nothing_has_been_stored(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            body = read(
                client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1)
            ).json()

        assert any("Nothing has been counted yet" in c for c in body["caveats"])

    def test_the_store_read_is_exact_to_the_instant(self) -> None:
        """A record an instant after the window's start is out of a window that ends at it."""
        now = datetime.now(UTC).replace(microsecond=0)
        with application() as client:
            ingest(client, [record(at=now + timedelta(seconds=30))])
            before = read(client, start=now, end=now + timedelta(seconds=10)).json()
            after = read(client, start=now, end=now + timedelta(minutes=1)).json()

        assert before["totals"]["flows"] == 0
        assert after["totals"]["flows"] == 1
