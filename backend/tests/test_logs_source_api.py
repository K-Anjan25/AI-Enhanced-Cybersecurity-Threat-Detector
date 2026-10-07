"""Which read model the log routes answer from, over HTTP (T-419).

Three things the service tests cannot see:

* the source a *deployment* gets. The default settings name no database, so the
  routes answer ``source: tail``; a deployment that names one gets the store; a
  deployment that turns the store off gets the tail and a sentence naming the setting.
* the span bound follows the source, and the refusal names it -- 15 minutes for a
  tail, 92 days for the store. A caller told only "narrow the window" would keep
  guessing which of the two applies.
* a configured store that cannot be read is a **503**, not an empty screen. That is
  the failure this whole read model exists to avoid (R-70), and it is testable here
  with a database URL nothing is listening on.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from app.auth.tokens import TokenService
from app.core.config import Environment, LogStoreMode, Settings
from app.main import create_app
from fastapi.testclient import TestClient

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)

#: A URL nothing is listening on, and one whose host cannot resolve. Both are
#: configuration a deployment can really arrive with; neither is dialled at startup.
UNREACHABLE = "postgresql+psycopg://aegis:aegis@127.0.0.1:59999/aegis"  # pragma: allowlist secret


def settings_for(**overrides: object) -> Settings:
    """Settings for one deployment shape, never reading the ambient environment."""
    base: dict[str, object] = {
        "env": Environment.TEST,
        "service_name": "aegis-backend-test",
        "secret_key": SECRET,
        "log_level": "WARNING",
        "log_tail_max_age_seconds": 900.0,
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


def read(client: TestClient, *, start: datetime, end: datetime) -> object:
    """Read the cluster view over the given window."""
    auth = client.app.state.token_service
    return client.get(
        "/api/v1/logs",
        params={"start": start.isoformat(), "end": end.isoformat()},
        headers=headers(auth),
    )


class TestTheDefaultDeployment:
    """No database URL named: the tail answers, and says why."""

    @pytest.fixture
    def client(self) -> Iterator[TestClient]:
        yield from client_for(settings_for())

    def test_the_source_is_the_tail(self, client: TestClient) -> None:
        response = read(client, start=START, end=START + timedelta(minutes=5))

        assert response.status_code == 200
        assert response.json()["source"] == "tail"

    def test_the_read_says_which_variable_would_change_it(self, client: TestClient) -> None:
        response = read(client, start=START, end=START + timedelta(minutes=5))

        caveats = response.json()["caveats"]
        assert any("AEGIS_DATABASE_URL" in caveat for caveat in caveats)

    def test_the_tail_still_bounds_the_window_at_its_retention(self, client: TestClient) -> None:
        response = read(client, start=START, end=START + timedelta(hours=2))

        assert response.status_code == 400
        assert "tail" in response.json()["detail"]

    def test_the_raw_line_read_says_the_same(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/logs/lines",
            params={"start": START.isoformat(), "end": (START + timedelta(minutes=5)).isoformat()},
            headers=headers(client.app.state.token_service),
        )

        assert response.status_code == 200
        assert response.json()["source"] == "tail"
        assert response.json()["dropped_lines"] == 0, "a tail can report what it dropped"

    def test_ingest_still_fills_the_tail(self, client: TestClient) -> None:
        """The default deployment's write path is unchanged: no database, no store.

        The timestamp is *now*, because the tail bounds its own age against the real
        clock and this fixture does not drive it -- a fixed instant from the day the
        test was written would be evicted the next day.
        """
        auth = client.app.state.token_service
        stamp = datetime.now(UTC).isoformat()
        body = (
            f'{{"schema_version": "log@1", "timestamp": "{stamp}", '
            '"host": "web-1", "service": "api", "level": "error", "message": "boom", '
            '"template_id": "t-1"}\n'
        )
        posted = client.post(
            "/api/v1/ingest/logs",
            content=body.encode(),
            headers={**headers(auth, "analyst"), "content-type": "application/x-ndjson"},
        )

        assert posted.status_code == 200
        assert posted.json()["accepted"] == 1
        assert len(client.app.state.log_tail) == 1

        # And it is readable through the route, from the tail, inside its retention.
        now = datetime.now(UTC)
        response = read(client, start=now - timedelta(minutes=1), end=now + timedelta(minutes=1))

        assert response.json()["source"] == "tail"
        assert response.json()["lines_seen"] == 1


class TestAStoreIsTurnedOff:
    """``AEGIS_LOG_STORE=off`` is a choice, and the read explains it as one."""

    @pytest.fixture
    def client(self) -> Iterator[TestClient]:
        yield from client_for(
            settings_for(
                log_store=LogStoreMode.OFF,
                # An unroutable port with no credential half: the point of the test is
                # that the store is switched off by configuration, not a dial.
                database_url="postgresql+psycopg://aegis@127.0.0.1:59999/aegis",
            )
        )

    def test_the_tail_answers_even_though_a_url_is_named(self, client: TestClient) -> None:
        response = read(client, start=START, end=START + timedelta(minutes=5))

        assert response.json()["source"] == "tail"

    def test_the_reason_names_the_setting(self, client: TestClient) -> None:
        response = read(client, start=START, end=START + timedelta(minutes=5))

        assert any("AEGIS_LOG_STORE is off" in caveat for caveat in response.json()["caveats"])


class TestAStoreThatCannotBeRead:
    """Configured but unreachable: an error, never a smaller answer."""

    @pytest.fixture
    def client(self) -> Iterator[TestClient]:
        yield from client_for(settings_for(database_url=UNREACHABLE))

    def test_the_cluster_read_is_a_503(self, client: TestClient) -> None:
        response = read(client, start=START, end=START + timedelta(minutes=5))

        assert response.status_code == 503
        assert "log store" in response.json()["detail"]

    def test_the_raw_line_read_is_a_503(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/logs/lines",
            params={"start": START.isoformat(), "end": (START + timedelta(minutes=5)).isoformat()},
            headers=headers(client.app.state.token_service),
        )

        assert response.status_code == 503

    def test_it_does_not_quietly_answer_from_the_tail(self, client: TestClient) -> None:
        """The whole point: an empty screen and a broken database must not look alike."""
        auth = client.app.state.token_service
        client.app.state.log_tail.append([])  # the tail exists and is not consulted
        response = client.get(
            "/api/v1/logs",
            params={"start": START.isoformat(), "end": (START + timedelta(minutes=5)).isoformat()},
            headers=headers(auth),
        )

        assert response.status_code == 503
        assert "tails" not in response.text

    def test_a_wide_window_is_accepted_by_the_bound_and_reaches_the_store(
        self, client: TestClient
    ) -> None:
        """A 30-day window is inside the store's bound and reaches it.

        The failure past it is the store's own, not a span refusal -- which is how the
        two are told apart.
        """
        response = read(client, start=START - timedelta(days=30), end=START)

        assert response.status_code == 503

    def test_the_ingest_path_reports_a_store_it_cannot_write_to(self, client: TestClient) -> None:
        auth = client.app.state.token_service
        stamp = datetime.now(UTC).isoformat()
        body = (
            f'{{"schema_version": "log@1", "timestamp": "{stamp}", '
            '"host": "web-1", "service": "api", "level": "error", "message": "boom"}\n'
        )
        posted = client.post(
            "/api/v1/ingest/logs",
            content=body.encode(),
            headers={**headers(auth, "analyst"), "content-type": "application/x-ndjson"},
        )

        assert posted.status_code == 503
        assert "could not be stored" in posted.json()["detail"]


class TestTheSpanBound:
    """Two sources, two bounds, and a refusal that names the one that applies."""

    def test_the_stores_bound_is_ninety_two_days(self) -> None:
        from app.services.log_store import MAX_SPAN_SECONDS

        assert MAX_SPAN_SECONDS == 92 * 24 * 60 * 60

    def test_a_tail_refusal_names_the_tail(self) -> None:
        client = next(client_for(settings_for()))
        response = read(client, start=START, end=START + timedelta(days=1))

        assert response.status_code == 400
        assert "the tail can read" in response.json()["detail"]
        assert "900s" in response.json()["detail"], "the bound is stated, not implied"

    def test_a_store_refusal_names_the_store(self) -> None:
        client = next(client_for(settings_for(database_url=UNREACHABLE)))
        response = read(client, start=START - timedelta(days=100), end=START)

        assert response.status_code == 400
        assert "the store can read" in response.json()["detail"]
        assert "7948800s" in response.json()["detail"], "92 days, in the source's own units"
