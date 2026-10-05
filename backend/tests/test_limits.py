"""T-316: rate limiting, request size caps and back-pressure (R-56).

R-56 is a **coverage** rule -- "rate limiting on every unauthenticated and every
write endpoint" -- so the tests that matter most are the ones that would notice an
endpoint *outside* the limit: a walk of the live application compared against the
policy's own classification, and a planted route that must be in scope. The rest
assert the mechanisms: the bucket's arithmetic, the header the client is told to
obey, the body that is refused before a parser sees it, and the batch that is
refused whole rather than partly accepted.

Everything here runs without a network: the policy is driven by an injected clock,
and the middleware is exercised through the ASGI test client, which is the layer
the rules actually live at.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.middleware import (
    BODY_TOO_LARGE_DETAIL,
    RATE_LIMIT_DETAIL,
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
)
from app.auth.rbac import DOC_ROUTES, ROUTE_MATRIX, UNAUTHENTICATED_ROUTES
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from app.services import limits
from app.services.audit_log import MUTATING_METHODS, InMemoryAuditTrail
from app.services.limits import (
    EXEMPT_ROUTES,
    LIMITED_UNAUTHENTICATED_ROUTES,
    WRITE_METHODS,
    AdmissionController,
    RateLimitPolicy,
    TokenBucket,
    fingerprint,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = "l" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
#: A valid flow@1 record: accepted batches are what the back-pressure tests need,
#: because a batch that is rejected record by record puts nothing in flight.
FLOW = {
    "timestamp": "2026-03-15T10:00:00Z",
    "src_ip": "10.0.0.1",
    "dst_ip": "10.0.0.2",
    "src_port": 1234,
    "dst_port": 80,
    "protocol": "tcp",
    "direction": "inbound",
    "packets": 10,
    "src_packets": 5,
    "dst_packets": 5,
    "src_bytes": 1000,
    "dst_bytes": 2000,
    "duration": 1.5,
}


def headers(auth: TokenService, role: str = "analyst") -> dict[str, str]:
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.token_service = auth
    with TestClient(app) as test_client:
        yield test_client


def update_limits(client: TestClient, **kwargs: int) -> RateLimitPolicy:
    """Tighten (or loosen) the live policy on a built app."""
    settings = client.app.state.settings  # type: ignore[attr-defined]
    policy = RateLimitPolicy(
        credential_per_minute=kwargs.get("credential", settings.rate_limit_requests_per_minute),
        anonymous_per_minute=kwargs.get("anonymous", settings.rate_limit_anonymous_per_minute),
        secret=APP_SECRET,
    )
    client.app.state.rate_limit_policy = policy  # type: ignore[attr-defined]
    return policy


def trail(client: TestClient) -> InMemoryAuditTrail:
    return client.app.state.audit_trail  # type: ignore[attr-defined]


def audit_count(client: TestClient) -> int:
    now = datetime.now(UTC)
    return len(trail(client).entries(start=now - timedelta(hours=1), end=now + timedelta(hours=1)))


# --- the token bucket ---------------------------------------------------------


def test_a_full_bucket_allows_a_minute_of_traffic_then_refuses() -> None:
    bucket = TokenBucket(60, now=0.0)
    for index in range(60):
        assert bucket.take(now=0.0).allowed, index
    refused = bucket.take(now=0.0)
    assert refused.allowed is False
    assert refused.retry_after == 1  # one token per second at sixty a minute
    assert refused.remaining == 0


def test_retry_after_rounds_up_rather_than_promising_early() -> None:
    """Six a minute is one token every ten seconds; four seconds buys 0.4 of one."""
    bucket = TokenBucket(6, now=0.0)
    for _ in range(6):
        bucket.take(now=0.0)
    assert bucket.take(now=4.0).retry_after == 6
    assert bucket.take(now=9.0).retry_after == 1
    assert bucket.take(now=10.0).allowed is True


def test_an_awkward_rate_rounds_the_wait_up() -> None:
    """Seven a minute is one every 8.57 s: the client is told 9, never 8."""
    bucket = TokenBucket(7, now=0.0)
    for _ in range(7):
        bucket.take(now=0.0)
    assert bucket.take(now=0.0).retry_after == 9


def test_a_refused_request_does_not_consume_a_token() -> None:
    """Otherwise a client retrying inside the window would extend its own wait."""
    bucket = TokenBucket(1, now=0.0)
    assert bucket.take(now=0.0).allowed is True
    first = bucket.take(now=0.0)
    second = bucket.take(now=0.0)
    assert (first.retry_after, second.retry_after) == (60, 60)


def test_an_idle_bucket_refills_to_capacity_and_no_further() -> None:
    bucket = TokenBucket(6, now=0.0)
    for _ in range(6):
        bucket.take(now=0.0)
    assert bucket.take(now=3600.0).allowed is True
    for _ in range(5):
        assert bucket.take(now=3600.0).allowed is True
    assert bucket.take(now=3600.0).allowed is False


def test_a_rate_limit_of_zero_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="at least one request per minute"):
        TokenBucket(0, now=0.0)


# --- the policy ---------------------------------------------------------------


@pytest.mark.parametrize("method", sorted(WRITE_METHODS))
def test_every_write_method_is_limited(method: str) -> None:
    policy = RateLimitPolicy(secret=APP_SECRET)
    assert policy.is_limited(method, "/api/v1/anything") is True
    assert policy.is_limited(method.lower(), "/api/v1/anything") is True


@pytest.mark.parametrize("path", sorted(LIMITED_UNAUTHENTICATED_ROUTES))
def test_every_unauthenticated_route_is_limited_whatever_its_method(path: str) -> None:
    policy = RateLimitPolicy(secret=APP_SECRET)
    assert policy.is_limited("GET", path) is True


def test_the_unauthenticated_set_matches_the_route_tables() -> None:
    """The literals in ``app.services.limits`` and the rbac tables cannot drift."""
    assert LIMITED_UNAUTHENTICATED_ROUTES == UNAUTHENTICATED_ROUTES | DOC_ROUTES


def test_nothing_is_exempt_from_r56() -> None:
    """An exemption is how a coverage rule stops being one; there are none."""
    assert frozenset() == EXEMPT_ROUTES


def test_reads_that_need_a_credential_are_out_of_scope() -> None:
    """A read is cheap, already needs a token, and the alert stream is long-lived."""
    policy = RateLimitPolicy(secret=APP_SECRET)
    assert policy.is_limited("GET", "/api/v1/alerts") is False
    assert policy.is_limited("GET", "/api/v1/audit") is False


def test_an_out_of_scope_request_takes_no_token() -> None:
    policy = RateLimitPolicy(credential_per_minute=1, secret=APP_SECRET)
    for _ in range(50):
        decision = policy.check(
            method="GET", path="/api/v1/alerts", credential="key", client_ip="10.0.0.1"
        )
        assert decision.allowed is True
    assert policy.tracked == 0


def test_identity_is_a_fingerprint_for_a_credential_and_an_address_otherwise() -> None:
    policy = RateLimitPolicy(secret=APP_SECRET)
    with_credential = policy.identity(credential="aegis_sk_7_secret", client_ip="10.0.0.1")
    other = policy.identity(credential="aegis_sk_7_secret", client_ip="10.0.0.9")
    assert with_credential == other, "the credential decides the bucket, not the address"
    assert policy.identity(credential=None, client_ip="10.0.0.1").startswith("address:")
    assert policy.identity(credential=None, client_ip=None) == "address:unknown"


def test_two_credentials_do_not_share_a_bucket() -> None:
    policy = RateLimitPolicy(credential_per_minute=1, secret=APP_SECRET)
    first = policy.check(
        method="POST",
        path="/api/v1/ingest/flows",
        credential="aegis_sk_1_a",
        client_ip="10.0.0.1",
    )
    second = policy.check(
        method="POST",
        path="/api/v1/ingest/flows",
        credential="aegis_sk_1_b",
        client_ip="10.0.0.1",
    )
    assert (first.allowed, second.allowed) == (True, True)


def test_a_request_with_a_credential_does_not_spend_the_address_budget() -> None:
    """An office full of collectors must not compete with one anonymous client."""
    policy = RateLimitPolicy(credential_per_minute=5, anonymous_per_minute=1, secret=APP_SECRET)
    for _ in range(5):
        assert policy.check(
            method="POST", path="/x", credential="aegis_sk_1_a", client_ip="10.0.0.1"
        ).allowed
    assert policy.check(method="POST", path="/x", credential=None, client_ip="10.0.0.1").allowed


def test_idle_buckets_are_pruned_so_rotating_identities_cannot_leak_memory() -> None:
    policy = RateLimitPolicy(secret=APP_SECRET)
    for index in range(5):
        policy.check(method="POST", path="/x", credential=f"key-{index}", client_ip=None, now=0.0)
    assert policy.tracked == 5
    policy.check(
        method="POST",
        path="/x",
        credential="fresh",
        client_ip=None,
        now=limits.BUCKET_TTL_SECONDS + 1,
    )
    assert policy.tracked == 1, "everything idle past the TTL is dropped"


def test_the_bucket_table_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_TRACKED_IDENTITIES", 3)
    policy = RateLimitPolicy(secret=APP_SECRET)
    for index in range(10):
        policy.check(method="POST", path="/x", credential=f"key-{index}", client_ip=None, now=0.0)
    assert policy.tracked <= 3


def test_a_rate_limit_of_zero_is_refused_by_the_policy() -> None:
    with pytest.raises(ValueError, match="at least one request per minute"):
        RateLimitPolicy(credential_per_minute=0, secret=APP_SECRET)


# --- the fingerprint ----------------------------------------------------------


def test_a_fingerprint_is_stable_and_keyed() -> None:
    first = fingerprint(APP_SECRET, "credential:abc")
    assert first == fingerprint(APP_SECRET, "credential:abc")
    assert first != fingerprint(APP_SECRET, "credential:abd")
    assert first != fingerprint("other-secret-that-is-long-enough-0123456789", "credential:abc")


def test_a_fingerprint_does_not_carry_the_credential() -> None:
    """R-58: the limiter holds a name for the credential, never the credential."""
    printed = fingerprint(APP_SECRET, "credential:aegis_sk_7_secret")
    assert len(printed) == 64
    assert int(printed, 16) >= 0  # hex, so it is usable as a dict key and as a log field
    assert "aegis_sk" not in printed
    assert "secret" not in printed


def test_a_short_application_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        fingerprint("short", "credential:abc")


# --- admission control --------------------------------------------------------


def test_admission_is_all_or_nothing() -> None:
    controller = AdmissionController(5)
    assert controller.admit(3) is True
    assert controller.admit(3) is False
    assert controller.backlog == 3, "a refused batch must not partially admit"


def test_admission_releases_and_never_goes_negative() -> None:
    controller = AdmissionController(5)
    controller.admit(4)
    controller.release(4)
    assert controller.backlog == 0
    controller.release(10)
    assert controller.backlog == 0


def test_admission_reports_a_retry_after_rather_than_guessing_a_long_one() -> None:
    assert AdmissionController(1).retry_after() == 1


@pytest.mark.parametrize("bad", [0, -1])
def test_a_meaningless_admission_capacity_is_refused(bad: int) -> None:
    with pytest.raises(ValueError, match="at least one record"):
        AdmissionController(bad)


def test_admission_refuses_a_negative_batch_or_release() -> None:
    controller = AdmissionController(5)
    with pytest.raises(ValueError, match="negative number of records"):
        controller.admit(-1)
    with pytest.raises(ValueError, match="negative number of records"):
        controller.release(-1)


# --- through the middleware ---------------------------------------------------


def test_the_write_limit_answers_429_with_retry_after(
    client: TestClient, auth: TokenService
) -> None:
    update_limits(client, credential=2)
    granted = headers(auth)
    for index in range(2):
        response = client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted)
        assert response.status_code == 200, index
        # The fixture is a *valid* record, so the request really did put a record
        # in flight -- otherwise the back-pressure gate would be admitting zero.
        assert response.json() == {
            "received": 1,
            "accepted": 1,
            "rejected": 0,
            "errors": [],
        }
    refused = client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted)
    assert refused.status_code == 429
    assert refused.json() == {"detail": RATE_LIMIT_DETAIL}
    assert int(refused.headers["retry-after"]) >= 1


def test_a_throttled_request_never_reaches_the_route(
    client: TestClient, auth: TokenService
) -> None:
    """The 429 is produced before routing, so nothing downstream did any work."""
    update_limits(client, credential=1)
    granted = headers(auth)
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 200
    before = audit_count(client)
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 429
    assert audit_count(client) == before


def test_two_credentials_have_separate_allowances(client: TestClient, auth: TokenService) -> None:
    update_limits(client, credential=1)
    first, second = headers(auth), headers(auth)
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=first).status_code == 200
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=first).status_code == 429
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=second).status_code == 200


def test_an_api_key_is_bucketed_by_itself(client: TestClient, auth: TokenService) -> None:
    update_limits(client, credential=1)
    key = client.post(
        "/api/v1/keys",
        json={"name": "collector", "scopes": ["ingest:write"]},
        headers=headers(auth, "admin"),
    ).json()
    keyed = {"X-API-Key": key["secret"]}
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=keyed).status_code == 200
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=keyed).status_code == 429


def test_an_unauthenticated_route_is_limited_per_address(client: TestClient) -> None:
    update_limits(client, anonymous=1)
    assert client.get("/healthz").status_code == 200
    refused = client.get("/healthz")
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "60"


def test_a_forwarded_header_does_not_buy_a_bucket(client: TestClient) -> None:
    """X-Forwarded-For is attacker-controlled here, so it is not an identity."""
    update_limits(client, anonymous=1)
    assert client.get("/healthz", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
    refused = client.get("/healthz", headers={"X-Forwarded-For": "203.0.113.2"})
    assert refused.status_code == 429


def test_readiness_is_limited_too(client: TestClient) -> None:
    """R-56 says every unauthenticated endpoint, and readiness is one."""
    update_limits(client, anonymous=1)
    client.get("/readyz")
    assert client.get("/readyz").status_code == 429


def test_reads_are_not_throttled_by_the_write_limit(client: TestClient, auth: TokenService) -> None:
    update_limits(client, credential=1)
    granted = headers(auth)
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 200
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 429
    for _ in range(3):
        assert (
            client.get(
                "/api/v1/alerts",
                headers=granted,
                params={
                    "start": "2026-10-01T00:00:00Z",
                    "end": "2026-10-02T00:00:00Z",
                },
            ).status_code
            != 429
        )


def test_the_settings_drive_the_limits(settings: Settings, auth: TokenService) -> None:
    app = create_app(settings.model_copy(update={"rate_limit_requests_per_minute": 1}))
    app.state.token_service = auth
    with TestClient(app) as client:
        granted = headers(auth)
        assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 200
        assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 429


def test_the_request_id_is_on_the_throttled_response(client: TestClient) -> None:
    """The limiter runs inside the request-id middleware, so a 429 is traceable."""
    update_limits(client, anonymous=1)
    client.get("/healthz")
    refused = client.get("/healthz")
    assert refused.status_code == 429
    assert refused.headers["x-request-id"]


def test_the_middlewares_are_installed_in_order(client: TestClient) -> None:
    names = [middleware.cls.__name__ for middleware in client.app.user_middleware]  # type: ignore[attr-defined]
    assert names.index("RequestIdMiddleware") < names.index("RateLimitMiddleware")
    assert "BodySizeLimitMiddleware" in names


# --- the body cap -------------------------------------------------------------


def test_a_declared_body_over_the_cap_is_refused_before_parsing(
    client: TestClient, auth: TokenService
) -> None:
    client.app.state.max_request_bytes = 512  # type: ignore[attr-defined]
    response = client.post(
        "/api/v1/ingest/flows",
        content=b"[]",
        headers={
            **headers(auth),
            "content-length": "4096",
            "content-type": "application/json",
        },
    )
    assert response.status_code == 413
    assert BODY_TOO_LARGE_DETAIL in response.json()["detail"]
    assert response.headers["connection"] == "close"
    assert response.headers["x-request-id"], "the cap runs inside the request-id middleware"


def test_the_cap_applies_before_routing(client: TestClient) -> None:
    """An oversized body is refused without revealing whether the path exists."""
    client.app.state.max_request_bytes = 16  # type: ignore[attr-defined]
    response = client.post("/api/v1/does-not-exist", content=b"x" * 64)
    assert response.status_code == 413


def test_a_streamed_body_is_counted_and_refused_at_the_cap(
    client: TestClient, auth: TokenService
) -> None:
    """No declared length, so the only control is the count as bytes arrive."""
    client.app.state.max_request_bytes = 1024  # type: ignore[attr-defined]

    def chunks() -> Iterator[bytes]:
        for _ in range(8):
            yield b"x" * 512

    response = client.post(
        "/api/v1/ingest/flows",
        content=chunks(),
        headers={**headers(auth), "content-type": "application/x-ndjson"},
    )
    assert response.status_code == 413


def test_a_body_within_the_cap_is_parsed_normally(client: TestClient, auth: TokenService) -> None:
    client.app.state.max_request_bytes = 4096  # type: ignore[attr-defined]
    assert (
        client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth)).status_code == 200
    )


def test_a_lying_content_length_does_not_get_through(
    client: TestClient, auth: TokenService
) -> None:
    """The header is a hint; the count is the control."""
    client.app.state.max_request_bytes = 256  # type: ignore[attr-defined]

    def chunks() -> Iterator[bytes]:
        for _ in range(4):
            yield b"y" * 200

    response = client.post(
        "/api/v1/ingest/flows",
        content=chunks(),
        headers={
            **headers(auth),
            "content-length": "10",
            "content-type": "application/x-ndjson",
        },
    )
    assert response.status_code == 413


def test_the_body_cap_is_scoped_to_write_methods() -> None:
    """A body on a read is odd, and the cap is not the place to police it."""
    middleware = BodySizeLimitMiddleware(echo_app, max_bytes=4)
    scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}
    sent = drive(middleware, scope, [{"type": "http.request", "body": b"z" * 64}])
    assert status_of(sent) == 200


async def draining_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """A stand-in for a parser: read the body to the end, then answer."""
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_the_running_total_spans_chunks() -> None:
    """Five and five is ten, whatever the chunks look like."""
    middleware = BodySizeLimitMiddleware(draining_app, max_bytes=8)
    scope = {"type": "http", "method": "POST", "path": "/x", "headers": []}
    sent = drive(
        middleware,
        scope,
        [
            {"type": "http.request", "body": b"z" * 5, "more_body": True},
            {"type": "http.request", "body": b"z" * 5, "more_body": False},
        ],
    )
    assert status_of(sent) == 413


def test_the_configured_byte_cap_reaches_the_middleware(
    settings: Settings, auth: TokenService
) -> None:
    """A deployment that lowers the cap gets the cap it configured."""
    app = create_app(settings.model_copy(update={"max_request_bytes": 1024}))
    app.state.token_service = auth
    # The value reaches the middleware itself as well as the state override: the
    # wiring is asserted here because a wrong constructor argument would otherwise
    # be invisible while the state happened to hold the right number.
    installed = next(
        entry for entry in app.user_middleware if entry.cls.__name__ == "BodySizeLimitMiddleware"
    )
    assert installed.kwargs["max_bytes"] == 1024
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingest/flows",
            content=b"[" + b" " * 2048 + b"]",
            headers={**headers(auth), "content-type": "application/json"},
        )
        assert response.status_code == 413


def test_the_cap_does_not_apply_to_a_read(client: TestClient) -> None:
    """A GET with a body is odd, and capping it would break an odd client for nothing."""
    client.app.state.max_request_bytes = 8  # type: ignore[attr-defined]
    assert client.get("/healthz").status_code == 200


# --- back-pressure ------------------------------------------------------------


def test_a_full_buffer_refuses_the_batch_whole_with_retry_after(
    client: TestClient, auth: TokenService
) -> None:
    controller: AdmissionController = client.app.state.admission  # type: ignore[attr-defined]
    controller.admit(controller.capacity)
    before = audit_count(client)
    refused = client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth))
    assert refused.status_code == 503
    assert refused.headers["retry-after"] == "1"
    assert "refused whole" in refused.json()["detail"]
    assert (
        audit_count(client) == before
    ), "a refused batch changed nothing, so the trail stays still"


def test_only_accepted_records_are_admitted(client: TestClient, auth: TokenService) -> None:
    """A batch the collector got half wrong costs the buffer only what it fits."""
    client.app.state.admission = AdmissionController(1)  # type: ignore[attr-defined]
    granted = headers(auth)
    response = client.post(
        "/api/v1/ingest/flows", json=[FLOW, {"src_ip": "10.0.0.1"}], headers=granted
    )
    assert response.status_code == 200, "one accepted record fits a one-record buffer"
    assert response.json()["accepted"] == 1
    assert client.app.state.admission.backlog == 0  # type: ignore[attr-defined]


def test_the_buffer_is_released_when_the_request_ends(
    client: TestClient, auth: TokenService
) -> None:
    controller: AdmissionController = client.app.state.admission  # type: ignore[attr-defined]
    granted = headers(auth)
    for _ in range(3):
        assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 200
    assert controller.backlog == 0


def test_a_batch_larger_than_the_buffer_is_refused_not_truncated(
    client: TestClient, auth: TokenService
) -> None:
    client.app.state.admission = AdmissionController(1)  # type: ignore[attr-defined]
    response = client.post("/api/v1/ingest/flows", json=[FLOW, FLOW], headers=headers(auth))
    assert response.status_code == 503


def test_a_missing_buffer_fails_loudly(client: TestClient, auth: TokenService) -> None:
    del client.app.state.admission  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="admission is not configured"):
        client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth))


# --- the ASGI contract, driven directly ----------------------------------------


def drive(
    middleware: Any, scope: dict[str, Any], messages: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Run one ASGI exchange to completion and return what the client would receive."""
    inbox = list(messages or [])

    async def receive() -> dict[str, Any]:
        if inbox:
            return inbox.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    sent: list[dict[str, Any]] = []
    asyncio.run(middleware(scope, receive, send))
    return sent


