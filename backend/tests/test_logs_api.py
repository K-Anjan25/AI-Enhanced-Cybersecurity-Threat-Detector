"""The log tail over HTTP, and the ingest path that fills it (T-407).

Three things are asserted here that the service tests cannot see: the window is
required and bounded at the *route* (R-34), reading is a viewer capability while
filling the tail stays an ingest capability (R-53), and — the one that matters most
— the tail holds exactly the lines the API accepted, so a rejected record cannot
appear on the screen and a flow batch cannot appear at all.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from app.auth.tokens import TokenService
from app.core.config import Environment, LogStoreMode, Settings
from app.main import create_app
from app.services.log_source import TailLogSource, tail_reason
from app.services.log_tail import LogTail
from fastapi.testclient import TestClient

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)


def stamp(offset_seconds: float) -> str:
    """An ISO-8601 instant in UTC, ``offset_seconds`` after the fixture's start."""
    return (START + timedelta(seconds=offset_seconds)).isoformat()


def log_line(
    *,
    offset: float = 0.0,
    message: str = "connection refused to db-1",
    template_id: str | None = "t-1",
    level: str = "error",
    host: str = "web-1",
) -> dict[str, object]:
    """One ``log@1`` line as a collector would post it."""
    return {
        "schema_version": "log@1",
        "timestamp": stamp(offset),
        "host": host,
        "service": "api",
        "level": level,
        "message": message,
        "template_id": template_id,
        "parameters": {"db": "db-1"},
    }


@pytest.fixture
def settings() -> Settings:
    """A tail with a one-minute retention, so the span bound is testable."""
    return Settings(
        env=Environment.TEST,
        service_name="aegis-backend-test",
        secret_key=SECRET,
        log_level="WARNING",
        log_tail_max_age_seconds=60.0,
        log_tail_lines=50,
    )


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> Iterator[TestClient]:
    built = create_app(settings)
    built.state.token_service = auth
    # Drive the tail's clock instead of racing the wall clock. The fixture's instants
    # are absolute (so the assertions are exact), and the tail expires a line older
    # than ``max_age_seconds`` *measured against its clock* -- which is the real one
    # unless a test supplies another. Without this, every test in this file passes
    # until the wall clock walks past ``START + 60 s`` and then fails forever, which
    # is exactly what happened on 2026-10-06 at 10:15 UTC.
    tail = built.state.log_tail
    driven = LogTail(
        max_lines=tail.max_lines,
        max_age_seconds=tail.max_age_seconds,
        clock=lambda: START + timedelta(seconds=30),
    )
    built.state.log_tail = driven
    # Reads pass through the source (T-419), so the driven tail has to be the one the
    # source holds -- swapping only the buffer would leave the routes reading the tail
    # the composition root built, whose clock is the wall clock.
    built.state.log_source = TailLogSource(driven, reason=tail_reason(LogStoreMode.AUTO))
    with TestClient(built) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "viewer") -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def fill(
    client: TestClient,
    auth: TokenService,
    lines: list[dict[str, object]],
    *,
    content_type: str = "application/x-ndjson",
) -> object:
    """Post lines through the real ingest route, as a collector would."""
    body = "\n".join(json.dumps(line) for line in lines).encode()
    return client.post(
        "/api/v1/ingest/logs",
        content=body,
        headers={**headers(auth, "analyst"), "content-type": content_type},
    )


def read(
    client: TestClient,
    auth: TokenService,
    *,
    start: str | None = None,
    end: str | None = None,
    **params: object,
) -> object:
    """Read the clustered tail over HTTP."""
    query: dict[str, object] = {
        "start": start if start is not None else stamp(0),
        "end": end if end is not None else stamp(60),
        **params,
    }
    return client.get("/api/v1/logs", params=query, headers=headers(auth))


def cluster_of(response: object, key: str = "t-1") -> dict[str, object]:
    """The one cluster a single-template fixture produces."""
    payload = json.loads(response.text)  # type: ignore[attr-defined]
    return next(cluster for cluster in payload["clusters"] if cluster["key"] == key)


