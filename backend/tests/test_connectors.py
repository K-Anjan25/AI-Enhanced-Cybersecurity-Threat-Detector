"""Connector ingest — real configuration, real sync, honest status.

These tests exist because the previous implementation lied: it reported four
"connected" integrations with invented asset counts, and "Sync" returned
success without contacting anything. Every assertion here encodes the opposite
contract — a number is only returned if it was measured, and a failure is
reported as a failure.
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.models import AuditLog, ConnectorSource, Org, SecurityAlert
from app.services import connector_service


@pytest.fixture()
def org(db_session):
    row = Org(name="Acme Inc", slug="acme")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Status honesty
# ---------------------------------------------------------------------------


def test_catalogue_reports_not_connected_without_config(db_session, org):
    """No configuration => no claim of connection, and no invented telemetry."""
    rows = connector_service.list_connectors(db_session, org_id=org.id)

    assert len(rows) == 10  # Phase 40 expanded to 10, Phase 41 keeps 10
    for row in rows:
        assert row["status"] == "not_connected"
        assert row["live"] is False
        assert row["assets_monitored"] is None
        assert row["latency_ms"] is None
        assert row["last_sync"] is None


def test_configured_but_never_synced_is_configured_not_connected(db_session, org):
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "tok"}, actor="admin"
    )
    rows = {r["id"]: r for r in connector_service.list_connectors(db_session, org_id=org.id)}

    assert rows["okta"]["status"] == "configured"
    assert rows["okta"]["live"] is False
    # Still no fabricated numbers: nothing has been ingested yet.
    assert rows["okta"]["assets_monitored"] is None


def test_connected_only_after_a_successful_sync(db_session, org, monkeypatch):
    connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {
            "mode": "poll",
            "endpoint": "https://example.test/events",
            "auth_header": "Authorization",
            "auth_token": "Bearer abc",
        },
        actor="admin",
    )

    monkeypatch.setattr(
        connector_service.requests,
        "get",
        lambda *a, **kw: _FakeResponse(
            [{"message": "Suspicious sign-in from 198.51.100.7", "severity": "HIGH",
              "source_ip": "198.51.100.7"}]
        ),
    )

    result = connector_service.sync(db_session, org_id=org.id, connector_id="okta", actor="admin")
    assert result["status"] == "synced"
    assert result["ingested"] == 1

    rows = {r["id"]: r for r in connector_service.list_connectors(db_session, org_id=org.id)}
    assert rows["okta"]["status"] == "connected"
    assert rows["okta"]["live"] is True
    # Measured, not invented.
    assert rows["okta"]["assets_monitored"] == 1
    assert rows["okta"]["latency_ms"] >= 0
    assert rows["okta"]["last_sync"] == "just now"
    assert rows["okta"]["events_ingested"] == 1


# ---------------------------------------------------------------------------
# Sync outcomes
# ---------------------------------------------------------------------------


def test_sync_without_config_records_a_request_and_says_so(db_session, org):
    result = connector_service.sync(db_session, org_id=org.id, connector_id="okta", actor="analyst")

    assert result["status"] == "recorded"
    assert "No source is configured" in result["message"]
    assert result["live"] is False
    assert "CONNECTOR_SYNC_REQUESTED" in {a.action for a in db_session.query(AuditLog).all()}


def test_sync_on_push_connector_does_not_pretend_to_fetch(db_session, org):
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "tok"}, actor="admin"
    )
    result = connector_service.sync(db_session, org_id=org.id, connector_id="okta", actor="analyst")

    assert result["status"] == "recorded"
    assert "push ingest" in result["message"]


def test_sync_failure_is_reported_not_swallowed(db_session, org, monkeypatch):
    connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {"mode": "poll", "endpoint": "https://example.test/events"},
        actor="admin",
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(connector_service.requests, "get", _boom)

    result = connector_service.sync(db_session, org_id=org.id, connector_id="okta", actor="analyst")

    assert result["status"] == "error"
    assert "connection refused" in result["message"]
    assert result["live"] is False

    # The failure is persisted and surfaced by the status endpoint.
    rows = {r["id"]: r for r in connector_service.list_connectors(db_session, org_id=org.id)}
    assert rows["okta"]["status"] == "error"
    assert "connection refused" in rows["okta"]["last_error"]
    assert "CONNECTOR_SYNC_FAILED" in {a.action for a in db_session.query(AuditLog).all()}


def test_sync_is_tenant_scoped(db_session, org, monkeypatch):
    """Another tenant's configuration must not make my connector 'connected'."""
    from app.models import Org

    other = Org(name="Other", slug="other")
    db_session.add(other)
    db_session.commit()

    connector_service.upsert_config(
        db_session, other.id, "okta", {"mode": "push", "ingest_token": "t"}, actor="admin"
    )
    rows = {r["id"]: r for r in connector_service.list_connectors(db_session, org_id=org.id)}
    assert rows["okta"]["status"] == "not_connected"