def status_of(sent: list[dict[str, Any]]) -> int:
    return next(message["status"] for message in sent if message["type"] == "http.response.start")


def body_of(sent: list[dict[str, Any]]) -> bytes:
    return b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )


def header_of(sent: list[dict[str, Any]], name: bytes) -> str | None:
    for message in sent:
        if message["type"] != "http.response.start":
            continue
        for key, value in message["headers"]:
            if key == name:
                return value.decode()
    return None


ECHO_APP_CALLS: list[str] = []


async def echo_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """A minimal ASGI app: it reports the first message the body middleware passed it."""
    message = await receive()
    ECHO_APP_CALLS.append(message["type"])
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_a_body_cap_of_zero_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="at least one byte"):
        BodySizeLimitMiddleware(echo_app, max_bytes=0)


def test_the_configured_cap_applies_without_a_scope_app() -> None:
    """The middleware is usable on its own, away from ``create_app``."""
    middleware = BodySizeLimitMiddleware(echo_app, max_bytes=8)
    scope = {"type": "http", "method": "POST", "path": "/x", "headers": []}
    sent = drive(middleware, scope, [{"type": "http.request", "body": b"z" * 64}])
    assert status_of(sent) == 413
    assert b"at most 8 bytes" in body_of(sent)


def test_a_body_exactly_at_the_cap_is_accepted() -> None:
    """The boundary is inclusive: a cap of eight bytes accepts eight bytes."""
    ECHO_APP_CALLS.clear()
    middleware = BodySizeLimitMiddleware(echo_app, max_bytes=8)
    scope = {"type": "http", "method": "POST", "path": "/x", "headers": []}
    sent = drive(middleware, scope, [{"type": "http.request", "body": b"z" * 8}])
    assert status_of(sent) == 200
    assert ECHO_APP_CALLS == ["http.request"]
    over = drive(middleware, scope, [{"type": "http.request", "body": b"z" * 9}])
    assert status_of(over) == 413


