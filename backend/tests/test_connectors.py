"""Connector ingest — real configuration, real sync, honest status.

These tests exist because the previous implementation lied: it reported four
"connected" integrations with invented asset counts, and "Sync" returned
success without contacting anything. Every assertion here encodes the opposite
contract — a number is only returned if it was measured, and a failure is
reported as a failure.
"""

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

    assert len(rows) == 4
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
