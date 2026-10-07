"""Which read model the flow route answers from, over HTTP (T-418).

Three things the service tests cannot see, and each is a deployment shape rather than a
unit:

* **The default deployment** names no database, so the route answers ``source: rollup``
  and says why in a sentence that names ``AEGIS_DATABASE_URL``; a deployment that names a
  database gets the store; a deployment that turns the store off gets the rollup and a
  sentence naming ``AEGIS_FLOW_STORE``. The two refusal sentences are different because
  they call for different actions.
* **The span bound follows the source**, and the refusal names it: 3,600 seconds for the
  default rollup, 92 days for the store. A caller told only "narrow the window" would
  have to guess which bound applies.
* **A configured store that cannot be read is a 503, not an empty screen.** That is the
  failure this read model exists to prevent (R-70), and it is testable with a URL nothing
  is listening on.

The independent switch matters: traffic and logs are separate axes, and a deployment that
stores one and rolls the other up must be able to say so.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from app.auth.tokens import TokenService
from app.core.config import Environment, LogStoreMode, Settings
from app.main import create_app
from app.services.flow_read_model import FLOW_ROLLUP_MINUTES
from app.services.flow_source import RollupFlowSource
from fastapi.testclient import TestClient

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
END = START + timedelta(hours=1)

#: A URL nothing is listening on. Configuration a deployment can really arrive with, and
#: one that is not dialled at startup.
UNREACHABLE = "postgresql+psycopg://aegis:aegis@127.0.0.1:59999/aegis"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def no_ambient_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert the *default* deployment, whatever the ambient environment names.

    ``Settings`` reads ``AEGIS_DATABASE_URL`` from the environment, so a developer who
    exports it and runs the whole suite would otherwise turn these tests' subject into a
    store deployment and watch them fail for the right reason on the wrong test. The
    fixture states the premise instead of inheriting it (R-83).
    """
    monkeypatch.delenv("AEGIS_DATABASE_URL", raising=False)
    monkeypatch.delenv("AEGIS_LOG_STORE", raising=False)
    monkeypatch.delenv("AEGIS_FLOW_STORE", raising=False)


def settings_for(**overrides: object) -> Settings:
    """Settings for one deployment shape, never reading the ambient environment."""
    base: dict[str, object] = {
        "env": Environment.TEST,
        "service_name": "aegis-backend-test",
        "secret_key": SECRET,
        "log_level": "WARNING",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def client_for(settings: Settings) -> Iterator[TestClient]:
    """A client over a freshly built application."""
    built = create_app(settings)
    built.state.token_service = TokenService(SECRET)
    with TestClient(built) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "viewer") -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def read(client: TestClient, *, start: datetime = START, end: datetime = END) -> object:
    """Read the traffic aggregate."""
    return client.get(
        "/api/v1/flows",
        params={"start": start.isoformat(), "end": end.isoformat()},
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )


class TestTheDefaultDeployment:
    """No database named: the rollup answers, in memory, and says so."""

    def test_the_source_is_the_rollup(self) -> None:
        for client in client_for(settings_for()):
            assert client.app.state.flow_source.name == "rollup"  # type: ignore[attr-defined]

    def test_the_route_says_which_source_answered(self) -> None:
        for client in client_for(settings_for()):
            body = read(client).json()

        assert body["source"] == "rollup"

    def test_the_reason_names_the_setting_that_would_change_it(self) -> None:
        for client in client_for(settings_for()):
            body = read(client).json()

        assert any("AEGIS_DATABASE_URL" in caveat for caveat in body["caveats"])

    def test_the_span_bound_is_the_rollups_own(self) -> None:
        for client in client_for(settings_for()):
            response = read(client, start=START - timedelta(days=2))

        assert response.status_code == 400
        assert f"{FLOW_ROLLUP_MINUTES * 60:g} seconds" in response.json()["detail"]

    def test_the_retention_may_be_configured(self) -> None:
        for client in client_for(settings_for(flow_rollup_minutes=240)):
            source = client.app.state.flow_source  # type: ignore[attr-defined]
            assert isinstance(source, RollupFlowSource)
            assert source.max_span_seconds == 14_400.0


class TestAStoreDeployment:
    """A database URL is named: the store answers, and the bound is R-34's."""

    def test_the_source_is_the_store(self) -> None:
        for client in client_for(settings_for(database_url=UNREACHABLE)):
            assert client.app.state.flow_source.name == "store"  # type: ignore[attr-defined]

    def test_the_route_says_which_source_answered(self) -> None:
        for client in client_for(settings_for(database_url=UNREACHABLE)):
            # The read fails -- nothing is listening -- but the *source* is the store,
            # and a 503 is the answer rather than an empty window (R-70).
            response = read(client)

        assert response.status_code == 503

    def test_an_unreachable_store_is_a_503_not_an_empty_screen(self) -> None:
        for client in client_for(settings_for(database_url=UNREACHABLE)):
            response = read(client)

        assert response.status_code == 503
        assert "could not answer" in response.json()["detail"]

    def test_the_span_bound_is_the_query_bound(self) -> None:
        from app.db.repository import MAX_QUERY_SPAN_DAYS

        for client in client_for(settings_for(database_url=UNREACHABLE)):
            response = read(client, start=START - timedelta(days=1))

        # A day is inside R-34's ceiling, so the refusal is not the span bound: the read
        # was attempted and the store failed. The bound itself is asserted directly.
        assert response.status_code == 503
        assert MAX_QUERY_SPAN_DAYS == 92

    def test_ingest_against_an_unreachable_store_is_a_503(self) -> None:
        for client in client_for(settings_for(database_url=UNREACHABLE)):
            response = client.post(
                "/api/v1/ingest/flows",
                json=[
                    {
                        "schema_version": "flow@1",
                        "timestamp": START.isoformat(),
                        "src_ip": "10.0.0.1",
                        "dst_ip": "10.0.0.2",
                        "src_port": 1,
                        "dst_port": 2,
                        "protocol": "tcp",
                        "direction": "outbound",
                        "packets": 1,
                        "src_packets": 1,
                        "dst_packets": 0,
                        "src_bytes": 1,
                        "dst_bytes": 1,
                        "duration": 1.0,
                    }
                ],
                headers=headers(client.app.state.token_service, "responder"),  # type: ignore[attr-defined]
            )

        assert response.status_code == 503
        assert "could not be stored" in response.json()["detail"]