def test_a_disconnect_is_passed_through() -> None:
    """A client that goes away is not a body, and the cap must not read it as one."""
    ECHO_APP_CALLS.clear()
    middleware = BodySizeLimitMiddleware(echo_app, max_bytes=8)
    scope = {"type": "http", "method": "POST", "path": "/x", "headers": []}
    sent = drive(middleware, scope, [{"type": "http.disconnect"}])
    assert status_of(sent) == 200
    assert ECHO_APP_CALLS == ["http.disconnect"]


def test_the_constructed_policy_applies_without_a_scope_app() -> None:
    # No credential on these scopes, so the anonymous limit is what applies.
    middleware = RateLimitMiddleware(
        echo_app,
        policy=RateLimitPolicy(credential_per_minute=1, anonymous_per_minute=1, secret=APP_SECRET),
    )
    scope = {"type": "http", "method": "POST", "path": "/x", "headers": []}
    assert status_of(drive(middleware, scope, [])) == 200
    refused = drive(middleware, scope, [])
    assert status_of(refused) == 429
    assert header_of(refused, b"retry-after") == "60"


def test_an_address_less_client_is_counted_under_one_name() -> None:
    """An ASGI server always reports a peer, but the contract does not require it."""
    policy = RateLimitPolicy(credential_per_minute=1, anonymous_per_minute=1, secret=APP_SECRET)
    middleware = RateLimitMiddleware(echo_app, policy=policy)
    plain = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [],
        "app": _StateApp(policy),
    }
    assert status_of(drive(middleware, plain, [])) == 200
    assert policy.tracked == 1, "no address still means one bucket, not a new one per request"
    assert status_of(drive(middleware, plain, [])) == 429
    blank = dict(plain, client=("", 0))
    assert status_of(drive(middleware, blank, [])) == 429, "an empty host is the same bucket"


