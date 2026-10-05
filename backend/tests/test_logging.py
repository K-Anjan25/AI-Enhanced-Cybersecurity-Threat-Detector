"""T-318: structured logs with correlation ids and the R-54 redaction allowlist.

The acceptance criterion is a sentence about a leak -- "a planted username in an
error path never reaches the log output" -- so the tests here do not inspect a
helper's return value and stop. They plant the username where an error path really
puts it: in the token subject of a request that is refused, in a query string, in
a header, and in the message of an exception, and then they read the *rendered
output* the process actually produced.

That distinction matters. ``structlog.testing.capture_logs`` replaces the processor
chain, so a test written against it would pass with the redaction processors
deleted -- it would be asserting that the code called a logger, not that the log is
safe. Every test below reads stdout: the same bytes a log shipper would forward.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import structlog
from app.auth.tokens import TokenService
from app.core.config import Environment, Settings
from app.core.logging import (
    ALLOWED_FIELDS,
    IDENTIFIER_FIELDS,
    REDACTED,
    SECRET_FIELDS,
    configure_logging,
    get_logger,
    redact_text,
)
from app.main import create_app
from app.services.limits import RateLimitPolicy
from fastapi.testclient import TestClient

SECRET = "t" * 48  # pragma: allowlist secret
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
OTHER_SECRET = "another-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
PLANTED_USER = "alice@corp"
PLANTED_HOST = "web-01"


@pytest.fixture
def settings() -> Settings:
    """Settings that log at INFO, so the access line is not filtered away."""
    return Settings(
        env=Environment.TEST,
        service_name="aegis-test",
        secret_key=APP_SECRET,
        log_level="INFO",
    )


@pytest.fixture
def auth() -> TokenService:
    return TokenService(APP_SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.token_service = auth
    with TestClient(app) as test_client:
        yield test_client


def headers(
    auth: TokenService, role: str = "viewer", subject: str = PLANTED_USER
) -> dict[str, str]:
    """A bearer header whose subject is the planted username."""
    pair = auth.issue(subject, role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def read_logs(capsys: pytest.CaptureFixture[str]) -> tuple[str, list[dict[str, Any]]]:
    """Everything written to stdout so far: the raw text, and the parsed events."""
    out = capsys.readouterr().out
    events = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    return out, events


def last_event(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """The most recent JSON log line, or a failure if there is none."""
    _raw, events = read_logs(capsys)
    assert events, "nothing was logged, so the assertion would be vacuous"
    return events[-1]


# --- the acceptance criterion -------------------------------------------------


def test_a_planted_username_in_an_error_path_never_reaches_the_log(
    client: TestClient, auth: TokenService, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-54, driven through a refusal: the subject, the query and a header."""
    response = client.post(
        "/api/v1/models/flow/promote",
        headers={**headers(auth), "X-Forwarded-Host": PLANTED_HOST},
        params={"actor": PLANTED_USER, "email": PLANTED_USER},
    )
    assert response.status_code == 403, "a viewer cannot promote a model"

    raw, events = read_logs(capsys)
    assert "alice" not in raw and "corp" not in raw, raw
    assert PLANTED_HOST not in raw
    assert events, "the refusal logged nothing, which is not the same as logging safely"
    request_lines = [event for event in events if event["event"] == "request"]
    assert len(request_lines) == 1
    assert request_lines[0]["status"] == 403
    assert request_lines[0]["route"] == "/api/v1/models/{model_id}/promote"
    assert request_lines[0]["request_id"] == response.headers["x-request-id"]
    assert request_lines[0]["trace_id"] == response.headers["x-trace-id"]