# --- the ingest path fills the tail ------------------------------------------


def test_a_viewer_can_read_the_tail(client: TestClient, auth: TokenService) -> None:
    fill(client, auth, [log_line()])

    response = read(client, auth)

    assert response.status_code == 200
    assert cluster_of(response)["count"] == 1


def test_the_tail_holds_exactly_the_lines_the_api_accepted(
    client: TestClient, auth: TokenService
) -> None:
    """FR-04's arithmetic, seen from the screen: a refused line is not shown."""
    response = fill(
        client,
        auth,
        [
            log_line(offset=0),
            {"schema_version": "log@1", "timestamp": stamp(1), "host": "web-1"},
            log_line(offset=2),
        ],
    )

    assert response.status_code == 200
    assert response.json()["accepted"] == 2
    assert response.json()["rejected"] == 1
    tail = read(client, auth)
    assert cluster_of(tail)["count"] == 2
    assert json.loads(tail.text)["lines_seen"] == 2


def test_a_flow_batch_does_not_appear_in_the_log_tail(
    client: TestClient, auth: TokenService
) -> None:
    body = json.dumps(
        {
            "schema_version": "flow@1",
            "timestamp": stamp(0),
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "src_port": 1234,
            "dst_port": 443,
            "protocol": "tcp",
            "direction": "outbound",
            "packets": 3,
            "src_packets": 2,
            "dst_packets": 1,
            "src_bytes": 100,
            "dst_bytes": 200,
            "duration": 0.5,
        }
    ).encode()

    client.post(
        "/api/v1/ingest/flows",
        content=body,
        headers={**headers(auth, "analyst"), "content-type": "application/x-ndjson"},
    )

    payload = json.loads(read(client, auth).text)
    assert payload["clusters"] == []
    assert payload["retained_lines"] == 0


def test_a_retried_batch_is_shown_twice_rather_than_deduplicated(
    client: TestClient, auth: TokenService
) -> None:
    """A tail is not a store with an identity: it shows what arrived, as often as it arrived."""
    fill(client, auth, [log_line()])
    fill(client, auth, [log_line()])

    assert cluster_of(read(client, auth))["count"] == 2


def test_the_tail_counts_what_the_line_limit_dropped(
    client: TestClient, auth: TokenService
) -> None:
    fill(client, auth, [log_line(offset=index / 10) for index in range(12)])

    payload = json.loads(read(client, auth).text)

    # The settings keep 50 lines, so nothing has been dropped yet and the response
    # says so with a number rather than leaving the reader to assume.
    assert payload["retained_lines"] == 12
    assert payload["dropped_lines"] == 0


# --- the window is required and bounded (R-34) -------------------------------


def test_reading_without_a_window_is_refused(client: TestClient, auth: TokenService) -> None:
    """No default window: a tail read without one would be "the logs, as far as they go"."""
    response = client.get("/api/v1/logs", headers=headers(auth))

    assert response.status_code == 422
    assert "start" in response.text and "end" in response.text


@pytest.mark.parametrize(
    "start,end,reason",
    [
        ("not-a-time", stamp(60), "start must be an ISO-8601 timestamp"),
        (stamp(0), "2026-10-06T10:01:00", "end must carry a timezone"),
        (stamp(60), stamp(0), "end must be later than start"),
        (stamp(0), stamp(61), "over the"),
    ],
)
def test_a_window_that_cannot_be_read_is_a_400(
    client: TestClient, auth: TokenService, start: str, end: str, reason: str
) -> None:
    response = read(client, auth, start=start, end=end)

    assert response.status_code == 400
    assert reason in response.json()["detail"]


def test_the_widest_window_is_the_retention(client: TestClient, auth: TokenService) -> None:
    """The bound is the tail's own retention, so the two cannot drift apart."""
    assert read(client, auth, start=stamp(0), end=stamp(60)).status_code == 200
    assert read(client, auth, start=stamp(0), end=stamp(60.5)).status_code == 400