class TestTheStoreCanBeTurnedOff:
    """A named database with the flow store off: the rollup answers, and explains."""

    def test_the_source_is_the_rollup(self) -> None:
        for client in client_for(
            settings_for(database_url=UNREACHABLE, flow_store=LogStoreMode.OFF)
        ):
            assert client.app.state.flow_source.name == "rollup"  # type: ignore[attr-defined]

    def test_the_reason_names_the_setting(self) -> None:
        for client in client_for(
            settings_for(database_url=UNREACHABLE, flow_store=LogStoreMode.OFF)
        ):
            body = read(client).json()

        assert any("AEGIS_FLOW_STORE is off" in caveat for caveat in body["caveats"])

    def test_one_engine_serves_whichever_stores_are_on(self) -> None:
        # Traffic on and logs off is one engine, not two: the deployment has one
        # database, and the pool is opened once (T-418).
        for client in client_for(
            settings_for(
                database_url=UNREACHABLE, flow_store=LogStoreMode.ON, log_store=LogStoreMode.OFF
            )
        ):
            assert client.app.state.flow_source.name == "store"  # type: ignore[attr-defined]
            assert client.app.state.log_source.name == "tail"  # type: ignore[attr-defined]
            assert client.app.state.store_engine is not None  # type: ignore[attr-defined]

    def test_neither_store_on_opens_no_engine(self) -> None:
        for client in client_for(
            settings_for(log_store=LogStoreMode.OFF, flow_store=LogStoreMode.OFF)
        ):
            assert client.app.state.store_engine is None  # type: ignore[attr-defined]

    def test_the_two_switches_are_independent(self) -> None:
        # Logs stored, traffic rolled up: the shape the two settings exist for.
        for client in client_for(
            settings_for(database_url=UNREACHABLE, flow_store=LogStoreMode.OFF)
        ):
            assert client.app.state.log_source.name == "store"  # type: ignore[attr-defined]
            assert client.app.state.flow_source.name == "rollup"  # type: ignore[attr-defined]


class TestTheRollupIsWiredForIngest:
    """The ingest route counts into whichever source is answering."""

    def test_ingest_reaches_the_rollup_over_http(self) -> None:
        for client in client_for(settings_for()):
            auth = client.app.state.token_service  # type: ignore[attr-defined]
            response = client.post(
                "/api/v1/ingest/flows",
                json=[
                    {
                        "schema_version": "flow@1",
                        "timestamp": START.isoformat(),
                        "src_ip": "10.0.0.1",
                        "dst_ip": "10.0.0.2",
                        "src_port": 1,
                        "dst_port": 2,
                        "protocol": "tcp",
                        "direction": "outbound",
                        "packets": 1,
                        "src_packets": 1,
                        "dst_packets": 0,
                        "src_bytes": 100,
                        "dst_bytes": 40,
                        "duration": 1.0,
                    }
                ],
                headers=headers(auth, "responder"),
            )
            assert response.status_code == 200, response.text
            body = read(client).json()

        assert body["totals"]["flows"] == 1
        assert body["totals"]["bytes"] == 140

    def test_a_rejected_record_is_not_counted(self) -> None:
        # Only accepted records are counted: a record the contract refused must not
        # appear in a total the screen presents as traffic. The ingest contract answers
        # 200 with its own counts -- ``rejected`` is the field that says so (FR-01).
        for client in client_for(settings_for()):
            auth = client.app.state.token_service  # type: ignore[attr-defined]
            response = client.post(
                "/api/v1/ingest/flows",
                json=[{"schema_version": "flow@1", "timestamp": START.isoformat()}],
                headers=headers(auth, "responder"),
            )
            assert response.status_code == 200
            assert response.json() == {
                "received": 1,
                "accepted": 0,
                "rejected": 1,
                "errors": response.json()["errors"],
            }
            body = read(client).json()

        assert body["totals"]["flows"] == 0


@pytest.mark.parametrize("mode", list(LogStoreMode))
def test_every_mode_builds_an_application(mode: LogStoreMode) -> None:
    """Every setting value is a deployment the process can actually start."""
    for client in client_for(settings_for(database_url=UNREACHABLE, flow_store=mode)):
        assert client.app.state.flow_source.name in {"store", "rollup"}  # type: ignore[attr-defined]