# ---------------------------------------------------------------------------
# Push ingest
# ---------------------------------------------------------------------------


def test_push_ingest_requires_the_shared_secret(db_session, org):
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "s3cret"}, actor="admin"
    )

    with pytest.raises(PermissionError):
        connector_service.ingest_push(db_session, "okta", "wrong", [{"message": "x"}])

    result = connector_service.ingest_push(
        db_session, "okta", "s3cret", [{"message": "Impossible travel detected", "severity": "HIGH"}]
    )
    assert result["status"] == "ingested"
    assert result["ingested"] == 1

    alert = db_session.query(SecurityAlert).filter(SecurityAlert.source == "okta").first()
    assert alert is not None
    assert alert.org_id == org.id
    # MITRE mapping still ran on the ingested event.
    assert alert.mitre_technique_id


def test_push_ingest_rejects_a_non_ascii_token_instead_of_crashing(db_session, org):
    """hmac.compare_digest() refuses non-ASCII str outright. Comparing bytes
    keeps a wrong token a wrong token: 401, not a 500 from a TypeError."""
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "s3cret"}, actor="admin"
    )
    with pytest.raises(PermissionError):
        connector_service.ingest_push(
            db_session, "okta", "s3crét", [{"message": "Impossible travel"}]
        )


def test_push_ingest_skips_duplicates_and_unmappable_events(db_session, org):
    connector_service.upsert_config(
        db_session, org.id, "sentinel", {"mode": "push", "ingest_token": "t"}, actor="admin"
    )
    events = [
        {"message": "Malware detected on host-7", "severity": 9},  # numeric scale -> CRITICAL
        {"message": "Malware detected on host-7", "severity": 9},  # duplicate within payload
        {"severity": "LOW"},  # no message at all -> skipped, not invented
    ]
    result = connector_service.ingest_push(db_session, "sentinel", "t", events)

    assert result["ingested"] == 1
    assert result["skipped"] == 2

    alert = db_session.query(SecurityAlert).filter(SecurityAlert.source == "sentinel").first()
    assert alert.severity == "CRITICAL"


def test_unconfigured_connector_rejects_ingest(db_session, org):
    with pytest.raises(PermissionError):
        connector_service.ingest_push(db_session, "okta", "anything", [{"message": "x"}])


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_config_never_leaks_outbound_credentials(db_session, org):
    connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {"mode": "poll", "endpoint": "https://e.test/x", "auth_header": "Authorization",
         "auth_token": "Bearer super-secret", "ingest_token": "push-secret"},
        actor="admin",
    )
    cfg = connector_service.get_config(db_session, org.id, "okta")
    serialized = connector_service.serialize_config(cfg)

    assert "super-secret" not in str(serialized)
    assert "push-secret" not in str(serialized)
    assert serialized["has_auth_token"] is True
    assert serialized["has_ingest_token"] is True