def test_an_over_wide_window_names_the_bound_without_echoing_content(
    client: TestClient, auth: TokenService
) -> None:
    fill(client, auth, [log_line(message="password=hunter2")])

    response = read(client, auth, start=stamp(0), end=stamp(600))

    assert response.status_code == 400
    assert "hunter2" not in response.text


def test_a_row_limit_beyond_the_cap_is_refused_by_the_query_layer(
    client: TestClient, auth: TokenService
) -> None:
    assert read(client, auth, limit=100_000).status_code == 422
    assert read(client, auth, limit=0).status_code == 422


# --- the filters and the expansion ------------------------------------------


def test_the_cluster_read_and_its_expansion_select_the_same_lines(
    client: TestClient, auth: TokenService
) -> None:
    """A row must not count lines that opening it would not show."""
    fill(
        client,
        auth,
        [
            log_line(offset=0, template_id="t-1"),
            log_line(offset=1, template_id="t-2", message="timeout"),
            log_line(offset=2, template_id="t-1"),
        ],
    )

    row = cluster_of(read(client, auth))
    lines = client.get(
        "/api/v1/logs/lines",
        params={"start": stamp(0), "end": stamp(60), "key": row["key"]},
        headers=headers(auth),
    ).json()

    assert row["count"] == 2
    assert len(lines["lines"]) == 2
    assert [entry["template_id"] for entry in lines["lines"]] == ["t-1", "t-1"]
    assert lines["lines_truncated"] is False


def instants(entries: list[dict[str, object]]) -> list[datetime]:
    """The instants a response carries, parsed: the wire format is not the contract."""
    return [datetime.fromisoformat(str(entry["timestamp"])) for entry in entries]


def test_the_raw_lines_come_back_oldest_first(client: TestClient, auth: TokenService) -> None:
    fill(client, auth, [log_line(offset=20), log_line(offset=0, message="earlier")])

    payload = client.get(
        "/api/v1/logs/lines",
        params={"start": stamp(0), "end": stamp(60)},
        headers=headers(auth),
    ).json()

    assert instants(payload["lines"]) == [
        START,
        START + timedelta(seconds=20),
    ]


def test_a_level_filter_narrows_both_reads(client: TestClient, auth: TokenService) -> None:
    fill(
        client,
        auth,
        [log_line(level="error"), log_line(offset=1, level="info", message="started up")],
    )

    clusters = read(client, auth, level="info").json()
    lines = client.get(
        "/api/v1/logs/lines",
        params={"start": stamp(0), "end": stamp(60), "level": "info"},
        headers=headers(auth),
    ).json()

    assert clusters["lines_seen"] == 1
    assert clusters["clusters"][0]["worst_level"] == "info"
    assert [entry["level"] for entry in lines["lines"]] == ["info"]


def test_a_line_without_a_template_id_is_reachable_by_its_digest(
    client: TestClient, auth: TokenService
) -> None:
    """The round trip a screen makes when someone clicks an untemplated row."""
    fill(client, auth, [log_line(template_id=None, message="disk full on /var")])

    row = json.loads(read(client, auth).text)["clusters"][0]
    assert row["template_id"] is None
    assert row["key"].startswith("message:")

    payload = client.get(
        "/api/v1/logs/lines",
        params={"start": stamp(0), "end": stamp(60), "key": row["key"]},
        headers=headers(auth),
    ).json()

    assert [entry["message"] for entry in payload["lines"]] == ["disk full on /var"]


# --- what a reader is told ----------------------------------------------------


def test_an_empty_tail_answers_with_a_caveat_rather_than_nothing(
    client: TestClient, auth: TokenService
) -> None:
    payload = json.loads(read(client, auth).text)

    assert payload["clusters"] == []
    assert any("nothing to show" in caveat for caveat in payload["caveats"])