class _StateApp:
    """A stand-in for ``scope['app']``: only ``state`` is read."""

    def __init__(self, policy: RateLimitPolicy) -> None:
        self.state = SimpleNamespace(rate_limit_policy=policy)


def test_two_addresses_have_separate_buckets() -> None:
    """The anonymous budget is per client, not one global allowance."""
    policy = RateLimitPolicy(credential_per_minute=1, anonymous_per_minute=1, secret=APP_SECRET)
    middleware = RateLimitMiddleware(echo_app, policy=policy)
    first = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [],
        "client": ("10.0.0.1", 5),
    }
    second = dict(first, client=("10.0.0.2", 5))
    assert status_of(drive(middleware, first, [])) == 200
    assert status_of(drive(middleware, first, [])) == 429
    assert status_of(drive(middleware, second, [])) == 200


def test_a_client_cannot_evade_the_limit_by_alternating_credentials() -> None:
    """Two identities must not reset each other's bucket while both are live."""
    policy = RateLimitPolicy(credential_per_minute=1, secret=APP_SECRET)
    args = {"method": "POST", "path": "/x", "client_ip": "10.0.0.1"}
    assert policy.check(credential="aegis_sk_1_a", **args).allowed is True
    assert policy.check(credential="aegis_sk_1_b", **args).allowed is True
    assert policy.check(credential="aegis_sk_1_a", **args).allowed is False