def test_an_exception_message_is_scrubbed(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """The error path proper: a message that names the user, rendered as a log."""
    configure_logging(settings)
    logger = get_logger("aegis.test")
    try:
        msg = f"no such user: {PLANTED_USER} on host={PLANTED_HOST}"
        raise LookupError(msg)
    except LookupError:
        logger.error("lookup failed for user=%s", PLANTED_USER, exc_info=True)

    raw, events = read_logs(capsys)
    assert "alice" not in raw and "corp" not in raw and PLANTED_HOST not in raw, raw
    assert events[0]["event"].startswith("lookup failed")
    assert "id:" in events[0]["exception"] or REDACTED in events[0]["exception"]
    assert "id:" in str(events[0]["event"])


def test_the_path_and_the_query_string_are_never_logged(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A URL is user input, and a query string is where an identifier hides."""
    client.get("/api/v1/alerts", params={"email": PLANTED_USER, "host": PLANTED_HOST})
    client.get("/no-such-route-alice-corp")

    raw, events = read_logs(capsys)
    routes = [event["route"] for event in events if event["event"] == "request"]
    assert routes == ["/api/v1/alerts", "unmatched"], "the template, or one series for nothing"
    assert "alice" not in raw and "corp" not in raw
    assert PLANTED_HOST not in raw
    assert "/no-such-route" not in raw


def test_the_access_line_reports_the_refusals_too(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 429 the limiter produced before routing is a request this process handled."""
    client.app.state.rate_limit_policy = RateLimitPolicy(  # type: ignore[attr-defined]
        credential_per_minute=1, anonymous_per_minute=1, secret=APP_SECRET
    )
    granted = headers(TokenService(APP_SECRET), role="analyst")
    assert client.get("/healthz", headers=granted).status_code == 200
    assert client.get("/healthz", headers=granted).status_code == 429

    _raw, events = read_logs(capsys)
    refused = [event for event in events if event["event"] == "request" and event["status"] == 429]
    assert len(refused) == 1
    assert refused[0]["route"] == "unmatched"
    assert refused[0]["level"] == "warning"


# --- the correlation ids ------------------------------------------------------


def test_every_line_carries_the_request_and_trace_ids(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    response = client.get("/healthz")
    event = last_event(capsys)
    assert event["request_id"] == response.headers["x-request-id"]
    assert event["trace_id"] == response.headers["x-trace-id"]
    assert event["service"] == "aegis-test"


def test_a_line_logged_inside_a_request_carries_the_ids(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not only the access line: anything the request logs joins the same trace.

    The check happens in the *same task* as the request. ``asyncio.run`` gives its
    coroutine a copy of the context, so ids bound inside a request are invisible to
    the caller afterwards whatever the code does -- a leak is only observable
    through a binding that was never unbound, in the task that made it.
    """
    import asyncio

    from app.api.middleware import MetricsMiddleware, TracingMiddleware
    from app.main import RequestIdMiddleware

    configure_logging(settings)
    seen: list[dict[str, Any]] = []

    async def handler(scope: Any, receive: Any, send: Any) -> None:
        seen.append(dict(structlog.contextvars.get_contextvars()))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def serve() -> None:
        stack = RequestIdMiddleware(TracingMiddleware(MetricsMiddleware(handler)))
        scope = {"type": "http", "method": "GET", "path": "/healthz", "headers": []}
        await stack(scope, _receive, _send)
        get_logger("aegis.test").info("after the request")
        seen.append(dict(structlog.contextvars.get_contextvars()))

    asyncio.run(serve())

    assert seen[0]["request_id"] and seen[0]["trace_id"], "the handler sees both ids"
    assert (
        "request_id" not in seen[1] and "trace_id" not in seen[1]
    ), "the ids were still bound after the request returned"
    assert seen[1]["service"] == "aegis-test", "the service name must survive the unbind"

    _raw, events = read_logs(capsys)
    access = [event for event in events if event["event"] == "request"]
    assert access[0]["request_id"] == seen[0]["request_id"]
    assert access[0]["trace_id"] == seen[0]["trace_id"]
    after = [event for event in events if event["event"] == "after the request"]
    assert after and "request_id" not in after[0] and "trace_id" not in after[0]
    assert after[0]["service"] == "aegis-test"


def test_the_tracing_middleware_unbinds_what_it_binds(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """Driven alone, with no request-id middleware to clean up after it."""
    import asyncio

    from app.api.middleware import TracingMiddleware

    configure_logging(settings)
    seen: list[dict[str, Any]] = []

    async def handler(scope: Any, receive: Any, send: Any) -> None:
        seen.append(dict(structlog.contextvars.get_contextvars()))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def serve() -> None:
        scope = {"type": "http", "method": "GET", "path": "/healthz", "headers": []}
        await TracingMiddleware(handler)(scope, _receive, _send)
        seen.append(dict(structlog.contextvars.get_contextvars()))

    asyncio.run(serve())
    assert seen[0]["trace_id"]
    assert "trace_id" not in seen[1], "a middleware that binds must unbind"


def test_two_requests_do_not_share_a_correlation_id(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    first = client.get("/healthz")
    second = client.get("/healthz")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert first.headers["x-trace-id"] != second.headers["x-trace-id"]


# --- the allowlist ------------------------------------------------------------


def test_every_field_the_application_logs_is_allowlisted(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    client.get("/healthz")
    event = last_event(capsys)
    # `level` and `timestamp` are structlog's own, added after the allowlist runs.
    assert set(event) - {"level", "timestamp"} <= ALLOWED_FIELDS


def test_the_allowlist_admits_no_identifier_or_secret_field() -> None:
    """The two halves of R-54 cannot disagree: nothing is both allowed and redacted."""
    assert not ALLOWED_FIELDS & IDENTIFIER_FIELDS
    assert not ALLOWED_FIELDS & SECRET_FIELDS


def test_an_unknown_field_is_dropped(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """An allowlist that admits everything is not an allowlist."""
    configure_logging(settings)
    get_logger("aegis.test").info("lookup", planted=PLANTED_USER, user=PLANTED_USER)

    raw, events = read_logs(capsys)
    assert "planted" not in events[0]
    assert "alice" not in raw and "corp" not in raw


def test_a_field_holding_the_planted_name_as_its_key_is_dropped(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """The *key* can be the identifier, so a dropped key is never reported."""
    configure_logging(settings)
    get_logger("aegis.test").info("lookup", **{PLANTED_USER: 1})

    raw, events = read_logs(capsys)
    assert events[0]["event"] == "lookup"
    assert "alice" not in raw and "corp" not in raw


def test_nested_mappings_are_filtered_too(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    get_logger("aegis.test").info(
        "nested", detail={"user": PLANTED_USER, "note": "10.0.0.1", "count": 2}
    )

    raw, events = read_logs(capsys)
    detail = events[0]["detail"]
    assert detail["user"].startswith("id:")
    assert "note" not in detail, "a nested field is a field"
    assert "alice" not in raw and "10.0.0.1" not in raw


def test_a_list_of_values_is_scrubbed(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    get_logger("aegis.test").info("batch", reason=[PLANTED_USER, "10.0.0.1"])

    raw, events = read_logs(capsys)
    assert "alice" not in raw and "10.0.0.1" not in raw
    assert events[0]["reason"][0].startswith("id:")


# --- identifiers: hashed, not printed ----------------------------------------


@pytest.mark.parametrize(
    "field", ["user", "username", "actor", "host", "hostname", "src_ip", "email"]
)
def test_an_identifier_field_is_hashed(
    settings: Settings, capsys: pytest.CaptureFixture[str], field: str
) -> None:
    """R-54 allows redaction *or* a salted hash; the hash keeps correlation."""
    configure_logging(settings)
    get_logger("aegis.test").info("identified", **{field: PLANTED_USER})

    raw, events = read_logs(capsys)
    assert events[0][field].startswith("id:")
    assert PLANTED_USER not in raw


def test_the_same_identifier_hashes_the_same_way(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    logger = get_logger("aegis.test")
    logger.info("first", user=PLANTED_USER)
    logger.info("second", user=PLANTED_USER)
    logger.info("third", user="bob@corp")

    _raw, events = read_logs(capsys)
    assert events[0]["user"] == events[1]["user"], "a hash that changes per line joins nothing"
    assert events[0]["user"] != events[2]["user"]


def test_the_hash_is_keyed_by_the_deployment_secret(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hash under a constant key is a lookup table away from the value."""
    configure_logging(settings)
    get_logger("aegis.test").info("first", user=PLANTED_USER)
    first = last_event(capsys)["user"]

    configure_logging(settings.model_copy(update={"secret_key": OTHER_SECRET}))
    get_logger("aegis.test").info("second", user=PLANTED_USER)
    _raw, events = read_logs(capsys)
    second = events[0]["user"]
    assert second.startswith("id:") and second != first, "a new deployment key is a new name"


def test_a_bare_hostname_in_prose_is_not_recognised() -> None:
    """The boundary, stated rather than implied: shape cannot identify a hostname.

    Any word could be one, so the control for hostnames is the allowlist -- a
    hostname reaches a log line only by being bound to a field, and a ``host`` field
    is hashed. This test exists so the boundary is a decision on record rather than
    a surprise during an incident review.
    """
    assert PLANTED_HOST in redact_text(f"the collector at {PLANTED_HOST} is down")


def test_an_identifier_is_redacted_when_no_key_is_configured(
    settings: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before configuration there is no key, and a default key would be a lie."""
    from app.core import logging as logging_module

    configure_logging(settings)
    monkeypatch.setattr(logging_module, "_id_key", None)
    get_logger("aegis.test").info("identified", user=PLANTED_USER)

    raw, events = read_logs(capsys)
    assert events[0]["user"] == REDACTED
    assert PLANTED_USER not in raw


# --- secrets ------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["token", "access_token", "authorization", "api_key", "password", "secret", "cookie"]
)
def test_a_secret_field_is_never_rendered(
    settings: Settings, capsys: pytest.CaptureFixture[str], field: str
) -> None:
    configure_logging(settings)
    get_logger("aegis.test").info("authenticated", **{field: "hunter2-super-secret"})

    raw, events = read_logs(capsys)
    assert events[0][field] == REDACTED
    assert "hunter2" not in raw


@pytest.mark.parametrize(
    ("text", "planted"),
    [
        (PLANTED_USER, "alice"),
        ("10.0.0.1", "10.0.0.1"),
        ("2001:db8::1", "2001:db8"),
        ("2001:0db8:0000:0000:0000:0000:0000:0001", "0db8"),
        ("Bearer abcdefghijklmnop", "abcdefghijklmnop"),
        (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "eyJhbGciOiJIUzI1NiJ9",
        ),
    ],
)
def test_free_text_identifiers_are_removed(text: str, planted: str) -> None:
    assert planted not in redact_text(f"failure near {text} here")


@pytest.mark.parametrize(
    "text", ["2026-10-05T10:00:00.123456Z", "10:00:00", "12:34:56", "1:2:3", "2026-10-05"]
)
def test_a_timestamp_is_not_mistaken_for_an_address(text: str) -> None:
    """The IPv6 rule needs its ``::`` or all eight groups: a clock is not an address."""
    assert redact_text(text) == text


def test_the_logged_timestamp_survives(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    get_logger("aegis.test").info("tick")
    event = last_event(capsys)
    parsed = datetime.fromisoformat(event["timestamp"])
    assert parsed.tzinfo is not None
    assert parsed.astimezone(UTC).year == datetime.now(UTC).year


# --- the renderer and the stdlib path ----------------------------------------


def test_development_still_redacts(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    """Console output is for humans; a username is not more welcome there."""
    configure_logging(settings.model_copy(update={"env": Environment.DEVELOPMENT}))
    get_logger("aegis.test").info("lookup", user=PLANTED_USER, planted=PLANTED_USER)

    raw, events = read_logs(capsys)
    assert not events, "development output is not JSON, by design"
    assert "lookup" in raw and "id:" in raw
    assert PLANTED_USER not in raw and "planted" not in raw


def test_a_stdlib_record_is_scrubbed_on_its_way_out(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """Uvicorn's access lines never reach a structlog processor, so the formatter scrubs."""
    configure_logging(settings)
    logging.getLogger("uvicorn.access").warning("GET /x?user=%s 200", PLANTED_USER)

    raw, _events = read_logs(capsys)
    assert "alice" not in raw and "corp" not in raw
    assert "id:" in raw


def test_configure_logging_replaces_its_handlers(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """Called at every application start, including many starts in one process."""
    before = len(logging.getLogger().handlers)
    configure_logging(settings)
    configure_logging(settings)
    after = logging.getLogger().handlers
    assert len(after) == 1, f"handlers accumulated: {before} -> {len(after)}"
    assert logging.getLogger().level == logging.INFO
    assert settings.log_level == "INFO"


def test_the_level_follows_the_outcome(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 5xx is an error line, a 4xx a warning, a 2xx information."""
    import asyncio

    from app.api.middleware import MetricsMiddleware

    configure_logging(settings)

    def drive(status: int) -> None:
        async def app(scope: Any, receive: Any, send: Any) -> None:
            await send({"type": "http.response.start", "status": status, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        asyncio.run(
            MetricsMiddleware(app)(
                {"type": "http", "method": "GET", "path": "/x", "headers": []},
                _receive,
                _send,
            )
        )

    drive(200)
    drive(404)
    drive(500)
    _raw, events = read_logs(capsys)
    assert [(event["status"], event["level"]) for event in events] == [
        (200, "info"),
        (404, "warning"),
        (500, "error"),
    ]


def test_the_method_is_logged_as_the_api_takes_it(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """A proxy may send a lower-cased method; the series and the line agree anyway."""
    import asyncio

    from app.api.middleware import MetricsMiddleware

    configure_logging(settings)

    async def ok(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    asyncio.run(
        MetricsMiddleware(ok)(
            {"type": "http", "method": "post", "path": "/x", "headers": []},
            _receive,
            _send,
        )
    )
    assert last_event(capsys)["method"] == "POST"


def test_the_duration_is_measured_not_stamped(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """A duration that is not measured is a field that lies with confidence."""
    import asyncio

    from app.api.middleware import MetricsMiddleware

    configure_logging(settings)

    async def slow(scope: Any, receive: Any, send: Any) -> None:
        await asyncio.sleep(0.02)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    asyncio.run(
        MetricsMiddleware(slow)(
            {"type": "http", "method": "GET", "path": "/x", "headers": []},
            _receive,
            _send,
        )
    )
    event = last_event(capsys)
    assert event["duration_ms"] >= 10, event


async def _receive() -> dict[str, Any]:
    """A request with no body."""
    return {"type": "http.request", "body": b""}


async def _send(_message: dict[str, Any]) -> None:
    """Discard what the application sends; the log line is what is measured."""
    return None