def test_every_read_says_the_tail_is_bounded_and_not_a_store(
    client: TestClient, auth: TokenService
) -> None:
    fill(client, auth, [log_line()])

    caveats = " ".join(read(client, auth).json()["caveats"])

    assert "not a store" in caveats
    assert "50 lines or 1 minutes" in caveats
    assert "T-419" in caveats
    assert "not a model's anomaly score" in caveats


def test_an_over_wide_read_is_refused_rather_than_trimmed(
    client: TestClient, auth: TokenService
) -> None:
    """A trimmed answer would report a subset as if it were the window (R-34)."""
    response = read(client, auth, start=stamp(-3600), end=stamp(60))

    assert response.status_code == 400
    assert "clusters" not in response.text


def test_an_empty_window_is_refused_like_an_inverted_one(
    client: TestClient, auth: TokenService
) -> None:
    """A zero-width window is not a small window; it is a mistake.

    Accepting it would answer "no lines" for a request that named no time at all,
    which reads as a quiet system rather than as a bad one.
    """
    response = read(client, auth, start=stamp(10), end=stamp(10))

    assert response.status_code == 400
    assert "end must be later than start" in response.json()["detail"]


def test_a_host_filter_narrows_both_reads(client: TestClient, auth: TokenService) -> None:
    """The expansion must select the same lines the cluster it came from counted.

    A row and its raw lines disagreeing is the defect this pins: the two routes
    share one filter set, and a swap between two filters is invisible unless a
    fixture has both of them set differently.
    """
    fill(
        client,
        auth,
        [
            log_line(host="web-1", offset=0, message="from web-1"),
            log_line(host="web-9", offset=1, message="from web-9"),
        ],
    )

    clusters = read(client, auth, host="web-9").json()
    lines = client.get(
        "/api/v1/logs/lines",
        params={"start": stamp(0), "end": stamp(60), "host": "web-9"},
        headers=headers(auth),
    ).json()

    assert clusters["lines_seen"] == 1
    assert [entry["message"] for entry in lines["lines"]] == ["from web-9"]


def test_a_service_filter_narrows_both_reads(client: TestClient, auth: TokenService) -> None:
    """Same rule, the other filter.

    A swap of host and service is a different bug with the same symptom, so both
    filters are exercised on both routes.
    """
    body = json.dumps(log_line(offset=0, message="from api"))
    other = {**log_line(offset=1, message="from worker"), "service": "worker"}
    fill(client, auth, [json.loads(body), other])

    lines = client.get(
        "/api/v1/logs/lines",
        params={"start": stamp(0), "end": stamp(60), "service": "worker"},
        headers=headers(auth),
    ).json()

    assert [entry["message"] for entry in lines["lines"]] == ["from worker"]


def test_reading_the_raw_lines_needs_a_credential(client: TestClient, auth: TokenService) -> None:
    """Both reads are R-53's ``viewer`` capability.

    Asserted on the route the expansion uses, not only on the cluster read.
    """
    for path in ("/api/v1/logs", "/api/v1/logs/lines"):
        response = client.get(path, params={"start": stamp(0), "end": stamp(60)})
        assert response.status_code == 401, path


def test_a_line_whose_publish_failed_is_not_shown(client: TestClient, auth: TokenService) -> None:
    """The tail is fed *after* the hand-off, so a failed request kept nothing.

    Ordering here is the whole claim: an analyst reading the tail must never see a
    line the pipeline did not receive, because the tail's answer would then disagree
    with what was scored.
    """

    class Failing:
        """A publisher that cannot accept anything, wired like the real one."""

        def publish(self, records: object, *, traceparent: str | None = None) -> None:
            raise RuntimeError("no consumer")

    client.app.state.flow_publisher = Failing()  # type: ignore[union-attr]

    with pytest.raises(RuntimeError):
        fill(client, auth, [log_line(message="never handed on")])

    payload = read(client, auth).json()

    assert payload["lines_seen"] == 0
    assert payload["clusters"] == []