def test_a_read_only_route_is_never_counted_even_without_routing() -> None:
    policy = RateLimitPolicy(credential_per_minute=1, secret=APP_SECRET)
    middleware = RateLimitMiddleware(echo_app, policy=policy)
    scope = {"type": "http", "method": "GET", "path": "/api/v1/alerts", "headers": []}
    for _ in range(3):
        assert status_of(drive(middleware, scope, [])) == 200
    assert policy.tracked == 0


def test_a_websocket_scope_is_left_alone() -> None:
    """The alert stream (T-310) must not be counted as traffic while it is open."""
    policy = RateLimitPolicy(credential_per_minute=1, secret=APP_SECRET)
    middleware = RateLimitMiddleware(echo_app, policy=policy)
    assert status_of(drive(middleware, {"type": "websocket"}, [])) == 200
    assert policy.tracked == 0


def test_the_exemption_mechanism_exists_and_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is exempt today; if a decision ever adds one, the mechanism works."""
    policy = RateLimitPolicy(secret=APP_SECRET)
    monkeypatch.setattr(limits, "EXEMPT_ROUTES", frozenset({("POST", "/skip")}))
    assert policy.is_limited("POST", "/skip") is False
    assert policy.is_limited("POST", "/api/v1/ingest/flows") is True


# --- R-56's coverage rule -----------------------------------------------------


def _routes(app: FastAPI, path: str) -> list[Any]:
    """Every route object at one path, walking nested routers."""
    found: list[Any] = []
    for route in app.routes:
        if getattr(route, "path", None) == path:
            found.append(route)
        for attribute in ("original_router", "router"):
            inner = getattr(route, attribute, None)
            if inner is not None and hasattr(inner, "routes"):
                found.extend(_routes(inner, path))
    return found


def _live_methods(app: FastAPI) -> set[tuple[str, str]]:
    from app.auth.rbac import registered_paths

    found: set[tuple[str, str]] = set()
    for path in registered_paths(app.routes):
        for route in _routes(app, path):
            for method in getattr(route, "methods", ()) or ():
                found.add((method.upper(), path))
    return found


def test_r56_covers_every_write_and_unauthenticated_route(settings: Settings) -> None:
    """The criterion, checked against the application rather than a list.

    A new write endpoint, or a route added to the unauthenticated table, is in
    scope the moment it exists -- and a route that *should* be in scope but is not
    fails here rather than in production.
    """
    app = create_app(settings)
    policy = app.state.rate_limit_policy
    covered = {
        (method, path) for method, path in _live_methods(app) if policy.is_limited(method, path)
    }
    required = {
        (method, path)
        for method, path in _live_methods(app)
        if method in MUTATING_METHODS or path in LIMITED_UNAUTHENTICATED_ROUTES
    }
    assert required - covered == set(), "R-56 routes outside the limit"
    # And the limit is not simply "everything": authenticated reads are out of scope.
    assert ("GET", "/api/v1/alerts") not in covered


def test_the_coverage_check_is_not_vacuous(settings: Settings) -> None:
    app = create_app(settings)
    writes = {pair for pair in _live_methods(app) if pair[0] in MUTATING_METHODS}
    assert len(writes) >= 10
    assert {"/healthz", "/readyz"} <= {path for _method, path in _live_methods(app)}


def test_a_new_write_route_is_in_scope_the_moment_it_exists(
    settings: Settings, auth: TokenService
) -> None:
    """The mechanism, proved by planting the defect the rule exists to catch."""
    app = create_app(settings)
    app.state.token_service = auth
    app.state.rate_limit_policy = RateLimitPolicy(
        credential_per_minute=1, anonymous_per_minute=1, secret=APP_SECRET
    )

    @app.post("/api/v1/uncovered/probe")
    def probe() -> dict[str, str]:
        return {"ok": "true"}

    assert app.state.rate_limit_policy.is_limited("POST", "/api/v1/uncovered/probe") is True
    with TestClient(app) as client:
        assert client.post("/api/v1/uncovered/probe").status_code == 200
        refused = client.post("/api/v1/uncovered/probe")
        assert refused.status_code == 429
        assert refused.headers["retry-after"] == "60"


def test_a_new_unauthenticated_route_is_in_scope(settings: Settings) -> None:
    """The unauthenticated half, without needing a second application."""
    app = create_app(settings)
    for path in ROUTE_MATRIX:
        assert app.state.rate_limit_policy.is_limited("GET", path) is (
            path in LIMITED_UNAUTHENTICATED_ROUTES
        )
    assert app.state.rate_limit_policy.is_limited("GET", "/healthz") is True