def test_poll_mode_requires_an_endpoint(db_session, org):
    with pytest.raises(ValueError):
        connector_service.upsert_config(
            db_session, org.id, "okta", {"mode": "poll"}, actor="admin"
        )


# ---------------------------------------------------------------------------
# SSRF guard on the outbound poll
# ---------------------------------------------------------------------------


@pytest.fixture()
def production(monkeypatch):
    """Non-dev ENVIRONMENT — the guard is deliberately off in dev/test so the
    local walkthrough can point a connector at 127.0.0.1."""
    monkeypatch.setattr(connector_service.settings, "ENVIRONMENT", "production")
    return "production"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9000/events",
        "http://localhost/events",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.3.17/events",
        "http://192.168.1.1/events",
        "http://172.16.0.9/events",
    ],
)
def test_production_refuses_internal_poll_endpoints(production, db_session, org, url):
    """Poll mode makes the server fetch a tenant-supplied URL, so an internal
    address has to be refused rather than fetched."""
    with pytest.raises(ValueError, match="refusing to fetch"):
        connector_service.upsert_config(
            db_session, org.id, "okta", {"mode": "poll", "endpoint": url}, actor="admin"
        )


def test_production_refuses_non_http_schemes(production, db_session, org):
    with pytest.raises(ValueError, match="http"):
        connector_service.upsert_config(
            db_session,
            org.id,
            "okta",
            {"mode": "poll", "endpoint": "file:///etc/passwd"},
            actor="admin",
        )


def test_dev_environment_still_allows_loopback(db_session, org):
    """The escape hatch has to keep working: docs/demo.md walks a connector
    against a local mock endpoint."""
    monkeypatched = connector_service.settings.ENVIRONMENT
    try:
        connector_service.settings.ENVIRONMENT = "development"
        saved = connector_service.upsert_config(
            db_session,
            org.id,
            "okta",
            {"mode": "poll", "endpoint": "http://127.0.0.1:9000/events"},
            actor="admin",
        )
    finally:
        connector_service.settings.ENVIRONMENT = monkeypatched
    assert saved["endpoint"] == "http://127.0.0.1:9000/events"


def test_sync_refuses_to_fetch_an_internal_endpoint_even_if_config_predates_it(
    production, db_session, org, monkeypatch
):
    """Defence in depth: a row written in dev (or before the guard) must not
    turn into an internal request at poll time — and it must be recorded as a
    failed sync, not a silent success."""
    connector_service.settings.ENVIRONMENT = "development"
    connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {"mode": "poll", "endpoint": "http://169.254.169.254/latest/meta-data/"},
        actor="admin",
    )
    connector_service.settings.ENVIRONMENT = "production"

    def _must_not_run(*args, **kwargs):  # pragma: no cover - guard must fire first
        raise AssertionError("requests.get must not be reached")

    monkeypatch.setattr(connector_service.requests, "get", _must_not_run)

    result = connector_service.sync(db_session, org.id, "okta", actor="admin")
    assert result["status"] == "error"
    assert "refusing to fetch" in (result.get("message") or "")


def test_unknown_connector_is_rejected(db_session, org):
    with pytest.raises(ValueError):
        connector_service.upsert_config(
            db_session, org.id, "not-a-connector", {"mode": "push"}, actor="admin"
        )


def test_configuration_is_audited(db_session, org):
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "t"}, actor="admin"
    )
    connector_service.delete_config(db_session, org.id, "okta", actor="admin")

    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert "CONNECTOR_CONFIGURED" in actions
    assert "CONNECTOR_REMOVED" in actions
    assert db_session.query(ConnectorSource).count() == 0


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def test_http_config_and_ingest_flow(client, auth_headers):
    # Configure a push connector (needs alerts:write, which ANALYST has).
    resp = client.put(
        "/api/v1/connectors/okta/config",
        json={"mode": "push", "ingest_token": "letmein"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["has_ingest_token"] is True
    assert "letmein" not in resp.text

    # The status endpoint now shows it as configured, still not "connected".
    status = client.get("/api/v1/analyst/connectors", headers=auth_headers).json()
    okta = next(r for r in status if r["id"] == "okta")
    assert okta["status"] == "configured"

    # Webhook with the wrong token -> 401, with the right token -> 201.
    bad = client.post(
        "/api/v1/connectors/ingest/okta",
        json={"events": [{"message": "x"}]},
        headers={"X-Connector-Token": "nope"},
    )
    assert bad.status_code == 401

    good = client.post(
        "/api/v1/connectors/ingest/okta",
        json={"events": [{"message": "MFA reset for admin", "severity": "MEDIUM",
                          "source_ip": "203.0.113.9"}]},
        headers={"X-Connector-Token": "letmein"},
    )
    assert good.status_code == 201
    assert good.json()["ingested"] == 1

    # And now it is genuinely connected, with a real asset count.
    status = client.get("/api/v1/analyst/connectors", headers=auth_headers).json()
    okta = next(r for r in status if r["id"] == "okta")
    assert okta["status"] == "connected"
    assert okta["live"] is True
    assert okta["assets_monitored"] == 1


class _FakeResponse:
    """Minimal stand-in for a requests.Response carrying JSON events."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# Credentials at rest
# ---------------------------------------------------------------------------


def _raw_row(db_session, connector_id):
    """The stored row, bypassing the service layer entirely."""
    return (
        db_session.query(ConnectorSource)
        .filter(ConnectorSource.connector_id == connector_id)
        .first()
    )


def test_credentials_are_encrypted_at_rest(db_session, org):
    connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {
            "mode": "poll",
            "endpoint": "https://provider.example/events",
            "auth_header": "Authorization",
            "auth_token": "Bearer live-provider-token",
            "ingest_token": "push-shared-secret",
        },
        actor="admin",
    )
    row = _raw_row(db_session, "okta")

    # Neither secret is recoverable from a dump of the table.
    assert "live-provider-token" not in row.auth_token
    assert "push-shared-secret" not in row.ingest_token
    assert row.auth_token.startswith("enc:v1:")
    assert row.ingest_token.startswith("enc:v1:")


def test_credentials_round_trip_and_are_never_serialised(db_session, org):
    saved = connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {"mode": "push", "ingest_token": "push-shared-secret"},
        actor="admin",
    )
    assert saved["has_ingest_token"] is True
    assert "push-shared-secret" not in str(saved)

    # The real secret is used, not a hash of it: a valid push is accepted.
    result = connector_service.ingest_push(
        db_session, "okta", "push-shared-secret", [{"message": "Impossible travel"}]
    )
    assert result["status"] == "ingested"


def test_outbound_auth_header_carries_the_decrypted_credential(db_session, org, monkeypatch):
    connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {
            "mode": "poll",
            "endpoint": "https://provider.example/events",
            "auth_header": "Authorization",
            "auth_token": "Bearer live-provider-token",
        },
        actor="admin",
    )

    captured = {}

    def _fake_get(url, headers=None, timeout=None):
        captured["headers"] = headers

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return [{"message": "Impossible travel detected", "severity": "HIGH"}]

        return _Resp()

    monkeypatch.setattr(connector_service.requests, "get", _fake_get)
    connector_service.sync(db_session, org.id, "okta", actor="admin")

    assert captured["headers"]["Authorization"] == "Bearer live-provider-token"


def test_rotated_key_fails_closed_on_push(db_session, org, monkeypatch):
    """A credential we cannot read must not become 'no credential configured' —
    that would let any token through."""
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "s3cret"}, actor="admin"
    )
    monkeypatch.setattr(connector_service.settings, "JWT_SECRET_KEY", "a-different-key")

    with pytest.raises(PermissionError):
        connector_service.ingest_push(db_session, "okta", "s3cret", [{"message": "x"}])
    with pytest.raises(PermissionError):
        connector_service.ingest_push(db_session, "okta", "anything", [{"message": "x"}])


def test_rotated_key_is_reported_on_sync_not_hidden(db_session, org, monkeypatch):
    connector_service.upsert_config(
        db_session,
        org.id,
        "okta",
        {
            "mode": "poll",
            "endpoint": "https://provider.example/events",
            "auth_header": "Authorization",
            "auth_token": "Bearer live-provider-token",
        },
        actor="admin",
    )
    monkeypatch.setattr(connector_service.settings, "JWT_SECRET_KEY", "a-different-key")

    def _must_not_run(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("must not poll with an unreadable credential")

    monkeypatch.setattr(connector_service.requests, "get", _must_not_run)

    result = connector_service.sync(db_session, org.id, "okta", actor="admin")
    assert result["status"] == "error"
    assert "re-enter the credential" in result["message"]


# ---------------------------------------------------------------------------
# Ingest rate limiting
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_rate_counters():
    connector_service.reset_ingest_rate_limits()
    yield
    connector_service.reset_ingest_rate_limits()


def test_ingest_is_rate_limited_per_connector(db_session, org, monkeypatch):
    monkeypatch.setattr(connector_service.settings, "CONNECTOR_INGEST_RATE_LIMIT", 2)
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "s3cret"}, actor="admin"
    )
    connector_service.upsert_config(
        db_session,
        org.id,
        "sentinel",
        {"mode": "push", "ingest_token": "s3cret"},
        actor="admin",
    )

    for _ in range(2):
        connector_service.ingest_push(db_session, "okta", "s3cret", [{"message": "x"}])

    with pytest.raises(connector_service.RateLimited) as exc:
        connector_service.ingest_push(db_session, "okta", "s3cret", [{"message": "x"}])
    assert exc.value.retry_after >= 1

    # One connector exhausting its budget does not silence the others.
    connector_service.ingest_push(db_session, "sentinel", "s3cret", [{"message": "x"}])


def test_rate_limit_window_expires(db_session, org, monkeypatch):
    monkeypatch.setattr(connector_service.settings, "CONNECTOR_INGEST_RATE_LIMIT", 1)
    connector_service.upsert_config(
        db_session, org.id, "okta", {"mode": "push", "ingest_token": "s3cret"}, actor="admin"
    )

    real_monotonic = connector_service.time.monotonic
    connector_service.ingest_push(db_session, "okta", "s3cret", [{"message": "x"}])
    with pytest.raises(connector_service.RateLimited):
        connector_service.ingest_push(db_session, "okta", "s3cret", [{"message": "x"}])

    # Jump past the window; the counter must slide rather than latch forever.
    started = real_monotonic()
    monkeypatch.setattr(
        connector_service.time, "monotonic", lambda: started + connector_service._INGEST_WINDOW_SECONDS + 1
    )
    connector_service.ingest_push(db_session, "okta", "s3cret", [{"message": "x"}])


def test_rate_limited_ingest_returns_429_with_retry_after(client, auth_headers, monkeypatch):
    monkeypatch.setattr(connector_service.settings, "CONNECTOR_INGEST_RATE_LIMIT", 1)
    client.put(
        "/api/v1/connectors/okta/config",
        json={"mode": "push", "ingest_token": "s3cret"},
        headers=auth_headers,
    ).raise_for_status()

    ok = client.post(
        "/api/v1/connectors/ingest/okta",
        json={"events": [{"message": "Impossible travel detected"}]},
        headers={"X-Connector-Token": "s3cret"},
    )
    assert ok.status_code == 201

    limited = client.post(
        "/api/v1/connectors/ingest/okta",
        json={"events": [{"message": "Impossible travel detected"}]},
        headers={"X-Connector-Token": "s3cret"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1

    client.delete("/api/v1/connectors/okta/config", headers=auth_headers)


# ---------------------------------------------------------------------------
# IP pinning (closes the DNS-rebinding half of the SSRF gap)
# ---------------------------------------------------------------------------


def test_pinned_request_targets_the_ip_that_was_validated(production, monkeypatch):
    """The point of pinning: one lookup, and the address it returned is the
    address used. A hostile nameserver answers the *next* lookup with an
    internal address — but there is no next lookup."""
    answers = [
        ["93.184.216.34", "93.184.216.35"],  # public, what will be validated
        ["169.254.169.254"],  # what a rebind would have handed the request
    ]
    lookups = {"n": 0}

    def _getaddrinfo(host, port, *args, **kwargs):
        ips = answers[min(lookups["n"], len(answers) - 1)]
        lookups["n"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0)) for ip in ips]

    monkeypatch.setattr(connector_service.socket, "getaddrinfo", _getaddrinfo)

    captured = {}

    def _fake_get(request_url, headers=None, timeout=None):
        captured["url"] = request_url
        captured["headers"] = headers

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return []

        return _Resp()

    monkeypatch.setattr(connector_service.requests, "get", _fake_get)

    connector_service._fetch_events("http://events.example/events.json", {"Authorization": "Bearer x"})

    assert captured["url"] == "http://93.184.216.34/events.json"
    assert captured["headers"]["Host"] == "events.example"
    assert captured["headers"]["Authorization"] == "Bearer x"
    # Exactly one resolution: the one that was validated.
    assert lookups["n"] == 1


def test_pinned_fetch_refuses_an_internal_address_it_resolved(production, monkeypatch):
    """Rebinding in its purest form: the name resolves straight to cloud
    metadata. Validating a different lookup would miss this entirely."""
    monkeypatch.setattr(
        connector_service.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port or 0))
        ],
    )

    def _must_not_run(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("must not connect to a link-local address")

    monkeypatch.setattr(connector_service.requests, "get", _must_not_run)

    with pytest.raises(ValueError, match="refusing to fetch"):
        connector_service._fetch_events("http://rebound.example/events.json", None)


def test_pinned_fetch_refuses_an_ip_literal_in_production(production, monkeypatch):
    """A config written in dev as http://127.0.0.1 must not survive a deploy."""

    def _must_not_run(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("must not fetch from loopback in production")

    monkeypatch.setattr(connector_service.requests, "get", _must_not_run)

    with pytest.raises(ValueError, match="refusing to fetch"):
        connector_service._fetch_events("http://127.0.0.1:9000/events.json", None)


def test_ip_literal_endpoints_are_fetched_unchanged():
    url = "http://127.0.0.1:8099/events.json"
    assert connector_service._pin_to_ip(url) == (url, {}, None, ["127.0.0.1"])


def test_unresolvable_host_is_left_to_fail_naturally(monkeypatch):
    def _boom(host, port, *args, **kwargs):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(connector_service.socket, "getaddrinfo", _boom)
    url = "http://nowhere.example/events.json"
    assert connector_service._pin_to_ip(url) == (url, {}, None, [])


def test_pinned_fetch_works_over_a_real_socket(monkeypatch):
    """End to end against a local server reached by a name, not an IP — the
    same shape as production, without production's DNS."""
    events = [{"message": "Impossible travel", "severity": "HIGH", "source_ip": "203.0.113.24"}]
    body = json.dumps(events).encode()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    real_getaddrinfo = socket.getaddrinfo

    def _fake_getaddrinfo(host, p, *args, **kwargs):
        if host == "events.test":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p or 0))]
        return real_getaddrinfo(host, p, *args, **kwargs)

    monkeypatch.setattr(connector_service.socket, "getaddrinfo", _fake_getaddrinfo)
    try:
        response = connector_service._fetch_events(f"http://events.test:{port}/events.json", None)
        assert response.status_code == 200
        assert response.json() == events
    finally:
        server.shutdown()
        server.server_close()
